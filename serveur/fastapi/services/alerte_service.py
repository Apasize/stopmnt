import asyncpg
import redis.asyncio as aioredis
import json
from datetime import datetime, timezone
from config import settings

async def verifier_seuils_et_alerter(
    db, redis, patient_id, departement, capteur, mesures
):
    row = await db.fetchrow(
        "SELECT seuils_custom FROM patients WHERE patient_id = $1",
        patient_id
    )

    seuils = dict(settings.SEUILS_DEFAUT)

    if row and row['seuils_custom']:
        custom = row['seuils_custom']
        if isinstance(custom, str):
            try:
                custom = json.loads(custom)
            except Exception:
                custom = {}
        if isinstance(custom, dict) and custom:
            seuils.update(custom)

    niveau  = None
    message = None

    if capteur == 'tensiometre':
        sys_v = mesures.get('systolique', 0)
        dias  = mesures.get('diastolique', 0)
        s     = seuils.get('systolique', {})
        if sys_v >= s.get('critique_haut', 9999):
            niveau  = 'critique'
            message = f'HTA critique : {sys_v}/{dias} mmHg'
        elif sys_v >= s.get('alerte_haut', 9999):
            niveau  = 'alerte'
            message = f'HTA : {sys_v}/{dias} mmHg'

    elif capteur == 'glucometre':
        glyc = mesures.get('glycemie', 0)
        s    = seuils.get('glycemie', {})
        if glyc <= s.get('critique_bas', -1) or glyc >= s.get('critique_haut', 9999):
            niveau  = 'critique'
            message = f'Glycémie critique : {glyc} g/L'
        elif glyc <= s.get('alerte_bas', -1) or glyc >= s.get('alerte_haut', 9999):
            niveau  = 'alerte'
            message = f'Glycémie anormale : {glyc} g/L'

    if not niveau:
        return None

    alerte_id = await db.fetchval(
        """INSERT INTO alertes
           (patient_id, departement, capteur, niveau, message)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING id""",
        patient_id, departement, capteur, niveau, message
    )

    alerte = {
        'id'          : alerte_id,
        'patient_id'  : patient_id,
        'departement' : departement,
        'capteur'     : capteur,
        'niveau'      : niveau,
        'message'     : message,
        'timestamp'   : datetime.now(timezone.utc).isoformat(),
    }

    await redis.lpush('queue:alertes', json.dumps(alerte))
    return alerte
