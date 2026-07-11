FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg build-essential python3-dev libsndfile1 curl ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*

# YouTube'ning "n" signature challenge'ini yechish uchun yt-dlp'ga JS runtime
# kerak (https://github.com/yt-dlp/yt-dlp/wiki/EJS) — bo'lmasa faqat
# storyboard (rasm) formatlar qoladi, haqiqiy video/audio format topilmaydi.
# Node.js'ni rasmiy nodejs.org'dan aniq versiya + SHA256 tekshiruvi bilan
# o'rnatamiz (curl-to-shell emas — faqat yuklab olish + tekshirish + ochish).
ARG NODE_VERSION=22.23.1
RUN cd /tmp \
    && curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.xz \
    && curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt \
    && grep "node-v${NODE_VERSION}-linux-arm64.tar.xz" SHASUMS256.txt | sha256sum -c - \
    && tar -xJf node-v${NODE_VERSION}-linux-arm64.tar.xz -C /usr/local --strip-components=1 \
    && rm -f node-v${NODE_VERSION}-linux-arm64.tar.xz SHASUMS256.txt

WORKDIR /app/backend

COPY backend/requirements.txt backend/requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Aarch64'da standart "pip install torch" CUDA versiyasini tortib olishi
# mumkin — bu VM'da GPU yo'q, shuning uchun CPU-only index'dan o'rnatamiz.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements-ai.txt

COPY backend/ .
COPY frontend/ ../frontend/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
