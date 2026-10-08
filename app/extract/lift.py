import re
from datetime import date

from app.extract.boxes import Locator, field_confidence
from app.extract.parse import clean, parse_age, parse_date, parse_number, parse_sex, strip_honorific
from app.ingest.models import PageData
from app.schemas import (
    DischargeSummary,
    ExtractionMeta,
    Field,
    LabReport,
    LabResult,
    MedicationItem,
    PatientInfo,
    Prescription,
)


class Lifter:
    def __init__(self, pages: list[PageData], retried: bool, low: bool):
        self.loc = Locator(pages)
        self.retried = retried
        self.low = low

    def field(self, value, search=None, anchor=None, kind=str):
        search = value if search is None else search
        if kind is str:
            value = clean(value) or None
        if value is None or value == "":
            return Field[kind](), None
        match, hit, box = self.loc.locate(search, anchor)
        ocr_conf = hit[1].confidence if hit else 0.0
        conf = field_confidence(match, ocr_conf, self.retried, self.low)
        found = match >= self.loc_threshold
        f = Field[kind](value=value, confidence=conf, source_box=box if found else None)
        if not found:
            f.reasons.append("value not found in document text")
            hit = None
        return f, hit

    @property
    def loc_threshold(self) -> float:
        from app.config import get_settings

        return get_settings().box_match_min_score / 100.0

    def text(self, value, anchor=None) -> Field:
        return self.field(value, anchor=anchor)[0]

    def date(self, raw) -> Field:
        d = parse_date(raw)
        if d is None:
            return Field[date]()
        return self.field(d, search=clean(raw), kind=date)[0]

    def texts(self, values) -> list[Field]:
        return [self.text(v) for v in values or [] if clean(v)]

    def patient(self, name, age, sex, pid=None) -> PatientInfo:
        p = PatientInfo()
        p.name, _ = self.field(strip_honorific(name), search=clean(name))
        a = parse_age(age)
        if a is not None:
            p.age_years, _ = self.field(a, search=str(a), kind=int)
        sx = parse_sex(sex)
        if sx:
            p.sex, _ = self.field(sx, search=clean(sex))
        if pid:
            p.identifier, _ = self.field(pid)
        return p

    def lab(self, t) -> LabResult:
        r = LabResult()
        r.test_name, hit = self.field(t.name)
        raw_value = clean(t.value)
        num = parse_number(raw_value)
        if num is not None:
            r.value, _ = self.field(num, search=raw_value.replace(",", ""), anchor=hit, kind=float)
            if not re.fullmatch(r"-?\d+(\.\d+)?", raw_value.replace(",", "")):
                r.value_text, _ = self.field(raw_value, anchor=hit)
        elif raw_value:
            r.value_text, _ = self.field(raw_value, anchor=hit)
        r.unit, _ = self.field(t.unit, anchor=hit)
        r.reference_range, _ = self.field(t.reference_range, anchor=hit)
        flag = clean(t.flag).upper()
        if flag in ("H", "L", "HIGH", "LOW", "HH", "LL", "*"):
            r.printed_flag, _ = self.field(flag[0] if flag != "*" else "*", search=flag, anchor=hit)
        return r

    def med(self, m) -> MedicationItem:
        item = MedicationItem()
        item.name, hit = self.field(m.name)
        item.strength, _ = self.field(m.strength, anchor=hit)
        item.dosage, _ = self.field(m.dosage, anchor=hit)
        item.timing, _ = self.field(m.timing, anchor=hit)
        item.duration, _ = self.field(m.duration, anchor=hit)
        item.instructions, _ = self.field(m.instructions, anchor=hit)
        form = detect_form(m.name)
        if form:
            item.form = Field[str](value=form, confidence=item.name.confidence, source_box=item.name.source_box)
        return item


FORMS = {
    "tab": "tablet", "tablet": "tablet", "cap": "capsule", "capsule": "capsule", "syp": "syrup", "syrup": "syrup",
    "inj": "injection", "injection": "injection", "sachet": "sachet", "sach": "sachet", "drop": "drops", "drops": "drops",
    "oint": "ointment", "ointment": "ointment", "cream": "cream", "gel": "gel", "susp": "suspension", "inh": "inhaler",
    "ors": "sachet", "powder": "powder", "spray": "spray",
}


def detect_form(name: str) -> str | None:
    words = clean(name).lower().replace(".", " ").split()
    for w in words[:2]:
        if w in FORMS:
            return FORMS[w]
    return None


def lift(doc_type: str, raw, pages: list[PageData], meta: ExtractionMeta):
    lf = Lifter(pages, retried=meta.attempts > 1, low=meta.low_confidence)
    if doc_type == "lab_report":
        return LabReport(
            patient=lf.patient(raw.patient_name, raw.age, raw.sex, raw.patient_id),
            facility=lf.text(raw.facility),
            referring_doctor=lf.text(raw.referring_doctor),
            pathologist=lf.text(raw.pathologist),
            collected_on=lf.date(raw.collected_date),
            reported_on=lf.date(raw.report_date),
            results=[lf.lab(t) for t in raw.tests if clean(t.name) and clean(t.value)],
            meta=meta,
        )
    if doc_type == "prescription":
        return Prescription(
            patient=lf.patient(raw.patient_name, raw.age, raw.sex),
            prescriber=lf.text(raw.doctor_name),
            prescriber_registration=lf.text(raw.doctor_registration),
            facility=lf.text(raw.clinic),
            date=lf.date(raw.date),
            complaints=lf.texts(raw.complaints),
            diagnoses=lf.texts(raw.diagnoses),
            medications=[lf.med(m) for m in raw.medicines if clean(m.name)],
            advice=lf.texts(raw.advice),
            follow_up=lf.text(raw.follow_up),
            is_handwritten=bool(raw.handwritten),
            meta=meta,
        )
    return DischargeSummary(
        patient=lf.patient(raw.patient_name, raw.age, raw.sex, raw.patient_id),
        facility=lf.text(raw.hospital),
        attending_doctor=lf.text(raw.doctor),
        admission_date=lf.date(raw.admission_date),
        discharge_date=lf.date(raw.discharge_date),
        diagnoses=lf.texts(raw.diagnoses),
        presenting_complaints=lf.texts(raw.presenting_complaints),
        hospital_course=lf.text(raw.hospital_course),
        procedures=lf.texts(raw.procedures),
        investigations=[lf.lab(t) for t in raw.investigations if clean(t.name) and clean(t.value)],
        discharge_medications=[lf.med(m) for m in raw.discharge_medicines if clean(m.name)],
        follow_up=lf.text(raw.follow_up),
        advice=lf.texts(raw.advice),
        meta=meta,
    )
