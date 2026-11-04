"""
middleware/security.py
Vérification des tokens JWT et gestion du RBAC.
Chaque endpoint protégé appelle ces fonctions via Depends().
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timezone
import redis.asyncio as aioredis

from config import settings
from database import get_redis

# HTTPBearer extrait le token du header Authorization: Bearer <token>
bearer_scheme = HTTPBearer()


async def verifier_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    redis: aioredis.Redis = Depends(get_redis)
) -> dict:
    """
    Vérifie qu'un token JWT est valide.
    Retourne le payload décodé si tout est OK.
    Lève une HTTPException 401 si le token est invalide ou révoqué.
    """
    token = credentials.credentials

    # Vérifier si le token est dans la blacklist Redis
    # (tokens révoqués avant leur expiration naturelle)
    est_revoque = await redis.get(f"blacklist:{token}")
    if est_revoque:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token révoqué",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Décoder et vérifier le token JWT
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier que le token n'est pas expiré
    exp = payload.get("exp")
    if not exp or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
        )

    return payload


async def get_utilisateur_courant(
    payload: dict = Depends(verifier_token)
) -> dict:
    """
    Extrait l'utilisateur courant depuis le payload JWT.
    Disponible dans tous les endpoints protégés.
    """
    user_id = payload.get("user_id")
    role    = payload.get("role")
    email   = payload.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformé",
        )

    return {
        "user_id"    : user_id,
        "role"       : role,
        "email"      : email,
        "patient_id" : payload.get("patient_id"),
        "departement": payload.get("departement"),
        "exp"        : payload.get("exp"),
    }


def verifier_role(*roles_autorises: str):
    """
    Fabrique un vérificateur de rôle pour le RBAC.
    Usage dans un endpoint :
        async def mon_endpoint(user = Depends(verifier_role("medecin", "admin")))
    """
    async def _verifier(
        user: dict = Depends(get_utilisateur_courant)
    ) -> dict:
        if user["role"] not in roles_autorises:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Rôles autorisés : {roles_autorises}",
            )
        return user
    return _verifier


async def verifier_perimetre_patient(db, user: dict, patient_id: str) -> None:
    """Un médecin ne lit que les patients de son département ; l'admin voit tout."""
    if user["role"] == "admin":
        return
    departement = await db.fetchval(
        "SELECT departement FROM patients WHERE patient_id = $1", patient_id
    )
    if departement is None:
        raise HTTPException(status_code=404, detail="Patient introuvable")
    if departement != user.get("departement"):
        raise HTTPException(status_code=403, detail="Patient hors de votre département")


# Raccourcis prêts à l'emploi pour les endpoints
RequirePatient  = Depends(verifier_role("patient"))
RequireMedecin  = Depends(verifier_role("medecin", "admin"))
RequireAdmin    = Depends(verifier_role("admin"))
RequireAny      = Depends(get_utilisateur_courant)
