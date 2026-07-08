# Coolify-friendly image.
FROM python:3.11-slim

WORKDIR /app

# System deps: build-essential for eth-account / coincurve wheels; ffmpeg for
# yt-dlp audio extraction; gosu so the entrypoint can fix volume ownership as
# root then drop to the app user; curl for the platform container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ffmpeg gosu ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY src ./src
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Unprivileged app user (defense in depth). /data is the durable mount-point
# (ledger + ingest sessions), pre-created + owned so a fresh named volume
# inherits appuser ownership; the entrypoint additionally chowns it at boot.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

ENV PORT=8788 \
    CC_SESSION_DIR=/data/sessions \
    LEDGER_PATH=/data/ledger.db \
    HF_HOME=/data/hf \
    PYTHONUNBUFFERED=1

EXPOSE 8788

# The entrypoint starts as root only to chown the mounted volume, then
# `gosu appuser` runs the server. No app code executes as root.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Shell form so ${PORT} expands at runtime. --proxy-headers so the 402
# challenge advertises the real https:// resource URL behind Coolify/Traefik.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
