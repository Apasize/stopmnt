"""
services/auth_service.py
Logique métier pour l'authentification.
"""

from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timezone, timedelta
import secrets
import string

from config import settings

# Contexte de hachage — utilise bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hacher_password(password: str) -> str:
    """Hache un mot de passe avec bcrypt."""
    return pwd_context.hash(password)


def verifier_password(password_clair: str, hash: str) -> bool:
    """Vérifie qu'un mot de passe correspond à son hash."""
    return pwd_context.verify(password_clair, hash)


def generer_token(user_id: int, email: str, role: str,
                   patient_id: str = None, departement: str = None) -> dict:
    """
    Génère un token JWT avec les informations de l'utilisateur.
    Le token expire après JWT_EXPIRE_H heures.
    """
    maintenant = datetime.now(timezone.utc)
    expiration = maintenant + timedelta(hours=settings.JWT_EXPIRE_H)

    payload = {
        "user_id"    : user_id,
        "email"      : email,
        "role"       : role,
        "iat"        : maintenant,
        "exp"        : expiration,
    }
    if patient_id:
        payload["patient_id"] = patient_id
    if departement:
        payload["departement"] = departement

    token = jwt.encode(payload, settings.JWT_SECRET,
                       algorithm=settings.JWT_ALGORITHM)

    return {
        "access_token" : token,
        "token_type"   : "bearer",
        "expires_in"   : settings.JWT_EXPIRE_H * 3600,
        "role"         : role,
    }


def generer_patient_id(departement: str) -> str:
    """
    Génère un identifiant patient unique.
    Format : DEPT-XXXXX (ex: ATL-48291)
    """
    prefixes = {
        "littoral"   : "LIT",
        "atlantique" : "ATL",
        "oueme"      : "OUE",
        "mono"       : "MON",
        "plateau"    : "PLA",
    }
    prefix = prefixes.get(departement, "STO")
    suffixe = ''.join(secrets.choice(string.digits) for _ in range(5))
    return f"{prefix}-{suffixe}"
