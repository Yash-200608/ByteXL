import re

UNIT_ALIASES = {
    "mg/dl": "mg/dL", "mg%": "mg/dL", "mg/100ml": "mg/dL", "mgs/dl": "mg/dL",
    "mmol/l": "mmol/L", "mmol/lit": "mmol/L", "meq/l": "mmol/L",
    "umol/l": "µmol/L", "µmol/l": "µmol/L", "micromol/l": "µmol/L",
    "g/dl": "g/dL", "gm/dl": "g/dL", "g%": "g/dL", "gm%": "g/dL", "gms/dl": "g/dL", "gm/dL": "g/dL",
    "g/l": "g/L", "gm/l": "g/L",
    "%": "%", "percent": "%",
    "/cumm": "/µL", "cells/cumm": "/µL", "/cmm": "/µL", "cells/cmm": "/µL", "/ul": "/µL", "/µl": "/µL", "cells/ul": "/µL",
    "/mm3": "/µL", "cells/mm3": "/µL", "/c.mm": "/µL",
    "10^3/ul": "10^3/µL", "10^3/µl": "10^3/µL", "x10^3/ul": "10^3/µL", "thou/ul": "10^3/µL", "thou/cumm": "10^3/µL",
    "10^9/l": "10^3/µL", "x10^9/l": "10^3/µL", "k/ul": "10^3/µL", "10*3/ul": "10^3/µL",
    "lakh/cumm": "lakh/µL", "lakhs/cumm": "lakh/µL", "lakh/ul": "lakh/µL", "lakh/mm3": "lakh/µL", "lakhs/ul": "lakh/µL",
    "mill/cumm": "10^6/µL", "million/cumm": "10^6/µL", "million/ul": "10^6/µL", "10^6/ul": "10^6/µL", "mill/ul": "10^6/µL",
    "x10^12/l": "10^6/µL", "10^12/l": "10^6/µL", "m/ul": "10^6/µL", "10*6/ul": "10^6/µL",
    "uiu/ml": "µIU/mL", "µiu/ml": "µIU/mL", "miu/l": "µIU/mL", "uiu/l": "µIU/mL", "microiu/ml": "µIU/mL", "mu/l": "µIU/mL",
    "ng/ml": "ng/mL", "pg/ml": "pg/mL", "nmol/l": "nmol/L", "pmol/l": "pmol/L", "ng/dl": "ng/dL", "ug/dl": "µg/dL",
    "µg/dl": "µg/dL", "mcg/dl": "µg/dL", "mg/l": "mg/L",
    "u/l": "U/L", "iu/l": "U/L", "units/l": "U/L",
    "fl": "fL", "pg": "pg", "mm/hr": "mm/h", "mm/h": "mm/h", "mm/1st hr": "mm/h", "mm/1sthr": "mm/h", "mm at 1 hr": "mm/h",
    "/hpf": "/hpf", "cells/hpf": "/hpf", "/h.p.f": "/hpf", "ph": "pH",
}

CONVERSIONS: dict[tuple[str, str], float] = {
    ("g/L", "g/dL"): 0.1,
    ("10^3/µL", "/µL"): 1000.0,
    ("lakh/µL", "/µL"): 100000.0,
    ("/µL", "10^6/µL"): 1e-6,
    ("µIU/mL", "µIU/mL"): 1.0,
}

ANALYTE_CONVERSIONS: dict[str, dict[tuple[str, str], float]] = {
    "glucose": {("mmol/L", "mg/dL"): 18.016},
    "cholesterol": {("mmol/L", "mg/dL"): 38.67},
    "triglycerides": {("mmol/L", "mg/dL"): 88.57},
    "creatinine": {("µmol/L", "mg/dL"): 1 / 88.42},
    "urea": {("mmol/L", "mg/dL"): 6.006},
    "bun": {("mmol/L", "mg/dL"): 2.801},
    "uric_acid": {("µmol/L", "mg/dL"): 1 / 59.48},
    "bilirubin": {("µmol/L", "mg/dL"): 1 / 17.1},
    "calcium": {("mmol/L", "mg/dL"): 4.008},
    "vitamin_d": {("nmol/L", "ng/mL"): 1 / 2.496},
    "vitamin_b12": {("pmol/L", "pg/mL"): 1.355},
    "t4": {("nmol/L", "µg/dL"): 1 / 12.87},
    "t3": {("nmol/L", "ng/dL"): 65.1},
}

ANALYTE_BY_LOINC = {
    "1558-6": "glucose", "1521-4": "glucose", "2345-7": "glucose",
    "2093-3": "cholesterol", "2085-9": "cholesterol", "13457-7": "cholesterol", "13458-5": "cholesterol",
    "2571-8": "triglycerides", "2160-0": "creatinine", "3091-6": "urea", "3094-0": "bun", "3084-1": "uric_acid",
    "1975-2": "bilirubin", "1968-7": "bilirubin", "17861-6": "calcium", "62292-8": "vitamin_d", "2132-9": "vitamin_b12",
    "3026-2": "t4", "3053-6": "t3",
}


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.strip()
    if not u:
        return None
    key = re.sub(r"\s+", "", u.lower()).replace("μ", "µ").replace("cu.mm", "cumm").replace("cu mm", "cumm")
    key = key.replace("×", "x").replace("*", "*")
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    key2 = key.replace("µ", "u")
    if key2 in UNIT_ALIASES:
        return UNIT_ALIASES[key2]
    return u


def conversion_factor(from_unit: str | None, to_unit: str | None, loinc: str | None = None) -> float | None:
    f, t = normalize_unit(from_unit), normalize_unit(to_unit)
    if f is None or t is None:
        return 1.0 if f == t else None
    if f == t:
        return 1.0
    if (f, t) in CONVERSIONS:
        return CONVERSIONS[(f, t)]
    if (t, f) in CONVERSIONS:
        return 1.0 / CONVERSIONS[(t, f)]
    for a, b, factor in _chain():
        if (a, b) == (f, t):
            return factor
    analyte = ANALYTE_BY_LOINC.get(loinc or "")
    if analyte:
        table = ANALYTE_CONVERSIONS[analyte]
        if (f, t) in table:
            return table[(f, t)]
        if (t, f) in table:
            return 1.0 / table[(t, f)]
    return None


def _chain():
    out = []
    for (a, b), x in CONVERSIONS.items():
        for (c, d), y in CONVERSIONS.items():
            if b == c and a != d:
                out.append((a, d, x * y))
    return out


def convert(value: float | None, from_unit: str | None, to_unit: str | None, loinc: str | None = None) -> float | None:
    if value is None:
        return None
    factor = conversion_factor(from_unit, to_unit, loinc)
    if factor is None:
        return None
    return value * factor


def mgdl_to_mmol(value: float, analyte: str) -> float:
    factor = ANALYTE_CONVERSIONS[analyte][("mmol/L", "mg/dL")]
    return value / factor


def mmol_to_mgdl(value: float, analyte: str) -> float:
    factor = ANALYTE_CONVERSIONS[analyte][("mmol/L", "mg/dL")]
    return value * factor
