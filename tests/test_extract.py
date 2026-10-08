import json
from datetime import date

import pytest

from app.extract.evaluate import compare, same
from app.extract.extract import extract
from app.extract.flatten import to_flat
from app.extract.parse import parse_age, parse_date, parse_number, parse_sex
from app.extract.rules import lab_rows, med_lines
from app.ingest.ingest import ingest_file
from tests.conftest import ROOT, SAMPLES

TRUTH = ROOT / "tests" / "fixtures" / "synthetic_truth"

LAB_JSON = {
    "patient_name": "Mr. Rahul Sharma", "age": "45 Y", "sex": "Male", "patient_id": "", "facility": "SUNRISE DIAGNOSTICS PVT. LTD.",
    "referring_doctor": "Dr. Anjali Mehta, MD", "pathologist": "Dr. Sameer Kulkarni, MD (Pathology)",
    "collected_date": "12/03/2024 08:10", "report_date": "12/03/2024 17:45",
    "tests": [
        {"name": "Haemoglobin", "value": "12.1", "unit": "g/dL", "reference_range": "13.0 - 17.0", "flag": "L"},
        {"name": "HbA1c", "value": "7.2", "unit": "%", "reference_range": "4.0 - 5.6", "flag": "H"},
        {"name": "LDL Cholesterol", "value": "156", "unit": "mg/dL", "reference_range": "< 100", "flag": "H"},
        {"name": "Serum Potassium", "value": "9.9", "unit": "mmol/L", "reference_range": "3.5 - 5.1", "flag": ""},
    ],
}


@pytest.fixture
def lab_pages(settings_tmp):
    return ingest_file(SAMPLES / "lab_report_2024_03.pdf", "doc_test")


def test_parse_date_day_first():
    assert parse_date("12/03/2024 08:10") == date(2024, 3, 12)
    assert parse_date("22/9/24") == date(2024, 9, 22)
    assert parse_date("05-06-2024") == date(2024, 6, 5)
    assert parse_date("12 Mar 2024") == date(2024, 3, 12)
    assert parse_date("Mar 12, 2024") == date(2024, 3, 12)
    assert parse_date("2024-03-12") == date(2024, 3, 12)
    assert parse_date("13/25/2024") is None
    assert parse_date("") is None


def test_parse_numbers_age_sex():
    assert parse_number("7,800") == 7800
    assert parse_number("1,20,000") == 120000
    assert parse_number("< 0.5") == 0.5
    assert parse_number("Nil") is None
    assert parse_age("45 Y / Male") == 45
    assert parse_sex("M") == "male"
    assert parse_sex("Female") == "female"
    assert parse_sex("45 Y / Male") == "male"


def test_extract_with_llm_maps_boxes(lab_pages, fake_llm):
    fake_llm.responses.append(json.dumps(LAB_JSON))
    ex = extract("lab_report", lab_pages, mode="vision")
    assert ex.meta.method == "vision"
    assert ex.meta.attempts == 1
    assert ex.patient.name.value == "Rahul Sharma"
    assert ex.patient.sex.value == "male"
    assert ex.patient.age_years.value == 45
    assert ex.collected_on.value == date(2024, 3, 12)
    hb = ex.results[0]
    assert hb.value.value == 12.1
    assert hb.value.source_box is not None
    assert hb.test_name.confidence > 0.85
    assert hb.printed_flag.value == "L"
    page_h = lab_pages[0].height
    assert abs(hb.value.source_box.y0 - hb.test_name.source_box.y0) < page_h * 0.01
    ghost = ex.results[3]
    assert ghost.test_name.confidence < 0.6
    assert "value not found in document text" in ghost.value.reasons


def test_extract_retries_with_error_feedback(lab_pages, fake_llm):
    fake_llm.responses += ['{"tests": "oops"}', json.dumps(LAB_JSON)]
    ex = extract("lab_report", lab_pages, mode="vision")
    assert ex.meta.attempts == 2
    assert ex.meta.validation_errors
    feedback = fake_llm.calls[1]["messages"][-1]["content"]
    assert "rejected" in feedback and "tests" in feedback
    assert ex.results[0].test_name.confidence < 0.9


def test_extract_falls_back_to_rules_low_confidence(lab_pages, fake_llm):
    fake_llm.responses += ['{"tests": []}', '{"tests": []}']
    ex = extract("lab_report", lab_pages, mode="text")
    assert ex.meta.method == "rules"
    assert ex.meta.low_confidence
    names = [r.test_name.value for r in ex.results]
    assert "Haemoglobin" in names and "LDL Cholesterol" in names
    assert all(r.test_name.confidence <= 0.3 for r in ex.results)


def test_extract_when_ollama_down_uses_rules(lab_pages, fake_llm):
    from app.llm.client import LLMUnavailable

    def boom(messages):
        raise LLMUnavailable("down")

    fake_llm.responses += [boom, boom]
    ex = extract("lab_report", lab_pages, mode="vision")
    assert ex.meta.method == "rules"
    assert len(ex.results) == 12


def test_rules_med_lines():
    meds = med_lines("1. Tab Glycomet 500 mg   1-0-1 after food x 30 days\n2) Tab Dolo 650 SOS for fever x 3 days\nAdvice: walk")
    assert [m.name for m in meds] == ["Tab Glycomet 500 mg", "Tab Dolo 650"]
    assert meds[0].dosage == "1-0-1" and meds[0].timing == "after food" and meds[0].duration == "x 30 days"
    assert meds[1].dosage == "SOS"


def test_rules_lab_rows():
    rows = lab_rows("Test   Result   Unit   Ref\nHaemoglobin   12.1   g/dL   13.0 - 17.0   L\nPatient Name : X   Lab No : 1")
    assert len(rows) == 1 and rows[0].flag == "L" and rows[0].reference_range == "13.0 - 17.0"


def test_eval_compare_perfect_and_partial():
    truth = json.loads((TRUTH / "lab_report_2024_03.json").read_text())
    perfect = compare(truth, truth)
    assert perfect.precision == 1.0 and perfect.recall == 1.0
    pred = json.loads(json.dumps(truth))
    pred["results"] = pred["results"][:-1]
    pred["results"][0]["value"] = 99
    pred["patient"]["name"] = "Mr Rahul Sharma"
    sc = compare(truth, pred)
    assert sc.recall < 1.0 and sc.precision < 1.0
    assert any("Haemoglobin" in m for m in sc.misses)


def test_eval_same_rules():
    assert same(12.1, "12.1")
    assert same("2024-03-12", "12/03/2024", "collected_on")
    assert same("Dr. Anjali Mehta, MD", "dr anjali mehta md")
    assert not same(12.1, 13)


def test_flatten_roundtrip_rules(lab_pages, fake_llm):
    fake_llm.responses += ['{"tests": []}', '{"tests": []}']
    flat = to_flat(extract("lab_report", lab_pages, mode="text"))
    truth = json.loads((TRUTH / "lab_report_2024_03.json").read_text())
    assert compare(truth, flat).recall > 0.6


def test_eval_script_skips_empty_expected(tmp_path, settings_tmp):
    import scripts.eval as ev

    out = tmp_path / "eval.md"
    assert ev.main(["--out", str(out)]) == 0
    assert "expected JSON still empty" in out.read_text()


def test_tidy_med_grounded_fixes(lab_pages):
    from app.extract.lift import Lifter
    from app.extract.llm_schemas import MedicineLLM
    from app.ingest.models import OcrLine, PageData

    page = PageData(index=0, width=1000, height=1000, image_path="x", source="ocr",
                    lines=[OcrLine(text="1) Tab Dolo 650 SOS for fever x 3 days", box=[10, 10, 900, 40]),
                           OcrLine(text="2) Tab Pan 40 mg OD AC x 14 days", box=[10, 60, 900, 90])])
    lf = Lifter([page], retried=False, low=False)
    a = lf.med(MedicineLLM(name="Tab Dolo", strength="650", dosage="SOS", timing="x 3 days", duration=""))
    assert a.name.value == "Tab Dolo 650" and a.duration.value == "x 3 days" and a.timing.value is None
    b = lf.med(MedicineLLM(name="Tab Pan", strength="40 mg", dosage="OD AC", timing="", duration="x 14 days"))
    assert b.name.value == "Tab Pan 40 mg" and b.dosage.value == "OD" and b.timing.value == "AC"
    c = lf.med(MedicineLLM(name="Tab Pan", strength="80 mg", dosage="OD", timing="", duration=""))
    assert c.name.value == "Tab Pan"


def test_tidy_registration():
    from app.extract.lift import tidy_registration

    assert tidy_registration("MBBS, MD (Medicine)| Reg. No. MMC 2009/03/5678") == "MMC 2009/03/5678"
    assert tidy_registration("MMC 2009/03/5678") == "MMC 2009/03/5678"
