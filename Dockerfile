FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg build-essential python3-dev libsndfile1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
