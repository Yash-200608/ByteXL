#!/bin/sh
set -e
mkdir -p "$DATA_DIR"
if [ ! -d "$DATA_DIR/store" ]; then
  cp -r /app/deploy/demo_data/. "$DATA_DIR/"
fi
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 &
exec streamlit run ui/app.py --server.port "${PORT:-7860}" --server.address 0.0.0.0 --server.headless true \
  --server.enableXsrfProtection false --server.enableCORS false --browser.gatherUsageStats false
