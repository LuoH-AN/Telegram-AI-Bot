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
COPY main.py web_app.py ./
COPY telegram_bot/ ./telegram_bot/
COPY launcher/ ./launcher/
COPY config/ ./config/
COPY core/ ./core/
COPY database/ ./database/
COPY cache/ ./cache/
COPY services/ ./services/
COPY ai/ ./ai/
COPY platforms/ ./platforms/
COPY plugins/ ./plugins/
COPY openapi_tools/ ./openapi_tools/
COPY utils/ ./utils/
COPY static/ ./static/

# Health check port (Telegram)
EXPOSE 7860

# Python launcher: TELEGRAM_BOT_TOKEN set => Telegram starts.
# Override the default port via TELEGRAM_PORT.
CMD ["python", "/app/main.py"]
