FROM python:3.12-slim

WORKDIR /app

# Install runtime deps. Git is required for HF dataset git backend.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git git-lfs ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py ./
COPY platforms/ ./platforms/
COPY launcher/ ./launcher/
COPY config/ ./config/
COPY core/ ./core/
COPY database/ ./database/
COPY cache/ ./cache/
COPY services/ ./services/
COPY ai/ ./ai/
COPY handlers/ ./handlers/
COPY tools/ ./tools/
COPY utils/ ./utils/
COPY web/ ./web/
COPY static/ ./static/

# Health check ports (Telegram / Discord / WeChat)
EXPOSE 7860 7861 7862

# Unified Python launcher:
# - TELEGRAM_BOT_TOKEN set => Telegram starts
# - DISCORD_BOT_TOKEN set  => Discord starts
# - WECHAT_ENABLED=1       => WeChat starts
# Override defaults via TELEGRAM_PORT / DISCORD_PORT / WECHAT_PORT env vars.
CMD ["python", "/app/main.py"]
