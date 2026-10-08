import io
import logging
import threading
import time
import wave

from app.config import get_settings

log = logging.getLogger(__name__)


class SpeechUnavailable(RuntimeError):
    pass


_model = None
_lock = threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechUnavailable("Local speech recognition is not installed (pip install faster-whisper).") from exc
            s = get_settings()
            try:
                _model = WhisperModel(s.stt_model, device=s.stt_device, compute_type=s.stt_compute_type)
            except Exception as exc:
                log.exception("could not load Whisper model %s", s.stt_model)
                raise SpeechUnavailable(f"The speech model '{s.stt_model}' could not be loaded.") from exc
        return _model


def set_model(model) -> None:
    global _model
    with _lock:
        _model = model


def wav_seconds(audio: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return None


PROMPT_TESTS = ["HbA1c", "haemoglobin", "TSH", "creatinine", "LDL cholesterol", "HDL", "triglycerides", "SGPT", "SGOT",
                "vitamin D", "vitamin B12", "platelet count", "fasting blood sugar", "ESR", "CRP", "urine routine"]


def vocabulary_prompt(personal: list[str] | None = None, limit: int = 40) -> str:
    from app.normalize.medicines import load_medicines

    personal = list(dict.fromkeys(t for t in personal or [] if t))[:limit]
    brands = [b for b in sorted({m.brand for m in load_medicines().values()}) if b not in personal][: max(0, limit - len(personal))]
    tests = [t for t in PROMPT_TESTS if t not in personal]
    return ("A patient in India asks PERRY about their ByteXL medical records: lab reports, prescriptions, discharge summary. "
            f"Their records mention: {', '.join(personal)}. " if personal else
            "A patient in India asks PERRY about their ByteXL medical records: lab reports, prescriptions, discharge summary. ") + \
        f"Tests: {', '.join(tests)}. Medicines: {', '.join(brands)}."


COMMON_WORDS = {
    "should", "would", "could", "taking", "records", "medicines", "medicine", "report", "reports", "latest", "results", "result",
    "about", "there", "their", "which", "where", "these", "those", "tablet", "tablets", "doctor", "changed", "change", "please",
    "summary", "explain", "today", "night", "morning", "before", "after", "levels", "level", "values", "value", "anything",
}


def correct_terms(text: str, vocabulary: list[str] | None, threshold: float = 65.0) -> tuple[str, list[dict]]:
    import re

    from rapidfuzz import fuzz

    terms = [t for t in vocabulary or [] if re.fullmatch(r"[A-Za-z][A-Za-z\-]{3,}", t)]
    if not terms:
        return text, []
    fixes = []

    def fix(m):
        word = m.group(0)
        low = word.lower()
        if len(low) < 5 or low in COMMON_WORDS or any(low == t.lower() for t in terms):
            return word
        scored = sorted(((fuzz.ratio(low, t.lower()), t) for t in terms if t[0].lower() == low[0]), reverse=True)
        if not scored or scored[0][0] < threshold or (len(scored) > 1 and scored[1][0] >= scored[0][0] - 5):
            return word
        fixes.append({"heard": word, "corrected": scored[0][1]})
        return scored[0][1]

    return re.sub(r"[A-Za-z][A-Za-z\-]+", fix, text), fixes


def transcribe(audio: bytes, vocabulary: list[str] | None = None) -> dict:
    start = time.time()
    model = get_model()
    prompt = vocabulary_prompt(vocabulary) if get_settings().stt_vocab_prompt else None
    segments, info = model.transcribe(io.BytesIO(audio), vad_filter=True, beam_size=1, initial_prompt=prompt)
    raw = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip()).strip()
    text, fixes = correct_terms(raw, vocabulary)
    return {
        "text": text,
        "raw_text": raw,
        "corrections": fixes,
        "language": getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
        "duration_s": round(time.time() - start, 2),
    }
