import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import get_pg_pool, close_pg_pool, close_redis
from routers import auth, mesures, alertes, admin, influx, profil_medical

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Démarrage STOP-MNT API...")
    await get_pg_pool()
    print("PostgreSQL connecté")
    yield
    print("Arrêt STOP-MNT API...")
    await close_pg_pool()
    await close_redis()
    print("Connexions fermées")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv("CORS_ORIGINS", "https://localhost").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["Auth"])
app.include_router(mesures.router,  prefix="/api/v1/mesures",  tags=["Mesures"])
app.include_router(alertes.router,  prefix="/api/v1/alertes",  tags=["Alertes"])
app.include_router(admin.router,    prefix="/api/v1/admin",    tags=["Admin"])
app.include_router(influx.router,   prefix="/api/v1/influx",   tags=["InfluxDB"])
app.include_router(profil_medical.router, prefix="/api/v1/profil-medical", tags=["Profil médical"])

@app.get("/health")
async def health_check():
    return {
        "status"  : "ok",
        "version" : settings.APP_VERSION,
        "service" : settings.APP_NAME,
    }

@app.get("/")
async def root():
    return {
        "message" : "STOP-MNT IoMT API",
        "docs"    : "/docs",
        "health"  : "/health",
    }
