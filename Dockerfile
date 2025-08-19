FROM python:3.10-slim

# Устанавливаем зависимости для playwright
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libdbus-1-3 \
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
    wget gnupg && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости проекта
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры playwright
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "mgbot_ii15.py"]
