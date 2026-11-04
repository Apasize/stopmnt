"""
routers/mesures.py
Réception et consultation des mesures discrètes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg
import json

from database import get_db, get_redis
from models.mesure import MesureCreate
from middleware.security import get_utilisateur_courant, verifier_role, verifier_perimetre_patient
from services.alerte_service import verifier_seuils_et_alerter

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def envoyer_mesure(
    data  : MesureCreate,
    user  : dict = Depends(get_utilisateur_courant),
    db    : asyncpg.Connection = Depends(get_db),
    redis        = Depends(get_redis)
):
    """
    Reçoit une mesure discrète depuis le smartphone patient.
    Vérifie les seuils et déclenche une alerte si nécessaire.
    """
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Accès refusé")

    patient_id  = user["patient_id"]
    departement = user["departement"]

    # Vérifier que le dispositif est enrôlé et actif
    device_actif = await db.fetchval(
        """SELECT COUNT(*) FROM device_registry
           WHERE patient_id = $1 AND actif = TRUE""",
        patient_id
    )
    if not device_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dispositif non enrôlé ou révoqué"
        )

    # Mesure déjà reçue (réponse perdue puis renvoi) : pas de doublon ni de seconde alerte.
    if data.mesure_id:
        existante = await db.fetchval(
            "SELECT id FROM mesures_discretes WHERE patient_id = $1 AND mesure_uuid = $2",
            patient_id, data.mesure_id
        )
        if existante:
            return {"id": existante, "message": "Mesure déjà enregistrée", "anomalie": False, "doublon": True}

    # Détecter les anomalies localement
    anomalie = False
    alerte   = await verifier_seuils_et_alerter(
        db, redis, patient_id, departement,
        data.capteur, data.mesures
    )
    if alerte:
        anomalie = True

    # Enregistrer la mesure
    mesure_id = await db.fetchval(
        """INSERT INTO mesures_discretes
           (patient_id, departement, capteur, timestamp_data,
            mesures, anomalie, deferred, mesure_uuid)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           RETURNING id""",
        patient_id, departement, data.capteur,
        data.timestamp_data,
        json.dumps(data.mesures),
        anomalie, data.deferred, data.mesure_id
    )

    reponse = {
        "id"      : mesure_id,
        "message" : "Mesure enregistrée",
        "anomalie": anomalie,
    }
    if alerte:
        reponse["alerte"] = {
            "niveau" : alerte["niveau"],
            "message": alerte["message"],
        }

    return reponse


@router.get("/historique")
async def historique_mesures(
    limite : int  = 50,
    user   : dict = Depends(get_utilisateur_courant),
    db     : asyncpg.Connection = Depends(get_db)
):
    """
    Retourne l'historique des mesures du patient connecté.
    """
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Patient ID manquant")

    rows = await db.fetch(
        """SELECT id, capteur, timestamp_data, mesures, anomalie, deferred
           FROM mesures_discretes
           WHERE patient_id = $1
           ORDER BY timestamp_data DESC
           LIMIT $2""",
        patient_id, min(limite, 200)
    )

    return [
        {
            "id"        : r["id"],
            "capteur"   : r["capteur"],
            "timestamp" : r["timestamp_data"].isoformat(),
            "mesures"   : json.loads(r["mesures"]),
            "anomalie"  : r["anomalie"],
            "deferred"  : r["deferred"],
        }
        for r in rows
    ]


@router.get("/patient/{patient_id}")
async def mesures_patient(
    patient_id : str,
    limite     : int  = 50,
    user       : dict = Depends(verifier_role("medecin", "admin")),
    db         : asyncpg.Connection = Depends(get_db)
):
    """
    Retourne les mesures d'un patient — médecin et admin uniquement.
    """
    await verifier_perimetre_patient(db, user, patient_id)
    rows = await db.fetch(
        """SELECT id, capteur, timestamp_data, mesures, anomalie, deferred
           FROM mesures_discretes
           WHERE patient_id = $1
           ORDER BY timestamp_data DESC
           LIMIT $2""",
        patient_id, min(limite, 500)
    )

    return [
        {
            "id"        : r["id"],
            "capteur"   : r["capteur"],
            "timestamp" : r["timestamp_data"].isoformat(),
            "mesures"   : json.loads(r["mesures"]),
            "anomalie"  : r["anomalie"],
            "deferred"  : r["deferred"],
        }
        for r in rows
    ]
