FROM python:3.12-slim

ARG REPO_URL="https://github.com/LuoH-AN/Telegram-AI-Bot.git"
ARG REPO_BRANCH="main"

ENV HOT_UPDATE_REPO_URL="${REPO_URL}"
ENV HOT_UPDATE_BRANCH="${REPO_BRANCH}"
ENV APP_DIR="/opt/telegram-ai-bot"

WORKDIR ${APP_DIR}

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

RUN test -f "${APP_DIR}/entrypoints/main.py" && python -m py_compile "${APP_DIR}/entrypoints/main.py"

# Public web / health probe port
EXPOSE 7860

# Python launcher: TELEGRAM_BOT_TOKEN set => Telegram starts.
# Override the default port via TELEGRAM_PORT.
CMD ["python", "-m", "entrypoints.main"]
