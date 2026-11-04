"""
models/profil_medical.py
Modèles Pydantic pour le profil/dossier médical du patient.
"""

from pydantic import BaseModel, field_validator
from typing import Optional, List


GROUPES_SANGUINS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}


class ProfilMedicalUpsert(BaseModel):
    """Données envoyées par l'app pour créer ou mettre à jour le dossier médical."""
    groupe_sanguin      : Optional[str]       = None
    antecedents         : List[str]           = []
    maladies_chroniques : List[str]           = []
    traitements         : List[str]           = []

    @field_validator("groupe_sanguin")
    @classmethod
    def groupe_sanguin_valide(cls, v):
        if v is not None and v.upper() not in GROUPES_SANGUINS:
            raise ValueError(f"Groupe sanguin invalide. Valeurs : {sorted(GROUPES_SANGUINS)}")
        return v.upper() if v else v


class ProfilMedicalResponse(BaseModel):
    """Données renvoyées au client."""
    groupe_sanguin      : Optional[str]
    antecedents         : List[str]
    maladies_chroniques : List[str]
    traitements         : List[str]
    mis_a_jour          : Optional[str]
