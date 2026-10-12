import json

from app.agent.language import detect_language
from app.extract.evaluate import Score, compare, field_key
from scripts import eval as ev
from tests.conftest import ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "language_eval.json"


def test_language_fixture_covers_every_supported_language():
    from app.agent.language import SUPPORTED_CODES

    items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
    assert {i["code"] for i in items} == set(SUPPORTED_CODES)
    for code in SUPPORTED_CODES:
        assert sum(1 for i in items if i["code"] == code) == 3


def test_language_detection_on_labelled_questions():
    for code, total, correct, wrong in ev.language_eval(FIXTURE):
        assert correct == total, f"{code}: {wrong}"


def test_language_eval_reports_misses(tmp_path):
    fixture = tmp_path / "f.json"
    fixture.write_text(json.dumps({"items": [{"code": "ta", "text": "What changed?"}, {"code": "en", "text": "What changed?"}]}), encoding="utf-8")
    rows = {code: (n, k, w) for code, n, k, w in ev.language_eval(fixture)}
    assert rows["ta"][:2] == (1, 0) and "-> en" in rows["ta"][2][0]
    assert rows["en"][:2] == (1, 1)
    assert detect_language("What changed?").code == "en"


def test_field_key_collapses_list_labels():
    assert field_key("results[TSH].unit") == "results.unit"
    assert field_key("medications[Tab Dolo 650].timing") == "medications.timing"
    assert field_key("medications[]") == "medications"
    assert field_key("patient.name") == "patient.name"


def test_per_field_counts_add_up_to_the_totals():
    expected = {
        "facility": "City Care Hospital",
        "results": [
            {"test_name": "TSH", "value": 5.8, "unit": "uIU/mL"},
            {"test_name": "HbA1c", "value": 6.6, "unit": "%"},
        ],
    }
    predicted = {
        "facility": "City Care Hospital, Pune",
        "results": [
            {"test_name": "TSH", "value": 5.8, "unit": "ulU/mL"},
            {"test_name": "HbA1c", "value": 6.6, "unit": "%"},
            {"test_name": "Extra", "value": 1, "unit": "g"},
        ],
    }
    score = compare(expected, predicted)
    assert sum(c[0] for c in score.fields.values()) == score.expected
    assert sum(c[1] for c in score.fields.values()) == score.predicted
    assert sum(c[2] for c in score.fields.values()) == score.correct
    assert score.fields["results.value"] == [2, 3, 2]
    assert score.fields["results.unit"][2] == 1


def test_score_add_merges_field_counts():
    a, b = Score(), Score()
    a.record("results[A].value", 1, 1, 1)
    b.record("results[B].value", 1, 1, 0)
    a.add(b)
    assert a.fields == {"results.value": [2, 2, 1]}


def test_field_table_lists_precision_and_recall():
    s = Score()
    s.record("facility", 1, 1, 1)
    s.record("pathologist", 1, 0, 0)
    table = "\n".join(ev.field_table(s))
    assert "| `facility` | 1 | 1 | 1 | 1.00 | 1.00 |" in table
    assert "| `pathologist` | 1 | 0 | 0 | n/a | 0.00 |" in table


def test_review_stats_counts_flagged_fields(settings_tmp):
    from app.extract.extract import extract
    from app.ingest.ingest import ingest_file
    from tests.conftest import SAMPLES

    pages = ingest_file(SAMPLES / "lab_report_2024_03.pdf", "eval_review")
    ex = extract("lab_report", pages, mode="rules")
    before = ex.model_dump()
    stats = ev.review_stats(ex, pages)
    assert stats["fields"] > 0
    assert 0 < stats["flagged"] <= stats["fields"]
    assert len(stats["paths"]) == stats["flagged"]
    assert ex.model_dump() == before


def test_mock_ollama_is_flagged(monkeypatch):
    class Resp:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            if url.endswith("/api/tags"):
                return Resp({"models": [{"name": "mock-ollama:stand-in", "digest": "abc"}, {"name": "qwen2.5:7b", "digest": "0123456789abcdef", "details": {"parameter_size": "7B", "quantization_level": "Q4_K_M"}}]})
            return Resp({"version": "0.0.0"})

    monkeypatch.setattr(ev.httpx, "Client", Client)
    state = ev.ollama_state("http://x", ["qwen2.5:7b"])
    assert state["mock"] and state["reachable"]
    assert state["models"]["qwen2.5:7b"] == {"digest": "0123456789ab", "size": "7B", "quant": "Q4_K_M"}


def test_unreachable_ollama_is_reported():
    state = ev.ollama_state("http://127.0.0.1:1", ["qwen2.5:7b"])
    assert state == {"reachable": False, "version": "", "models": {}, "mock": False}


def test_handwriting_switch_adds_drug_fields_to_the_queue(settings_tmp, tmp_path):
    from app.extract.extract import extract
    from app.ingest.ingest import ingest_file
    from app.normalize.confirm import iter_fields
    from tests.fakes import RX_PDF_LINES, text_pdf

    path = tmp_path / "rx.pdf"
    path.write_bytes(text_pdf(RX_PDF_LINES))
    pages = ingest_file(path, "eval_rx")
    ex = extract("prescription", pages, mode="rules")
    for _, f in iter_fields(ex):
        f.confidence = 0.99
        f.reasons = []
        f.needs_confirmation = False
    plain = ev.review_stats(ex, pages)
    marked = ev.review_stats(ex, pages, marked_handwritten=True)
    assert marked["fields"] == plain["fields"]
    assert marked["flagged"] > plain["flagged"]
    assert any(p.endswith(".name") for p in marked["paths"]) and any(p.endswith(".dosage") for p in marked["paths"])
