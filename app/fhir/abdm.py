import copy
from datetime import datetime, timezone

from app.fhir.builder import NRCES, urn, validate_bundle
from app.fhir.codes import COMPOSITION_PROFILE, DOC_TYPE_LOINC, LOINC

SECTION_TYPES = {
    "DiagnosticReport": ("Lab results", "11502-2"),
    "MedicationRequest": ("Medications", "10160-0"),
    "Condition": ("Problems and complaints", "11450-4"),
    "Encounter": ("Encounter", "46240-8"),
    "DocumentReference": ("Source document", "55107-7"),
}


def to_document_bundle(bundle: dict, document_type: str, title: str | None = None) -> dict:
    b = copy.deepcopy(bundle)
    entries = b.get("entry", [])
    patient = next((e for e in entries if e["resource"]["resourceType"] == "Patient"), None)
    authors = [e for e in entries if e["resource"]["resourceType"] in ("Practitioner", "Organization")]
    encounter = next((e for e in entries if e["resource"]["resourceType"] == "Encounter"), None)
    sections = []
    for rtype, (stitle, code) in SECTION_TYPES.items():
        refs = [{"reference": e["fullUrl"]} for e in entries if e["resource"]["resourceType"] == rtype]
        if refs:
            sections.append({"title": stitle, "code": {"coding": [{"system": LOINC, "code": code}]}, "entry": refs})
    loinc, display = DOC_TYPE_LOINC[document_type]
    comp_url = urn("composition", b.get("identifier", {}).get("value", b.get("id")))
    composition = {
        "resourceType": "Composition",
        "id": comp_url.split(":")[-1],
        "meta": {"profile": [f"{NRCES}/{COMPOSITION_PROFILE[document_type]}"]},
        "status": "final",
        "type": {"coding": [{"system": LOINC, "code": loinc, "display": display}], "text": display},
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": title or display,
        "author": [{"reference": a["fullUrl"]} for a in authors] or [{"display": "ByteXL (patient-uploaded record)"}],
        "section": sections,
    }
    if patient:
        composition["subject"] = {"reference": patient["fullUrl"]}
    if encounter:
        composition["encounter"] = {"reference": encounter["fullUrl"]}
    b["type"] = "document"
    b["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    b["entry"] = [{"fullUrl": comp_url, "resource": composition}] + entries
    return validate_bundle(b)
