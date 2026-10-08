import logging
import os
import re
import threading

import numpy as np
from PIL import Image

from app.config import get_settings
from app.ingest.models import OcrLine

log = logging.getLogger(__name__)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

_engines: dict[str, object] = {}
_lock = threading.Lock()
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class OcrUnavailable(RuntimeError):
    pass


def _engine(lang: str):
    with _lock:
        if lang not in _engines:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise OcrUnavailable("paddleocr is not installed") from exc
            s = get_settings()
            kwargs = {"lang": lang}
            if lang == s.ocr_lang and s.ocr_det_model:
                kwargs = {"text_detection_model_name": s.ocr_det_model, "text_recognition_model_name": s.ocr_rec_model}
            _engines[lang] = PaddleOCR(
                **kwargs,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
        return _engines[lang]


def _run(lang: str, arr: np.ndarray) -> list[OcrLine]:
    engine = _engine(lang)
    with _lock:
        results = engine.predict(arr)
    lines: list[OcrLine] = []
    for res in results:
        texts = res["rec_texts"]
        scores = res["rec_scores"]
        boxes = res["rec_boxes"]
        for text, score, box in zip(texts, scores, boxes):
            text = str(text).strip()
            if not text:
                continue
            x0, y0, x1, y1 = (float(v) for v in list(box)[:4])
            lines.append(OcrLine(text=text, confidence=round(float(score), 4), box=[x0, y0, x1, y1]))
    return lines


def _overlap(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def ocr_image(image: Image.Image) -> list[OcrLine]:
    s = get_settings()
    arr = np.array(image.convert("RGB"))[:, :, ::-1].copy()
    lines = _run(s.ocr_lang, arr)
    if s.ocr_hindi:
        try:
            hindi = [l for l in _run("hi", arr) if DEVANAGARI.search(l.text)]
            for h in hindi:
                clash = [l for l in lines if _overlap(h.box, l.box) > 0.5]
                if not clash or all(c.confidence < h.confidence for c in clash):
                    lines = [l for l in lines if l not in clash] + [h]
        except Exception as exc:
            log.warning("Hindi OCR unavailable: %s", exc)
    return lines
