FROM python:3.11-slim

# Установка системных зависимостей для Playwright
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl unzip \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libatspi2.0-0 libwayland-client0 \
    libwayland-egl1 libwayland-server0 libxcursor1 \
    libxinerama1 libpango-1.0-0 libpangocairo-1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка Playwright + Chromium
RUN apt-get update && apt-get install -y \
    libgbm1 \
    libasound2 \
    fonts-unifont \
    fonts-ubuntu-font-family-console \
    && playwright install chromium

# Копируем весь проект
COPY . .

# Запуск бота
CMD ["python", "bot.py"]
