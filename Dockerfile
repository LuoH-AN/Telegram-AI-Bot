FROM python:3.12-slim

ARG BROWSER_HEADLESS=0
ARG INSTALL_SHELL_UTILS=1
ARG INSTALL_HEADFUL_SUPPORT=1
ARG INSTALL_CJK_FONTS=1

WORKDIR /app
ENV BROWSER_HEADLESS=${BROWSER_HEADLESS}

# Install runtime deps. Git is required for HF dataset git backend.
RUN set -eux; \
    apt-get update; \
    packages="git git-lfs"; \
    if [ "$INSTALL_SHELL_UTILS" = "1" ]; then \
        packages="$packages curl wget jq vim-tiny net-tools procps dnsutils iputils-ping"; \
    fi; \
    if [ "$INSTALL_HEADFUL_SUPPORT" = "1" ]; then \
        packages="$packages xvfb xauth"; \
    fi; \
    apt-get install -y --no-install-recommends $packages; \
    rm -rf /var/lib/apt/lists/*

# Create shell working directory and runtime_skills directory
RUN mkdir -p /tmp/shell /app/runtime_skills

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional Chinese fonts for page rendering / screenshots.
RUN set -eux; \
    if [ "$INSTALL_CJK_FONTS" = "1" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends fonts-noto-cjk; \
        rm -rf /var/lib/apt/lists/*; \
    fi

# Copy application code
COPY main.py start_bots.sh hf_dataset_store.py ./
COPY platforms/ ./platforms/
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

# Health check ports (Telegram / Discord / WeChat)
EXPOSE 7860 7861 7862

# Unified Python launcher:
# - TELEGRAM_BOT_TOKEN set => Telegram starts
# - DISCORD_BOT_TOKEN set  => Discord starts
# - WECHAT_ENABLED=1       => WeChat starts
# Override defaults via TELEGRAM_PORT / DISCORD_PORT / WECHAT_PORT env vars.
CMD ["python", "/app/main.py"]
