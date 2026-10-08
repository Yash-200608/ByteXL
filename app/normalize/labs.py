import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from app.config import get_settings
from app.normalize.units import convert, normalize_unit
from app.schemas import LabResult, NormalizedLab


@dataclass(frozen=True)
class LabRef:
    canonical_name: str
    aliases: tuple[str, ...]
    loinc: str
    panel: str
    unit: str | None
    low_male: float | None
    high_male: float | None
    low_female: float | None
    high_female: float | None
    critical_low: float | None
    critical_high: float | None
    low_meaning: str
    high_meaning: str
    low_meaning_hi: str
    high_meaning_hi: str

    def range_for(self, sex: str | None) -> tuple[float | None, float | None]:
        if sex == "female":
            return self.low_female, self.high_female
        if sex == "male":
            return self.low_male, self.high_male
        lows = [v for v in (self.low_male, self.low_female) if v is not None]
        highs = [v for v in (self.high_male, self.high_female) if v is not None]
        return (min(lows) if lows else None, max(highs) if highs else None)


def _f(v: str) -> float | None:
    v = (v or "").strip()
    return float(v) if v else None


def alias_key(name: str) -> str:
    s = name.lower().replace("μ", "µ")
    s = re.sub(r"[\[\]{}]", " ", s)
    s = re.sub(r"[^a-z0-9%()+\-./ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .:-")
    return s


@lru_cache
def load_lab_reference() -> tuple[LabRef, ...]:
    path = get_settings().reference_dir / "lab_tests.csv"
    refs = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aliases = tuple(alias_key(a) for a in row["aliases"].split("|") if a.strip())
            refs.append(
                LabRef(
                    canonical_name=row["canonical_name"],
                    aliases=tuple(dict.fromkeys(aliases + (alias_key(row["canonical_name"]),))),
                    loinc=row["loinc"],
                    panel=row["panel"],
                    unit=normalize_unit(row["unit"]) if row["unit"] else None,
                    low_male=_f(row["low_male"]),
                    high_male=_f(row["high_male"]),
                    low_female=_f(row["low_female"]),
                    high_female=_f(row["high_female"]),
                    critical_low=_f(row["critical_low"]),
                    critical_high=_f(row["critical_high"]),
                    low_meaning=row["low_meaning"],
                    high_meaning=row["high_meaning"],
                    low_meaning_hi=row["low_meaning_hi"],
                    high_meaning_hi=row["high_meaning_hi"],
                )
            )
    return tuple(refs)


@lru_cache
def _alias_index() -> dict[str, LabRef]:
    idx = {}
    for ref in load_lab_reference():
        for a in ref.aliases:
            idx.setdefault(a, ref)
    return idx


def by_loinc(loinc: str) -> LabRef | None:
    return next((r for r in load_lab_reference() if r.loinc == loinc), None)


def resolve_lab(name: str | None) -> tuple[LabRef | None, float]:
    if not name:
        return None, 0.0
    key = alias_key(name)
    idx = _alias_index()
    if key in idx:
        return idx[key], 100.0
    stripped = re.sub(r"^(serum|s\.|plasma|blood|total)\s+", "", key)
    stripped = re.sub(r"\s*\((calculated|calc|direct|measured)\)\s*$", "", stripped)
    if stripped in idx:
        return idx[stripped], 98.0
    no_paren = re.sub(r"\s*\(.*?\)\s*", " ", key).strip()
    if no_paren in idx:
        return idx[no_paren], 96.0
    best = process.extractOne(key, list(idx.keys()), scorer=fuzz.token_sort_ratio)
    if best and best[1] >= get_settings().lab_alias_min_score:
        return idx[best[0]], float(best[1])
    return None, float(best[1]) if best else 0.0


NUM = r"[-+]?\d+(?:\.\d+)?"


def parse_range(text: str | None) -> tuple[float | None, float | None] | None:
    if not text:
        return None
    s = text.lower().replace(",", "").replace("–", "-").replace("—", "-").replace("≤", "<=").replace("≥", ">=")
    s = re.sub(r"(desirable|normal|optimal|ref(erence)?|range|adult|male|female)\s*[:\-]?", " ", s)
    m = re.search(rf"({NUM})\s*(?:-|to)\s*({NUM})", s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo, hi) if lo <= hi else None
    m = re.search(rf"(?:<=?|upto|up to|less than|below)\s*({NUM})", s)
    if m:
        return None, float(m.group(1))
    m = re.search(rf"({NUM})\s*(?:max|maximum)\b", s)
    if m:
        return None, float(m.group(1))
    m = re.search(rf"(?:>=?|more than|above|greater than)\s*({NUM})", s)
    if m:
        return float(m.group(1)), None
    m = re.search(rf"({NUM})\s*(?:min|minimum)\b", s)
    if m:
        return float(m.group(1)), None
    return None


def classify_value(value: float, low: float | None, high: float | None, crit_low: float | None = None, crit_high: float | None = None) -> str:
    if crit_low is not None and value < crit_low:
        return "critical"
    if crit_high is not None and value > crit_high:
        return "critical"
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


def normalize_lab(result: LabResult, sex: str | None = None, age: int | None = None) -> NormalizedLab:
    ref, score = resolve_lab(result.test_name.value)
    value = result.value.value
    unit = normalize_unit(result.unit.value)
    out = NormalizedLab(match_score=score)
    if ref:
        out.canonical_name = ref.canonical_name
        out.loinc = ref.loinc
        out.panel = ref.panel
    if value is None:
        out.unit = unit
        return out
    target_unit = ref.unit if ref and ref.unit else unit
    if ref and ref.unit and unit and unit != ref.unit:
        converted = convert(value, unit, ref.unit, ref.loinc)
    else:
        converted = value
    if converted is None:
        out.value, out.unit = value, unit
        target_unit = unit
        factor_ok = False
    else:
        out.value, out.unit = _r(converted), target_unit
        factor_ok = True
        if unit and target_unit and unit != target_unit:
            out.conversion = f"{unit}→{target_unit} ×{round(converted / value, 6) if value else 0:g}"
    printed = parse_range(result.reference_range.value)
    crit_lo = crit_hi = None
    if ref and factor_ok:
        crit_lo, crit_hi = ref.critical_low, ref.critical_high
    if printed:
        lo, hi = printed
        out.range_source = "printed"
        out.flag = classify_value(value, lo, hi)
        if classify_value(out.value, None, None, crit_lo, crit_hi) == "critical":
            out.flag = "critical"
        if factor_ok and unit and target_unit and unit != target_unit:
            out.ref_low = _r(convert(lo, unit, target_unit, out.loinc)) if lo is not None else None
            out.ref_high = _r(convert(hi, unit, target_unit, out.loinc)) if hi is not None else None
        else:
            out.ref_low, out.ref_high = lo, hi
        return out
    if ref and factor_ok and (age is None or age >= 18):
        lo, hi = ref.range_for(sex)
        if lo is not None or hi is not None:
            out.range_source = "reference_table"
            out.ref_low, out.ref_high = lo, hi
            out.flag = classify_value(out.value, lo, hi, crit_lo, crit_hi)
            return out
    out.range_source = "none"
    out.flag = "unknown"
    return out
