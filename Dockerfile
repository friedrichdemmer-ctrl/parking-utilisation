FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py collector.py collector_daemon.py import_historical.py recluster.py apply_capacity_overrides.py entrypoint.sh ./
COPY capacity_overrides/ ./capacity_overrides/
RUN chmod +x entrypoint.sh

ENV PARKING_DB_PATH=/data/parking.db
ENV PARKING_ARCHIVE_PATH=/data/parking-data-archive

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
