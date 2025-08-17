FROM python:3.11-slim

# Chromium deps
RUN apt-get update && apt-get install -y     wget     libnss3     libatk1.0-0     libatk-bridge2.0-0     libdrm2     libxkbcommon0     libgbm1     libasound2     libxshmfence1     libx11-xcb1     libxcomposite1     libxdamage1     libxext6     libxfixes3     libxrandr2     libxtst6     libgtk-3-0     libpangocairo-1.0-0     libx11-6     libxcb1     libxrender1     libpango-1.0-0     libcairo2     libatspi2.0-0     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "mgbot_ii15.py"]
