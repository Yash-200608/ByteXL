import logging
import re

from app.agent.language import LANGUAGES, Language
from app.config import get_settings
from app.llm.client import LLMUnavailable, get_llm

log = logging.getLogger(__name__)

END = r"(?![0-9A-Za-z])"
BASE_PATTERNS = [
    r"\*\*[^*\n]+\*\*",
    r"`[^`\n]+`",
    r"https?://\S+",
    r"[\w.\-]+\.(?:pdf|png|jpe?g)" + END,
    r"\b(?:Tab|Cap|Syp|Inj|Cream|Oint|Drops?|Sachet)\.?\s+[A-Z][\w\-]*(?:\s+[A-Z0-9][\w\-]*)*(?:\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|k)?)?",
    r"\((?!high\b|low\b|within\b|far\b|no reference\b|current\b|normal\b)[a-z][a-z +\-]*\)",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}" + END,
    r"\b\d{4}-\d{2}-\d{2}" + END,
    r"[½¼¾\d]+(?:-[½¼¾\d]+){2,3}" + END,
    r"\b\d+(?:[.,]\d+)?\s*(?:%|mg/dL|g/dL|mmol/L|µIU/mL|uIU/mL|ng/mL|pg/mL|U/L|mg|mcg|ml|mL|/cumm|/µL|lakh/cumm|days?|weeks?|wks?|months?)?" + END,
    r"\b(?:OD|BD|BID|TDS|TID|QID|QDS|SOS|PRN|HS|AC|PC|STAT|ABHA|ByteXL|PERRY|LOINC|FHIR)" + END,
]


def _lab_name_pattern() -> str:
    from app.normalize.labs import load_lab_reference

    names = sorted({r.canonical_name for r in load_lab_reference()}, key=len, reverse=True)
    return r"\b(?:" + "|".join(re.escape(n) for n in names) + r")" + END


_PROTECT = None


def protect_pattern() -> re.Pattern:
    global _PROTECT
    if _PROTECT is None:
        _PROTECT = re.compile("|".join(BASE_PATTERNS[:6] + [_lab_name_pattern()] + BASE_PATTERNS[6:]))
    return _PROTECT
PLACEHOLDER = re.compile(r"\[\[(\d+)\]\]")
BULLET = re.compile(r"^(\s*(?:[-*>]|\d+[.)])\s+)")


def target_name(lang: Language) -> str:
    return LANGUAGES[lang.code][0] if lang.code in LANGUAGES else lang.name


def _call(text: str, target: str) -> str:
    s = get_settings()
    messages = [{"role": "system", "content": f"Translate the text below to {target}."}, {"role": "user", "content": text}]
    return (get_llm().chat(s.translate_model, messages, num_predict=1024) or "").strip()


def to_english(text: str, lang: Language) -> str | None:
    if lang.code in ("en", "hinglish"):
        return text
    try:
        out = _call(text, "English")
    except LLMUnavailable as exc:
        log.info("translation to English unavailable: %s", exc)
        return None
    return out if out and re.search(r"[A-Za-z]", out) else None


def _protect(line: str, start: int) -> tuple[str, list[str]]:
    spans: list[str] = []

    def sub(m):
        spans.append(m.group(0))
        return f"[[{start + len(spans) - 1}]]"

    return protect_pattern().sub(sub, line), spans


def _has_words(masked: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", PLACEHOLDER.sub("", masked)))


def _script_ok(text: str, lang: Language) -> bool:
    if lang.code not in LANGUAGES:
        return True
    lo, hi = LANGUAGES[lang.code][2]
    letters = [c for c in PLACEHOLDER.sub("", text) if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters) >= 0.5


def _restore(translated: str, spans: dict[int, str]) -> str | None:
    found = [int(n) for n in PLACEHOLDER.findall(translated)]
    if sorted(found) != sorted(spans):
        return None
    if re.search(r"[0-9]", PLACEHOLDER.sub("", translated)):
        return None
    return PLACEHOLDER.sub(lambda m: spans[int(m.group(1))], translated)


def _translate_line(line: str, lang: Language, target: str) -> tuple[str, bool]:
    prefix = ""
    m = BULLET.match(line)
    if m:
        prefix, line = m.group(1), line[m.end():]
    masked, spans = _protect(line, 0)
    if not _has_words(masked):
        return prefix + line, True
    try:
        out = _call(masked, target)
    except LLMUnavailable:
        return prefix + line, False
    first = out.splitlines()[0] if out else ""
    restored = _restore(first, dict(enumerate(spans)))
    if restored is None or not _script_ok(first, lang):
        return prefix + line, False
    return prefix + restored, True


def from_english(text: str, lang: Language) -> tuple[str, float]:
    if lang.code in ("en", "hinglish") or not text.strip():
        return text, 1.0
    target = target_name(lang)
    lines = text.split("\n")
    masked_lines, spans, offset = [], {}, 0
    for line in lines:
        masked, found = _protect(line, offset)
        for i, s in enumerate(found):
            spans[offset + i] = s
        offset += len(found)
        masked_lines.append(masked)
    try:
        whole = _call("\n".join(masked_lines), target)
    except LLMUnavailable as exc:
        log.info("translation unavailable: %s", exc)
        return text, 0.0
    out_lines = whole.split("\n") if whole else []
    restored = _restore(whole, spans) if whole else None
    if restored is not None and len(out_lines) == len(lines) and all(
            _script_ok(o, lang) or not _has_words(m) for o, m in zip(out_lines, masked_lines)):
        return restored, 1.0
    done, ok, total = [], 0, 0
    for line, masked in zip(lines, masked_lines):
        if not _has_words(masked):
            done.append(line)
            continue
        total += 1
        t, good = _translate_line(line, lang, target)
        done.append(t)
        ok += good
    return "\n".join(done), ok / total if total else 1.0
