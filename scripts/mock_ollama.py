import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rapidfuzz import fuzz

from app.config import get_settings
from app.extract.rules import rules_extract
from app.ingest.classify import rule_scores

TRUTH_DIR = ROOT / "tests" / "fixtures" / "synthetic_truth"
MOCK_TAG = "mock-ollama:stand-in"
SCHEMA_DOC_TYPE = {"LabReportLLM": "lab_report", "PrescriptionLLM": "prescription", "DischargeSummaryLLM": "discharge_summary"}
DELAY_S = 0.0


def _num(v) -> str:
    if v is None or v == "":
        return ""
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _date(iso: str) -> str:
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def _sex(s: str) -> str:
    return {"male": "Male", "female": "Female"}.get((s or "").lower(), s or "")


def _tests(rows: list[dict]) -> list[dict]:
    return [{"name": r.get("test_name", ""), "value": _num(r.get("value")) or r.get("value_text", ""), "unit": r.get("unit", ""),
             "reference_range": r.get("reference_range", ""), "flag": ""} for r in rows]


def _meds(rows: list[dict]) -> list[dict]:
    return [{"name": m.get("name", ""), "strength": m.get("strength", ""), "dosage": m.get("dosage", ""), "timing": m.get("timing", ""),
             "duration": m.get("duration", ""), "instructions": m.get("instructions", "")} for m in rows]


def truth_to_llm(stem: str, t: dict) -> dict:
    p = t.get("patient", {})
    head = {"patient_name": p.get("name", ""), "age": _num(p.get("age_years")), "sex": _sex(p.get("sex", ""))}
    if t["document_type"] == "lab_report":
        return {**head, "patient_id": "", "facility": t.get("facility", ""), "referring_doctor": t.get("referring_doctor", ""),
                "pathologist": t.get("pathologist", ""), "collected_date": _date(t.get("collected_on", "")),
                "report_date": _date(t.get("reported_on", "")), "tests": _tests(t.get("results", []))}
    if t["document_type"] == "prescription":
        return {**head, "doctor_name": t.get("prescriber", ""), "doctor_registration": t.get("prescriber_registration", ""),
                "clinic": t.get("facility", ""), "date": _date(t.get("date", "")), "complaints": t.get("complaints", []),
                "diagnoses": t.get("diagnoses", []), "medicines": _meds(t.get("medications", [])), "advice": t.get("advice", []),
                "follow_up": t.get("follow_up", ""), "handwritten": "handwritten" in stem}
    return {**head, "patient_id": "", "hospital": t.get("facility", ""), "doctor": t.get("attending_doctor", ""),
            "admission_date": _date(t.get("admission_date", "")), "discharge_date": _date(t.get("discharge_date", "")),
            "diagnoses": t.get("diagnoses", []), "presenting_complaints": t.get("presenting_complaints", []),
            "hospital_course": t.get("hospital_course", ""), "procedures": t.get("procedures", []),
            "investigations": _tests(t.get("investigations", [])), "discharge_medicines": _meds(t.get("discharge_medications", [])),
            "follow_up": t.get("follow_up", ""), "advice": t.get("advice", [])}


def _probes(t: dict) -> list[tuple[str, str]]:
    rows = t.get("results") or t.get("investigations") or []
    out = [(r.get("test_name", ""), _num(r.get("value")) or r.get("value_text", "")) for r in rows]
    out += [(m.get("name", ""), m.get("dosage", "")) for m in t.get("medications") or t.get("discharge_medications") or []]
    return [o for o in out if o[0]]


def match_truth(doc_type: str, text: str) -> tuple[str, dict] | None:
    low = text.lower()
    best, best_score = None, 0.0
    for f in sorted(TRUTH_DIR.glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        if t.get("document_type") != doc_type:
            continue
        probes = _probes(t)
        if not probes:
            continue
        hits = sum(1 for name, val in probes if fuzz.partial_ratio(name.lower(), low) >= 85 and (not val or val.lower() in low))
        score = hits / len(probes)
        if score > best_score:
            best, best_score = (f.stem, t), score
    return best if best_score >= 0.9 else None


def ocr_text(messages: list[dict]) -> str:
    content = messages[1]["content"] if len(messages) > 1 else ""
    m = re.search(r"<<<\n?(.*?)\n?>>>", content, re.S)
    if m:
        return m.group(1)
    m = re.search(r"Document text:\n(.*)", content, re.S)
    return m.group(1) if m else content


def extraction(title: str, messages: list[dict]) -> dict:
    doc_type = SCHEMA_DOC_TYPE[title]
    text = ocr_text(messages)
    hit = match_truth(doc_type, text)
    if hit:
        stem, truth = hit
        print(f"  [{title}] replaying reference answer for known sample '{stem}'", flush=True)
        return truth_to_llm(stem, truth)
    print(f"  [{title}] unknown document, answering with the rules extractor", flush=True)
    return rules_extract(doc_type, text).model_dump()


def classifier(messages: list[dict]) -> dict:
    scores = rule_scores(ocr_text(messages))
    best = max(scores, key=scores.get)
    return {"document_type": best, "reason": "mock: keyword scores"}


def _data(messages: list[dict]) -> dict:
    text = messages[1]["content"]
    start = text.index("{")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise ValueError("no json in summary prompt")


EN_FLAG = {"low": "low", "high": "high", "critical": "outside the critical limit"}
HI_FLAG = {"low": "कम", "high": "अधिक", "critical": "गंभीर सीमा से बाहर"}
DOC_EN = {"lab_report": "lab report", "prescription": "prescription", "discharge_summary": "hospital discharge summary"}
DOC_HI = {"lab_report": "लैब रिपोर्ट", "prescription": "डॉक्टर का पर्चा", "discharge_summary": "अस्पताल का डिस्चार्ज सारांश"}


def summary(messages: list[dict]) -> dict:
    d = _data(messages)
    hindi = bool(re.search(r"[ऀ-ॿ]", messages[0]["content"]))
    dt = d["document_type"]
    source = d.get("lab") or d.get("doctor") or d.get("hospital") or ""
    when = d.get("collected_on") or d.get("date") or d.get("discharge_date") or ""
    abn = d.get("abnormal_results", [])
    normal = [r["name"] for r in d.get("results", []) if r.get("flag") == "normal"]
    if hindi:
        what = f"यह {DOC_HI[dt]} है" + (f", {source} द्वारा" if source else "") + (f", तारीख {when}" if when else "") + "।"
        findings = [f"{a['name']} रिपोर्ट में {HI_FLAG.get(a['flag'], a['flag'])} दिखाया गया है।" for a in abn[:4]]
        if normal:
            findings.append("बाकी मान सामान्य सीमा के अंदर हैं।")
        if d.get("medicines"):
            findings.append("दवाएं और उन्हें लेने का तरीका नीचे वैसे ही दिया गया है जैसा डॉक्टर ने लिखा है।")
        out = [{"name": a["name"], "meaning": "यह मान सामान्य सीमा से बाहर है; इसके बारे में अपने डॉक्टर से बात करें।"} for a in abn]
        questions = ["इन परिणामों का मेरे लिए क्या मतलब है?", "अगली जांच कब करानी चाहिए?", "क्या मुझे अपनी दिनचर्या में कुछ ध्यान रखना चाहिए?"]
    else:
        what = f"This is a {DOC_EN[dt]}" + (f" from {source}" if source else "") + (f", dated {when}" if when else "") + "."
        findings = [f"The report shows {a['name']} as {EN_FLAG.get(a['flag'], a['flag'])} ({a['value']})." for a in abn[:4]]
        if normal:
            findings.append("The other values in the report are within the reference range.")
        if d.get("diagnoses_as_written"):
            findings.append("The doctor's note lists: " + ", ".join(x for x in d["diagnoses_as_written"] if x) + ".")
        if d.get("medicines"):
            findings.append("The medicines and how to take them are listed below, exactly as written.")
        if not findings:
            findings = ["The document records the details of this visit."]
        out = [{"name": a["name"], "meaning": a.get("general_meaning_hint") or "Ask your doctor what this value means for you."} for a in abn]
        questions = [f"Why is my {a['name']} {EN_FLAG.get(a['flag'], a['flag'])}, and should it be rechecked?" for a in abn[:2]]
        questions += {"lab_report": ["Do I need any repeat tests, and when?", "Is there anything I should change in my diet or activity?"],
                      "prescription": ["How long should I take each medicine?", "Which side effects should I watch for?"],
                      "discharge_summary": ["Which warning signs mean I should come back to hospital?", "When is my follow-up visit?"]}[dt]
    return {"what_this_is": what, "key_findings": findings[:6], "out_of_range": out, "questions": questions[:5]}


def answer(body: dict) -> str:
    title = (body.get("format") or {}).get("title", "") if isinstance(body.get("format"), dict) else ""
    messages = body.get("messages", [])
    if title in SCHEMA_DOC_TYPE:
        out = extraction(title, messages)
    elif title == "ClassifierOutput":
        out = classifier(messages)
    elif title == "SummaryLLM":
        out = summary(messages)
    else:
        out = {}
    return json.dumps(out, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            s = get_settings()
            names = sorted({s.vision_model, s.vision_fallback_model, s.text_model, MOCK_TAG})
            self._send(200, {"models": [{"name": n, "model": n} for n in names]})
        elif self.path in ("/", "/api/version"):
            self._send(200, {"version": "mock"})
        else:
            self._send(404, {"error": "not found"})

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not self.path.startswith("/api/chat"):
            self._send(404, {"error": "only /api/chat is mocked"})
            return
        start = time.time()
        try:
            content = answer(body)
        except Exception as exc:
            self._send(500, {"error": f"mock failed: {exc}"})
            return
        if DELAY_S:
            time.sleep(DELAY_S)
        self._send(200, {"model": body.get("model", ""), "created_at": datetime.now(timezone.utc).isoformat(),
                         "message": {"role": "assistant", "content": content}, "done": True,
                         "total_duration": int((time.time() - start) * 1e9)})

    def log_message(self, fmt, *args):
        print(f"mock-ollama {self.command} {self.path}", flush=True)


def main(argv=None) -> int:
    global DELAY_S
    ap = argparse.ArgumentParser(description="Stand-in for Ollama on machines that cannot run the models. Not a model.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11434)
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep per chat call, to mimic model latency")
    args = ap.parse_args(argv)
    DELAY_S = args.delay
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock Ollama listening on http://{args.host}:{args.port}  (stand-in only; install real Ollama for the presentation)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
