import re

from app.extract.llm_schemas import DischargeSummaryLLM, LabReportLLM, LabTestLLM, MedicineLLM, PrescriptionLLM
from app.extract.parse import clean, parse_age_sex, parse_number

FORM_RE = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?((?:tab|cap|syp|inj|sachet|sach|drops?|oint|cream|gel|susp|ors|powder|spray)\b\.?.*)$", re.I)
DOSE_RE = re.compile(
    r"\b(\d+(?:/\d)?\s*-\s*\d+(?:/\d)?\s*-\s*\d+(?:/\d)?(?:\s*-\s*\d+)?|od|bd|bid|tds|tid|qid|qds|sos|prn|stat|hs|once (?:a|daily|weekly)(?: (?:day|week))?|twice daily|thrice daily|weekly)\b",
    re.I,
)
TIMING_RE = re.compile(r"\b(after (?:food|meals?|breakfast|lunch|dinner)|before (?:food|meals?|breakfast|lunch|dinner)|empty stomach|at bedtime|bedtime|ac|pc|hs)\b", re.I)
DURATION_RE = re.compile(r"((?:x|×|for)\s*\d+\s*(?:days?|d|wks?|weeks?|months?|mo)\b|\(?continue\)?|long term)", re.I)
STRENGTH_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|k|%))\b", re.I)


def _kv(text: str, label: str) -> str:
    m = re.search(label + r"\s*[:\-]\s*(.+?)(?:\s{3,}|$)", text, flags=re.I | re.M)
    return clean(m.group(1)) if m else ""


def _cells(row: str) -> list[str]:
    return [c.strip() for c in re.split(r"\s{3,}|\t", row) if c.strip()]


def lab_rows(text: str) -> list[LabTestLLM]:
    tests = []
    for row in text.splitlines():
        cells = _cells(row)
        if len(cells) < 2 or not re.search(r"[a-z]{2}", cells[0], re.I):
            continue
        if parse_number(cells[1]) is None or ":" in cells[0]:
            continue
        unit = cells[2] if len(cells) > 2 and not re.match(r"^[<>]?\s*\d", cells[2]) else ""
        rest = cells[3:] if unit else cells[2:]
        rng = rest[0] if rest and re.search(r"\d", rest[0]) else ""
        flag = next((c for c in rest if c.upper() in ("H", "L")), "")
        tests.append(LabTestLLM(name=cells[0], value=cells[1], unit=unit, reference_range=rng, flag=flag))
    return tests


def med_lines(text: str) -> list[MedicineLLM]:
    meds = []
    for row in text.splitlines():
        m = FORM_RE.match(row)
        if not m:
            continue
        body = clean(m.group(1))
        dm = DOSE_RE.search(body)
        tm = TIMING_RE.search(body)
        cut = min([x.start() for x in (dm, tm) if x] + [len(body)])
        dur = DURATION_RE.search(body)
        if dur and dur.start() < cut:
            cut = dur.start()
        name = clean(body[:cut])
        sm = STRENGTH_RE.search(name)
        meds.append(
            MedicineLLM(
                name=name,
                strength=sm.group(1) if sm else "",
                dosage=dm.group(1) if dm else "",
                timing=tm.group(1) if tm and (not dm or tm.group(1).lower() != dm.group(1).lower()) else "",
                duration=dur.group(1) if dur else "",
            )
        )
    return meds


def _header(text: str) -> dict:
    age, sex = parse_age_sex(text)
    name = _kv(text, r"patient(?:'s)?\s*name") or _kv(text, r"patient") or _kv(text, r"name")
    name = re.split(r"\s{2,}|age|\d{1,3}\s*/\s*[mf]\b", name, flags=re.I)[0].strip()
    return {"patient_name": name, "age": str(age or ""), "sex": sex or ""}


def rules_extract(doc_type: str, text: str):
    h = _header(text)
    first = clean(text.splitlines()[0]) if text.strip() else ""
    if doc_type == "lab_report":
        return LabReportLLM(
            **h,
            facility=first,
            referring_doctor=_kv(text, r"ref(?:\.|erred)?\s*by"),
            collected_date=_kv(text, r"collected(?: on)?"),
            report_date=_kv(text, r"reported(?: on)?"),
            tests=lab_rows(text),
        )
    if doc_type == "prescription":
        dm = re.search(r"date\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})", text, re.I)
        return PrescriptionLLM(
            **h,
            doctor_name=first if first.lower().startswith("dr") else "",
            date=dm.group(1) if dm else "",
            complaints=[c for c in [_kv(text, r"c/o")] if c],
            diagnoses=[d.strip() for d in re.split(r",", _kv(text, r"(?:dx|diagnosis)")) if d.strip()],
            medicines=med_lines(text),
        )
    diag = []
    m = re.search(r"final diagnosis\s*:?\s*\n((?:\s*\d+[.)].*\n?)+)", text, re.I)
    if m:
        diag = [clean(re.sub(r"^\s*\d+[.)]\s*", "", d)) for d in m.group(1).splitlines() if d.strip()]
    return DischargeSummaryLLM(
        **h,
        patient_id=_kv(text, r"uhid"),
        hospital=first,
        doctor=_kv(text, r"consultant"),
        admission_date=_kv(text, r"date of admission"),
        discharge_date=_kv(text, r"date of discharge"),
        diagnoses=diag,
        investigations=lab_rows(text),
        discharge_medicines=med_lines(text),
        follow_up=_kv(text, r"follow[- ]?up"),
    )
