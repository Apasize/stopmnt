"""
models/utilisateur.py
Modèles pour les utilisateurs professionnels (médecins, admins).
"""

from pydantic import BaseModel, EmailStr
from typing import Optional


class UtilisateurCreate(BaseModel):
    """Création d'un compte médecin ou admin — par un admin uniquement."""
    email       : EmailStr
    password    : str
    nom         : str
    prenom      : str
    role        : str
    departement : Optional[str] = None

    @property
    def role_valide(self):
        return self.role in ["medecin", "admin", "epidemio"]


class LoginRequest(BaseModel):
    """Données de connexion."""
    email    : EmailStr
    password : str


class TokenResponse(BaseModel):
    """Réponse après connexion réussie."""
    access_token : str
    token_type   : str = "bearer"
    expires_in   : int  # secondes avant expiration
    role         : str
