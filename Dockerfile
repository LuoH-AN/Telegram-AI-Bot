FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py .
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
