# Build from the repository root:  docker build -f api/Dockerfile -t bazar-pulse-api .
FROM python:3.12-slim

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api/ api/
COPY data/status.json data/status.json
COPY data/forecasts/latest.json data/forecasts/latest.json
COPY data/clean/prices.parquet data/clean/prices.parquet
COPY data/monitoring/ data/monitoring/

RUN useradd --create-home app && chown -R app /app
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
