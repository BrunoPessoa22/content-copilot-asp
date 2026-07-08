FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY demo ./demo

ENV PORT=8787 \
    CC_SESSION_DIR=/tmp/content-copilot \
    PYTHONUNBUFFERED=1

EXPOSE 8787

CMD ["python", "-m", "src.server", "--transport", "http", "--port", "8787"]
