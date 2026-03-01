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
RUN camoufox fetch

# Install Playwright full Chromium browser + system dependencies + Chinese fonts
RUN playwright install --with-deps chromium
RUN playwright install --with-deps firefox
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY bot.py .
COPY discord_bot.py .
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

# Run Telegram + Discord in one container with separate PORT values.
# Override defaults via TELEGRAM_PORT / DISCORD_PORT env vars.
CMD ["/bin/bash", "-lc", "set -euo pipefail; TELEGRAM_PORT=\"${TELEGRAM_PORT:-7860}\"; DISCORD_PORT=\"${DISCORD_PORT:-7861}\"; PORT=\"$TELEGRAM_PORT\" xvfb-run -a python bot.py & tg_pid=$!; PORT=\"$DISCORD_PORT\" xvfb-run -a python discord_bot.py & dc_pid=$!; term(){ kill -TERM \"$tg_pid\" \"$dc_pid\" 2>/dev/null || true; wait \"$tg_pid\" \"$dc_pid\" 2>/dev/null || true; }; trap term INT TERM; wait -n \"$tg_pid\" \"$dc_pid\"; status=$?; term; exit $status"]
