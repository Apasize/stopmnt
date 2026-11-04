from fastapi import APIRouter, Depends, HTTPException
import os

import re

import asyncpg

from database import get_db
from middleware.security import verifier_role, verifier_perimetre_patient

router = APIRouter()

def get_influx_client():
    from influxdb_client import InfluxDBClient
    return InfluxDBClient(
        url   = os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
        token = os.getenv("INFLUXDB_TOKEN", ""),
        org   = os.getenv("INFLUXDB_ORG", "stopmnt")
    )

@router.get("/patients/{patient_id}/continues")
async def donnees_continues(
    patient_id : str,
    heures     : int  = 24,
    capteur    : str  = "ppg",
    user       : dict = Depends(verifier_role("medecin", "admin", "epidemio")),
    db         : asyncpg.Connection = Depends(get_db)
):
    await verifier_perimetre_patient(db, user, patient_id)
    # Ces valeurs entrent dans une requête Flux : on n'accepte que des identifiants simples.
    if not re.fullmatch(r"[\w-]{1,50}", capteur) or not re.fullmatch(r"[\w-]{1,50}", patient_id):
        raise HTTPException(status_code=400, detail="Paramètre invalide")
    heures = max(1, min(heures, 168))

    query = f'''
from(bucket: "physiological_data")
  |> range(start: -{heures}h)
  |> filter(fn: (r) => r._measurement == "{capteur}")
  |> filter(fn: (r) => r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "fc" or r._field == "spo2" or r._field == "freq_resp")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> sort(columns: ["_time"])
'''

    try:
        client    = get_influx_client()
        query_api = client.query_api()
        tables    = query_api.query(query)

        points = {}
        for table in tables:
            for record in table.records:
                ts    = record.get_time().isoformat()
                field = record.get_field()
                val   = record.get_value()
                if ts not in points:
                    points[ts] = {"timestamp": ts}
                if val is not None:
                    points[ts][field] = round(float(val), 2)

        client.close()
        return sorted(points.values(), key=lambda x: x["timestamp"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur InfluxDB : {str(e)}")
