FROM python:3.12-slim

WORKDIR /app

# Install runtime deps. Git is required for hot update support.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py ./
COPY entrypoints/ ./entrypoints/
COPY adapters/ ./adapters/
COPY application/ ./application/
COPY domain/ ./domain/
COPY infrastructure/ ./infrastructure/
COPY shared/ ./shared/

# Public web / health probe port
EXPOSE 7860

# Python launcher: TELEGRAM_BOT_TOKEN set => Telegram starts.
# Override the default port via TELEGRAM_PORT.
CMD ["python", "/app/main.py"]
