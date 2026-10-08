import datetime as dt
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field as PField

T = TypeVar("T")

DocumentType = Literal["lab_report", "prescription", "discharge_summary"]
Flag = Literal["low", "normal", "high", "critical", "unknown"]


class SourceBox(BaseModel):
    page: int = 0
    x0: float
    y0: float
    x1: float
    y1: float


class Field(BaseModel, Generic[T]):
    value: T | None = None
    confidence: float = PField(default=0.0, ge=0.0, le=1.0)
    source_box: SourceBox | None = None
    needs_confirmation: bool = False
    confirmed: bool = False
    reasons: list[str] = []
    original_value: Any = None


class PatientInfo(BaseModel):
    name: Field[str] = Field[str]()
    age_years: Field[int] = Field[int]()
    sex: Field[str] = Field[str]()
    identifier: Field[str] = Field[str]()


class NormalizedLab(BaseModel):
    canonical_name: str | None = None
    loinc: str | None = None
    panel: str | None = None
    value: float | None = None
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    range_source: Literal["printed", "reference_table", "none"] = "none"
    flag: Flag = "unknown"
    conversion: str | None = None
    match_score: float = 0.0


class LabResult(BaseModel):
    test_name: Field[str] = Field[str]()
    value: Field[float] = Field[float]()
    value_text: Field[str] = Field[str]()
    unit: Field[str] = Field[str]()
    reference_range: Field[str] = Field[str]()
    printed_flag: Field[str] = Field[str]()
    normalized: NormalizedLab | None = None


class Dosage(BaseModel):
    morning: float = 0
    afternoon: float = 0
    evening: float = 0
    night: float = 0
    dose_quantity: float | None = None
    dose_unit: str | None = None
    frequency: int | None = None
    period: float = 1
    period_unit: Literal["h", "d", "wk", "mo"] = "d"
    as_needed: bool = False
    when: list[str] = []
    duration_value: float | None = None
    duration_unit: Literal["d", "wk", "mo"] | None = None
    continue_indefinitely: bool = False
    single_dose: bool = False
    unparsed: list[str] = []
    conflicts: list[str] = []
    text: str = ""


class NormalizedMedication(BaseModel):
    brand: str | None = None
    generic: str | None = None
    strength: str | None = None
    form: str | None = None
    drug_class: str | None = None
    matched: bool = False
    match_score: float = 0.0
    dosage: Dosage | None = None


class MedicationItem(BaseModel):
    name: Field[str] = Field[str]()
    form: Field[str] = Field[str]()
    strength: Field[str] = Field[str]()
    dosage: Field[str] = Field[str]()
    timing: Field[str] = Field[str]()
    duration: Field[str] = Field[str]()
    instructions: Field[str] = Field[str]()
    normalized: NormalizedMedication | None = None


class ExtractionMeta(BaseModel):
    model: str = ""
    attempts: int = 0
    method: Literal["vision", "text", "rules"] = "vision"
    validation_errors: list[str] = []
    low_confidence: bool = False
    duration_s: float = 0.0


class LabReport(BaseModel):
    document_type: Literal["lab_report"] = "lab_report"
    patient: PatientInfo = PatientInfo()
    facility: Field[str] = Field[str]()
    referring_doctor: Field[str] = Field[str]()
    pathologist: Field[str] = Field[str]()
    collected_on: Field[dt.date] = Field[dt.date]()
    reported_on: Field[dt.date] = Field[dt.date]()
    results: list[LabResult] = []
    meta: ExtractionMeta = ExtractionMeta()


class Prescription(BaseModel):
    document_type: Literal["prescription"] = "prescription"
    patient: PatientInfo = PatientInfo()
    prescriber: Field[str] = Field[str]()
    prescriber_registration: Field[str] = Field[str]()
    facility: Field[str] = Field[str]()
    date: Field[dt.date] = Field[dt.date]()
    complaints: list[Field[str]] = []
    diagnoses: list[Field[str]] = []
    medications: list[MedicationItem] = []
    advice: list[Field[str]] = []
    follow_up: Field[str] = Field[str]()
    is_handwritten: bool = False
    meta: ExtractionMeta = ExtractionMeta()


class DischargeSummary(BaseModel):
    document_type: Literal["discharge_summary"] = "discharge_summary"
    patient: PatientInfo = PatientInfo()
    facility: Field[str] = Field[str]()
    attending_doctor: Field[str] = Field[str]()
    admission_date: Field[dt.date] = Field[dt.date]()
    discharge_date: Field[dt.date] = Field[dt.date]()
    diagnoses: list[Field[str]] = []
    presenting_complaints: list[Field[str]] = []
    hospital_course: Field[str] = Field[str]()
    procedures: list[Field[str]] = []
    investigations: list[LabResult] = []
    discharge_medications: list[MedicationItem] = []
    follow_up: Field[str] = Field[str]()
    advice: list[Field[str]] = []
    meta: ExtractionMeta = ExtractionMeta()


Extraction = LabReport | Prescription | DischargeSummary
MODELS: dict[str, type[BaseModel]] = {
    "lab_report": LabReport,
    "prescription": Prescription,
    "discharge_summary": DischargeSummary,
}


def parse_extraction(data: dict) -> LabReport | Prescription | DischargeSummary:
    return MODELS[data["document_type"]].model_validate(data)


def document_date(ex) -> dt.date | None:
    if isinstance(ex, LabReport):
        return ex.collected_on.value or ex.reported_on.value
    if isinstance(ex, Prescription):
        return ex.date.value
    if isinstance(ex, DischargeSummary):
        return ex.discharge_date.value or ex.admission_date.value
    return None


def lab_results(ex) -> list[LabResult]:
    if isinstance(ex, LabReport):
        return ex.results
    if isinstance(ex, DischargeSummary):
        return ex.investigations
    return []


def medications(ex) -> list[MedicationItem]:
    if isinstance(ex, Prescription):
        return ex.medications
    if isinstance(ex, DischargeSummary):
        return ex.discharge_medications
    return []
