from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "bytexl"
    mongo_timeout_ms: int = 1500
    store_backend: str = "auto"
    data_dir: Path = ROOT / "data"

    ollama_url: str = "http://localhost:11434"
    vision_model: str = "qwen2.5vl:7b"
    vision_fallback_model: str = "qwen2.5vl:3b"
    text_model: str = "qwen2.5:7b"
    extraction_mode: str = "vision"
    llm_timeout_s: float = 900.0
    llm_num_ctx: int = 8192
    llm_temperature: float = 0.0
    vision_max_side: int = 1280
    vision_slow_threshold_s: float = 90.0

    ocr_lang: str = "en"
    ocr_det_model: str = "PP-OCRv5_mobile_det"
    ocr_rec_model: str = "PP-OCRv5_mobile_rec"
    ocr_hindi: bool = False
    pdf_dpi: int = 200
    min_page_chars: int = 30

    conf_high: float = 0.85
    conf_low: float = 0.60
    handwritten_ocr_conf: float = 0.90
    lab_alias_min_score: float = 90.0
    medicine_min_score: float = 88.0
    box_match_min_score: float = 80.0
    active_med_default_days: int = 90
    reconcile_as_of: str = "latest_document"
    summary_on_upload: bool = True

    api_url: str = "http://localhost:8000"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def store_dir(self) -> Path:
        return self.data_dir / "store"

    @property
    def reference_dir(self) -> Path:
        return ROOT / "data" / "reference"

    @property
    def prompts_dir(self) -> Path:
        return ROOT / "app" / "extract" / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
