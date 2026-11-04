#!/bin/sh
set -e

# cron ne transmet pas l'environnement du conteneur.
[ -f /etc/backup.env ] && . /etc/backup.env

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
RETENTION_DAYS=7

echo "=== Backup STOP-MNT $DATE ==="

# ── PostgreSQL ────────────────────────────────────────
echo "Backup PostgreSQL..."
PGPASSWORD=$POSTGRES_PASSWORD pg_dump \
    -h postgres_primary \
    -U $POSTGRES_USER \
    -d $POSTGRES_DB \
    -F c \
    -f "$BACKUP_DIR/postgres_$DATE.dump" || { rm -f "$BACKUP_DIR/postgres_$DATE.dump"; echo "ERREUR backup PostgreSQL"; exit 1; }

if [ $? -eq 0 ]; then
    echo "PostgreSQL OK : postgres_$DATE.dump"
else
    echo "ERREUR backup PostgreSQL"
    exit 1
fi

# ── InfluxDB ──────────────────────────────────────────
echo "Backup InfluxDB..."
influx backup \
    --host http://influxdb:8086 \
    --token $INFLUXDB_TOKEN \
    "$BACKUP_DIR/influxdb_$DATE"

if [ $? -eq 0 ]; then
    echo "InfluxDB OK : influxdb_$DATE/"
else
    echo "ERREUR backup InfluxDB"
    exit 1
fi

# ── Nettoyage des anciens backups ─────────────────────
echo "Nettoyage backups > ${RETENTION_DAYS} jours..."
find "$BACKUP_DIR" -name "postgres_*.dump" \
    -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -type d -name "influxdb_*" \
    -mtime +$RETENTION_DAYS -exec rm -rf {} + 2>/dev/null || true

# ── Résumé ────────────────────────────────────────────
echo "=== Backups disponibles ==="
ls -lh "$BACKUP_DIR"/postgres_*.dump 2>/dev/null || echo "Aucun backup PostgreSQL"
ls -d "$BACKUP_DIR"/influxdb_* 2>/dev/null || echo "Aucun backup InfluxDB"
echo "=== Backup terminé ==="
