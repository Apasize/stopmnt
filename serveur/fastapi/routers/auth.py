"""
routers/auth.py
Endpoints d'authentification et d'enrôlement des dispositifs.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
import asyncpg
import os
from datetime import datetime, timezone, timedelta

from database import get_db, get_redis
from models.patient import PatientRegister
from models.utilisateur import LoginRequest, TokenResponse
from services.auth_service import (hacher_password, verifier_password,
                                    generer_token, generer_patient_id)
from services.cert_service import generer_certificat_dispositif
from fastapi.security import HTTPAuthorizationCredentials
from middleware.security import get_utilisateur_courant, bearer_scheme

router  = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_patient(
    request : Request,
    data    : PatientRegister,
    db      : asyncpg.Connection = Depends(get_db)
):
    """
    Inscription d'un nouveau patient.
    Crée le compte et génère automatiquement un patient_id unique.
    """
    # Vérifier que l'email n'est pas déjà utilisé
    existant = await db.fetchrow(
        "SELECT id FROM patients WHERE email = $1", data.email
    )
    if existant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email déjà utilisé"
        )

    patient_id    = generer_patient_id(data.departement)
    password_hash = hacher_password(data.password)

    await db.execute(
        """INSERT INTO patients
           (patient_id, email, password_hash, nom, prenom,
            date_naissance, departement, telephone)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
        patient_id, data.email, password_hash,
        data.nom, data.prenom, data.date_naissance,
        data.departement, data.telephone
    )

    return {
        "message"    : "Compte créé avec succès",
        "patient_id" : patient_id,
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request : Request,
    data    : LoginRequest,
    db      : asyncpg.Connection = Depends(get_db)
):
    """
    Connexion d'un patient ou utilisateur professionnel.
    Retourne un token JWT valide.
    """
    # Chercher dans les patients d'abord
    patient = await db.fetchrow(
        "SELECT * FROM patients WHERE email = $1 AND actif = TRUE",
        data.email
    )
    if patient and verifier_password(data.password, patient["password_hash"]):
        return generer_token(
            user_id    = patient["id"],
            email      = patient["email"],
            role       = "patient",
            patient_id = patient["patient_id"],
            departement= patient["departement"],
        )

    # Chercher dans les utilisateurs professionnels
    user = await db.fetchrow(
        "SELECT * FROM utilisateurs WHERE email = $1 AND actif = TRUE",
        data.email
    )
    if user and verifier_password(data.password, user["password_hash"]):
        # Mettre à jour la dernière connexion
        await db.execute(
            "UPDATE utilisateurs SET derniere_connexion = NOW() WHERE id = $1",
            user["id"]
        )
        return generer_token(
            user_id    = user["id"],
            email      = user["email"],
            role       = user["role"],
            departement= user["departement"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email ou mot de passe incorrect"
    )


@router.post("/logout")
async def logout(
    user        : dict = Depends(get_utilisateur_courant),
    credentials : HTTPAuthorizationCredentials = Depends(bearer_scheme),
    redis              = Depends(get_redis),
):
    """
    Déconnexion — ajoute le token à la blacklist Redis.
    Le token sera invalide immédiatement même s'il n'a pas encore expiré.
    """
    # Même clé que celle lue par verifier_token ; conservée jusqu'à l'expiration du jeton.
    await redis.set(
        f"blacklist:{credentials.credentials}",
        "1",
        ex=max(1, int(user["exp"] - datetime.now(timezone.utc).timestamp())),
    )
    return {"message": "Déconnecté avec succès"}


@router.post("/device/enroll")
@limiter.limit("3/minute")
async def enroller_dispositif(
    request : Request,
    user    : dict = Depends(get_utilisateur_courant),
    db      : asyncpg.Connection = Depends(get_db)
):
    """
    Enrôle le smartphone courant et génère son certificat X.509.
    Seul un patient authentifié peut enrôler un dispositif.
    Le certificat généré permet la connexion au broker MQTT.
    """
    if user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un patient peut enrôler un dispositif"
        )

    patient_id = user["patient_id"]
    device_id  = f"{patient_id}-{user['user_id']}"

    # Générer le certificat X.509
    cert_data = generer_certificat_dispositif(device_id, patient_id)

    # Enregistrer dans le Device Registry
    await db.execute(
        """INSERT INTO device_registry
           (device_id, patient_id, cert_fingerprint, cert_cn, date_expiration)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (device_id) DO UPDATE
           SET cert_fingerprint = $3,
               cert_cn          = $4,
               date_expiration  = $5,
               actif            = TRUE""",
        device_id,
        patient_id,
        cert_data["fingerprint"],
        cert_data["common_name"],
        datetime.fromisoformat(cert_data["expires_at"])
    )

    # Journaliser dans audit_logs
    await db.execute(
        """INSERT INTO audit_logs (patient_id, action, details)
           VALUES ($1, $2, $3)""",
        patient_id,
        "device_enrolled",
        f'{{"device_id": "{device_id}"}}'
    )

    return {
        "message"         : "Dispositif enrôlé avec succès",
        "device_id"       : device_id,
        "certificate_pem" : cert_data["certificate_pem"],
        "private_key_pem" : cert_data["private_key_pem"],
        "expires_at"      : cert_data["expires_at"],
        "mqtt_host"       : os.getenv("SERVER_IP", "localhost"),
        "mqtt_port"       : 8883,
    }


@router.post("/device/revoke")
async def revoquer_dispositif(
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """
    Révoque le certificat du dispositif courant.
    Utile si le téléphone est perdu ou volé.
    """
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Patient ID manquant")

    await db.execute(
        """UPDATE device_registry
           SET actif = FALSE
           WHERE patient_id = $1""",
        patient_id
    )

    await db.execute(
        """INSERT INTO audit_logs (patient_id, action)
           VALUES ($1, $2)""",
        patient_id, "device_revoked"
    )

    return {"message": "Dispositif révoqué"}


@router.get("/me")
async def mon_profil(
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """Retourne le profil du patient connecté."""
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Pas un patient")

    row = await db.fetchrow(
        """SELECT patient_id, email, nom, prenom, departement,
                  telephone, date_inscription
           FROM patients WHERE patient_id = $1""",
        patient_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Patient introuvable")
    return dict(row)


from pydantic import BaseModel


class FcmTokenRequest(BaseModel):
    fcm_token: str


@router.post("/device/fcm-token", status_code=status.HTTP_204_NO_CONTENT)
async def enregistrer_fcm_token(
    data : FcmTokenRequest,
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """
    Enregistre ou met à jour le token FCM du dispositif courant.
    Appelé par l'app mobile au démarrage (ou quand Firebase régénère le token).
    """
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Patient ID manquant")

    updated = await db.execute(
        """UPDATE device_registry
           SET fcm_token = $1, dernier_acces = NOW()
           WHERE patient_id = $2 AND actif = TRUE""",
        data.fcm_token, patient_id
    )
    if updated == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Aucun dispositif actif pour ce patient")
