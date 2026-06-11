FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt gunicorn

COPY . .

RUN chmod +x /app/docker/entrypoint.sh /app/docker/scheduler-loop.sh \
    && useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data/backups/nitrokey /app/data/backups/f5 /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8010

ENTRYPOINT ["/app/docker/entrypoint.sh"]
