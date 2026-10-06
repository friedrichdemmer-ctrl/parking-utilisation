FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py brand.py requests_store.py legal_pages.py legal.json collector.py collector_daemon.py import_historical.py recluster.py apply_capacity_overrides.py scraper_daemon.py feed_health.py utilisation_report.py report_template.html trends_report.py trends_template.html competitive.py competitive_links.py yield_report.py yield_template.html garage_types.py garage_links.py city_briefing.py garage_prices.py revenue_model.py site_api.py alerts.py reports_job.py sync_archive.py archive_sync_daemon.py entrypoint.sh ./
COPY capacity_overrides/ ./capacity_overrides/
COPY garage_links/ ./garage_links/
COPY site/ ./site/
COPY competitive/ ./competitive/
COPY garage_prices/ ./garage_prices/
COPY scrapers/ ./scrapers/
COPY annotations/ ./annotations/
RUN chmod +x entrypoint.sh

ENV PARKING_DB_PATH=/data/parking.db
ENV PARKING_ARCHIVE_PATH=/data/parking-data-archive

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
