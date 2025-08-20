# Используем официальный Python-образ
FROM python:3.11-slim

# Установка системных зависимостей (только базовые)
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python-зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запускаем твоего бота
CMD ["python", "mgbot_ii15.py"]
