FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    curl gnupg lsb-release cron ca-certificates \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] \
       https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Extraire ./influx avec le chemin exact
RUN curl -sL https://dl.influxdata.com/influxdb/releases/influxdb2-client-2.8.0-linux-amd64.tar.gz \
    | tar xz -C /usr/local/bin --strip-components=0 ./influx \
    && chmod +x /usr/local/bin/influx

RUN echo "0 * * * * /backup/backup.sh >> /var/log/backup.log 2>&1" \
    > /etc/cron.d/stopmnt-backup \
    && chmod 0644 /etc/cron.d/stopmnt-backup \
    && crontab /etc/cron.d/stopmnt-backup

COPY backup.sh /backup/backup.sh
RUN chmod +x /backup/backup.sh
RUN touch /var/log/backup.log

CMD ["sh", "-c", "export -p | grep -E ' (POSTGRES|INFLUXDB)_' > /etc/backup.env; exec cron -f"]
