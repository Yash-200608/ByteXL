import logging
import time
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.extract.lift import lift
from app.extract.llm_schemas import LLM_SCHEMAS
from app.extract.rules import rules_extract
from app.ingest.models import PageData
from app.llm.client import LLMUnavailable, get_llm
from app.schemas import ExtractionMeta

log = logging.getLogger(__name__)
MAX_VISION_PAGES = 2


def load_prompt(name: str) -> str:
    return (get_settings().prompts_dir / f"{name}.txt").read_text()


def page_text(pages: list[PageData]) -> str:
    if len(pages) == 1:
        return pages[0].text
    return "\n".join(f"--- page {p.index + 1} ---\n{p.text}" for p in pages)


def _check(doc_type: str):
    def check(obj):
        problems = []
        if doc_type == "lab_report" and not obj.tests:
            problems.append("tests: list is empty; include every test row with a result")
        if doc_type == "prescription" and not obj.medicines:
            problems.append("medicines: list is empty; include every prescribed medicine")
        return problems

    return check


def _run_llm(doc_type: str, mode: str, pages: list[PageData], text: str):
    s = get_settings()
    schema = LLM_SCHEMAS[doc_type]
    prompt = load_prompt(doc_type).replace("{ocr_text}", text[:6000])
    system = load_prompt("system")
    llm = get_llm()
    if mode == "vision":
        images = [Image.open(Path(p.image_path)) for p in pages[:MAX_VISION_PAGES]]
        return llm.structured(s.vision_model, schema, system, prompt, images=images, extra_check=_check(doc_type))
    return llm.structured(s.text_model, schema, system, prompt, extra_check=_check(doc_type))


def extract(doc_type: str, pages: list[PageData], mode: str | None = None):
    s = get_settings()
    mode = mode or s.extraction_mode
    text = page_text(pages)
    start = time.time()
    errors: list[str] = []
    modes = [] if mode == "rules" else [mode] + (["text"] if mode == "vision" else [])
    for m in modes:
        try:
            res = _run_llm(doc_type, m, pages, text)
        except LLMUnavailable as exc:
            log.warning("LLM %s extraction unavailable: %s", m, exc)
            errors.append(f"{m}: {exc}")
            continue
        errors.extend(res.errors)
        if res.obj is not None:
            meta = ExtractionMeta(
                model=res.model,
                attempts=res.attempts,
                method=m,
                validation_errors=errors,
                low_confidence=False,
                duration_s=round(time.time() - start, 2),
            )
            return lift(doc_type, res.obj, pages, meta)
        break
    raw = rules_extract(doc_type, text)
    meta = ExtractionMeta(
        model="rules",
        attempts=0,
        method="rules",
        validation_errors=errors,
        low_confidence=True,
        duration_s=round(time.time() - start, 2),
    )
    return lift(doc_type, raw, pages, meta)
