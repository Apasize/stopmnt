"""
models/patient.py
Modèles Pydantic pour la validation des données patients.
Pydantic valide automatiquement les types et formats
avant que le code métier ne soit exécuté.
"""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import date


class PatientRegister(BaseModel):
    """Données reçues lors de l'inscription d'un patient."""
    email           : EmailStr
    password        : str
    nom             : Optional[str] = None
    prenom          : Optional[str] = None
    date_naissance  : Optional[date] = None
    departement     : str
    telephone       : Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_fort(cls, v):
        if len(v) < 8:
            raise ValueError("Le mot de passe doit faire au moins 8 caractères")
        return v

    @field_validator("departement")
    @classmethod
    def departement_valide(cls, v):
        valides = ["littoral", "atlantique", "oueme", "mono", "plateau"]
        if v.lower() not in valides:
            raise ValueError(f"Département invalide. Valeurs : {valides}")
        return v.lower()


class PatientUpdate(BaseModel):
    """Données modifiables par le patient."""
    nom             : Optional[str] = None
    prenom          : Optional[str] = None
    date_naissance  : Optional[date] = None
    telephone       : Optional[str] = None
    seuils_custom   : Optional[dict] = None


class PatientResponse(BaseModel):
    """Données renvoyées au client — jamais le mot de passe."""
    patient_id      : str
    email           : str
    nom             : Optional[str]
    prenom          : Optional[str]
    departement     : str
    date_inscription: str
