"""
routers/admin.py
Endpoints d'administration — accès admin uniquement.
"""

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from database import get_db
from models.utilisateur import UtilisateurCreate
from services.auth_service import hacher_password
from middleware.security import verifier_role

router = APIRouter()


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def creer_utilisateur(
    data : UtilisateurCreate,
    user : dict = Depends(verifier_role("admin")),
    db   : asyncpg.Connection = Depends(get_db)
):
    """
    Crée un compte médecin ou admin.
    Seul un admin peut créer des comptes professionnels.
    """
    existant = await db.fetchrow(
        "SELECT id FROM utilisateurs WHERE email = $1", data.email
    )
    if existant:
        raise HTTPException(status_code=409, detail="Email déjà utilisé")

    if data.role not in ["medecin", "admin", "epidemio"]:
        raise HTTPException(status_code=400, detail="Rôle invalide")

    user_id = await db.fetchval(
        """INSERT INTO utilisateurs
           (email, password_hash, nom, prenom, role, departement)
           VALUES ($1,$2,$3,$4,$5,$6)
           RETURNING id""",
        data.email, hacher_password(data.password),
        data.nom, data.prenom, data.role, data.departement
    )

    return {
        "message" : "Utilisateur créé",
        "user_id" : user_id,
        "email"   : data.email,
        "role"    : data.role,
    }


@router.get("/patients")
async def lister_patients(
    departement : str  = None,
    limite      : int  = 50,
    user        : dict = Depends(verifier_role("admin", "medecin")),
    db          : asyncpg.Connection = Depends(get_db)
):
    """Liste les patients — filtrables par département."""
    if departement:
        rows = await db.fetch(
            """SELECT patient_id, email, nom, prenom, departement,
                      date_inscription, actif
               FROM patients WHERE departement = $1
               ORDER BY date_inscription DESC LIMIT $2""",
            departement, min(limite, 500)
        )
    else:
        rows = await db.fetch(
            """SELECT patient_id, email, nom, prenom, departement,
                      date_inscription, actif
               FROM patients
               ORDER BY date_inscription DESC LIMIT $1""",
            min(limite, 500)
        )

    return [dict(r) for r in rows]

@router.get("/rapport/{departement}")
async def rapport_departement(
    departement : str,
    user        : dict = Depends(verifier_role("admin", "epidemio", "medecin")),
    db          : asyncpg.Connection = Depends(get_db)
):
    """Rapport épidémiologique agrégé par département."""
    stats = await db.fetchrow(
        """SELECT
           COUNT(DISTINCT patient_id)                              AS nb_patients,
           COUNT(*)                                               AS nb_mesures,
           SUM(CASE WHEN anomalie = TRUE  THEN 1 ELSE 0 END)     AS nb_anomalies,
           SUM(CASE WHEN deferred = TRUE  THEN 1 ELSE 0 END)     AS nb_deferred
           FROM mesures_discretes WHERE departement = $1""",
        departement
    )

    alertes = await db.fetch(
        """SELECT niveau, COUNT(*) AS n
           FROM alertes WHERE departement = $1
           GROUP BY niveau""",
        departement
    )

    return {
        "departement"       : departement,
        "nb_patients"       : stats["nb_patients"],
        "nb_mesures"        : stats["nb_mesures"],
        "nb_anomalies"      : stats["nb_anomalies"],
        "nb_deferred"       : stats["nb_deferred"],
        "alertes_par_niveau": {r["niveau"]: r["n"] for r in alertes},
    }


@router.get("/devices")
async def lister_devices(
    user : dict = Depends(verifier_role("admin")),
    db   : asyncpg.Connection = Depends(get_db)
):
    """Liste tous les dispositifs enrôlés."""
    rows = await db.fetch(
        """SELECT device_id, patient_id, cert_cn,
                  date_enrolement, date_expiration, actif, dernier_acces
           FROM device_registry
           ORDER BY date_enrolement DESC"""
    )
    return [dict(r) for r in rows]


@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id : str,
    user       : dict = Depends(verifier_role("admin", "medecin")),
    db         : asyncpg.Connection = Depends(get_db)
):
    row = await db.fetchrow(
        """SELECT patient_id, email, nom, prenom, departement,
                  date_inscription, actif
           FROM patients WHERE patient_id = $1""",
        patient_id
    )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Patient introuvable")
    return dict(row)
