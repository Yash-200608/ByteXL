import re

from app.schemas import Dosage

WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "a": 1, "an": 1}
FRACTIONS = {"½": 0.5, "1/2": 0.5, "¼": 0.25, "1/4": 0.25, "¾": 0.75, "3/4": 0.75, "1½": 1.5, "1 1/2": 1.5}
SLOT = r"(?:\d+(?:\.\d+)?|½|¼|¾|1½|\d/\d)"
SLOTS_RE = re.compile(rf"(?<![\d/])({SLOT})\s*[-–]\s*({SLOT})\s*[-–]\s*({SLOT})(?:\s*[-–]\s*({SLOT}))?(?![\d/])")
DUR_UNITS = {"d": "d", "day": "d", "days": "d", "dys": "d",
             "w": "wk", "wk": "wk", "wks": "wk", "week": "wk", "weeks": "wk",
             "m": "mo", "mo": "mo", "mth": "mo", "mths": "mo", "month": "mo", "months": "mo"}
DURATION_RE = re.compile(
    r"(?:\bx\s*|×\s*|\bfor\s+|\bdays?\s*[:\-]\s*|\b)(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|fourteen|fifteen|twenty|thirty|a|an)\s*"
    r"(days?|dys|d|wks?|weeks?|w|months?|mths?|mo|m)\b"
)

FREQ_PATTERNS: list[tuple[str, dict]] = [
    (r"\b(qid|qds|q\.i\.d|four times (?:a|daily|per) ?(?:day)?)\b", {"frequency": 4, "when": ["MORN", "AFT", "EVE", "NIGHT"]}),
    (r"\b(tds|tid|t\.d\.s|t\.i\.d|thrice daily|thrice a day|three times (?:a|daily|per) ?(?:day)?)\b", {"frequency": 3, "slots": (1, 1, 1)}),
    (r"\b(bd|bid|b\.d|b\.i\.d|twice daily|twice a day|two times (?:a|per) day|12 ?hourly|q12h)\b", {"frequency": 2, "slots": (1, 0, 1)}),
    (r"\b(od|o\.d|once daily|once a day|daily|1 time a day|q24h|every day)\b", {"frequency": 1}),
    (r"\b(8 ?hourly|q8h)\b", {"frequency": 3, "slots": (1, 1, 1)}),
    (r"\b(6 ?hourly|q6h)\b", {"frequency": 4}),
    (r"\b(once (?:a )?week(?:ly)?|weekly|once in a week|1 time a week)\b", {"frequency": 1, "period_unit": "wk"}),
    (r"\b(twice (?:a )?week(?:ly)?)\b", {"frequency": 2, "period_unit": "wk"}),
    (r"\b(alternate days?|every other day|on alternate days)\b", {"frequency": 1, "period": 2}),
    (r"\b(once (?:a )?month(?:ly)?|monthly)\b", {"frequency": 1, "period_unit": "mo"}),
]
PRN_RE = re.compile(r"\b(sos|s\.o\.s|prn|p\.r\.n|as needed|as and when required|when required|if needed|if required|when needed|as required)\b")
STAT_RE = re.compile(r"\bstat\b")
CONTINUE_RE = re.compile(r"\b(continue|to continue|cont\.?|long term|lifelong|till further advice|until further advice)\b")
TIMING_PATTERNS: list[tuple[str, str]] = [
    (r"\b(before breakfast|empty stomach|on empty stomach|early morning empty stomach|e/s)\b", "ACM"),
    (r"\b(after breakfast)\b", "PCM"),
    (r"\b(before lunch)\b", "ACD"),
    (r"\b(after lunch)\b", "PCD"),
    (r"\b(before dinner)\b", "ACV"),
    (r"\b(after dinner)\b", "PCV"),
    (r"\b(before food|before meals?|ac|a/c|a\.c)\b", "AC"),
    (r"\b(after food|after meals?|pc|p/c|p\.c|with food|with meals?)\b", "PC"),
    (r"\b(hs|h\.s|at bedtime|bedtime|at bed time|at night before sleep)\b", "HS"),
]
SLOT_WHEN = ("MORN", "AFT", "NIGHT")

EN_WHEN = {
    "AC": "before food", "PC": "after food", "ACM": "before breakfast", "PCM": "after breakfast", "ACD": "before lunch",
    "PCD": "after lunch", "ACV": "before dinner", "PCV": "after dinner", "HS": "at bedtime",
}


def _num(tok: str) -> float:
    tok = tok.strip()
    if tok in FRACTIONS:
        return FRACTIONS[tok]
    if "/" in tok:
        a, b = tok.split("/", 1)
        return float(a) / float(b) if float(b) else 0.0
    return float(tok)


def _fmt(n: float) -> str:
    if n == 0.5:
        return "½"
    return f"{n:g}"


def _strip_sig_noise(text: str) -> str:
    t = text.lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"\b(tab|tabs|tablet|cap|caps|capsule|syp|syrup|inj|sachet|drops?)\b\.?", " ", t)
    return re.sub(r"\s+", " ", t).strip()


QTY_RE = re.compile(r"(?<![\d/-])(\d+(?:\.\d+)?|½|1½)\s*(tsp|teaspoons?|tbsp|ml|tabs?|tablets?|caps?|capsules?|puffs?|drops?|units?|iu|sachets?)\b")
QTY_UNITS = {"tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp", "tbsp": "tbsp", "ml": "mL", "tab": "tablet", "tabs": "tablet",
             "tablet": "tablet", "tablets": "tablet", "cap": "capsule", "caps": "capsule", "capsule": "capsule", "capsules": "capsule",
             "puff": "puff", "puffs": "puff", "drop": "drop", "drops": "drop", "unit": "unit", "units": "unit", "iu": "unit",
             "sachet": "sachet", "sachets": "sachet"}


def parse_dosage(*parts: str | None) -> Dosage:
    raw = " ".join(p for p in parts if p and p.strip())
    d = Dosage()
    qm = QTY_RE.search(raw.lower())
    if qm:
        d.dose_quantity = _num(qm.group(1))
        d.dose_unit = QTY_UNITS[qm.group(2)]
        raw = raw[: qm.start()] + " " + raw[qm.end():]
    text = _strip_sig_noise(raw)
    consumed: list[tuple[int, int]] = []

    def eat(m):
        consumed.append(m.span())

    slots = None
    m = SLOTS_RE.search(text)
    if m:
        vals = [_num(g) for g in m.groups() if g is not None]
        eat(m)
        if len(vals) == 4:
            d.morning, d.afternoon, d.evening, d.night = vals
            d.frequency = sum(1 for v in vals if v > 0)
            d.when = [w for w, v in zip(("MORN", "AFT", "EVE", "NIGHT"), vals) if v > 0]
        else:
            d.morning, d.afternoon, d.night = vals
            d.frequency = sum(1 for v in vals if v > 0)
            d.when = [w for w, v in zip(SLOT_WHEN, vals) if v > 0]
        slots = vals

    abbrev_freq = None
    for pattern, spec in FREQ_PATTERNS:
        fm = re.search(pattern, text)
        if not fm:
            continue
        if any(fm.start() < e and fm.end() > s for s, e in consumed):
            continue
        eat(fm)
        abbrev_freq = spec["frequency"]
        if "period_unit" in spec:
            d.period_unit = spec["period_unit"]
        if "period" in spec:
            d.period = spec["period"]
        if slots is None:
            d.frequency = spec["frequency"]
            if "slots" in spec:
                q = d.dose_quantity or 1
                d.morning, d.afternoon, d.night = (v * q for v in spec["slots"])
                d.when = [w for w, v in zip(SLOT_WHEN, spec["slots"]) if v > 0]
            elif "when" in spec:
                d.when = list(spec["when"])
        elif d.period_unit == "d" and spec["frequency"] != d.frequency and fm.group(0) not in ("daily", "every day"):
            d.conflicts.append(f"'{fm.group(0)}' means {spec['frequency']}×/day but slots {'-'.join(_fmt(v) for v in slots)} give {d.frequency}")
        break

    pm = PRN_RE.search(text)
    if pm:
        d.as_needed = True
        eat(pm)
    sm = STAT_RE.search(text)
    if sm:
        d.single_dose = True
        eat(sm)
    cm = CONTINUE_RE.search(text)
    if cm:
        d.continue_indefinitely = True
        eat(cm)

    for dm in DURATION_RE.finditer(text):
        if any(dm.start() < e and dm.end() > s for s, e in consumed):
            continue
        n = dm.group(1)
        d.duration_value = float(WORD_NUM.get(n, n)) if n in WORD_NUM else float(n)
        d.duration_unit = DUR_UNITS[dm.group(2)]
        eat(dm)
        break

    timing = []
    for pattern, code in TIMING_PATTERNS:
        for tm in re.finditer(pattern, text):
            if any(tm.start() < e and tm.end() > s for s, e in consumed):
                continue
            eat(tm)
            if code not in timing:
                timing.append(code)
    specific = [c for c in timing if c in ("ACM", "PCM", "ACD", "PCD", "ACV", "PCV")]
    if specific:
        timing = [c for c in timing if c not in ("AC", "PC") or not any(s.startswith(c) for s in specific)]
    if "HS" in timing and slots is None and abbrev_freq in (None, 1):
        d.night = d.night or (d.dose_quantity or 1)
        d.frequency = d.frequency or 1
        if "NIGHT" not in d.when:
            d.when.append("NIGHT")
    if "ACM" in timing and slots is None and abbrev_freq in (None, 1) and d.period_unit == "d":
        d.morning = d.morning or (d.dose_quantity or 1)
        d.frequency = d.frequency or 1
        if "MORN" not in d.when:
            d.when.append("MORN")
    d.when = list(dict.fromkeys(d.when + timing))

    leftovers = text
    for s, e in sorted(consumed, reverse=True):
        leftovers = leftovers[:s] + " " + leftovers[e:]
    leftovers = re.sub(r"\b(for|x|and|then|in|the|of|to|with|mg|mcg|ml|gm|g|iu|k|\d+(\.\d+)?|[a-z])\b", " ", leftovers)
    leftovers = re.sub(r"[^a-z]+", " ", leftovers).strip()
    if leftovers:
        d.unparsed = leftovers.split()
    d.text = describe(d)
    return d


def describe(d: Dosage) -> str:
    bits = []
    night_label = "at bedtime" if "HS" in d.when else "at night"
    slots = [("in the morning", d.morning), ("in the afternoon", d.afternoon), ("in the evening", d.evening), (night_label, d.night)]
    unit = ""
    if d.dose_unit:
        plural = d.dose_quantity and d.dose_quantity > 1 and d.dose_unit in ("tablet", "capsule", "puff", "drop", "unit", "sachet")
        unit = f" {d.dose_unit}{'s' if plural else ''}"
    if d.single_dose:
        bits.append(f"single dose{f' of {_fmt(d.dose_quantity)}{unit}' if d.dose_quantity else ''}")
    elif any(v for _, v in slots) and d.period_unit == "d" and d.period == 1:
        bits.append(", ".join(f"{_fmt(v)}{unit} {label}" for label, v in slots if v))
    elif d.frequency:
        unit = {"d": "day", "wk": "week", "mo": "month", "h": "hour"}[d.period_unit]
        times = {1: "once", 2: "twice"}.get(d.frequency, f"{d.frequency} times")
        bits.append(f"{times} every {_fmt(d.period)} {unit}s" if d.period != 1 else f"{times} a {unit}")
    if d.dose_quantity and not any(v for _, v in slots) and not d.single_dose:
        bits.insert(0, f"{_fmt(d.dose_quantity)}{unit}")
    if d.as_needed:
        bits.append("only when needed")
    food = [EN_WHEN[w] for w in d.when if w in EN_WHEN and not (w == "HS" and d.night)]
    if food:
        bits.append(", ".join(food))
    if d.duration_value:
        unit = {"d": "day", "wk": "week", "mo": "month"}[d.duration_unit]
        bits.append(f"for {_fmt(d.duration_value)} {unit}{'s' if d.duration_value != 1 else ''}")
    if d.continue_indefinitely:
        bits.append("continue until your doctor says otherwise")
    return " · ".join(bits) if bits else ""


def total_days(d: Dosage) -> float | None:
    if d.duration_value is None:
        return None
    return d.duration_value * {"d": 1, "wk": 7, "mo": 30}[d.duration_unit]
