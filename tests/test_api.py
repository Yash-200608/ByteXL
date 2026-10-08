import pytest

from app.patients import generate_abha_number, valid_abha_address, valid_abha_number, verhoeff_valid
from tests.conftest import SAMPLES
from tests.fakes import RX_PDF_LINES, router, text_pdf


@pytest.fixture
def api(client, fake_llm):
    fake_llm.handler = router()
    return client


@pytest.fixture
def patient(api):
    r = api.post("/patients", json={"name": "Rahul Sharma", "sex": "male", "birth_year": 1979})
    assert r.status_code == 201
    return r.json()


def upload(api, pid, name, data, ctype):
    r = api.post(f"/patients/{pid}/documents?sync=true", files={"file": (name, data, ctype)})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"]["state"] == "done", body["status"]
    return body


def test_mock_abha():
    for _ in range(50):
        n = generate_abha_number()
        assert valid_abha_number(n)
        assert verhoeff_valid(n.replace("-", ""))
    assert not valid_abha_number("91-1234-5678-901")
    assert valid_abha_address("rahul.sharma1234@abdm")
    assert not valid_abha_address("bad address@abdm")


def test_patient_creation_and_link(api, patient):
    assert valid_abha_number(patient["abha_number"])
    assert patient["abha_address"].endswith("@abdm")
    new = generate_abha_number()
    r = api.post(f"/patients/{patient['_id']}/abha/link", json={"abha_number": new, "abha_address": "rahul.s@abdm"})
    assert r.status_code == 200 and r.json()["abha_linked"] and r.json()["abha_number"] == new
    r = api.post(f"/patients/{patient['_id']}/abha/link", json={"abha_number": "12-3456-7890-1234"})
    assert r.status_code in (200, 422)
    assert api.post(f"/patients/{patient['_id']}/abha/link", json={"abha_number": "1234"}).status_code == 422
    assert api.get("/patients/nope").status_code == 404


def test_rejects_unsupported_file(api, patient):
    r = api.post(f"/patients/{patient['_id']}/documents", files={"file": ("x.gif", b"GIF89a....", "image/gif")})
    assert r.status_code == 415


def test_full_flow_lab_and_prescription(api, patient):
    pid = patient["_id"]
    lab = upload(api, pid, "lab_report_2024_03.pdf", (SAMPLES / "lab_report_2024_03.pdf").read_bytes(), "application/pdf")
    rx = upload(api, pid, "rx.pdf", text_pdf(RX_PDF_LINES), "application/pdf")
    assert lab["document_type"] == "lab_report"
    assert rx["document_type"] == "prescription"

    doc = api.get(f"/documents/{lab['id']}").json()
    hb = doc["extraction"]["results"][0]
    assert hb["test_name"]["value"] == "Haemoglobin"
    assert hb["value"]["source_box"] is not None and 0 < hb["value"]["confidence"] <= 1
    assert hb["normalized"]["flag"] == "low" and hb["normalized"]["loinc"] == "718-7"
    plt = doc["extraction"]["results"][2]
    assert plt["normalized"]["value"] == 240000

    rxdoc = api.get(f"/documents/{rx['id']}").json()
    paths = {q["path"] for q in rxdoc["confirm_queue"]}
    assert {"medications.0.name", "medications.0.dosage"} <= paths
    assert any("Handwritten" in w for w in rxdoc["warnings"])

    fhir = api.get(f"/documents/{lab['id']}/fhir").json()
    kinds = [e["resource"]["resourceType"] for e in fhir["entry"]]
    assert fhir["type"] == "collection"
    assert kinds.count("Observation") == 9 and "DiagnosticReport" in kinds and "DocumentReference" in kinds
    pat = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "Patient")
    assert pat["identifier"][0]["value"] == patient["abha_number"]
    obs = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "Observation")
    assert obs["interpretation"][0]["coding"][0]["code"] == "L"
    assert obs["referenceRange"][0]["low"]["value"] == 13.0

    rx_fhir = api.get(f"/documents/{rx['id']}/fhir").json()
    mr = [e["resource"] for e in rx_fhir["entry"] if e["resource"]["resourceType"] == "MedicationRequest"]
    assert len(mr) == 3
    glyco = mr[1]
    assert glyco["medicationCodeableConcept"]["coding"][0]["code"] == "metformin"
    rep = glyco["dosageInstruction"][0]["timing"]["repeat"]
    assert rep["frequency"] == 2 and rep["periodUnit"] == "d" and "PC" in rep["when"]
    assert rep["boundsDuration"]["value"] == 1 and rep["boundsDuration"]["code"] == "mo"
    assert mr[0]["dosageInstruction"][0]["asNeededBoolean"] is True

    abdm = api.get(f"/documents/{rx['id']}/fhir?profile=abdm").json()
    assert abdm["type"] == "document" and abdm["entry"][0]["resource"]["resourceType"] == "Composition"
    assert abdm["meta"]["versionId"] == "1" and abdm["meta"]["profile"][0].endswith("/DocumentBundle")
    sections = abdm["entry"][0]["resource"]["section"]
    assert len(sections) == 1 and sections[0]["code"]["coding"][0]["code"] == "440545006"
    assert {r["type"] for r in sections[0]["entry"]} == {"MedicationRequest", "Binary"}
    binary = next(e["resource"] for e in abdm["entry"] if e["resource"]["resourceType"] == "Binary")
    assert binary["data"] and binary["contentType"] == "application/pdf"
    prac = next(e["resource"] for e in abdm["entry"] if e["resource"]["resourceType"] == "Practitioner")
    assert prac["identifier"][0]["type"]["coding"][0]["code"] == "MD" and prac["identifier"][0]["value"] == "MMC 2009/03/5678"

    assert "profile" not in fhir.get("meta", {}) and fhir["meta"]["versionId"] == "1"
    dr = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "DiagnosticReport")
    assert dr["resultsInterpreter"] and dr["conclusion"].startswith("Software-computed flags, not a clinical interpretation.")
    assert "HbA1c (high)" in dr["conclusion"]
    hb = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "Observation" and e["resource"]["code"]["coding"][0]["code"] == "718-7")
    assert hb["code"]["coding"][0]["display"] == "Hemoglobin [Mass/volume] in Blood" and hb["code"]["text"] == "Haemoglobin"
    org = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "Organization")
    assert org["identifier"][0]["type"]["coding"][0]["code"] == "OIN"
    docref = next(e["resource"] for e in fhir["entry"] if e["resource"]["resourceType"] == "DocumentReference")
    assert docref["content"][0]["attachment"]["data"]
    lab_abdm = api.get(f"/documents/{lab['id']}/fhir?profile=abdm").json()
    lab_sections = lab_abdm["entry"][0]["resource"]["section"]
    assert len(lab_sections) == 1 and [r["type"] for r in lab_sections[0]["entry"]] == ["DiagnosticReport", "DocumentReference"]
    assert lab_abdm["entry"][0]["resource"]["type"]["coding"][0] == {"system": "http://snomed.info/sct", "code": "4241000179101", "display": "Laboratory report"}
    assert abdm["entry"][0]["resource"]["type"]["coding"][0]["code"] == "440545006"
    assert dr["category"][0]["coding"][0]["system"] == "http://snomed.info/sct"

    timeline = api.get(f"/patients/{pid}/timeline").json()
    assert [t["document_type"] for t in timeline] == ["prescription", "lab_report"]
    assert timeline[1]["abnormal_count"] == 6
    assert api.get(f"/patients/{pid}/timeline?type=lab_report").json()[0]["document_id"] == lab["id"]

    trend = api.get(f"/patients/{pid}/trends/4548-4").json()
    assert trend["points"][0]["value"] == 7.2 and trend["points"][0]["flag"] == "high"
    assert any(t["loinc"] == "4548-4" for t in api.get(f"/patients/{pid}/trends").json())

    export = api.get(f"/patients/{pid}/export").json()
    patients = [e for e in export["entry"] if e["resource"]["resourceType"] == "Patient"]
    assert len(patients) == 1
    assert sum(1 for e in export["entry"] if e["resource"]["resourceType"] == "Observation") == 9

    summary = api.get(f"/documents/{lab['id']}/summary?lang=en").json()
    assert summary["disclaimer"].startswith("This summary was generated by software")
    assert {o["name"] for o in summary["out_of_range"]} >= {"HbA1c", "Haemoglobin", "LDL Cholesterol"}


def test_confirm_updates_bundle_and_index(api, patient):
    pid = patient["_id"]
    lab = upload(api, pid, "lab.pdf", (SAMPLES / "lab_report_2024_03.pdf").read_bytes(), "application/pdf")
    did = lab["id"]
    api.get(f"/documents/{did}/summary?lang=en")
    r = api.post(f"/documents/{did}/confirm", json={"items": [{"path": "results.4.value", "action": "edit", "value": "5.4"}]})
    assert r.status_code == 200, r.text
    res = r.json()["extraction"]["results"][4]
    assert res["value"]["value"] == 5.4 and res["value"]["confirmed"] and res["value"]["original_value"] == 7.2
    assert res["normalized"]["flag"] == "normal"
    trend = api.get(f"/patients/{pid}/trends/4548-4").json()
    assert trend["points"][0]["value"] == 5.4
    fhir = api.get(f"/documents/{did}/fhir").json()
    hba1c = [e["resource"] for e in fhir["entry"] if e["resource"].get("code", {}).get("text") == "HbA1c"][0]
    assert hba1c["valueQuantity"]["value"] == 5.4 and hba1c["interpretation"][0]["coding"][0]["code"] == "N"
    s = api.get(f"/documents/{did}/summary?lang=en").json()
    assert "HbA1c" not in {o["name"] for o in s["out_of_range"]}
    assert api.post(f"/documents/{did}/confirm", json={"items": [{"path": "results.99.value"}]}).status_code == 422


def test_medications_reconciliation(api, patient, fake_llm):
    pid = patient["_id"]
    upload(api, pid, "rx1.pdf", text_pdf(RX_PDF_LINES), "application/pdf")
    lines2 = [l.replace("22/9/24", "25/9/24").replace("Tab Dolo 650   SOS  for fever  x 3 days", "Tab Gluconorm 500  1-0-1  x 1 month") for l in RX_PDF_LINES]
    fake_llm.handler = router(rx={**__import__("tests.fakes", fromlist=["RX"]).RX, "date": "25/9/24",
                                  "medicines": [{"name": "Tab Gluconorm 500", "strength": "500", "dosage": "1-0-1", "timing": "", "duration": "x 1 month", "instructions": ""}]})
    upload(api, pid, "rx2.pdf", text_pdf(lines2), "application/pdf")
    meds = api.get(f"/patients/{pid}/medications").json()
    assert meds["as_of"] == "2024-09-25"
    notes = meds["reconciliation_notes"]
    assert [n["generic"] for n in notes] == ["metformin"]
    assert "ask your doctor" in notes[0]["text"].lower()


def test_pipeline_survives_ollama_down(api, patient, fake_llm):
    from app.llm.client import LLMUnavailable

    def down(*a, **k):
        raise LLMUnavailable("connection refused")

    fake_llm.handler = down
    lab = upload(api, patient["_id"], "lab.pdf", (SAMPLES / "lab_report_2024_03.pdf").read_bytes(), "application/pdf")
    doc = api.get(f"/documents/{lab['id']}").json()
    assert doc["extraction"]["meta"]["method"] == "rules"
    assert any("fallback" in w for w in doc["warnings"])
    s = api.get(f"/documents/{lab['id']}/summary?lang=hi").json()
    assert s["method"] == "template" and "डॉक्टर" in s["disclaimer"]


@pytest.mark.slow
def test_full_flow_image_prescription(api, patient):
    data = (SAMPLES / "prescription_handwritten_2024_09.png").read_bytes()
    rx = upload(api, patient["_id"], "rx.png", data, "image/png")
    assert rx["document_type"] == "prescription"
    assert rx["pages"][0]["source"] == "ocr"
    assert len(rx["extraction"]["medications"]) == 3
    r = api.get(f"/documents/{rx['id']}/pages/0")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_mark_handwritten_forces_confirmation(api, patient, fake_llm):
    from tests.fakes import RX

    fake_llm.handler = router(rx={**RX, "handwritten": False})
    rx = upload(api, patient["_id"], "rx.pdf", text_pdf(RX_PDF_LINES), "application/pdf")
    assert rx["confirm_queue"] == []
    r = api.post(f"/documents/{rx['id']}/handwritten", json={"handwritten": True})
    assert r.status_code == 200
    paths = {q["path"] for q in r.json()["confirm_queue"]}
    assert {"medications.0.name", "medications.0.dosage", "medications.2.name"} <= paths
    lab = upload(api, patient["_id"], "lab.pdf", (SAMPLES / "lab_report_2024_03.pdf").read_bytes(), "application/pdf")
    assert api.post(f"/documents/{lab['id']}/handwritten", json={"handwritten": True}).status_code == 422
