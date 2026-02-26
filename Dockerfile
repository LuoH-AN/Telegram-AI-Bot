FROM python:3.12-slim

WORKDIR /app

# Install useful CLI tools for the shell tool
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq vim-tiny net-tools procps dnsutils iputils-ping \
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

# Health check port
EXPOSE 7860

# Run the bot
CMD ["python", "bot.py"]
