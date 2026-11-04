"""
models/mesure.py
Modèles pour les mesures discrètes.
"""

import re
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import datetime


class MesureCreate(BaseModel):
    """
    Données envoyées par le smartphone lors d'une mesure discrète.
    Le timestamp_data est l'heure réelle de la mesure côté patient
    (peut être dans le passé si la donnée était bufférisée).
    """
    capteur         : str
    timestamp_data  : datetime
    mesures         : dict
    deferred        : bool = False  # True si la donnée était dans le buffer local

    mesure_id       : Optional[str] = None  # identifiant stable généré par le terminal

    @field_validator("capteur")
    @classmethod
    def capteur_valide(cls, v):
        # Le nom peut venir de l'appareil (montre BLE) : on contrôle sa forme, pas une liste fermée.
        if not re.fullmatch(r"[\w .:()-]{1,50}", v):
            raise ValueError("Nom de capteur invalide")
        return v

    @model_validator(mode="after")
    def tension_coherente(self):
        # Une systolique inferieure ou egale a la diastolique est une erreur de saisie.
        sys_v, dia_v = self.mesures.get("systolique"), self.mesures.get("diastolique")
        if isinstance(sys_v, (int, float)) and isinstance(dia_v, (int, float)) and sys_v <= dia_v:
            raise ValueError("Tension incoherente : systolique inferieure ou egale a la diastolique")
        return self


class MesureResponse(BaseModel):
    """Réponse après enregistrement d'une mesure."""
    id          : int
    capteur     : str
    timestamp   : str
    mesures     : dict
    anomalie    : bool
    deferred    : bool
