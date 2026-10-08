from app.normalize.labs import normalize_lab
from app.normalize.medicines import normalize_medication
from app.schemas import lab_results, medications


def normalize_extraction(ex, sex: str | None = None, age: int | None = None):
    sex = sex or ex.patient.sex.value
    age = age if age is not None else ex.patient.age_years.value
    for r in lab_results(ex):
        r.normalized = normalize_lab(r, sex, age)
    for m in medications(ex):
        m.normalized = normalize_medication(m)
    return ex
