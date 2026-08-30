# ---- Stage 1: build web assets -------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/ .
RUN npm run build

# ---- Stage 2: runtime (NVIDIA CUDA runtime with Python) -----------------------
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04 AS runtime

# Install Python 3.12 + pip
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*

# Symlink python3.12 -> python3
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

WORKDIR /app

ENV PYTHONPATH=/app/backend \
    HIVESTACK_CONFIG_DIR=/config \
    HIVESTACK_DATA_DIR=/data \
    HIVESTACK_MODELS_DIR=/models \
    HIVESTACK_EMBED_CACHE=/opt/hivestack-models/embed \
    HIVESTACK_IN_CONTAINER=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r /app/backend/requirements.txt

# pre-cache the offline embedding model so RAG works with zero network at runtime
RUN python3 -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/opt/hivestack-models/embed')" \
    && echo "[hivestack] embed model cached"

COPY backend/ /app/backend/
COPY scripts/backup.py /app/scripts/backup.py
COPY --from=web /web/dist /app/web/dist
COPY docker/entrypoint.sh /usr/local/bin/hivestack-entrypoint
COPY docker/maintenance.sh /usr/local/bin/hivestack-maintenance
RUN chmod +x /usr/local/bin/hivestack-entrypoint /usr/local/bin/hivestack-maintenance

EXPOSE 8080
VOLUME ["/config", "/data", "/models"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4).status == 200 else 1)"

ENTRYPOINT ["hivestack-entrypoint"]