"""
config.py
Centralise toutes les variables de configuration.
Toutes les valeurs sensibles viennent des variables d'environnement
définies dans le fichier .env — jamais hardcodées ici.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:

    # ── Application ───────────────────────────────────
    APP_NAME        = "STOP-MNT IoMT API"
    APP_VERSION     = "1.0.0"
    DEBUG           = os.getenv("DEBUG", "false").lower() == "true"

    # ── PostgreSQL ────────────────────────────────────
    # On se connecte via le nom du service Docker "postgres_primary"
    # Docker résout ce nom en IP automatiquement dans le réseau interne
    POSTGRES_HOST   = os.getenv("POSTGRES_HOST", "postgres_primary")
    POSTGRES_PORT   = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER   = os.getenv("POSTGRES_USER", "stopmnt_user")
    POSTGRES_PASS   = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB     = os.getenv("POSTGRES_DB", "stopmnt_db")

    @property
    def DATABASE_URL(self):
        # URL de connexion PostgreSQL pour asyncpg
        return (f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASS}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}")

    # ── Redis ─────────────────────────────────────────
    REDIS_HOST      = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT      = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD  = os.getenv("REDIS_PASSWORD", "")

    # ── JWT ───────────────────────────────────────────
    JWT_SECRET      = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM   = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_H    = int(os.getenv("JWT_EXPIRE_HOURS", "1"))

    # ── Certificats X.509 ─────────────────────────────
    # Chemin vers la CA dans le conteneur FastAPI
    CA_CERT_PATH    = os.getenv("CA_CERT_PATH", "/certs/ca.crt")
    CA_KEY_PATH     = os.getenv("CA_KEY_PATH", "/certs/ca.key")

    # Durée de validité des certificats clients en jours
    CERT_VALIDITY_DAYS = int(os.getenv("CERT_VALIDITY_DAYS", "365"))

    # ── Seuils physiologiques par défaut ──────────────
    # Ces valeurs sont les défauts — chaque patient peut avoir les siens
    SEUILS_DEFAUT = {
        "fc":           {"critique_bas": 40,   "alerte_bas": 50,
                         "alerte_haut": 100,   "critique_haut": 120},
        "spo2":         {"critique_bas": 90,   "alerte_bas": 94},
        "freq_resp":    {"critique_bas": 10,   "critique_haut": 25},
        "glycemie":     {"critique_bas": 0.70, "alerte_bas": 0.80,
                         "alerte_haut": 1.80,  "critique_haut": 2.00},
        "systolique":   {"alerte_haut": 160,   "critique_haut": 180},
        "diastolique":  {"alerte_haut": 100,   "critique_haut": 110},
        "pm25":         {"alerte_haut": 35.4,  "critique_haut": 55.4},
    }

    # ── Rate limiting ─────────────────────────────────
    # Nombre de requêtes maximum par minute par IP
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

settings = Settings()
