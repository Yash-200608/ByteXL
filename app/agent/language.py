import re
from dataclasses import dataclass

SCRIPTS = {
    "hi": ("Hindi", (0x0900, 0x097F)),
    "bn": ("Bengali", (0x0980, 0x09FF)),
    "pa": ("Punjabi", (0x0A00, 0x0A7F)),
    "gu": ("Gujarati", (0x0A80, 0x0AFF)),
    "or": ("Odia", (0x0B00, 0x0B7F)),
    "ta": ("Tamil", (0x0B80, 0x0BFF)),
    "te": ("Telugu", (0x0C00, 0x0C7F)),
    "kn": ("Kannada", (0x0C80, 0x0CFF)),
    "ml": ("Malayalam", (0x0D00, 0x0D7F)),
}

HINGLISH_MARKERS = {
    "meri", "mera", "mere", "mujhe", "mujhko", "hamara", "hamari", "kya", "kyaa", "hai", "hain", "tha", "thi", "kaise",
    "kab", "kitna", "kitni", "kitne", "dikhao", "dikha", "batao", "bata", "batana", "samjhao", "samjha", "samjhaiye", "mein",
    "aur", "nahi", "nahin", "haan", "kuch", "sab", "sabhi", "wala", "wali", "wale", "dawai", "dawa", "dawaiyan", "dawaiyon",
    "pichla", "pichli", "pichle", "abhi", "konsi", "kaunsi", "kaun", "kyun", "kyon", "chahiye", "hua", "hui", "huyi", "ko",
    "se", "ka", "ki", "ke", "liye", "lena", "leni", "lu", "loon", "karo", "kijiye", "badla", "badli", "badlav", "jaankari",
    "rakha", "likha", "likhi", "aakhri", "akhri", "naya", "nayi", "purana", "purani", "kitnaa", "bhi", "yeh", "ye", "woh", "vo",
}
STRONG_HINGLISH = {
    "meri", "mera", "mere", "mujhe", "kya", "hai", "hain", "dikhao", "batao", "samjhao", "samjhaiye", "dawai", "dawa", "kaise",
    "kitna", "kitni", "pichla", "pichli", "kaunsi", "konsi", "chahiye", "badla", "aakhri", "akhri", "nahi", "nahin",
}


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    script: str

    @property
    def is_hindi_family(self) -> bool:
        return self.code in ("hi", "hinglish")


ENGLISH = Language("en", "English", "Latin")


def _script_counts(text: str) -> dict[str, int]:
    counts = {code: 0 for code in SCRIPTS}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii():
            latin += ch.isalpha()
            continue
        for code, (_, (lo, hi)) in SCRIPTS.items():
            if lo <= cp <= hi:
                counts[code] += 1
                break
    counts["latin"] = latin
    return counts


def detect_language(text: str) -> Language:
    counts = _script_counts(text or "")
    indic = {k: v for k, v in counts.items() if k != "latin" and v}
    if indic:
        code = max(indic, key=indic.get)
        if indic[code] >= max(2, counts["latin"] * 0.25):
            return Language(code, SCRIPTS[code][0], SCRIPTS[code][0])
    words = re.findall(r"[a-z]+", (text or "").lower())
    if not words:
        return ENGLISH
    hits = [w for w in words if w in HINGLISH_MARKERS]
    strong = [w for w in words if w in STRONG_HINGLISH]
    if strong and (len(hits) / len(words) >= 0.2 or len(strong) >= 2):
        return Language("hinglish", "Hinglish", "Latin")
    return ENGLISH


def reply_instruction(lang: Language) -> str:
    keep = "Keep medicine names, test names, numbers, units and dates exactly as they appear in the data."
    if lang.code == "en":
        return f"Reply in English. {keep}"
    if lang.code == "hinglish":
        return ("Reply in Hinglish: conversational Hindi written in Roman (English) letters, the way the user wrote, "
                f"mixing in English words naturally. Do not use Devanagari. {keep}")
    return f"Reply in {lang.name}, written in the {lang.script} script. {keep}"
