"""
routers/alertes.py
Gestion des alertes — consultation et acquittement.
"""

from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from database import get_db
from middleware.security import get_utilisateur_courant, verifier_role

router = APIRouter()


@router.get("")
async def lister_alertes(
    acquittees : bool = False,
    limite     : int  = 50,
    user       : dict = Depends(verifier_role("medecin", "admin")),
    db         : asyncpg.Connection = Depends(get_db)
):
    """
    Liste les alertes — médecin et admin uniquement.
    Par défaut retourne les alertes non acquittées.
    Un médecin ne voit que les alertes de son département.
    """
    if user["role"] == "medecin" and user.get("departement"):
        rows = await db.fetch(
            """SELECT id, patient_id, departement, capteur,
                      niveau, message, timestamp, acquittee
               FROM alertes
               WHERE acquittee = $1 AND departement = $2
               ORDER BY timestamp DESC
               LIMIT $3""",
            acquittees, user["departement"], min(limite, 200)
        )
    else:
        # Admin voit tout
        rows = await db.fetch(
            """SELECT id, patient_id, departement, capteur,
                      niveau, message, timestamp, acquittee
               FROM alertes
               WHERE acquittee = $1
               ORDER BY timestamp DESC
               LIMIT $2""",
            acquittees, min(limite, 500)
        )

    return [
        {
            "id"          : r["id"],
            "patient_id"  : r["patient_id"],
            "departement" : r["departement"],
            "capteur"     : r["capteur"],
            "niveau"      : r["niveau"],
            "message"     : r["message"],
            "timestamp"   : r["timestamp"].isoformat(),
            "acquittee"   : r["acquittee"],
        }
        for r in rows
    ]


@router.put("/{alerte_id}/acquitter")
async def acquitter_alerte(
    alerte_id : int,
    user      : dict = Depends(verifier_role("medecin", "admin")),
    db        : asyncpg.Connection = Depends(get_db)
):
    """
    Acquitte une alerte — marque qu'un médecin en a pris connaissance.
    """
    alerte = await db.fetchrow(
        "SELECT id, acquittee, departement FROM alertes WHERE id = $1",
        alerte_id
    )
    if not alerte:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    if user["role"] != "admin" and alerte["departement"] != user.get("departement"):
        raise HTTPException(status_code=403, detail="Alerte hors de votre département")
    if alerte["acquittee"]:
        return {"message": "Alerte déjà acquittée"}

    await db.execute(
        """UPDATE alertes
           SET acquittee = TRUE,
               acquittee_par = $1,
               timestamp_acquittement = NOW()
           WHERE id = $2""",
        user["user_id"], alerte_id
    )

    return {"message": f"Alerte {alerte_id} acquittée"}


@router.get("/mes-alertes")
async def mes_alertes(
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """
    Alertes du patient connecté — pour l'app mobile.
    """
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Pas un patient")

    rows = await db.fetch(
        """SELECT id, capteur, niveau, message, timestamp
           FROM alertes
           WHERE patient_id = $1
           ORDER BY timestamp DESC
           LIMIT 20""",
        patient_id
    )

    return [
        {
            "id"      : r["id"],
            "capteur" : r["capteur"],
            "niveau"  : r["niveau"],
            "message" : r["message"],
            "timestamp": r["timestamp"].isoformat(),
        }
        for r in rows
    ]
