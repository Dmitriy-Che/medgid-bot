FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости для Playwright и шрифты
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    fonts-unifont \
    fonts-dejavu-core \
    libnss3 \
    libxss1 \
    libasound2 \
    libxshmfence1 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем только Chromium без --with-deps
RUN playwright install chromium

COPY . .

CMD ["python", "mgbot_ii15.py"]
