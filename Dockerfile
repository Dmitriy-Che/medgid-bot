# Используем официальный Python-образ
FROM python:3.11-slim

# Установка системных зависимостей для Playwright + Chromium
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libssl3 \
    fonts-liberation \
    fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python-зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ставим Playwright и Chromium с правильными флагами
RUN playwright install chromium --with-deps

# Устанавливаем правильные переменные среды для Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV CHROMIUM_CHANNEL="stable"

# Копируем весь проект
COPY . .

# Запускаем твоего бота
CMD ["python", "mgbot_ii15.py"]
