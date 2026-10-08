import logging

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="ByteXL", version="0.1.0", description="Local-first personal health copilot")
app.include_router(health_router)
app.include_router(api_router)
