from datetime import date

from app.config import get_settings
from app.normalize.confirm import get_field
from app.normalize.reconcile import MedEntry, active_medications, reconcile
from app.pipeline import load_extraction, rebuild
from app.schemas import DischargeSummary, LabReport, Prescription, lab_results, medications
from app.store import get_repository

TYPE_TITLE = {"lab_report": "Lab report", "prescription": "Prescription", "discharge_summary": "Discharge summary"}


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def timeline(patient_id: str, doc_type: str | None = None) -> list[dict]:
    repo = get_repository()
    docs = repo.find("documents", {"patient_id": patient_id})
    out = []
    for d in docs:
        if doc_type and d.get("document_type") != doc_type:
            continue
        ex = load_extraction(d) if d.get("extraction") else None
        item = {
            "document_id": d["_id"],
            "date": d.get("document_date"),
            "document_type": d.get("document_type"),
            "title": TYPE_TITLE.get(d.get("document_type"), "Document"),
            "source": None,
            "filename": d.get("filename"),
            "status": d.get("status", {}),
            "highlights": [],
            "abnormal": [],
            "abnormal_count": 0,
            "pending_confirmations": len(d.get("confirm_queue") or []),
        }
        if isinstance(ex, LabReport):
            item["source"] = ex.facility.value
        elif isinstance(ex, Prescription):
            item["source"] = ex.prescriber.value or ex.facility.value
            item["highlights"] = [m.normalized.generic if m.normalized and m.normalized.generic else m.name.value for m in ex.medications][:6]
            item["highlights"] = [h for h in item["highlights"] if h]
            item["diagnoses"] = [c.value for c in ex.diagnoses if c.value]
        elif isinstance(ex, DischargeSummary):
            item["source"] = ex.facility.value
            item["diagnoses"] = [c.value for c in ex.diagnoses if c.value]
            item["highlights"] = item["diagnoses"][:3]
        if ex is not None:
            for r in lab_results(ex):
                n = r.normalized
                if n and n.flag in ("low", "high", "critical"):
                    item["abnormal"].append({"name": n.canonical_name or r.test_name.value, "value": r.value.value, "unit": r.unit.value, "flag": n.flag})
            item["abnormal_count"] = len(item["abnormal"])
            if isinstance(ex, LabReport):
                item["highlights"] = [f"{a['name']} {a['flag']}" for a in item["abnormal"]][:6]
        out.append(item)
    out.sort(key=lambda x: (x["date"] or "0000", x["document_id"]), reverse=True)
    return out


def trends(patient_id: str, loinc: str) -> dict:
    repo = get_repository()
    rows = repo.find("observations_index", {"patient_id": patient_id, "loinc": loinc})
    rows.sort(key=lambda r: r.get("date") or "")
    from app.normalize.labs import by_loinc

    ref = by_loinc(loinc)
    return {
        "loinc": loinc,
        "name": ref.canonical_name if ref else (rows[0]["name"] if rows else loinc),
        "unit": rows[-1]["unit"] if rows else (ref.unit if ref else None),
        "ref_low": rows[-1]["ref_low"] if rows else None,
        "ref_high": rows[-1]["ref_high"] if rows else None,
        "points": [{"date": r["date"], "value": r["value"], "flag": r["flag"], "document_id": r["document_id"],
                    "ref_low": r.get("ref_low"), "ref_high": r.get("ref_high")} for r in rows],
    }


def available_trends(patient_id: str) -> list[dict]:
    rows = get_repository().find("observations_index", {"patient_id": patient_id})
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["loinc"], {"loinc": r["loinc"], "name": r["name"], "count": 0, "latest_flag": None, "latest_date": ""})
        g["count"] += 1
        if (r.get("date") or "") >= g["latest_date"]:
            g["latest_date"] = r.get("date") or ""
            g["latest_flag"] = r.get("flag")
    return sorted(groups.values(), key=lambda g: (-g["count"], g["name"]))


def medication_entries(patient_id: str) -> list[MedEntry]:
    entries = []
    for d in get_repository().find("documents", {"patient_id": patient_id}):
        ex = load_extraction(d) if d.get("extraction") else None
        if ex is None:
            continue
        for i, m in enumerate(medications(ex)):
            entries.append(MedEntry(d["_id"], ex.document_type, _date(d.get("document_date")), m, i))
    return entries


def as_of_date(entries: list[MedEntry]) -> date:
    if get_settings().reconcile_as_of == "today":
        return date.today()
    dates = [e.document_date for e in entries if e.document_date]
    return max(dates) if dates else date.today()


def medications_view(patient_id: str) -> dict:
    entries = medication_entries(patient_id)
    as_of = as_of_date(entries)
    active = active_medications(entries, as_of)
    notes = reconcile(entries, as_of)
    return {
        "as_of": as_of.isoformat(),
        "active": [{
            "document_id": e.document_id,
            "document_type": e.document_type,
            "date": e.document_date.isoformat() if e.document_date else None,
            "name": e.item.name.value,
            "generic": e.item.normalized.generic if e.item.normalized else None,
            "how_to_take": e.item.normalized.dosage.text if e.item.normalized and e.item.normalized.dosage else None,
            "as_written": " ".join(x for x in (e.item.dosage.value, e.item.timing.value, e.item.duration.value) if x),
        } for e in active],
        "reconciliation_notes": [n.to_dict() for n in notes],
    }


def coerce(path: str, current, value):
    from app.extract.parse import parse_date, parse_number

    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    leaf = path.split(".")[-1]
    if isinstance(current, date) or leaf.endswith(("_on", "_date")) or leaf == "date":
        return parse_date(str(value))
    if isinstance(current, int) and not isinstance(current, bool) or leaf == "age_years":
        n = parse_number(str(value))
        return int(n) if n is not None else None
    if isinstance(current, float) or leaf == "value":
        return parse_number(str(value))
    return str(value).strip()


def confirm(doc_id: str, items: list[dict]) -> dict:
    repo = get_repository()
    doc = repo.get("documents", doc_id)
    ex = load_extraction(doc)
    for it in items:
        f = get_field(ex, it["path"])
        if it.get("action") == "edit":
            new = coerce(it["path"], f.value, it.get("value"))
            if f.original_value is None:
                f.original_value = f.value.isoformat() if hasattr(f.value, "isoformat") else f.value
            f.value = new
        f.confirmed = True
        f.needs_confirmation = False
        f.confidence = 1.0
        f.reasons = []
    return rebuild(doc_id, ex)



def set_handwritten(doc_id: str, value: bool) -> dict:
    doc = get_repository().get("documents", doc_id)
    ex = load_extraction(doc)
    if not isinstance(ex, Prescription):
        raise ValueError("Only prescriptions can be marked as handwritten.")
    ex.is_handwritten = value
    return rebuild(doc_id, ex)
