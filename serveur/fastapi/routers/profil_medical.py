"""
routers/profil_medical.py
Dossier médical patient — lecture et mise à jour.
Accessible par le patient lui-même (GET/PUT) et par les soignants (GET).
"""

from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg
import json

from database import get_db
from models.profil_medical import ProfilMedicalUpsert, ProfilMedicalResponse
from middleware.security import get_utilisateur_courant, verifier_role, verifier_perimetre_patient

router = APIRouter()


@router.get("/moi", response_model=ProfilMedicalResponse)
async def lire_mon_profil_medical(
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """Retourne le dossier médical du patient connecté."""
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Pas un patient")

    row = await db.fetchrow(
        """SELECT groupe_sanguin, antecedents, maladies_chroniques,
                  traitements, mis_a_jour
           FROM profil_medical WHERE patient_id = $1""",
        patient_id
    )
    if not row:
        # Dossier vide — retourner la structure vide plutôt qu'un 404
        return ProfilMedicalResponse(
            groupe_sanguin=None, antecedents=[], maladies_chroniques=[], traitements=[], mis_a_jour=None
        )

    return ProfilMedicalResponse(
        groupe_sanguin      = row["groupe_sanguin"],
        antecedents         = json.loads(row["antecedents"]),
        maladies_chroniques = json.loads(row["maladies_chroniques"]),
        traitements         = json.loads(row["traitements"]),
        mis_a_jour          = row["mis_a_jour"].isoformat() if row["mis_a_jour"] else None,
    )


@router.put("/moi", response_model=ProfilMedicalResponse)
async def mettre_a_jour_mon_profil_medical(
    data : ProfilMedicalUpsert,
    user : dict = Depends(get_utilisateur_courant),
    db   : asyncpg.Connection = Depends(get_db)
):
    """Crée ou met à jour le dossier médical du patient connecté."""
    patient_id = user.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Pas un patient")

    row = await db.fetchrow(
        """INSERT INTO profil_medical
               (patient_id, groupe_sanguin, antecedents, maladies_chroniques, traitements, mis_a_jour)
           VALUES ($1, $2, $3, $4, $5, NOW())
           ON CONFLICT (patient_id) DO UPDATE
               SET groupe_sanguin      = EXCLUDED.groupe_sanguin,
                   antecedents         = EXCLUDED.antecedents,
                   maladies_chroniques = EXCLUDED.maladies_chroniques,
                   traitements         = EXCLUDED.traitements,
                   mis_a_jour          = NOW()
           RETURNING groupe_sanguin, antecedents, maladies_chroniques, traitements, mis_a_jour""",
        patient_id,
        data.groupe_sanguin,
        json.dumps(data.antecedents),
        json.dumps(data.maladies_chroniques),
        json.dumps(data.traitements),
    )

    return ProfilMedicalResponse(
        groupe_sanguin      = row["groupe_sanguin"],
        antecedents         = json.loads(row["antecedents"]),
        maladies_chroniques = json.loads(row["maladies_chroniques"]),
        traitements         = json.loads(row["traitements"]),
        mis_a_jour          = row["mis_a_jour"].isoformat(),
    )


@router.get("/patient/{patient_id}", response_model=ProfilMedicalResponse)
async def lire_profil_medical_patient(
    patient_id : str,
    user       : dict = Depends(verifier_role("medecin", "admin")),
    db         : asyncpg.Connection = Depends(get_db)
):
    """Lit le dossier médical d'un patient — médecin et admin uniquement."""
    await verifier_perimetre_patient(db, user, patient_id)
    row = await db.fetchrow(
        """SELECT groupe_sanguin, antecedents, maladies_chroniques,
                  traitements, mis_a_jour
           FROM profil_medical WHERE patient_id = $1""",
        patient_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Dossier médical introuvable")

    return ProfilMedicalResponse(
        groupe_sanguin      = row["groupe_sanguin"],
        antecedents         = json.loads(row["antecedents"]),
        maladies_chroniques = json.loads(row["maladies_chroniques"]),
        traitements         = json.loads(row["traitements"]),
        mis_a_jour          = row["mis_a_jour"].isoformat() if row["mis_a_jour"] else None,
    )
