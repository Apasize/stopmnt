#!/usr/bin/env python3
"""
Tests d'integration du serveur STOP-MNT, sur le systeme deploye (Docker Compose).
A lancer sur le serveur. Les comptes de test sont crees puis supprimes.
Sortie : un resultat par test et resultats_tests.json.
"""
import json, ssl, statistics, subprocess, time, urllib.request, urllib.error, uuid
from concurrent.futures import ThreadPoolExecutor

BASE = "https://127.0.0.1/api/v1"
CTX = ssl._create_unverified_context()
R = []


def api(m, p, d=None, t=None):
    h = {"Content-Type": "application/json"}
    if t:
        h["Authorization"] = "Bearer " + t
    q = urllib.request.Request(BASE + p, method=m, headers=h, data=json.dumps(d).encode() if d is not None else None)
    try:
        with urllib.request.urlopen(q, context=CTX, timeout=20) as r:
            b = r.read()
            return r.status, json.loads(b) if b else None
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, b.decode(errors="ignore")


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def sql(q):
    return subprocess.run("docker exec -i stopmnt-postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At'", shell=True, input=q + ";", capture_output=True, text=True).stdout.strip()


def ok(nom, cond, detail=""):
    R.append({"test": nom, "ok": bool(cond), "detail": str(detail)})
    print(("OK   " if cond else "ECHEC"), nom, detail, flush=True)


tag = uuid.uuid4().hex[:8]
ep, em1, em2 = f"pat{tag}@stopmnt-test.org", f"med{tag}@stopmnt-test.org", f"mex{tag}@stopmnt-test.org"
mdp = "Test-" + tag + "-Aa1!"
pid = None
try:
    ok("accès sans jeton refusé", api("GET", "/mesures/historique")[0] in (401, 403))
    c, r = api("POST", "/auth/register", {"email": ep, "password": mdp, "nom": "Test", "prenom": "Patient", "date_naissance": "1970-01-01", "departement": "atlantique", "telephone": "+22900000000"})
    pid = (r or {}).get("patient_id") if isinstance(r, dict) else None
    ok("inscription d'un patient", c == 201 and pid, c)
    c, r = api("POST", "/auth/login", {"email": ep, "password": "mauvais"})
    ok("mauvais mot de passe refusé", c == 401, c)
    c, r = api("POST", "/auth/login", {"email": ep, "password": mdp})
    tp = r.get("access_token") if isinstance(r, dict) else None
    ok("connexion du patient", c == 200 and tp, c)
    ms = {"capteur": "tensiometre", "timestamp_data": "2026-11-03T08:00:00Z", "mesures": {"systolique": 120, "diastolique": 80}}
    ok("mesure refusée sans dispositif enrôlé", api("POST", "/mesures", ms, tp)[0] == 403)
    c, enr = api("POST", "/auth/device/enroll", {}, tp)
    ok("enrôlement du dispositif : certificat délivré", c in (200, 201) and "certificate_pem" in enr, c)
    inv = {"capteur": "tensiometre", "timestamp_data": "2026-11-03T08:01:00Z", "mesures": {"systolique": 80, "diastolique": 120}}
    ok("tension incohérente refusée", api("POST", "/mesures", inv, tp)[0] == 422)
    for nom_f, cle in (("c.pem", "certificate_pem"), ("k.pem", "private_key_pem")):
        subprocess.run(f"docker exec -i stopmnt-mosquitto sh -c 'cat > /tmp/{nom_f}'", shell=True, input=enr[cle], text=True)
    ok("mesure enregistrée", api("POST", "/mesures", ms, tp)[0] == 201)
    mid = uuid.uuid4().hex
    m2 = dict(ms, mesure_id=mid)
    c1, r1 = api("POST", "/mesures", m2, tp)
    c2, r2 = api("POST", "/mesures", dict(m2, deferred=True), tp)
    n = sql(f"select count(*) from mesures_discretes where patient_id='{pid}' and mesure_uuid='{mid}'")
    ok("renvoi d'une mesure : aucun doublon", c1 == 201 and c2 == 201 and n == "1" and r2.get("doublon"), f"lignes={n}")
    ok("oxymètre accepté", api("POST", "/mesures", {"capteur": "oxymetre", "timestamp_data": "2026-11-03T08:01:00Z", "mesures": {"spo2": 97}}, tp)[0] == 201)
    ok("nom de montre accepté", api("POST", "/mesures", {"capteur": "Oraimo Watch 2", "timestamp_data": "2026-11-03T08:02:00Z", "mesures": {"fc": 70}}, tp)[0] == 201)
    ok("nom de capteur malformé refusé", api("POST", "/mesures", {"capteur": "a'; DROP", "timestamp_data": "2026-11-03T08:02:00Z", "mesures": {}}, tp)[0] == 422)
    c, r = api("POST", "/mesures", {"capteur": "tensiometre", "timestamp_data": "2026-11-03T08:03:00Z", "mesures": {"systolique": 190, "diastolique": 125}}, tp)
    ok("valeur critique : alerte créée", c == 201 and r.get("anomalie"), r.get("alerte") if isinstance(r, dict) else r)
    c, r = api("PUT", "/profil-medical/moi", {"groupe_sanguin": "O+", "antecedents": ["hta"], "maladies_chroniques": [], "traitements": []}, tp)
    ok("dossier médical : écriture", c == 200, c)
    c, r = api("GET", "/profil-medical/moi", t=tp)
    ok("dossier médical : lecture", c == 200 and r.get("groupe_sanguin") == "O+", c)
    # Medecins de test
    h = sh(f"""docker exec stopmnt-fastapi python -c "from services.auth_service import hacher_password as h;print(h('{mdp}'))" """)
    for e, dep in ((em1, "atlantique"), (em2, "littoral")):
        sql(f"insert into utilisateurs (email,password_hash,nom,prenom,role,departement) values ('{e}','{h}','Test','Med','medecin','{dep}')")
    t1 = api("POST", "/auth/login", {"email": em1, "password": mdp})[1]["access_token"]
    t2 = api("POST", "/auth/login", {"email": em2, "password": mdp})[1]["access_token"]
    ok("patient : pas d'accès aux routes médecin", api("GET", f"/mesures/patient/{pid}", t=tp)[0] == 403)
    ok("médecin du département : lecture permise", api("GET", f"/mesures/patient/{pid}", t=t1)[0] == 200)
    ok("médecin d'un autre département : mesures refusées", api("GET", f"/mesures/patient/{pid}", t=t2)[0] == 403)
    ok("médecin d'un autre département : dossier refusé", api("GET", f"/profil-medical/patient/{pid}", t=t2)[0] == 403)
    c, r = api("GET", "/alertes", t=t1)
    al = [a for a in (r or []) if a.get("patient_id") == pid] if c == 200 else []
    ok("alerte visible par le médecin du département", al, len(al))
    if al:
        ok("autre département : acquittement refusé", api("PUT", f"/alertes/{al[0]['id']}/acquitter", t=t2)[0] == 403)
        ok("médecin du département : acquittement", api("PUT", f"/alertes/{al[0]['id']}/acquitter", t=t1)[0] == 200)
    # Limite de debit de Nginx
    with ThreadPoolExecutor(20) as p:
        cs = list(p.map(lambda i: api("GET", "/auth/me", t=tp)[0], range(300)))
    ok("Nginx : les rafales sont limitées", 429 in cs or 503 in cs, {x: cs.count(x) for x in set(cs)})
    time.sleep(40)
    # Charge sur l'API, derriere Nginx dont la limite par client ne s'applique pas ici.
    def une(i):
        d = json.dumps({"capteur": "tensiometre", "timestamp_data": "2026-11-03T09:00:00Z", "mesures": {"systolique": 120, "diastolique": 80}, "mesure_id": uuid.uuid4().hex}).encode()
        q = urllib.request.Request("http://127.0.0.1:8000/api/v1/mesures", method="POST", data=d, headers={"Content-Type": "application/json", "Authorization": "Bearer " + tp})
        t0 = time.time()
        try:
            with urllib.request.urlopen(q, timeout=30) as r:
                c = r.status
        except urllib.error.HTTPError as e:
            c = e.code
        return c, (time.time() - t0) * 1000
    t0 = time.time()
    with ThreadPoolExecutor(20) as p:
        res = list(p.map(une, range(1000)))
    du = time.time() - t0
    lat = sorted(x[1] for x in res)
    err = sum(1 for x in res if x[0] != 201)
    det = {"requetes": len(res), "concurrence": 20, "erreurs": err, "debit_par_s": round(len(res) / du, 1), "p50_ms": round(lat[len(lat) // 2], 1), "p95_ms": round(lat[int(.95 * len(lat))], 1), "p99_ms": round(lat[int(.99 * len(lat))], 1)}
    ok("charge : 1 000 envois directs à l'API", err == 0, det)
    # Deconnexion
    ok("avant déconnexion : jeton valable", api("GET", "/auth/me", t=tp)[0] == 200)
    ok("déconnexion", api("POST", "/auth/logout", t=tp)[0] == 200)
    ok("après déconnexion : jeton refusé", api("GET", "/auth/me", t=tp)[0] == 401)
    # MQTT : ecriture puis panne d'InfluxDB
    _q = lambda m: f"""docker exec stopmnt-influxdb sh -c 'influx query --hide-headers "from(bucket:\\"physiological_data\\") |> range(start:-30m) |> filter(fn:(r)=>r.patient_id==\\"{pid}\\" and r.valeur_test==\\"{m}\\" or r.patient_id==\\"{pid}\\") |> count()"'"""
    def pub(v):
        r = subprocess.run(f"""docker exec stopmnt-mosquitto mosquitto_pub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt --cert /tmp/c.pem --key /tmp/k.pem --insecure -q 1 -t stopmnt/atlantique/{pid}/continu/ppg -m '{{"mesures": {{"fc": {v}, "spo2": 98}}}}'""", shell=True, capture_output=True, text=True)
        return r.returncode, r.stderr[:120]
    def compte():
        o = sh(f"""docker exec stopmnt-influxdb sh -c 'influx query --raw "from(bucket:\\"physiological_data\\") |> range(start:-30m) |> filter(fn:(r)=>r.patient_id==\\"{pid}\\" and r._field==\\"fc\\") |> count()"' """)
        vals = [l.split(",")[-3] if False else l for l in o.splitlines() if l and not l.startswith("#") and "_value" not in l]
        import csv, io
        tot = 0
        for row in csv.reader(io.StringIO("\n".join(o.splitlines()))):
            pass
        rows = [r for r in csv.reader(io.StringIO(o)) if r and not r[0].startswith("#")]
        if len(rows) >= 2:
            i = rows[0].index("_value")
            tot = sum(int(r[i]) for r in rows[1:])
        return tot
    print(pub(71)); time.sleep(4)
    n1 = compte()
    ok("MQTT : message écrit dans InfluxDB", n1 >= 1, n1)
    sh("docker stop stopmnt-influxdb"); time.sleep(2)
    print(pub(72), pub(73)); time.sleep(6)
    sh("docker start stopmnt-influxdb"); time.sleep(25)
    n2 = compte()
    ok("MQTT : messages reçus pendant une panne d'InfluxDB non perdus", n2 >= n1 + 2, f"avant={n1} apres={n2}")
    # Sauvegarde et restauration
    sh("docker exec stopmnt-backup /backup/backup.sh")
    d = sh("ls -t data/backups/postgres_*.dump | head -1")
    n_ref = sql("select count(*) from mesures_discretes")
    sql("drop database if exists restau_test"); sql("create database restau_test")
    sh(f"docker exec -i stopmnt-postgres sh -c 'pg_restore -U $POSTGRES_USER -d restau_test --no-owner' < {d}")
    n_res = sh("""docker exec stopmnt-postgres sh -c 'psql -U $POSTGRES_USER -d restau_test -Atc "select count(*) from mesures_discretes"' """)
    sql("drop database if exists restau_test")
    ok("sauvegarde restaurée : même nombre de mesures", n_res == n_ref and n_ref != "", f"base={n_ref} restaurée={n_res}")
finally:
    sql("delete from utilisateurs where email like '%@stopmnt-test.org'")
    for ancien in sql("select patient_id from patients where email like '%@stopmnt-test.org'").split():
        for t in ("mesures_discretes", "alertes", "device_registry", "profil_medical", "audit_logs"):
            sql(f"delete from {t} where patient_id='{ancien}'")
        sql(f"delete from patients where patient_id='{ancien}'")
    if False:
        for t in ("mesures_discretes", "alertes", "device_registry", "profil_medical", "audit_logs"):
            sql(f"delete from {t} where patient_id='{pid}'")
        sql(f"delete from patients where patient_id='{pid}'")
    sql(f"delete from utilisateurs where email in ('{em1}','{em2}')")
    json.dump(R, open("resultats_tests.json", "w"), ensure_ascii=False, indent=1)
    print(sum(x["ok"] for x in R), "réussis sur", len(R))
