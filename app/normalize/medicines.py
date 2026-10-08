import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from app.config import get_settings
from app.normalize.dosing import parse_dosage
from app.schemas import MedicationItem, NormalizedMedication

FORM_WORDS = r"(tab|tabs|tablet|cap|caps|capsule|syp|syrup|inj|injection|sachet|sach|drops?|oint|ointment|cream|gel|susp|suspension|inh|inhaler|spray|powder)"
STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\s*(mg|mcg|µg|g|gm|ml|iu|k|%|units?)\b", re.I)


@dataclass(frozen=True)
class MedRef:
    brand: str
    generic: str
    strength: str
    form: str
    drug_class: str

    @property
    def components(self) -> list[str]:
        return [c.strip() for c in self.generic.split("+") if c.strip()]


def brand_key(name: str) -> str:
    s = name.lower().replace("-", " ")
    s = re.sub(rf"^\s*(\d+\s*[.)]\s*)?{FORM_WORDS}\b\.?\s*", "", s)
    s = STRENGTH_RE.sub(" ", s)
    s = re.sub(r"\b\d+(\.\d+)?\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _load(path) -> list[MedRef]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("brand") and row.get("generic"):
                out.append(MedRef(row["brand"].strip(), row["generic"].strip().lower(), (row.get("strength") or "").strip(),
                                  (row.get("form") or "").strip(), (row.get("drug_class") or "").strip()))
    return out


@lru_cache
def load_medicines() -> dict[str, MedRef]:
    ref_dir = get_settings().reference_dir
    refs = _load(ref_dir / "medicines.csv")
    extended = ref_dir / "medicines_extended.csv"
    if extended.exists():
        refs += _load(extended)
    index: dict[str, MedRef] = {}
    for r in refs:
        index.setdefault(brand_key(r.brand), r)
    generics: dict[str, MedRef] = {}
    for r in refs:
        generics.setdefault(r.generic, MedRef(r.generic.title(), r.generic, "", r.form, r.drug_class))
    for g, r in generics.items():
        index.setdefault(brand_key(g), r)
    return index


def resolve_medicine(name: str | None) -> tuple[MedRef | None, float]:
    if not name:
        return None, 0.0
    key = brand_key(name)
    if not key:
        return None, 0.0
    idx = load_medicines()
    if key in idx:
        return idx[key], 100.0
    for variant in (key.replace("rn", "m"), key.replace("0", "o").replace("1", "l"), key.replace("cl", "d"), key.replace("vv", "w")):
        if variant != key and variant in idx:
            return idx[variant], 92.0
    words = key.split()
    for n in range(len(words) - 1, 0, -1):
        k = " ".join(words[:n])
        if k in idx:
            return idx[k], 95.0
    best = process.extractOne(key, list(idx.keys()), scorer=fuzz.ratio)
    if best and best[1] >= get_settings().medicine_min_score:
        return idx[best[0]], float(best[1])
    first = words[0]
    best = process.extractOne(first, list(idx.keys()), scorer=fuzz.ratio)
    if best and best[1] >= get_settings().medicine_min_score and len(first) >= 4:
        return idx[best[0]], float(best[1]) - 5
    return None, float(best[1]) if best else 0.0


def extract_strength(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        m = STRENGTH_RE.search(t)
        if m:
            unit = m.group(2).lower().replace("µg", "mcg")
            return f"{m.group(1).replace(' ', '')}{'K' if unit == 'k' else ' ' + unit}"
    for t in texts:
        if t:
            m = re.search(r"\b(\d+(?:\.\d+)?)\s*$", t.strip())
            if m:
                return m.group(1)
    return None


def normalize_medication(item: MedicationItem) -> NormalizedMedication:
    ref, score = resolve_medicine(item.name.value)
    dosage = parse_dosage(item.dosage.value, item.timing.value, item.duration.value, item.instructions.value)
    strict = parse_dosage(item.dosage.value, item.duration.value)
    dosage.unparsed = strict.unparsed
    form = item.form.value or (ref.form if ref else None)
    return NormalizedMedication(
        brand=ref.brand if ref and ref.brand.lower() != ref.generic else None,
        generic=ref.generic if ref else None,
        strength=extract_strength(item.strength.value, item.name.value) or (ref.strength if ref else None) or None,
        form=form,
        drug_class=ref.drug_class if ref else None,
        matched=ref is not None,
        match_score=score,
        dosage=dosage,
    )
