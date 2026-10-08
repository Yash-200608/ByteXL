from pydantic import BaseModel

from app.config import get_settings
from app.schemas import DischargeSummary, Field, LabReport, LabResult, MedicationItem, Prescription

SKIP = {"normalized", "meta"}
LABELS = {
    "test_name": "Test", "value": "Result", "value_text": "Result", "unit": "Unit", "reference_range": "Reference range",
    "printed_flag": "Printed flag", "name": "Medicine", "dosage": "Dosage", "timing": "Timing", "duration": "Duration",
    "strength": "Strength", "instructions": "Instructions", "form": "Form",
}


def iter_fields(model: BaseModel, prefix: str = ""):
    for key in type(model).model_fields:
        if key in SKIP:
            continue
        value = getattr(model, key)
        path = f"{prefix}{key}"
        if isinstance(value, Field):
            yield path, value
        elif isinstance(value, BaseModel):
            yield from iter_fields(value, path + ".")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, Field):
                    yield f"{path}.{i}", item
                elif isinstance(item, BaseModel):
                    yield from iter_fields(item, f"{path}.{i}.")


def resolve_path(model, path: str):
    cur = model
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else getattr(cur, p)
    last = parts[-1]
    return cur, last


def get_field(model, path: str) -> Field:
    parent, last = resolve_path(model, path)
    f = parent[int(last)] if isinstance(parent, list) else getattr(parent, last)
    if not isinstance(f, Field):
        raise KeyError(path)
    return f


def _flag(f: Field, reason: str):
    if f.confirmed:
        return
    if reason not in f.reasons:
        f.reasons.append(reason)
    f.needs_confirmation = True


def _lab_rules(r: LabResult):
    n = r.normalized
    if r.test_name.value and (n is None or not n.loinc):
        _flag(r.test_name, "test name not recognised")
    if n is None:
        return
    printed = (r.printed_flag.value or "").upper()
    if printed in ("H", "L") and n.flag in ("low", "normal", "high"):
        expected = {"H": "high", "L": "low"}[printed]
        if n.flag != expected:
            _flag(r.value, f"printed flag {printed} disagrees with computed '{n.flag}'")
    if n.flag == "critical":
        _flag(r.value, "critical value — please verify against the report")


def _med_rules(m: MedicationItem, handwritten: bool):
    n = m.normalized
    if handwritten:
        _flag(m.name, "handwritten prescription — confirm medicine name")
        if m.dosage.value or (n and n.dosage and n.dosage.text):
            _flag(m.dosage, "handwritten prescription — confirm dosage")
    if m.name.value and (n is None or not n.matched):
        _flag(m.name, "medicine not recognised in the reference list")
    if n and n.dosage:
        if n.dosage.unparsed and m.dosage.value:
            _flag(m.dosage, "dosage not fully understood: " + " ".join(n.dosage.unparsed))
        for c in n.dosage.conflicts:
            _flag(m.dosage, c)
        if m.dosage.value and not (n.dosage.frequency or n.dosage.as_needed or n.dosage.single_dose):
            _flag(m.dosage, "frequency not understood")


def apply_confirmation_rules(ex, handwritten: bool = False) -> list[dict]:
    s = get_settings()
    for path, f in iter_fields(ex):
        if f.value is None or f.confirmed:
            continue
        if f.confidence < s.conf_low:
            _flag(f, f"low confidence ({f.confidence:.2f})")
        if "value not found in document text" in f.reasons:
            f.needs_confirmation = True
    if isinstance(ex, (LabReport, DischargeSummary)):
        for r in ex.results if isinstance(ex, LabReport) else ex.investigations:
            _lab_rules(r)
    if isinstance(ex, (Prescription, DischargeSummary)):
        meds = ex.medications if isinstance(ex, Prescription) else ex.discharge_medications
        hw = handwritten or (isinstance(ex, Prescription) and ex.is_handwritten)
        for m in meds:
            _med_rules(m, hw)
    return confirm_queue(ex)


def _label(ex, path: str) -> str:
    parts = path.split(".")
    leaf = LABELS.get(parts[-1], parts[-1].replace("_", " ").capitalize())
    if len(parts) >= 3 and parts[1].isdigit():
        try:
            parent = getattr(ex, parts[0])[int(parts[1])]
            name = getattr(parent, "test_name", None) or getattr(parent, "name", None)
            if name is not None and name.value:
                return f"{name.value} · {leaf}"
        except (AttributeError, IndexError):
            pass
    if parts[0] == "patient":
        return {"name": "Patient name", "age_years": "Patient age", "sex": "Patient sex", "identifier": "Patient ID"}.get(parts[-1], "Patient")
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0].replace('_', ' ').capitalize()} #{int(parts[1]) + 1}"
    return leaf


def confirm_queue(ex) -> list[dict]:
    out = []
    for path, f in iter_fields(ex):
        if f.needs_confirmation and not f.confirmed:
            out.append({
                "path": path,
                "label": _label(ex, path),
                "value": f.value.isoformat() if hasattr(f.value, "isoformat") else f.value,
                "confidence": f.confidence,
                "reasons": list(f.reasons),
                "source_box": f.source_box.model_dump() if f.source_box else None,
            })
    return out
