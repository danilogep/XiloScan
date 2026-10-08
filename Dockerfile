# XiloScan — imagem única para o Railway: builda o frontend (PWA) e serve
# API + imagens + SPA na mesma origem (necessário para o service worker do PWA).

# ─────────────────────────────── 1) build do frontend (Vite) ───────────────
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# chama a API na mesma origem (sem host separado)
ENV VITE_API_URL=""
RUN npm run build

# ─────────────────────────────── 2) backend + runtime ──────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# libs de sistema para opencv/faiss
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# torch/faiss na variante CPU (imagem menor; Railway roda em CPU)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
      -r backend/requirements.txt

# código, dados e artefatos do modelo
COPY backend/ backend/
COPY data/ data/
# o dist do frontend construído no estágio anterior
COPY --from=frontend /app/frontend/dist frontend/dist

ENV XILOSCAN_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
# Railway injeta $PORT
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
