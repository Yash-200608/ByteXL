import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import streamlit.components.v1 as components

SPEECH_LANG = {
    "en": "en-IN", "hinglish": "en-IN", "hi": "hi-IN", "mr": "mr-IN", "bn": "bn-IN", "te": "te-IN", "ta": "ta-IN",
    "gu": "gu-IN", "ur": "ur-IN", "kn": "kn-IN", "or": "or-IN", "ml": "ml-IN", "pa": "pa-IN",
}
RECOGNITION_LANGS = {
    "English": "en-IN", "हिंदी": "hi-IN", "বাংলা": "bn-IN", "मराठी": "mr-IN", "తెలుగు": "te-IN", "தமிழ்": "ta-IN",
    "ગુજરાતી": "gu-IN", "اردو": "ur-IN", "ಕನ್ನಡ": "kn-IN", "ଓଡ଼ିଆ": "or-IN", "മലയാളം": "ml-IN", "ਪੰਜਾਬੀ": "pa-IN",
}
INDIAN_VOICE_NAMES = {
    "neerja", "prabhat", "heera", "ravi", "kalpana", "hemant", "swara", "madhur", "aarav", "aashi", "ananya", "kavya", "kunal",
    "rehaan", "tanishaa", "nabanita", "bashkar", "pallavi", "valluvar", "shruti", "mohan", "gagan", "sapna", "midhun",
    "sobhana", "aarohi", "manohar", "dhwani", "niranjan", "sukanya", "subhasini", "gul", "salman", "uzma", "asad", "vaani",
}
SAMPLE = {
    "en": "Hi, I'm PERRY. Your latest HbA1c was 6.6%, according to your lab report dated 20 Sep 2024.",
    "hi": "नमस्ते, मैं PERRY हूं। मैं आपके हेल्थ रिकॉर्ड समझने में मदद करता हूं।",
}
MAX_SPEECH_CHARS = 1200
FILENAME = re.compile(r"\S+\.(?:pdf|png|jpe?g)\b", re.I)
NOTE = re.compile(r"^_?\(.*\)_?$")
MONTHS = {m: date(2000, i, 1).strftime("%B") for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
UNITS = [
    (r"(?:µ|u|micro)IU/mL", "micro international units per millilitre"), (r"mg/dL", "milligrams per decilitre"),
    (r"g/dL", "grams per decilitre"), (r"mmol/L", "millimoles per litre"), (r"ng/mL", "nanograms per millilitre"),
    (r"pg/mL", "picograms per millilitre"), (r"U/L", "units per litre"), (r"lakh/cumm", "lakh per cubic millimetre"),
    (r"/cumm", "per cubic millimetre"), (r"/µL", "per microlitre"), (r"mm/h", "millimetres per hour"),
]
SPOKEN = [
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: _iso_spoken(m)),
    (r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", lambda m: f"{int(m.group(1))} {MONTHS[m.group(2)]}"),
    (r"\bHbA1c\b", "H b A 1 c"), (r"\bTab\.?\s", "Tablet "), (r"\bCap\.?\s", "Capsule "), (r"\bSyp\.?\s", "Syrup "),
    (r"\bInj\.?\s", "Injection "), (r"\b(OD|BD|TDS|QID|HS|AC|PC)\b", lambda m: " ".join(m.group(1))),
    (r"\bx\s*(\d+)\s*(?:wks?|weeks?)\b", r"for \1 weeks"), (r"\bx\s*(\d+)\s*(days?|months?)\b", r"for \1 \2"),
    (r"\b([0-9½]+)-([0-9½]+)-([0-9½]+)\b", r"\1, \2, \3"), (r"(\d)\s*%", r"\1 percent"),
]


def _iso_spoken(m) -> str:
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return m.group(0)
    return f"{d.day} {d.strftime('%B')} {d.year}"


def pronounce(line: str) -> str:
    for pattern, spoken in UNITS:
        line = re.sub(rf"(?<=[\d\s]){pattern}(?![A-Za-z])", " " + spoken, line)
    for pattern, spoken in SPOKEN:
        line = re.sub(pattern, spoken, line)
    return line


def clean_for_speech(markdown: str) -> str:
    lines = []
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line or NOTE.match(line):
            continue
        line = re.sub(r"^(?:[-*>]\s*)+", "", line)
        line = FILENAME.sub("", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", line)
        line = line.replace("→", " to ").replace("·", ", ").replace("—", ", ")
        line = "".join(c for c in line if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co") and c not in "️‍")
        line = pronounce(line)
        line = re.sub(r"\s*,\s*(,\s*)+", ", ", line)
        line = re.sub(r"\s+", " ", line)
        line = re.sub(r"\s+([,.;:])", r"\1", line).strip(" ,")
        if not line:
            continue
        if line[-1] not in ".!?:;।۔":
            line += "."
        lines.append(line)
    text = " ".join(lines)
    if len(text) > MAX_SPEECH_CHARS:
        cut = text[:MAX_SPEECH_CHARS]
        end = max(cut.rfind(". "), cut.rfind("। "), cut.rfind("? "))
        text = cut[: end + 1] if end > 200 else cut
    return text


def _norm_lang(lang: str) -> str:
    return (lang or "").replace("_", "-").lower()


def voice_score(voice: dict, tag: str) -> int:
    lang, name = _norm_lang(voice.get("lang")), (voice.get("name") or "").lower()
    score = 0
    if lang == tag.lower():
        score += 100
    if lang.endswith("-in"):
        score += 40
    if "natural" in name or "neural" in name:
        score += 25
    if any(n in name for n in INDIAN_VOICE_NAMES) or "india" in name:
        score += 15
    if not voice.get("local"):
        score += 5
    return score


def rank_voices(voices: list[dict], lang_code: str, allow_online: bool = True) -> list[dict]:
    tag = SPEECH_LANG.get(lang_code or "en", "en-IN")
    base = tag.split("-")[0]
    eligible = [v for v in voices or [] if _norm_lang(v.get("lang")).split("-")[0] == base and (allow_online or v.get("local"))]
    return sorted(eligible, key=lambda v: (-voice_score(v, tag), v.get("name", "")))


def pick_voice(voices: list[dict], lang_code: str, allow_online: bool = True, preferred: str | None = None) -> str | None:
    ranked = rank_voices(voices, lang_code, allow_online)
    if preferred and any(v["name"] == preferred for v in ranked):
        return preferred
    return ranked[0]["name"] if ranked else None


def has_indian_voice(voices: list[dict], allow_online: bool = True) -> bool:
    return any(_norm_lang(v.get("lang")).endswith("-in") and (allow_online or v.get("local")) for v in voices or [])


def voice_label(v: dict) -> str:
    where = "on device" if v.get("local") else "online"
    return f"{v['name']} · {v.get('lang')} · {where}"


def speak(text: str, lang_code: str, voice_name: str | None = None, rate: float = 0.95, pitch: float = 1.0,
          allow_online: bool = True) -> None:
    tag = SPEECH_LANG.get(lang_code or "en", "en-IN")
    payload = json.dumps({"text": clean_for_speech(text), "tag": tag, "voice": voice_name, "rate": rate, "pitch": pitch,
                          "online": allow_online, "nonce": time.time()}, ensure_ascii=False)
    components.html(f"""<script>
const p = {payload};
const w = window.parent;
const synth = w.speechSynthesis;
function go() {{
  if (!synth || !p.text) return;
  const voices = synth.getVoices().filter(x => p.online || x.localService);
  const base = p.tag.split('-')[0];
  const norm = x => x.lang.toLowerCase().replace('_', '-');
  let v = (p.voice && voices.find(x => x.name === p.voice))
          || voices.find(x => norm(x) === p.tag.toLowerCase()) || voices.find(x => norm(x).startsWith(base + '-'))
          || voices.find(x => norm(x) === base);
  if (!v && base !== 'en') return;
  synth.cancel();
  const u = new w.SpeechSynthesisUtterance(p.text);
  u.lang = v ? v.lang : p.tag;
  if (v) u.voice = v;
  u.rate = p.rate;
  u.pitch = p.pitch;
  const body = w.document.body;
  u.onstart = () => body.classList.add('perry-speaking');
  u.onend = () => body.classList.remove('perry-speaking');
  u.onerror = () => body.classList.remove('perry-speaking');
  synth.speak(u);
}}
if (synth && synth.getVoices().length) go(); else if (synth) synth.addEventListener('voiceschanged', go, {{once: true}});
</script>""", height=0)


def stop_speaking() -> None:
    components.html("<script>window.parent.speechSynthesis && window.parent.speechSynthesis.cancel();"
                    "window.parent.document.body.classList.remove('perry-speaking');</script>", height=0)


_mic = components.declare_component("perry_mic", path=str(Path(__file__).parent / "components" / "perry_mic"))
_voices = components.declare_component("perry_voices", path=str(Path(__file__).parent / "components" / "perry_voices"))


def browser_mic(lang_tag: str, key: str):
    return _mic(lang=lang_tag, key=key, default=None)


def browser_voices(key: str = "perry-voices") -> list[dict]:
    return _voices(key=key, default=[]) or []
