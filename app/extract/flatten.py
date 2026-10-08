from app.schemas import DischargeSummary, LabReport, Prescription


def _v(f):
    v = f.value
    if v is None:
        return "" if not isinstance(v, (int, float)) else None
    return v.isoformat() if hasattr(v, "isoformat") else v


def _lab(r):
    return {
        "test_name": _v(r.test_name),
        "value": r.value.value,
        "value_text": _v(r.value_text),
        "unit": _v(r.unit),
        "reference_range": _v(r.reference_range),
    }


def _med(m):
    return {
        "name": _v(m.name),
        "strength": _v(m.strength),
        "dosage": _v(m.dosage),
        "timing": _v(m.timing),
        "duration": _v(m.duration),
    }


def _patient(p):
    return {"name": _v(p.name), "age_years": p.age_years.value, "sex": _v(p.sex)}


def to_flat(ex) -> dict:
    if isinstance(ex, LabReport):
        return {
            "document_type": ex.document_type,
            "patient": _patient(ex.patient),
            "facility": _v(ex.facility),
            "referring_doctor": _v(ex.referring_doctor),
            "pathologist": _v(ex.pathologist),
            "collected_on": _v(ex.collected_on),
            "reported_on": _v(ex.reported_on),
            "results": [_lab(r) for r in ex.results],
        }
    if isinstance(ex, Prescription):
        return {
            "document_type": ex.document_type,
            "patient": _patient(ex.patient),
            "prescriber": _v(ex.prescriber),
            "prescriber_registration": _v(ex.prescriber_registration),
            "facility": _v(ex.facility),
            "date": _v(ex.date),
            "complaints": [_v(c) for c in ex.complaints],
            "diagnoses": [_v(d) for d in ex.diagnoses],
            "medications": [_med(m) for m in ex.medications],
            "advice": [_v(a) for a in ex.advice],
            "follow_up": _v(ex.follow_up),
        }
    if isinstance(ex, DischargeSummary):
        return {
            "document_type": ex.document_type,
            "patient": _patient(ex.patient),
            "facility": _v(ex.facility),
            "attending_doctor": _v(ex.attending_doctor),
            "admission_date": _v(ex.admission_date),
            "discharge_date": _v(ex.discharge_date),
            "diagnoses": [_v(d) for d in ex.diagnoses],
            "presenting_complaints": [_v(c) for c in ex.presenting_complaints],
            "hospital_course": _v(ex.hospital_course),
            "procedures": [_v(p) for p in ex.procedures],
            "investigations": [_lab(r) for r in ex.investigations],
            "discharge_medications": [_med(m) for m in ex.discharge_medications],
            "follow_up": _v(ex.follow_up),
            "advice": [_v(a) for a in ex.advice],
        }
    raise TypeError(type(ex))
