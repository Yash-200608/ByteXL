import re
from datetime import date

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)*")


def clean(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _year(y: int) -> int:
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y


def parse_date(s: str | None) -> date | None:
    s = clean(s).lower()
    if not s:
        return None
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
        try:
            return date(y, mo, d)
        except ValueError:
            try:
                return date(y, d, mo)
            except ValueError:
                return None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([a-z]{3})[a-z]*[\s\-/.,]*(\d{2,4})\b", s)
    if m and m.group(2) in MONTHS:
        try:
            return date(_year(int(m.group(3))), MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b([a-z]{3})[a-z]*[\s\-/.,]+(\d{1,2})(?:st|nd|rd|th)?[\s,]+(\d{4})\b", s)
    if m and m.group(1) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    return None


def parse_number(s: str | None) -> float | None:
    s = clean(s)
    if not s:
        return None
    s2 = s.replace(" ", "")
    m = re.match(r"^[<>≤≥=]*\s*([-+]?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|[-+]?\d*\.?\d+)", s2)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_age(s: str | None) -> int | None:
    s = clean(s).lower()
    m = re.search(r"(\d{1,3})\s*(y|yr|yrs|years?)?\b", s)
    if not m:
        return None
    age = int(m.group(1))
    return age if 0 < age < 120 else None


def parse_sex(s: str | None) -> str | None:
    s = clean(s).lower()
    if not s:
        return None
    if re.search(r"\b(f|female|woman|mrs|ms|miss)\b", s):
        return "female"
    if re.search(r"\b(m|male|man|mr)\b", s):
        return "male"
    if "other" in s or "trans" in s:
        return "other"
    return None


def parse_age_sex(text: str) -> tuple[int | None, str | None]:
    m = re.search(r"(\d{1,3})\s*(?:y|yrs?|years?)?\s*[/,\-]\s*(m|f|male|female)\b", text, flags=re.I)
    if m:
        return int(m.group(1)), parse_sex(m.group(2))
    return None, None


def strip_honorific(name: str | None) -> str:
    name = clean(name)
    return re.sub(r"^(mr|mrs|ms|miss|master|baby|smt|shri|sri)\.?\s+", "", name, flags=re.I)
