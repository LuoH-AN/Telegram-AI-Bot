FROM python:3.12-slim

WORKDIR /app
ENV BROWSER_HEADLESS=0

# Install useful CLI tools for the shell tool
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq vim-tiny net-tools procps dnsutils iputils-ping xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

# Create shell working directory
RUN mkdir -p /tmp/shell

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright full Chromium browser + system dependencies + Chinese fonts
RUN playwright install --with-deps chromium
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY bot.py .
COPY discord_bot.py .
COPY start_bots.sh .
COPY hf_dataset_store.py .
COPY config/ ./config/
COPY database/ ./database/
COPY cache/ ./cache/
COPY services/ ./services/
COPY ai/ ./ai/
COPY handlers/ ./handlers/
COPY tools/ ./tools/
COPY utils/ ./utils/
COPY web/ ./web/
COPY static/ ./static/

# Health check ports (Telegram / Discord)
EXPOSE 7860 7861

# Auto-start platforms by configured tokens:
# - TELEGRAM_BOT_TOKEN set => Telegram starts
# - DISCORD_BOT_TOKEN set  => Discord starts
# - both set => both start
# Override defaults via TELEGRAM_PORT / DISCORD_PORT env vars.
CMD ["/bin/bash", "-lc", "bash /app/start_bots.sh"]
