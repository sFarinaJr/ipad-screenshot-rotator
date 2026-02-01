# Use uma imagem base Python recente (suporta Playwright bem)
FROM python:3.12-slim-bookworm

# Instala dependências do sistema necessárias para Playwright/Chromium
# (isso roda como root durante o build, sem pedir senha)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libappindicator3-1 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgtk-3-0 \
    libnspr4 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia e instala pacotes Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala os browsers do Playwright (agora com dependências já instaladas)
RUN playwright install --with-deps chromium

# Copia o resto do código
COPY . .

# Expõe a porta (Render usa variável PORT)
ENV PORT=5000

# Comando para rodar a app (usa gunicorn para produção, ou python direto)
CMD ["python", "app.py"]
