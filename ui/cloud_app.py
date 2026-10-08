import os
import shutil
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

CLOUD = {
    "STORE_BACKEND": "json",
    "DATA_DIR": str(ROOT / "data"),
    "OLLAMA_URL": "http://127.0.0.1:1",
    "EXTRACTION_MODE": "rules",
    "SUMMARY_MODE": "template",
    "PERRY_MODE": "template",
    "PERRY_INDIC_MODE": "english",
    "API_URL": "http://127.0.0.1:8000",
    "DEMO_NOTICE": "Cloud demo: this server has no GPU, so PERRY's local AI models are replaced by its rule-based fallbacks, "
                   "and photo OCR is off (text PDFs work). Synthetic demo data only — please don't upload real health records.",
}
for key, value in CLOUD.items():
    os.environ.setdefault(key, value)

import httpx
import streamlit as st
import uvicorn

st.set_page_config(page_title="PERRY · Your Personal Health Assistant", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")


@st.cache_resource(show_spinner=False)
def start_api():
    data = Path(os.environ["DATA_DIR"])
    if not (data / "store").exists():
        shutil.copytree(ROOT / "deploy" / "demo_data", data, dirs_exist_ok=True)
    from app.api.main import app

    url = urlparse(os.environ["API_URL"])
    server = uvicorn.Server(uvicorn.Config(app, host=url.hostname, port=url.port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(120):
        try:
            httpx.get(f"{os.environ['API_URL']}/health", timeout=2)
            break
        except httpx.HTTPError:
            time.sleep(0.5)
    return server


with st.spinner("Waking PERRY up…"):
    start_api()

from common import NAV

pages = [st.Page(path, title=label, icon=icon, default=(i == 0)) for i, (path, label, icon) in enumerate(NAV)]
st.navigation(pages, position="hidden").run()
