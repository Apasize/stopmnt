"""
worker.py
Service de traitement en arrière-plan.
Reçoit les données MQTT et les écrit dans InfluxDB.
Dépile les alertes Redis et envoie les notifications.
"""

import asyncio
import json
import time
import logging
import os
import ssl
import signal
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import redis.asyncio as aioredis
import asyncpg
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, messaging

load_dotenv()

# ── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("worker")

# ── Configuration depuis variables d'environnement ────
MQTT_HOST     = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "8883"))
MQTT_CA_CERT  = os.getenv("MQTT_CA_CERT", "/certs/ca.crt")
MQTT_CERT     = os.getenv("MQTT_CERT", "/certs/worker.crt")
MQTT_KEY      = os.getenv("MQTT_KEY", "/certs/worker.key")

INFLUX_URL    = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN", "")
INFLUX_ORG    = os.getenv("INFLUXDB_ORG", "stopmnt")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "physiological_data")

REDIS_HOST    = os.getenv("REDIS_HOST", "redis")
REDIS_PORT    = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASS    = os.getenv("REDIS_PASSWORD", "")

FCM_CREDS     = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

PG_HOST       = os.getenv("POSTGRES_HOST", "postgres_primary")
PG_PORT       = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER       = os.getenv("POSTGRES_USER", "stopmnt_user")
PG_PASS       = os.getenv("POSTGRES_PASSWORD", "")
PG_DB         = os.getenv("POSTGRES_DB", "stopmnt_db")

# ── Clients globaux ───────────────────────────────────
influx_client = None
influx_write  = None
redis_client  = None
pg_pool       = None


# ── Initialisation ────────────────────────────────────

async def init_connexions():
    """Initialise toutes les connexions au démarrage."""
    global influx_client, influx_write, redis_client, pg_pool

    # InfluxDB
    influx_client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )
    influx_write = influx_client.write_api(write_options=SYNCHRONOUS)
    log.info("InfluxDB connecté")

    # Redis
    redis_client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASS,
        decode_responses=True
    )
    await redis_client.ping()
    log.info("Redis connecté")

    # PostgreSQL
    pg_pool = await asyncpg.create_pool(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        database=PG_DB,
        min_size=2, max_size=5
    )
    log.info("PostgreSQL connecté")

    # Firebase Admin SDK
    if FCM_CREDS and os.path.isfile(FCM_CREDS) and not firebase_admin._apps:
        try:
            cred = credentials.Certificate(FCM_CREDS)
            firebase_admin.initialize_app(cred)
            log.info("Firebase Admin SDK initialisé")
        except Exception as e:
            log.warning(f"Firebase init échoué : {e} — FCM désactivé")
    else:
        log.warning("GOOGLE_APPLICATION_CREDENTIALS manquant ou invalide — FCM désactivé")


# ── Traitement des messages MQTT ──────────────────────

def traiter_message_mqtt(topic: str, payload: dict):
    """
    Route un message MQTT vers le bon handler selon le topic.
    Format topic : stopmnt/{dept}/{pid}/{type}/{capteur}
    """
    parts = topic.split("/")
    if len(parts) < 5:
        log.warning(f"Topic invalide : {topic}")
        return

    dept    = parts[1]
    pid     = parts[2]
    type_   = parts[3]
    capteur = parts[4]

    if type_ == "continu":
        ecrire_influxdb(dept, pid, capteur, payload)
    elif type_ == "alerte":
        log.warning(f"Alerte reçue MQTT : {pid} — {payload.get('message','')}")
    else:
        log.info(f"Message type '{type_}' ignoré par le worker MQTT")


def ecrire_influxdb(dept: str, pid: str, capteur: str, payload: dict):
    """
    Écrit les données agrégées dans InfluxDB.
    Le payload contient des agrégats (moyenne, min, max, ecart_type).
    """
    try:
        agregats = payload.get("agregats", {})
        if not agregats:
            # Payload brut (non agrégé) — écriture directe des mesures
            mesures = payload.get("mesures", {})
            if not mesures:
                return

            point = Point(capteur) \
                .tag("patient_id", pid) \
                .tag("departement", dept) \
                .tag("capteur", capteur)

            for indicateur, valeur in mesures.items():
                if isinstance(valeur, (int, float)):
                    point = point.field(indicateur, float(valeur))

            point = point.time(
                datetime.now(timezone.utc),
                WritePrecision.MS
            )
            influx_write.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=point
            )

        else:
            # Payload agrégé — écriture des statistiques par indicateur
            ts_fin = payload.get("timestamp_fin",
                                  datetime.now(timezone.utc).isoformat())

            for indicateur, stats in agregats.items():
                point = Point(capteur) \
                    .tag("patient_id",  pid) \
                    .tag("departement", dept) \
                    .tag("capteur",     capteur) \
                    .tag("indicateur",  indicateur) \
                    .field("moyenne",    float(stats.get("moyenne", 0))) \
                    .field("min",        float(stats.get("min", 0))) \
                    .field("max",        float(stats.get("max", 0))) \
                    .field("ecart_type", float(stats.get("ecart_type", 0))) \
                    .field("n_samples",  int(stats.get("n_samples", 0))) \
                    .field("deferred",   int(payload.get("deferred", False))) \
                    .time(ts_fin, WritePrecision.MS)

                influx_write.write(
                    bucket=INFLUX_BUCKET,
                    org=INFLUX_ORG,
                    record=point
                )

        deferred = "[DEFERRED] " if payload.get("deferred") else ""
        log.info(f"{deferred}InfluxDB ← {dept}/{pid}/{capteur} "
                 f"({len(agregats) or 1} indicateur(s))")

    except Exception as e:
        log.error(f"Erreur écriture InfluxDB : {e}")
        raise  # le message ne sera pas acquitté : le courtier le redonnera


# ── Client MQTT ───────────────────────────────────────

def creer_client_mqtt():
    """Crée et configure le client MQTT avec TLS."""

    messages_recus = []

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("MQTT connecté")
            # Souscrire à tous les topics STOP-MNT
            client.subscribe("stopmnt/#", qos=2)
            log.info("Souscrit à stopmnt/#")
        else:
            log.error(f"Connexion MQTT échouée : code {rc}")

    def on_disconnect(client, userdata, flags, rc, properties=None):
        log.warning(f"MQTT déconnecté (rc={rc}) — reconnexion automatique...")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            traiter_message_mqtt(msg.topic, payload)
        except json.JSONDecodeError:
            log.warning(f"Payload non-JSON sur {msg.topic}")  # irrécupérable : on acquitte
        except Exception as e:
            log.error(f"Erreur traitement message, non acquitté : {e}")
            # Sans acquittement, le courtier garde le message ; une nouvelle session le redonne.
            time.sleep(5)
            client.reconnect()
            return
        client.ack(msg.mid, msg.qos)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="stopmnt-worker",
        clean_session=False,
        manual_ack=True,
    )

    # TLS
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(MQTT_CA_CERT)
    ctx.load_cert_chain(MQTT_CERT, MQTT_KEY)
    ctx.check_hostname = False
    client.tls_set_context(ctx)

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    return client


# ── Notification push FCM ────────────────────────────

async def envoyer_fcm(alerte: dict, pool: asyncpg.Pool) -> None:
    """Envoie une notification FCM au dispositif du patient."""
    if not firebase_admin._apps:
        return

    patient_id = alerte.get("patient_id")
    if not patient_id:
        return

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT fcm_token FROM device_registry
                   WHERE patient_id = $1 AND actif = TRUE
                     AND fcm_token IS NOT NULL
                   ORDER BY dernier_acces DESC LIMIT 1""",
                patient_id
            )
        if not row:
            log.debug(f"Pas de token FCM pour {patient_id}")
            return

        niveau  = alerte.get("niveau", "normal")
        message = alerte.get("message", "Nouvelle alerte")

        notif = messaging.Message(
            notification=messaging.Notification(
                title="Alerte critique STOP-MNT" if niveau == "critique" else "Alerte STOP-MNT",
                body=message,
            ),
            data={
                "type"       : "alerte",
                "niveau"     : niveau,
                "patient_id" : patient_id,
                "alerte_id"  : str(alerte.get("id", "")),
            },
            android=messaging.AndroidConfig(
                priority="high" if niveau == "critique" else "normal",
                notification=messaging.AndroidNotification(
                    channel_id="stopmnt_alertes",
                    priority="max" if niveau == "critique" else "default",
                ),
            ),
            token=row["fcm_token"],
        )
        messaging.send(notif)
        log.info(f"FCM envoyé -> {patient_id} ({niveau})")

    except messaging.UnregisteredError:
        log.warning(f"Token FCM invalide pour {patient_id} — nettoyage")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE device_registry SET fcm_token = NULL WHERE patient_id = $1",
                patient_id
            )
    except Exception as e:
        log.error(f"Erreur FCM : {e}")


# ── Queue Redis — traitement des alertes ──────────────

async def traiter_queue_alertes():
    """
    Dépile les alertes de la queue Redis en continu.
    En production : enverrait une notification push FCM.
    Pour l'instant : log + mise à jour PostgreSQL.
    """
    log.info("Worker alertes démarré")
    while True:
        try:
            # blpop = bloquant — attend jusqu'à ce qu'un élément arrive
            # timeout=5 = se réveille toutes les 5s même si rien n'arrive
            item = await redis_client.blpop("queue:alertes", timeout=5)

            if item:
                _, data = item
                alerte = json.loads(data)

                log.warning(
                    f"ALERTE {alerte['niveau'].upper()} — "
                    f"Patient {alerte['patient_id']} — "
                    f"{alerte['message']}"
                )

                # Mettre à jour dernier_acces du dispositif
                async with pg_pool.acquire() as conn:
                    await conn.execute(
                        """UPDATE device_registry
                           SET dernier_acces = NOW()
                           WHERE patient_id = $1""",
                        alerte["patient_id"]
                    )

                # Envoyer notification push FCM
                await envoyer_fcm(alerte, pg_pool)

        except Exception as e:
            log.error(f"Erreur queue alertes : {e}")
            await asyncio.sleep(2)


# ── Point d'entrée ────────────────────────────────────

async def main():
    log.info("=== Démarrage Worker STOP-MNT ===")

    # Initialiser les connexions
    await init_connexions()

    # Créer et connecter le client MQTT
    mqtt_client = creer_client_mqtt()
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    # Lancer le worker alertes en parallèle
    alertes_task = asyncio.create_task(traiter_queue_alertes())

    log.info("Worker opérationnel — en attente de messages...")

    # Garder le programme en vie
    try:
        await alertes_task
    except asyncio.CancelledError:
        log.info("Arrêt du worker...")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        if pg_pool:
            await pg_pool.close()
        if redis_client:
            await redis_client.close()
        if influx_client:
            influx_client.close()
        log.info("Worker arrêté proprement")


if __name__ == "__main__":
    asyncio.run(main())
