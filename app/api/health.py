import importlib.util

from fastapi import APIRouter

from app.config import get_settings
from app.llm.client import get_llm
from app.store import get_repository

router = APIRouter()


def _has(models: list[str], name: str) -> bool:
    base = name if ":" in name else f"{name}:latest"
    return name in models or base in models


@router.get("/health")
def health():
    s = get_settings()
    repo = get_repository()
    llm = get_llm()
    up = llm.is_up()
    installed = llm.models() if up else []
    return {
        "status": "ok",
        "store": {"backend": repo.backend, "ok": repo.ping()},
        "ollama": {"reachable": up, "url": s.ollama_url},
        "models": {
            "vision": s.vision_model,
            "vision_available": _has(installed, s.vision_model),
            "vision_fallback": s.vision_fallback_model,
            "vision_fallback_available": _has(installed, s.vision_fallback_model),
            "text": s.text_model,
            "text_available": _has(installed, s.text_model),
            "translate": s.translate_model,
            "translate_available": _has(installed, s.translate_model),
            "installed": installed,
        },
        "ocr": {"paddleocr": importlib.util.find_spec("paddleocr") is not None, "pymupdf": importlib.util.find_spec("pymupdf") is not None},
        "extraction_mode": s.extraction_mode,
        "speech": {"local_stt": importlib.util.find_spec("faster_whisper") is not None, "stt_model": s.stt_model},
    }
