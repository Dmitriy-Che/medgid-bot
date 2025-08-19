# Используем Python 3.10 slim-образ
FROM python:3.10-slim

# Устанавливаем системные зависимости для Playwright и Chromium
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    wget \
    curl \
    unzip \
    fonts-liberation \
    fonts-unifont \
    fonts-ubuntu \
    libasound2 \
    libxshmfence1 \
    libdrm2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости проекта
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ставим playwright и chromium (без --with-deps, так как deps мы сами доставили)
RUN pip install playwright
RUN playwright install chromium

# Копируем все файлы бота
COPY . .

# Запускаем бота
CMD ["python", "mgbot_ii15.py"]
