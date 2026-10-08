import copy
from datetime import datetime, timezone

from app.fhir.builder import NRCES, urn, validate_bundle
from app.fhir.codes import COMPOSITION_PROFILE, COMPOSITION_TYPE, SECTION_CODES, SNOMED


def _refs(entries: list[dict], rtype: str, typed: bool = False, where=None) -> list[dict]:
    out = []
    for e in entries:
        r = e["resource"]
        if r["resourceType"] == rtype and (where is None or where(r)):
            ref = {"reference": e["fullUrl"]}
            if typed:
                ref["type"] = rtype
            out.append(ref)
    return out


def _section(key: str, title: str, entries: list[dict]) -> dict | None:
    if not entries:
        return None
    code, display = SECTION_CODES[key]
    return {"title": title, "code": {"coding": [{"system": SNOMED, "code": code, "display": display}], "text": display}, "entry": entries}


def _is_complaint(condition: dict) -> bool:
    return any(c.get("code") == "409586006" for cat in condition.get("category", []) for c in cat.get("coding", []))


def _documentreference_to_binary(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        r = e["resource"]
        if r["resourceType"] != "DocumentReference":
            out.append(e)
            continue
        attachment = (r.get("content") or [{}])[0].get("attachment", {})
        if not attachment.get("data"):
            out.append(e)
            continue
        binary = {"resourceType": "Binary", "id": r["id"], "meta": {"profile": [f"{NRCES}/Binary"]},
                  "contentType": attachment.get("contentType") or "application/octet-stream", "data": attachment["data"]}
        out.append({"fullUrl": e["fullUrl"], "resource": binary})
    return out


def _sections(document_type: str, entries: list[dict]) -> list[dict]:
    if document_type == "prescription":
        items = _refs(entries, "MedicationRequest", typed=True) + _refs(entries, "Binary", typed=True)[:1]
        sections = [_section("prescription", "Prescription record", items)]
    elif document_type == "lab_report":
        items = _refs(entries, "DiagnosticReport", typed=True)[:1] + _refs(entries, "DocumentReference", typed=True)[:1]
        sections = [_section("lab_report", "Laboratory report", items)]
    else:
        sections = [
            _section("chief_complaints", "Chief complaints", _refs(entries, "Condition", where=_is_complaint)),
            _section("investigations", "Investigations", _refs(entries, "DiagnosticReport")),
            _section("medications", "Medications", _refs(entries, "MedicationRequest")),
            _section("discharge_document", "Document reference", _refs(entries, "DocumentReference")),
        ]
    return [s for s in sections if s]


def to_document_bundle(bundle: dict, document_type: str, title: str | None = None) -> dict:
    b = copy.deepcopy(bundle)
    entries = b.get("entry", [])
    if document_type == "prescription":
        entries = _documentreference_to_binary(entries)
    patient = next((e for e in entries if e["resource"]["resourceType"] == "Patient"), None)
    authors = [e for e in entries if e["resource"]["resourceType"] in ("Practitioner", "Organization")]
    encounter = next((e for e in entries if e["resource"]["resourceType"] == "Encounter"), None)
    code, display = COMPOSITION_TYPE[document_type]
    comp_url = urn("composition", b.get("identifier", {}).get("value", b.get("id")))
    composition = {
        "resourceType": "Composition",
        "id": comp_url.split(":")[-1],
        "meta": {"profile": [f"{NRCES}/{COMPOSITION_PROFILE[document_type]}"]},
        "status": "final",
        "type": {"coding": [{"system": SNOMED, "code": code, "display": display}], "text": display},
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": title or display,
        "author": [{"reference": a["fullUrl"]} for a in authors] or [{"display": "ByteXL (patient-uploaded record)"}],
        "section": _sections(document_type, entries),
    }
    if patient:
        composition["subject"] = {"reference": patient["fullUrl"]}
    if encounter:
        composition["encounter"] = {"reference": encounter["fullUrl"]}
    b["type"] = "document"
    b["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    b["meta"] = {**b.get("meta", {}), "versionId": b.get("meta", {}).get("versionId", "1"), "profile": [f"{NRCES}/DocumentBundle"]}
    b["entry"] = [{"fullUrl": comp_url, "resource": composition}] + entries
    return validate_bundle(b)
