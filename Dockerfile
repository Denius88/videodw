FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY TelegramBot ./TelegramBot
COPY WebSite/backend ./WebSite/backend

RUN mkdir -p "WebSite/backend/downloads" "TelegramBot/temp_downloads"

EXPOSE 8000

CMD ["uvicorn", "WebSite.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]