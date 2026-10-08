import json
import re

import pytest

from app.summary.render import describe_hi
from app.summary.safety import BANNED, DISCLAIMER, banned_hits, devanagari_ratio, ungrounded_numbers
from app.normalize.dosing import parse_dosage
from tests.conftest import SAMPLES
from tests.fakes import RX_PDF_LINES, router, summary_for, text_pdf

SECTIONS_EN = ["What this document is", "Values outside the reference range", "Questions to ask your doctor", "Disclaimer"]


@pytest.fixture
def api(client, fake_llm):
    fake_llm.handler = router()
    return client


def _setup(api, pid_name="Rahul Sharma"):
    from app.config import get_settings

    get_settings().summary_on_upload = False
    get_settings().hindi_summary_mode = "llm"
    pid = api.post("/patients", json={"name": pid_name, "sex": "male"}).json()["_id"]
    lab = api.post(f"/patients/{pid}/documents?sync=true", files={"file": ("lab.pdf", (SAMPLES / "lab_report_2024_03.pdf").read_bytes(), "application/pdf")}).json()
    rx = api.post(f"/patients/{pid}/documents?sync=true", files={"file": ("rx.pdf", text_pdf(RX_PDF_LINES), "application/pdf")}).json()
    return pid, lab["id"], rx["id"]


def _all_text(s: dict) -> str:
    parts = [s["what_this_is"], *s["key_findings"], *[o["meaning"] for o in s["out_of_range"]], *s["questions"], *s["notes"]]
    return "\n".join(parts)


def _abnormal_names(api, did):
    doc = api.get(f"/documents/{did}").json()
    return {r["normalized"]["canonical_name"] for r in doc["extraction"]["results"] if r["normalized"]["flag"] in ("low", "high", "critical")}


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_summary_has_disclaimer_no_banned_and_covers_abnormal(api, lang):
    _, lab, rx = _setup(api)
    for did in (lab, rx):
        s = api.get(f"/documents/{did}/summary?lang={lang}").json()
        assert s["disclaimer"] == DISCLAIMER[lang]
        assert DISCLAIMER[lang] in s["markdown"]
        assert banned_hits(_all_text(s), lang) == []
    s = api.get(f"/documents/{lab}/summary?lang={lang}").json()
    names = {o["name"] for o in s["out_of_range"]}
    assert _abnormal_names(api, lab) == names
    for o in s["out_of_range"]:
        assert o["name"] in s["markdown"] and o["value"] in s["markdown"]


def test_summary_medicines_are_deterministic_and_as_written(api):
    _, _, rx = _setup(api)
    en = api.get(f"/documents/{rx}/summary?lang=en").json()
    hi = api.get(f"/documents/{rx}/summary?lang=hi").json()
    glyco_en = next(m for m in en["medicines"] if "Glycomet" in m["name"])
    glyco_hi = next(m for m in hi["medicines"] if "Glycomet" in m["name"])
    assert glyco_en["how_to_take"] == "1 in the morning, 1 at night · after food · for 1 month"
    assert glyco_hi["name"] == "Tab Glycomet 500"
    assert "सुबह 1" in glyco_hi["how_to_take"] and "1 महीने तक" in glyco_hi["how_to_take"]
    assert glyco_en["as_written"] == "BD PC x 1 month"


def test_banned_phrase_triggers_regeneration(api, fake_llm):
    _, lab, _ = _setup(api)
    calls = []

    def handler(model, messages, schema):
        calls.append(messages)
        if len(calls) == 1:
            return summary_for(messages, bad="You have diabetes and should stop taking sugar.")
        return summary_for(messages)

    fake_llm.handler = handler
    s = api.get(f"/documents/{lab}/summary?lang=en").json()
    assert len(calls) == 2
    assert "forbidden phrases" in calls[1][-1]["content"]
    assert s["method"] == "llm" and s["attempts"] == 2
    assert banned_hits(_all_text(s)) == []


def test_persistent_violation_falls_back_to_template(api, fake_llm):
    _, lab, _ = _setup(api)
    fake_llm.handler = lambda m, msgs, sch: summary_for(msgs, bad="This is guaranteed to be cured.")
    s = api.get(f"/documents/{lab}/summary?lang=en").json()
    assert s["method"] == "template"
    assert banned_hits(_all_text(s)) == []
    assert _abnormal_names(api, lab) == {o["name"] for o in s["out_of_range"]}
    assert "This is a lab report from SUNRISE DIAGNOSTICS PVT. LTD." in s["what_this_is"]


def test_ungrounded_number_rejected(api, fake_llm):
    _, lab, _ = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        return summary_for(msgs, bad="HbA1c of 9.9 is typical." if len(calls) == 1 else None)

    fake_llm.handler = handler
    s = api.get(f"/documents/{lab}/summary?lang=en").json()
    assert "numbers not in the input" in calls[1][-1]["content"]
    assert "9.9" not in s["markdown"]


def test_missing_abnormal_coverage_triggers_retry(api, fake_llm):
    _, lab, _ = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        out = json.loads(summary_for(msgs))
        if len(calls) == 1:
            out["out_of_range"] = out["out_of_range"][:1]
        return json.dumps(out)

    fake_llm.handler = handler
    s = api.get(f"/documents/{lab}/summary?lang=en").json()
    assert "missing these abnormal results" in calls[1][-1]["content"]
    assert _abnormal_names(api, lab) == {o["name"] for o in s["out_of_range"]}


def test_summary_cached_and_invalidated(api, fake_llm):
    _, lab, _ = _setup(api)
    api.get(f"/documents/{lab}/summary?lang=en")
    n = len(fake_llm.calls)
    api.get(f"/documents/{lab}/summary?lang=en")
    assert len(fake_llm.calls) == n
    api.post(f"/documents/{lab}/confirm", json={"items": [{"path": "results.0.value", "action": "accept"}]})
    api.get(f"/documents/{lab}/summary?lang=en")
    assert len(fake_llm.calls) == n + 1


def test_hindi_requires_devanagari(api, fake_llm):
    _, lab, _ = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        if len(calls) == 1:
            out = json.loads(summary_for([{"content": "english"}, msgs[1]]))
            return json.dumps(out)
        return summary_for(msgs)

    fake_llm.handler = handler
    s = api.get(f"/documents/{lab}/summary?lang=hi").json()
    assert "Hindi" in calls[1][-1]["content"]
    assert devanagari_ratio(s["what_this_is"]) > 0.5


def test_reconciliation_note_in_summary(api, fake_llm):
    pid, _, rx = _setup(api)
    from tests.fakes import RX

    fake_llm.handler = router(rx={**RX, "date": "25/9/24", "medicines": [{"name": "Tab Gluconorm 500", "strength": "500", "dosage": "1-0-1", "timing": "", "duration": "x 1 month", "instructions": ""}]})
    lines = [l.replace("22/9/24", "25/9/24") for l in RX_PDF_LINES]
    rx2 = api.post(f"/patients/{pid}/documents?sync=true", files={"file": ("rx2.pdf", text_pdf(lines), "application/pdf")}).json()["id"]
    s = api.get(f"/documents/{rx2}/summary?lang=en").json()
    assert any("Metformin" in n and "ask your doctor" in n.lower() for n in s["notes"])


def test_safety_helpers():
    assert banned_hits("You have high sugar") == ["you have"]
    assert banned_hits("Please discuss with your doctor") == []
    assert banned_hits("The procedure is secure") == []
    assert banned_hits("यह गारंटी है", "hi") == ["गारंटी"]
    assert ungrounded_numbers("HbA1c 7.2 and 9.9", {7.2}) == [9.9]
    assert ungrounded_numbers("2 to 3 months", set()) == []
    assert len(BANNED["en"]) > 20 and len(BANNED["hi"]) > 10


def test_describe_hi():
    assert describe_hi(parse_dosage("1-0-1", "after food", "x 30 days")) == "सुबह 1, रात 1 · खाने के बाद · 30 दिन तक"
    assert describe_hi(parse_dosage("SOS")) == "केवल ज़रूरत होने पर"
    assert describe_hi(parse_dosage("once a week", "", "x 8 weeks")) == "हफ्ते में एक बार · 8 हफ्ते तक"


def test_ungrounded_condition_triggers_retry(api, fake_llm):
    _, lab, rx = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        return summary_for(msgs, bad="High sugar values point to diabetes." if len(calls) == 1 else None)

    fake_llm.handler = handler
    s = api.get(f"/documents/{lab}/summary?lang=en").json()
    assert "conditions that the document does not state" in calls[1][-1]["content"]
    assert "diabetes" not in _all_text(s).lower()


def test_condition_written_by_doctor_is_allowed(api, fake_llm):
    _, _, rx = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        return summary_for(msgs, bad="The doctor's note mentions subclinical hypothyroidism.")

    fake_llm.handler = handler
    s = api.get(f"/documents/{rx}/summary?lang=en").json()
    assert len(calls) == 1 and s["method"] == "llm"


def test_inference_phrases_banned():
    assert "may indicate" in banned_hits("This may indicate anaemia")
    assert "suggesting" in banned_hits("suggesting possible diabetes")
    assert banned_hits("This generally indicates a higher average blood sugar") == []


def test_wrong_month_rejected(api, fake_llm):
    _, lab, _ = _setup(api)
    calls = []

    def handler(model, msgs, sch):
        calls.append(msgs)
        return summary_for(msgs, bad="The report is dated May 12, 2024." if len(calls) == 1 else None)

    fake_llm.handler = handler
    api.get(f"/documents/{lab}/summary?lang=en")
    assert "months that do not match" in calls[1][-1]["content"]


def test_default_hindi_is_curated_without_llm(api, fake_llm):
    from app.config import get_settings

    _, lab, rx = _setup(api)
    get_settings().hindi_summary_mode = "template"
    n = len(fake_llm.calls)
    s = api.get(f"/documents/{lab}/summary?lang=hi").json()
    assert len(fake_llm.calls) == n and s["method"] == "template"
    assert devanagari_ratio(s["what_this_is"]) > 0.4
    hba1c = next(o for o in s["out_of_range"] if o["name"] == "HbA1c")
    assert "पिछले 2 से 3 महीनों" in hba1c["meaning"]
    assert any("HbA1c (अधिक)" in k for k in s["key_findings"])
    assert banned_hits(_all_text(s), "hi") == []
    r = api.get(f"/documents/{rx}/summary?lang=hi").json()
    assert any(m["name"] == "Tab Glycomet 500" for m in r["medicines"])
