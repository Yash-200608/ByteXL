import json
import uuid
from datetime import date, datetime, timezone

from fhir.resources.R4B.bundle import Bundle

from app.fhir.codes import (
    ABHA_ADDRESS_SYSTEM,
    ABHA_SYSTEM,
    DOC_TYPE_LOINC,
    GENERIC_SYSTEM,
    INTERPRETATION,
    LOINC,
    NRCES,
    UCUM,
    UCUM_CODES,
    UCUM_TIME,
)
from app.schemas import DischargeSummary, LabReport, LabResult, MedicationItem, Prescription, document_date

NS = uuid.UUID("6b1f3c0e-7f2a-4d55-9a57-0c7f4b2b9e11")


def urn(*parts) -> str:
    return f"urn:uuid:{uuid.uuid5(NS, '|'.join(str(p) for p in parts))}"


def _rid(full_url: str) -> str:
    return full_url.split(":")[-1]


def _meta(profile: str) -> dict:
    return {"profile": [f"{NRCES}/{profile}"]}


def _iso(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if isinstance(d, (date, datetime)) else str(d)


class BundleBuilder:
    def __init__(self, document: dict, patient: dict, extraction):
        self.doc = document
        self.patient = patient
        self.ex = extraction
        self.entries: list[dict] = []
        self.doc_id = document["_id"]
        self.when = _iso(document_date(extraction)) or (document.get("created_at") or "")[:10] or None

    def add(self, resource: dict, full_url: str) -> str:
        resource.setdefault("id", _rid(full_url))
        self.entries.append({"fullUrl": full_url, "resource": resource})
        return full_url

    def ref(self, full_url: str, display: str | None = None) -> dict:
        r = {"reference": full_url}
        if display:
            r["display"] = display
        return r

    def patient_resource(self) -> str:
        p = self.patient
        identifiers = []
        if p.get("abha_number"):
            identifiers.append({
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR", "display": "Medical record number"}], "text": "ABHA Number"},
                "system": ABHA_SYSTEM,
                "value": p["abha_number"],
            })
        if p.get("abha_address"):
            identifiers.append({"type": {"text": "ABHA Address"}, "system": ABHA_ADDRESS_SYSTEM, "value": p["abha_address"]})
        pid = self.ex.patient.identifier.value
        if pid:
            identifiers.append({"type": {"text": "Facility patient ID"}, "system": "urn:bytexl:facility-patient-id", "value": pid})
        res = {
            "resourceType": "Patient",
            "meta": _meta("Patient"),
            "identifier": identifiers or None,
            "name": [{"text": p.get("name") or self.ex.patient.name.value or "Unknown"}],
            "gender": p.get("sex") or self.ex.patient.sex.value or "unknown",
        }
        if p.get("birth_year"):
            res["birthDate"] = str(p["birth_year"])
        return self.add(res, urn("patient", p["_id"]))

    def practitioner(self, name: str | None, registration: str | None = None) -> str | None:
        if not name:
            return None
        res = {"resourceType": "Practitioner", "meta": _meta("Practitioner"), "name": [{"text": name}]}
        if registration:
            res["identifier"] = [{"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MD"}], "text": "Medical registration"},
                                  "system": "https://doctor.ndhm.gov.in", "value": registration}]
        return self.add(res, urn("practitioner", name.lower().strip(), registration or ""))

    def organization(self, name: str | None) -> str | None:
        if not name:
            return None
        return self.add({"resourceType": "Organization", "meta": _meta("Organization"), "name": name}, urn("organization", name.lower().strip()))

    def encounter(self, klass: str, start, end, practitioner: str | None, org: str | None, pat: str) -> str:
        codes = {"AMB": "ambulatory", "IMP": "inpatient encounter"}
        res = {
            "resourceType": "Encounter",
            "meta": _meta("Encounter"),
            "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": klass, "display": codes[klass]},
            "subject": self.ref(pat),
        }
        period = {k: v for k, v in (("start", _iso(start)), ("end", _iso(end))) if v}
        if period:
            res["period"] = period
        if practitioner:
            res["participant"] = [{"individual": self.ref(practitioner)}]
        if org:
            res["serviceProvider"] = self.ref(org)
        return self.add(res, urn("encounter", self.doc_id))

    def observation(self, r: LabResult, i: int, pat: str, effective, performer: list[str]) -> str | None:
        n = r.normalized
        name = r.test_name.value
        if not name:
            return None
        code = {"text": name}
        if n and n.loinc:
            code["coding"] = [{"system": LOINC, "code": n.loinc, "display": n.canonical_name}]
        res = {
            "resourceType": "Observation",
            "meta": _meta("Observation"),
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory", "display": "Laboratory"}]}],
            "code": code,
            "subject": self.ref(pat),
        }
        if effective:
            res["effectiveDateTime"] = _iso(effective)
        if performer:
            res["performer"] = [self.ref(p) for p in performer]
        value = n.value if n and n.value is not None else r.value.value
        unit = (n.unit if n and n.value is not None else r.unit.value) or None
        if value is not None:
            q = {"value": value}
            if unit:
                q["unit"] = unit
                if unit in UCUM_CODES:
                    q["system"] = UCUM
                    q["code"] = UCUM_CODES[unit]
            res["valueQuantity"] = q
        elif r.value_text.value:
            res["valueString"] = r.value_text.value
        if n and n.conversion:
            res["note"] = [{"text": f"As printed: {r.value.value:g} {r.unit.value or ''}".strip()}]
        rr = {}
        if n and n.ref_low is not None:
            rr["low"] = {"value": n.ref_low, **({"unit": n.unit} if n.unit else {})}
        if n and n.ref_high is not None:
            rr["high"] = {"value": n.ref_high, **({"unit": n.unit} if n.unit else {})}
        if r.reference_range.value:
            rr["text"] = r.reference_range.value
        if rr:
            res["referenceRange"] = [rr]
        if n and n.flag in INTERPRETATION:
            code_ = INTERPRETATION[n.flag]
            if n.flag == "critical":
                code_ = ("HH", "Critical high") if n.ref_high is not None and value is not None and value > n.ref_high else ("LL", "Critical low")
            res["interpretation"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": code_[0], "display": code_[1]}], "text": n.flag}]
        return self.add(res, urn("observation", self.doc_id, i))

    def diagnostic_report(self, results: list[LabResult], pat: str, effective, issued, performers: list[str], enc: str | None) -> str | None:
        obs = [o for i, r in enumerate(results) if (o := self.observation(r, i, pat, effective, performers))]
        if not obs:
            return None
        res = {
            "resourceType": "DiagnosticReport",
            "meta": _meta("DiagnosticReportLab"),
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "LAB", "display": "Laboratory"}]}],
            "code": {"coding": [{"system": LOINC, "code": "11502-2", "display": "Laboratory report"}], "text": "Laboratory report"},
            "subject": self.ref(pat),
            "result": [self.ref(o) for o in obs],
        }
        if effective:
            res["effectiveDateTime"] = _iso(effective)
        if issued:
            res["issued"] = f"{_iso(issued)}T00:00:00+05:30"
        if performers:
            res["performer"] = [self.ref(p) for p in performers]
        if enc:
            res["encounter"] = self.ref(enc)
        return self.add(res, urn("diagnosticreport", self.doc_id))

    def medication_request(self, m: MedicationItem, i: int, pat: str, requester: str | None, authored, enc: str | None) -> str | None:
        if not m.name.value:
            return None
        n = m.normalized
        concept = {"text": m.name.value}
        if n and n.generic:
            concept["coding"] = [{"system": GENERIC_SYSTEM, "code": n.generic, "display": n.generic}]
        dose = {}
        raw = " ".join(x for x in (m.dosage.value, m.timing.value, m.duration.value, m.instructions.value) if x)
        d = n.dosage if n else None
        dose["text"] = raw or (d.text if d else "")
        if d:
            if d.text:
                dose["patientInstruction"] = d.text
            repeat = {}
            if d.frequency:
                repeat["frequency"] = d.frequency
                repeat["period"] = d.period
                repeat["periodUnit"] = d.period_unit
            if d.single_dose:
                repeat["count"] = 1
            if d.when:
                repeat["when"] = d.when
            if d.duration_value:
                repeat["boundsDuration"] = {"value": d.duration_value, "unit": {"d": "days", "wk": "weeks", "mo": "months"}[d.duration_unit],
                                            "system": UCUM, "code": UCUM_TIME[d.duration_unit]}
            if repeat:
                dose["timing"] = {"repeat": repeat}
            if d.as_needed:
                dose["asNeededBoolean"] = True
            slot_values = {v for v in (d.morning, d.afternoon, d.evening, d.night) if v}
            qty = d.dose_quantity or (slot_values.pop() if len(slot_values) == 1 else None)
            if qty:
                unit = d.dose_unit or (n.form if n and n.form else None) or "unit"
                dose["doseAndRate"] = [{"doseQuantity": {"value": qty, "unit": unit}}]
        res = {
            "resourceType": "MedicationRequest",
            "meta": _meta("MedicationRequest"),
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": concept,
            "subject": self.ref(pat),
            "dosageInstruction": [dose],
        }
        if authored:
            res["authoredOn"] = _iso(authored)
        if requester:
            res["requester"] = self.ref(requester)
        if enc:
            res["encounter"] = self.ref(enc)
        return self.add(res, urn("medicationrequest", self.doc_id, i))

    def condition(self, text: str | None, i: int, pat: str, enc: str | None, recorded, kind: str) -> str | None:
        if not text:
            return None
        if kind == "complaint":
            category = {"coding": [{"system": "http://snomed.info/sct", "code": "409586006", "display": "Complaint"}], "text": "Presenting complaint"}
        else:
            category = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "encounter-diagnosis", "display": "Encounter Diagnosis"}]}
        res = {"resourceType": "Condition", "meta": _meta("Condition"), "category": [category], "code": {"text": text}, "subject": self.ref(pat)}
        if enc:
            res["encounter"] = self.ref(enc)
        if recorded:
            res["recordedDate"] = _iso(recorded)
        return self.add(res, urn("condition", self.doc_id, kind, i))

    def document_reference(self, pat: str, enc: str | None, authors: list[str], description: str | None) -> str:
        dtype = self.ex.document_type
        loinc, display = DOC_TYPE_LOINC[dtype]
        attachment = {
            "contentType": self.doc.get("content_type"),
            "url": f"/documents/{self.doc_id}/file",
            "title": self.doc.get("filename"),
        }
        if self.doc.get("sha1_b64"):
            attachment["hash"] = self.doc["sha1_b64"]
        if self.doc.get("size"):
            attachment["size"] = self.doc["size"]
        res = {
            "resourceType": "DocumentReference",
            "meta": _meta("DocumentReference"),
            "status": "current",
            "type": {"coding": [{"system": LOINC, "code": loinc, "display": display}], "text": display},
            "subject": self.ref(pat),
            "content": [{"attachment": attachment}],
        }
        if self.when:
            res["date"] = f"{self.when}T00:00:00+05:30"
        if authors:
            res["author"] = [self.ref(a) for a in authors]
        if description:
            res["description"] = description[:1000]
        if enc:
            res["context"] = {"encounter": [self.ref(enc)]}
        return self.add(res, urn("documentreference", self.doc_id))

    def build(self) -> dict:
        ex = self.ex
        pat = self.patient_resource()
        description = None
        authors: list[str] = []
        enc = None
        if isinstance(ex, LabReport):
            org = self.organization(ex.facility.value)
            path = self.practitioner(ex.pathologist.value)
            self.practitioner(ex.referring_doctor.value)
            performers = [p for p in (org, path) if p]
            self.diagnostic_report(ex.results, pat, ex.collected_on.value or ex.reported_on.value, ex.reported_on.value, performers, None)
            authors = performers
        elif isinstance(ex, Prescription):
            org = self.organization(ex.facility.value)
            doc = self.practitioner(ex.prescriber.value, ex.prescriber_registration.value)
            enc = self.encounter("AMB", ex.date.value, ex.date.value, doc, org, pat)
            for i, c in enumerate(ex.complaints):
                self.condition(c.value, i, pat, enc, ex.date.value, "complaint")
            for i, c in enumerate(ex.diagnoses):
                self.condition(c.value, i, pat, enc, ex.date.value, "diagnosis")
            for i, m in enumerate(ex.medications):
                self.medication_request(m, i, pat, doc, ex.date.value, enc)
            authors = [a for a in (doc, org) if a]
            description = "; ".join(a.value for a in ex.advice if a.value) or None
        elif isinstance(ex, DischargeSummary):
            org = self.organization(ex.facility.value)
            doc = self.practitioner(ex.attending_doctor.value)
            enc = self.encounter("IMP", ex.admission_date.value, ex.discharge_date.value, doc, org, pat)
            for i, c in enumerate(ex.presenting_complaints):
                self.condition(c.value, i, pat, enc, ex.admission_date.value, "complaint")
            for i, c in enumerate(ex.diagnoses):
                self.condition(c.value, i, pat, enc, ex.discharge_date.value, "diagnosis")
            self.diagnostic_report(ex.investigations, pat, ex.admission_date.value, None, [o for o in (org,) if o], enc)
            for i, m in enumerate(ex.discharge_medications):
                self.medication_request(m, i, pat, doc, ex.discharge_date.value, enc)
            authors = [a for a in (doc, org) if a]
            description = ex.hospital_course.value
        self.document_reference(pat, enc, authors, description)
        bundle = {
            "resourceType": "Bundle",
            "id": _rid(urn("bundle", self.doc_id)),
            "meta": {**_meta("DocumentBundle"), "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            "identifier": {"system": "urn:bytexl:document", "value": self.doc_id},
            "type": "collection",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entry": _dedupe(self.entries),
        }
        return validate_bundle(bundle)


def _dedupe(entries: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in entries:
        if e["fullUrl"] in seen:
            continue
        seen.add(e["fullUrl"])
        out.append(e)
    return out


def _strip_none(obj):
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_strip_none(v) for v in obj if v is not None]
    return obj


def validate_bundle(bundle: dict) -> dict:
    clean = _strip_none(bundle)
    parsed = Bundle.parse_obj(clean)
    return json.loads(parsed.json())


def build_bundle(document: dict, patient: dict, extraction) -> dict:
    return BundleBuilder(document, patient, extraction).build()


def merge_bundles(bundles: list[dict], patient_id: str) -> dict:
    entries = []
    for b in bundles:
        entries.extend(b.get("entry", []))
    bundle = {
        "resourceType": "Bundle",
        "id": _rid(urn("export", patient_id)),
        "meta": _meta("DocumentBundle"),
        "identifier": {"system": "urn:bytexl:patient-export", "value": patient_id},
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry": _dedupe(entries),
    }
    return validate_bundle(bundle)
