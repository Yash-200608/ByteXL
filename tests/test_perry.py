import copy
import json

import pytest

from app.agent import Perry, PerryTools, ToolError
from app.agent.language import detect_language
from tests.conftest import SAMPLES
from tests.fakes import LAB, RX, RX_PDF_LINES, router, text_pdf

LAB_SEP = copy.deepcopy(LAB)
LAB_SEP.update({"collected_date": "20/09/2024 08:00", "report_date": "20/09/2024 17:00"})
LAB_SEP["tests"] = [
    {"name": "HbA1c", "value": "6.6", "unit": "%", "reference_range": "4.0 - 5.6", "flag": "H"},
    {"name": "Total Cholesterol", "value": "198", "unit": "mg/dL", "reference_range": "< 200", "flag": ""},
]
RX_OTHER = {**RX, "patient_name": "Priya Nair", "doctor_name": "Dr. K. Rao", "diagnoses": ["Allergic rhinitis"], "handwritten": False,
            "medicines": [{"name": "Tab Montair LC", "strength": "", "dosage": "HS", "timing": "", "duration": "x 10 days", "instructions": ""}]}
DS = {
    "patient_name": "Rahul Sharma", "age": "45", "sex": "Male", "patient_id": "", "hospital": "CITY CARE HOSPITAL", "doctor": "Dr. Vikram Rao",
    "admission_date": "01/06/2024", "discharge_date": "05/06/2024", "diagnoses": ["Acute gastroenteritis with moderate dehydration"],
    "presenting_complaints": ["Loose stools and vomiting for 2 days"], "hospital_course": "Managed with IV fluids. Symptoms improved.",
    "procedures": [], "investigations": [{"name": "Serum Sodium", "value": "132", "unit": "mmol/L", "reference_range": "135 - 145", "flag": "L"}],
    "discharge_medicines": [{"name": "Tab Pantocid 40 mg", "strength": "40 mg", "dosage": "OD", "timing": "before breakfast", "duration": "x 7 days", "instructions": ""}],
    "follow_up": "Review in OPD after 1 week", "advice": ["Soft diet"],
}
DS_LINES = ["CITY CARE HOSPITAL", "DISCHARGE SUMMARY", "Patient: Rahul Sharma  45/M", "Date of Admission: 01/06/2024",
            "Date of Discharge: 05/06/2024", "Diagnosis: Acute gastroenteritis with moderate dehydration", "Hospital Course: Managed with IV fluids.",
            "Investigations: Serum Sodium 132 mmol/L", "Discharge Medications: Tab Pantocid 40 mg OD before breakfast x 7 days",
            "Follow up: Review in OPD after 1 week"]


def _with_ds(base):
    def handler(model, messages, schema):
        if (schema or {}).get("title") == "DischargeSummaryLLM":
            return json.dumps(DS)
        return base(model, messages, schema)

    return handler


def _upload(api, pid, name, data, mime="application/pdf"):
    return api.post(f"/patients/{pid}/documents?sync=true", files={"file": (name, data, mime)}).json()


@pytest.fixture
def world(client, fake_llm):
    from app.config import get_settings

    s = get_settings()
    s.summary_on_upload = False
    s.summary_mode = "template"
    s.perry_mode = "template"
    a = client.post("/patients", json={"name": "Rahul Sharma", "sex": "male", "birth_year": 1979}).json()["_id"]
    b = client.post("/patients", json={"name": "Priya Nair", "sex": "female", "birth_year": 1990}).json()["_id"]
    lab_pdf = (SAMPLES / "lab_report_2024_03.pdf").read_bytes()
    fake_llm.handler = _with_ds(router())
    lab_mar = _upload(client, a, "lab_mar.pdf", lab_pdf)
    rx = _upload(client, a, "rx.pdf", text_pdf(RX_PDF_LINES))
    ds = _upload(client, a, "discharge.pdf", text_pdf(DS_LINES))
    fake_llm.handler = router(lab=LAB_SEP)
    lab_sep = _upload(client, a, "lab_sep.pdf", lab_pdf)
    fake_llm.handler = router(rx=RX_OTHER)
    other = _upload(client, b, "other_rx.pdf", text_pdf(RX_PDF_LINES))
    fake_llm.handler = None
    return {"a": a, "b": b, "lab_mar": lab_mar["id"], "lab_sep": lab_sep["id"], "rx": rx["id"], "ds": ds["id"], "other": other["id"],
            "client": client, "llm": fake_llm, "settings": s}


def _ask(world, text, pid=None):
    return Perry(pid or world["a"]).respond(text).to_dict()


def test_documents_classified(world):
    docs = {d["filename"]: d["document_type"] for d in world["client"].get(f"/patients/{world['a']}/documents").json()}
    assert docs == {"lab_mar.pdf": "lab_report", "rx.pdf": "prescription", "discharge.pdf": "discharge_summary", "lab_sep.pdf": "lab_report"}


def test_tools_only_see_current_user(world):
    tools = PerryTools(world["a"])
    ids = {d["document_id"] for d in tools.call("get_my_documents", {"limit": 25})["documents"]}
    assert world["other"] not in ids and len(ids) == 4
    assert tools.call("search_my_records", {"query": "Montair"})["matches"] == []
    assert all("Montair" not in m["name"] for m in tools.call("get_my_medications")["medicines"])
    with pytest.raises(ToolError, match="couldn't find that document"):
        tools.call("get_my_document", {"document_id": world["other"]})
    with pytest.raises(ToolError, match="couldn't find that document"):
        tools.call("get_my_summary", {"document_id": world["other"], "language": "en"})
    other = PerryTools(world["b"])
    assert [m["name"] for m in other.call("get_my_medications")["medicines"]] == ["Tab Montair LC"]


def test_model_cannot_choose_user_id(world):
    tools = PerryTools(world["a"])
    for name, args in [("get_my_labs", {"test": "HbA1c", "patient_id": world["b"]}), ("get_my_profile", {"user_id": world["b"]}),
                       ("search_my_records", {"query": "x", "patient": world["b"]})]:
        with pytest.raises(ToolError, match="Invalid arguments"):
            tools.call(name, args)
    with pytest.raises(ToolError, match="Unknown tool"):
        tools.call("read_database", {"collection": "patients"})
    assert "patient" not in json.dumps(PerryTools.specs()).lower().replace("patient-uploaded", "")


def test_planner_trying_another_user_falls_back_safely(world):
    world["settings"].perry_mode = "llm"
    calls = []

    def handler(model, messages, schema):
        calls.append(schema)
        if (schema or {}).get("title") == "Plan":
            return json.dumps({"calls": [{"tool": "get_my_medications", "args": {"patient_id": world["b"]}}]})
        return "{}"

    world["llm"].handler = handler
    r = _ask(world, "What medicines are in my records?")
    assert "Tab Glycomet 500" in r["reply"] and "Montair" not in r["reply"]
    assert r["tools"] == ["get_my_medications"] and r["method"] == "composed"


def test_unknown_patient_rejected(world):
    with pytest.raises(ToolError):
        PerryTools("pat_doesnotexist")
    assert world["client"].post("/patients/pat_doesnotexist/perry", json={"message": "hi"}).status_code == 404


@pytest.mark.parametrize("question, intent, expected", [
    ("Explain my latest report", "summary", ["prescription", "Dr. Anjali Mehta"]),
    ("Explain my latest lab report", "summary", ["lab report", "HbA1c"]),
    ("What was my latest HbA1c?", "labs", ["6.6%", "20 Sep 2024", "7.2%"]),
    ("What medicines are in my records?", "medications", ["Tab Glycomet 500", "BD PC x 1 month", "Tab Pantocid 40 mg"]),
    ("Show me my timeline", "timeline", ["20 Sep 2024", "12 Mar 2024", "05 Jun 2024"]),
    ("What documents did I upload recently?", "documents", ["4 document", "lab_sep.pdf", "discharge.pdf"]),
    ("Do I have anything waiting for confirmation?", "pending", ["waiting for your confirmation", "Tab Dolo 650"]),
    ("Which document mentions cholesterol?", "search", ["Total Cholesterol", "198 mg/dL"]),
    ("What did my last discharge summary say?", "document", ["CITY CARE HOSPITAL", "Acute gastroenteritis with moderate dehydration", "Tab Pantocid 40 mg"]),
    ("What changed in my health records?", "compare", ["HbA1c", "7.2% → **6.6%**"]),
    ("What do you know about my records?", "overview", ["**4** documents", "Rahul Sharma"]),
    ("Which medicine was prescribed most recently?", "document", ["Dr. Anjali Mehta", "Tab Rosuvas 10"]),
])
def test_retrieval(world, question, intent, expected):
    r = _ask(world, question)
    assert r["intent"] == intent and r["state"] == "ok", r
    for e in expected:
        assert e in r["reply"], (e, r["reply"])
    assert "doc_" not in r["reply"] and "pat_" not in r["reply"]


def test_sources_are_reported(world):
    r = _ask(world, "What was my latest HbA1c?")
    assert {s["filename"] for s in r["sources"]} == {"lab_sep.pdf", "lab_mar.pdf"}


@pytest.mark.parametrize("text, code", [
    ("What was my latest HbA1c?", "en"),
    ("मेरी आखिरी रिपोर्ट समझाओ", "hi"),
    ("Meri latest HbA1c kya hai?", "hinglish"),
    ("Mere reports mein kya change hua?", "hinglish"),
    ("என் latest report என்ன சொல்றது?", "ta"),
    ("నా latest report ఏమి చెబుతోంది?", "te"),
    ("আমার শেষ রিপোর্ট কী বলছে?", "bn"),
    ("Show me my medicines", "en"),
    ("hi", "en"),
])
def test_language_detection(text, code):
    assert detect_language(text).code == code


def test_hindi_reply_keeps_names_and_doses(world):
    r = _ask(world, "मेरी दवाइयां दिखाओ")
    assert r["language"] == "hi" and "आपके रिकॉर्ड में दवाएं" in r["reply"]
    assert "Tab Glycomet 500" in r["reply"] and "BD PC x 1 month" in r["reply"]


def test_hinglish_reply(world):
    r = _ask(world, "Meri latest HbA1c kya hai?")
    assert r["language"] == "hinglish" and "Aapka latest **HbA1c** **6.6%** tha" in r["reply"]


def test_treatment_question_never_advises(world):
    world["settings"].perry_mode = "llm"
    calls = []

    def handler(model, messages, schema):
        calls.append(schema)
        return "You should stop taking Glycomet."

    world["llm"].handler = handler
    for q in ["Should I stop taking Glycomet?", "Glycomet band kar du kya?"]:
        r = _ask(world, q)
        assert r["intent"] == "treatment"
        assert "Glycomet" in r["reply"] and "BD PC x 1 month" in r["reply"] and "Rosuvas" not in r["reply"]
        assert "should stop" not in r["reply"].lower()
    assert calls == []


def _llm_world(world, answers, plan):
    world["settings"].perry_mode = "llm"
    seen = {"answers": 0}

    def handler(model, messages, schema):
        if (schema or {}).get("title") == "Plan":
            return json.dumps(plan)
        seen["answers"] += 1
        return answers[min(seen["answers"], len(answers)) - 1]

    world["llm"].handler = handler
    return seen


def test_llm_answer_accepted_when_grounded(world):
    good = "I found it — your latest HbA1c was 6.6%, according to your lab report dated 20 Sep 2024. Earlier it was 7.2%."
    seen = _llm_world(world, [good], {"calls": [{"tool": "get_my_labs", "args": {"test": "HbA1c"}}]})
    r = _ask(world, "What was my latest HbA1c?")
    assert r["method"] == "llm" and r["reply"] == good and seen["answers"] == 1


@pytest.mark.parametrize("bad", [
    "Your latest HbA1c was 9.1%.",
    "Your HbA1c is 6.6%, which means you have diabetes.",
    "Your HbA1c was 6.6%. You should stop taking Glycomet.",
    "Your HbA1c was 6.6%. This may indicate a serious problem.",
    "Your HbA1c was 6.6% in document doc_0123456789ab.",
    "{}",
])
def test_ungrounded_llm_answers_fall_back_to_records(world, bad):
    seen = _llm_world(world, [bad, bad], {"calls": [{"tool": "get_my_labs", "args": {"test": "HbA1c"}}]})
    r = _ask(world, "What was my latest HbA1c?")
    assert r["method"] == "composed" and seen["answers"] == 2
    assert "6.6%" in r["reply"] and "9.1" not in r["reply"] and "diabetes" not in r["reply"].lower()


def test_llm_corrects_after_feedback(world):
    good = "Your latest HbA1c was 6.6% (20 Sep 2024)."
    seen = _llm_world(world, ["Your latest HbA1c was 8.0%.", good], {"calls": [{"tool": "get_my_labs", "args": {"test": "HbA1c"}}]})
    r = _ask(world, "What was my latest HbA1c?")
    assert r["method"] == "llm" and r["reply"] == good and seen["answers"] == 2


def test_hinglish_llm_answer_must_not_switch_script(world):
    _llm_world(world, ["आपका HbA1c 6.6% है।", "आपका HbA1c 6.6% है।"], {"calls": [{"tool": "get_my_labs", "args": {"test": "HbA1c"}}]})
    r = _ask(world, "Meri latest HbA1c kya hai?")
    assert r["method"] == "composed" and r["reply"].startswith("Aapka latest")


def test_empty_plan_for_data_question_still_retrieves(world):
    _llm_world(world, ["{}"], {"calls": []})
    r = _ask(world, "What was my latest HbA1c?")
    assert r["tools"] == ["get_my_labs"] and "6.6%" in r["reply"]


def test_missing_information_is_not_invented(world):
    r = _ask(world, "What was my vitamin D?")
    assert r["state"] == "not_found" and "couldn't find" in r["reply"]
    r = _ask(world, "Find my MRI scan results")
    assert "couldn't find" in r["reply"]


def test_tool_failure_is_reported_not_hidden(world, monkeypatch):
    def boom(self, **kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(PerryTools, "get_my_labs", boom)
    r = _ask(world, "What was my latest HbA1c?")
    assert r["state"] == "error" and "couldn't access that part of your records" in r["reply"]
    assert "disk" not in r["reply"]


def test_llm_unavailable_uses_records(world):
    world["settings"].perry_mode = "llm"
    world["llm"].up = False

    def down(model, messages, schema):
        from app.llm.client import LLMUnavailable

        raise LLMUnavailable("connection refused")

    world["llm"].handler = down
    r = _ask(world, "What medicines are in my records?")
    assert r["method"] == "composed" and "Tab Glycomet 500" in r["reply"]


def test_greeting_needs_no_tools(world):
    r = _ask(world, "hi")
    assert r["tools"] == [] and "PERRY" in r["reply"]


def test_api_endpoint(world):
    c = world["client"]
    r = c.post(f"/patients/{world['a']}/perry", json={"message": "What was my latest HbA1c?",
                                                       "history": [{"role": "user", "content": "hello"}, {"role": "perry", "content": "Hi!"}]})
    assert r.status_code == 200 and "6.6%" in r.json()["reply"] and r.json()["tools"] == ["get_my_labs"]
    assert c.post(f"/patients/{world['a']}/perry", json={"message": ""}).status_code == 422
    assert c.post(f"/patients/{world['a']}/perry", json={"message": "x", "history": [{"role": "system", "content": "x"}]}).status_code == 422
    r = c.post(f"/patients/{world['b']}/perry", json={"message": "What medicines are in my records?"}).json()
    assert "Tab Montair LC" in r["reply"] and "Glycomet" not in r["reply"]


@pytest.mark.parametrize("text, code", [
    ("माझी औषधे दाखवा", "mr"),
    ("माझा शेवटचा रिपोर्ट काय आहे?", "mr"),
    ("میری دوائیں دکھائیں", "ur"),
    ("મારી દવાઓ બતાવો", "gu"),
    ("ನನ್ನ ಔಷಧಿಗಳನ್ನು ತೋರಿಸಿ", "kn"),
    ("എന്റെ മരുന്നുകൾ കാണിക്കൂ", "ml"),
    ("ମୋର ଔଷଧ ଦେଖାନ୍ତୁ", "or"),
    ("ਮੇਰੀਆਂ ਦਵਾਈਆਂ ਦਿਖਾਓ", "pa"),
    ("मेरी दवाइयां दिखाओ", "hi"),
])
def test_top_indian_languages_detected(text, code):
    assert detect_language(text).code == code


SCRIPT_WORD = {"Tamil": "மருந்து", "Marathi": "औषध", "Urdu": "دوائی", "Bengali": "ওষুধ", "Telugu": "మందు"}


def _translator(world, english_for: dict, tamper: bool = False, down: bool = False):
    import re as _re

    from app.llm.client import LLMUnavailable

    calls = []

    def handler(model, messages, schema):
        system = messages[0]["content"]
        if not system.startswith("Translate the text below to "):
            return "{}"
        calls.append(model)
        if down:
            raise LLMUnavailable("translator offline")
        target = system.removeprefix("Translate the text below to ").rstrip(".")
        text = messages[1]["content"]
        if target == "English":
            return english_for.get(text, "")
        out = _re.sub(r"[A-Za-z][A-Za-z'’\-]*", SCRIPT_WORD[target], text)
        if tamper:
            out = out.replace("[[1]]", "9.1", 1)
        return out

    world["llm"].handler = handler
    return calls


def test_tamil_question_answered_in_tamil_with_exact_values(world):
    calls = _translator(world, {"என் கடைசி HbA1c என்ன?": "What was my latest HbA1c?"})
    r = _ask(world, "என் கடைசி HbA1c என்ன?")
    assert r["language"] == "ta" and r["method"] == "composed+translated" and r["tools"] == ["get_my_labs"]
    assert "மருந்து" in r["reply"] and "**HbA1c**" in r["reply"] and "**6.6%**" in r["reply"] and "20 Sep 2024" in r["reply"]
    assert "couldn't answer" not in r["reply"]
    assert set(calls) == {world["settings"].translate_model}


def test_marathi_medicines_keep_names_and_doses(world):
    _translator(world, {"माझी औषधे दाखवा": "Show my medicines"})
    r = _ask(world, "माझी औषधे दाखवा")
    assert r["language"] == "mr" and r["intent"] == "medications"
    assert "Tab Glycomet 500" in r["reply"] and "BD" in r["reply"] and "PC" in r["reply"] and "औषध" in r["reply"]


def test_urdu_treatment_question_stays_safe(world):
    _translator(world, {"کیا میں Glycomet بند کر دوں؟": "Should I stop taking Glycomet?"})
    r = _ask(world, "کیا میں Glycomet بند کر دوں؟")
    assert r["language"] == "ur" and r["intent"] == "treatment"
    assert "Tab Glycomet 500" in r["reply"] and "BD" in r["reply"] and "should stop" not in r["reply"].lower()


def test_tampered_translation_never_changes_values(world):
    _translator(world, {"আমার শেষ HbA1c কত?": "What was my latest HbA1c?"}, tamper=True)
    r = _ask(world, "আমার শেষ HbA1c কত?")
    assert r["language"] == "bn" and "9.1" not in r["reply"] and "**6.6%**" in r["reply"]
    assert "kept in English" in r["reply"] or "couldn't answer in Bengali" in r["reply"]


def test_translator_offline_falls_back_to_english(world):
    _translator(world, {}, down=True)
    r = _ask(world, "నా మందులు చూపించు")
    assert r["language"] == "te" and "couldn't answer in Telugu" in r["reply"]
    assert r["intent"] == "medications" and "Tab Glycomet 500" in r["reply"]


def test_english_and_hinglish_never_call_translator(world):
    calls = _translator(world, {})
    _ask(world, "What was my latest HbA1c?")
    _ask(world, "Meri latest HbA1c kya hai?")
    assert calls == []


@pytest.mark.parametrize("text, intent", [
    ("ನನ್ನ ವರದಿಗಳನ್ನು ನನಗೆ ಕೊಡಿ.", "documents"),
    ("என் மருந்துகளை காட்டு", "medications"),
    ("আমার রিপোর্টে কী পরিবর্তন হয়েছে?", "compare"),
    ("నా పరీక్ష ఫలితాలు చూపించు", "labs"),
    ("میری دوائیں دکھائیں", "medications"),
])
def test_regional_keywords_route_without_translator(world, text, intent):
    _translator(world, {}, down=True)
    r = _ask(world, text)
    assert r["intent"] == intent and r["state"] == "ok"
    assert "couldn't answer in" in r["reply"] and "couldn't find" not in r["reply"]
