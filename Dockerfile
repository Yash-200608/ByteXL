FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN chmod +x deploy/start.sh && mkdir -p /app/data && chown user /app/data

USER user
ENV HOME=/home/user \
    PORT=7860 \
    DATA_DIR=/app/data \
    STORE_BACKEND=json \
    OLLAMA_URL=http://127.0.0.1:1 \
    EXTRACTION_MODE=rules \
    SUMMARY_MODE=template \
    PERRY_MODE=template \
    PERRY_INDIC_MODE=english \
    API_URL=http://127.0.0.1:8000 \
    DEMO_NOTICE="Cloud demo: this server has no GPU, so PERRY's local AI models are replaced by its rule-based fallbacks. Synthetic demo data only — please don't upload real health records."

EXPOSE 7860
CMD ["deploy/start.sh"]
