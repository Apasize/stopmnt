"""
database.py
Gestion des connexions à PostgreSQL et Redis.
Utilise des pools de connexions — plutôt que d'ouvrir/fermer
une connexion à chaque requête (coûteux), on maintient un pool
de connexions réutilisables.
"""

import asyncpg
import redis.asyncio as aioredis
from config import settings


# ── PostgreSQL ────────────────────────────────────────

# Variable globale qui contiendra le pool de connexions
_pg_pool = None

async def get_pg_pool():
    """
    Retourne le pool PostgreSQL existant ou en crée un nouveau.
    min_size=2 : 2 connexions toujours ouvertes
    max_size=10 : maximum 10 connexions simultanées
    """
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASS,
            database=settings.POSTGRES_DB,
            min_size=2,
            max_size=10,
        )
    return _pg_pool

async def get_db():
    """
    Dépendance FastAPI — fournit une connexion PostgreSQL à un endpoint.
    Utilisation dans un router :
        async def mon_endpoint(db = Depends(get_db)):
    La connexion est automatiquement rendue au pool après la requête.
    """
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        yield conn

async def close_pg_pool():
    """Ferme proprement le pool — appelé à l'arrêt de l'application."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ── Redis ─────────────────────────────────────────────

_redis_client = None

async def get_redis():
    """
    Retourne le client Redis existant ou en crée un nouveau.
    decode_responses=True : les réponses Redis sont des strings Python
    plutôt que des bytes bruts
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
    return _redis_client

async def close_redis():
    """Ferme proprement la connexion Redis."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
