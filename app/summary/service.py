import hashlib
import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from app.config import get_settings
from app.llm.client import LLMUnavailable, get_llm
from app.normalize.labs import resolve_lab
from app.pipeline import load_extraction
from app.records import medications_view
from app.schemas import DischargeSummary, LabReport, Prescription, lab_results, medications
from app.store import get_repository
from app.summary.render import FLAG_WORD, how_to_take, to_markdown
from app.summary.safety import DISCLAIMER, banned_hits, devanagari_ratio, numbers_in, ungrounded_conditions, ungrounded_months, ungrounded_numbers

log = logging.getLogger(__name__)
ABNORMAL = ("low", "high", "critical")


class OutOfRangeLLM(BaseModel):
    name: str
    meaning: str


class SummaryLLM(BaseModel):
    what_this_is: str = Field(min_length=10)
    key_findings: list[str] = Field(min_length=1, max_length=6)
    out_of_range: list[OutOfRangeLLM]
    questions: list[str] = Field(min_length=2, max_length=6)


def _fmt_value(v, unit) -> str:
    if v is None:
        return ""
    s = f"{v:g}" if isinstance(v, (int, float)) else str(v)
    return f"{s} {unit}".strip() if unit else s


def _meaning(name: str, flag: str, lang: str) -> str:
    ref, _ = resolve_lab(name)
    if not ref:
        return {"en": "Ask your doctor what this value means for you.", "hi": "अपने डॉक्टर से पूछें कि इस मान का आपके लिए क्या अर्थ है।"}[lang]
    if lang == "hi":
        text = ref.high_meaning_hi if flag in ("high", "critical") and ref.high_meaning_hi else ref.low_meaning_hi or ref.high_meaning_hi
        return f"यह आमतौर पर दर्शाता है कि {text}।" if text else "अपने डॉक्टर से पूछें कि इस मान का आपके लिए क्या अर्थ है।"
    text = ref.high_meaning if flag in ("high", "critical") and ref.high_meaning else ref.low_meaning or ref.high_meaning
    return f"This generally indicates {text}." if text else "Ask your doctor what this value means for you."


def summary_input(ex, lang: str) -> dict:
    results, abnormal = [], []
    for r in lab_results(ex):
        n = r.normalized
        flag = n.flag if n else "unknown"
        name = (n.canonical_name if n and n.canonical_name else None) or r.test_name.value
        item = {
            "name": name,
            "printed_name": r.test_name.value,
            "value": _fmt_value(r.value.value if r.value.value is not None else r.value_text.value, r.unit.value),
            "reference_range": r.reference_range.value or (f"{n.ref_low:g}-{n.ref_high:g} {n.unit}" if n and n.ref_low is not None and n.ref_high is not None else ""),
            "flag": flag,
        }
        results.append(item)
        if flag in ABNORMAL:
            abnormal.append({**item, "general_meaning_hint": _meaning(name, flag, "en")})
    meds = []
    for m in medications(ex):
        n = m.normalized
        meds.append({
            "name": m.name.value,
            "generic": n.generic if n else None,
            "how_to_take": how_to_take(n.dosage if n else None, lang),
            "as_written": " ".join(x for x in (m.dosage.value, m.timing.value, m.duration.value, m.instructions.value) if x),
        })
    data = {"document_type": ex.document_type, "patient_sex": ex.patient.sex.value}
    if isinstance(ex, LabReport):
        data.update({"lab": ex.facility.value, "collected_on": str(ex.collected_on.value or ""), "referring_doctor": ex.referring_doctor.value})
    elif isinstance(ex, Prescription):
        data.update({"doctor": ex.prescriber.value, "date": str(ex.date.value or ""), "complaints_as_written": [c.value for c in ex.complaints],
                     "diagnoses_as_written": [d.value for d in ex.diagnoses], "advice_as_written": [a.value for a in ex.advice], "follow_up": ex.follow_up.value})
    elif isinstance(ex, DischargeSummary):
        data.update({"hospital": ex.facility.value, "admission_date": str(ex.admission_date.value or ""), "discharge_date": str(ex.discharge_date.value or ""),
                     "diagnoses_as_written": [d.value for d in ex.diagnoses], "hospital_course_as_written": ex.hospital_course.value,
                     "follow_up": ex.follow_up.value, "advice_as_written": [a.value for a in ex.advice]})
    data.update({"results": results, "abnormal_results": abnormal, "medicines": meds})
    return data


SYSTEM = {
    "en": (
        "You explain Indian medical documents to patients in plain, warm English that a 12-year-old can follow. "
        "Strict rules: never diagnose; never say 'you have' a condition; never suggest starting, stopping, skipping or changing any medicine "
        "or dose; never give treatment advice; never promise outcomes. Describe what an out-of-range value generally indicates, using the "
        "provided hint. Never name a disease or condition unless the doctor wrote it in the document; key findings describe which values are "
        "high, low or within range, without guessing causes. Refer to 'the report', 'the document' or 'the doctor's note'. Use only numbers that appear in the input. "
        "Do not list medicines or doses; they are shown separately. Return JSON only."
    ),
    "hi": (
        "आप भारतीय मेडिकल दस्तावेज़ों को मरीज़ों के लिए सरल, आसान हिंदी (देवनागरी) में समझाते हैं। सख्त नियम: कभी निदान न करें; कभी 'आपको यह बीमारी है' न कहें; "
        "किसी भी दवा या खुराक को शुरू करने, बंद करने, छोड़ने या बदलने की सलाह कभी न दें; इलाज की सलाह न दें; कोई वादा न करें। "
        "सीमा से बाहर के मान आमतौर पर क्या दर्शाते हैं, यह दिए गए संकेत की मदद से बताएं। कोई बीमारी का नाम न लें जब तक डॉक्टर ने दस्तावेज़ में न लिखा हो; मुख्य बातों में केवल बताएं कि कौन से मान अधिक, कम या सामान्य हैं। 'रिपोर्ट' या 'दस्तावेज़' का उल्लेख करें। "
        "टेस्ट के नाम, दवाओं के नाम, संख्याएं और यूनिट अंग्रेज़ी में वैसे ही रखें जैसे दिए गए हैं, और अंक 0-9 में लिखें। केवल वही संख्याएं लिखें जो इनपुट में हैं। "
        "दवाओं की सूची न लिखें, वे अलग से दिखाई जाती हैं। केवल JSON लौटाएं।"
    ),
}

USER = {
    "en": (
        "Document data (already checked; flags were computed by software):\n{data}\n\n"
        "Fill the JSON fields:\n"
        "- what_this_is: 1-2 sentences saying what kind of document this is, who issued it and when.\n"
        "- key_findings: 2-5 short sentences about the most important points, as written in the document.\n"
        "- out_of_range: one entry for EVERY item in abnormal_results, with 'name' copied exactly and 'meaning' = one plain sentence on what such a value generally indicates. Empty list if abnormal_results is empty.\n"
        "- questions: 3-5 questions the patient could ask their doctor."
    ),
    "hi": (
        "दस्तावेज़ का डेटा (जांचा हुआ; फ्लैग सॉफ़्टवेयर ने निकाले हैं):\n{data}\n\n"
        "JSON फ़ील्ड भरें (सब हिंदी में):\n"
        "- what_this_is: 1-2 वाक्य कि यह किस तरह का दस्तावेज़ है, किसने और कब जारी किया।\n"
        "- key_findings: 2-5 छोटे वाक्य, दस्तावेज़ की सबसे ज़रूरी बातें।\n"
        "- out_of_range: abnormal_results की हर चीज़ के लिए एक प्रविष्टि; 'name' अंग्रेज़ी में बिल्कुल वैसा ही कॉपी करें, 'meaning' = एक सरल वाक्य कि ऐसा मान आमतौर पर क्या दर्शाता है। abnormal_results खाली हो तो खाली सूची।\n"
        "- questions: 3-5 सवाल जो मरीज़ अपने डॉक्टर से पूछ सकते हैं।"
    ),
}


def _llm_texts(obj: SummaryLLM) -> list[str]:
    return [obj.what_this_is, *obj.key_findings, *[o.meaning for o in obj.out_of_range], *obj.questions]


def _match_abnormal(name: str, abnormal: list[dict]) -> dict | None:
    best, score = None, 0
    for a in abnormal:
        for cand in (a["name"], a["printed_name"]):
            s = fuzz.token_sort_ratio((name or "").lower(), (cand or "").lower())
            if s > score:
                best, score = a, s
    return best if score >= 80 else None


def _document_text(data: dict) -> str:
    stripped = {k: v for k, v in data.items() if k != "abnormal_results"}
    return json.dumps(stripped, ensure_ascii=False, default=str)


def make_checker(data: dict, lang: str):
    allowed = numbers_in(json.dumps(data, ensure_ascii=False))
    doc_text = _document_text(data)

    def check(obj: SummaryLLM) -> list[str]:
        problems = []
        texts = _llm_texts(obj)
        joined = "\n".join(texts)
        hits = banned_hits(joined, lang)
        if hits:
            problems.append(f"uses forbidden phrases {hits}; rephrase without them")
        extra = ungrounded_numbers(joined, allowed)
        if extra:
            problems.append(f"mentions numbers not in the input: {extra}; only use numbers from the input")
        covered = {id(a) for o in obj.out_of_range if (a := _match_abnormal(o.name, data["abnormal_results"]))}
        missing = [a["name"] for a in data["abnormal_results"] if id(a) not in covered]
        if missing:
            problems.append(f"out_of_range is missing these abnormal results: {missing}")
        months = ungrounded_months(joined, json.dumps(data, ensure_ascii=False, default=str))
        if months:
            problems.append(f"mentions months that do not match the document dates: {months}; use the dates exactly as given")
        general = "\n".join([obj.what_this_is, *obj.key_findings, *obj.questions])
        cond = ungrounded_conditions(general, doc_text, lang)
        for o in obj.out_of_range:
            a = _match_abnormal(o.name, data["abnormal_results"])
            hint = (a["general_meaning_hint"] + " " + _meaning(a["name"], a["flag"], "hi")) if a else ""
            cond += ungrounded_conditions(o.meaning, doc_text + " " + hint, lang)
        if cond:
            problems.append(f"names conditions that the document does not state: {sorted(set(cond))}; describe values only, do not name diseases")
        if lang == "hi" and devanagari_ratio(obj.what_this_is + " ".join(obj.questions)) < 0.5:
            problems.append("write the text in Hindi (Devanagari script)")
        return problems

    return check


def template_sections(ex, data: dict, lang: str) -> dict:
    n_results = len(data["results"])
    n_abn = len(data["abnormal_results"])
    meds = data["medicines"]
    if lang == "hi":
        if isinstance(ex, LabReport):
            what = f"यह {data.get('lab') or 'लैब'} की लैब रिपोर्ट है" + (f", तारीख {data['collected_on']}" if data.get("collected_on") else "") + f"। इसमें {n_results} जांचों के परिणाम हैं।"
        elif isinstance(ex, Prescription):
            what = f"यह {data.get('doctor') or 'डॉक्टर'} का पर्चा है" + (f", तारीख {data['date']}" if data.get("date") else "") + f"। इसमें {len(meds)} दवाएं लिखी हैं।"
        else:
            what = f"यह {data.get('hospital') or 'अस्पताल'} का डिस्चार्ज सारांश है" + (f" ({data['admission_date']} से {data['discharge_date']})" if data.get("admission_date") else "") + "।"
        findings = []
        if n_results:
            findings.append(f"{n_results} में से {n_abn} मान सामान्य सीमा से बाहर हैं।")
            if n_abn:
                findings.append("सीमा से बाहर: " + ", ".join(f"{a['name']} ({FLAG_WORD['hi'][a['flag']]})" for a in data["abnormal_results"]) + "।")
            else:
                findings.append("सभी मान सामान्य सीमा के अंदर हैं।")
        if meds:
            findings.append(f"{len(meds)} दवाएं लिखी हैं; हर दवा को लेने का तरीका नीचे वैसे ही दिया गया है जैसा डॉक्टर ने लिखा है।")
        if data.get("diagnoses_as_written"):
            findings.append("डॉक्टर ने लिखा है: " + ", ".join(d for d in data["diagnoses_as_written"] if d) + "।")
        if data.get("follow_up"):
            findings.append(f"फॉलो-अप: {data['follow_up']}")
        questions = {
            "lab_report": ["इन परिणामों का मेरे लिए क्या मतलब है?", "क्या मुझे कोई और जांच करानी चाहिए, और कब?", "क्या खान-पान या दिनचर्या में कुछ बदलना चाहिए?"],
            "prescription": ["हर दवा कितने समय तक लेनी है?", "किन दुष्प्रभावों पर ध्यान देना चाहिए?", "क्या ये दवाएं मेरी दूसरी दवाओं के साथ ली जा सकती हैं?"],
            "discharge_summary": ["किन लक्षणों पर मुझे तुरंत अस्पताल आना चाहिए?", "मेरी अगली जांच कब है?", "घर पर खान-पान और आराम कैसे रखना है?"],
        }[ex.document_type]
        questions = [f"मेरा {a['name']} {FLAG_WORD['hi'][a['flag']]} क्यों है, और क्या इसे दोबारा जांचना चाहिए?" for a in data["abnormal_results"][:2]] + questions
    else:
        if isinstance(ex, LabReport):
            what = f"This is a lab report from {data.get('lab') or 'a laboratory'}" + (f" dated {data['collected_on']}" if data.get("collected_on") else "") + f". It lists {n_results} test results."
        elif isinstance(ex, Prescription):
            what = f"This is a prescription from {data.get('doctor') or 'a doctor'}" + (f" dated {data['date']}" if data.get("date") else "") + f". It lists {len(meds)} medicines."
        else:
            what = f"This is a discharge summary from {data.get('hospital') or 'a hospital'}" + (f" for a stay from {data['admission_date']} to {data['discharge_date']}" if data.get("admission_date") else "") + "."
        findings = []
        if n_results:
            findings.append(f"{n_abn} of {n_results} values are outside the reference range.")
            if n_abn:
                findings.append("Outside the range: " + ", ".join(f"{a['name']} ({FLAG_WORD['en'][a['flag']].lower()})" for a in data["abnormal_results"]) + ".")
        if meds:
            findings.append(f"{len(meds)} medicines are listed; how to take each one is shown below exactly as written.")
        if data.get("diagnoses_as_written"):
            findings.append("The doctor's note lists: " + ", ".join(d for d in data["diagnoses_as_written"] if d) + ".")
        if data.get("follow_up"):
            findings.append(f"Follow-up: {data['follow_up']}")
        questions = {
            "lab_report": ["What do these results mean for me?", "Do I need any repeat or additional tests, and when?", "Is there anything I should change in my diet or activity?"],
            "prescription": ["How long should I take each medicine?", "Which side effects should I watch for?", "Can these be taken with my other medicines?"],
            "discharge_summary": ["Which warning signs mean I should come back to hospital?", "When is my follow-up visit?", "What should I eat and how much rest do I need at home?"],
        }[ex.document_type]
        questions = [f"Why is my {a['name']} {FLAG_WORD['en'][a['flag']].lower()}, and should it be rechecked?" for a in data["abnormal_results"][:2]] + questions
    if not findings:
        findings = [what]
    return {"what_this_is": what, "key_findings": findings, "questions": questions, "meanings": {}}


def assemble(ex, data: dict, lang: str, sections: dict, notes: list[str]) -> dict:
    out_of_range = []
    for a in data["abnormal_results"]:
        meaning = sections["meanings"].get(a["name"]) or _meaning(a["name"], a["flag"], lang)
        out_of_range.append({"name": a["name"], "value": a["value"], "flag": a["flag"], "flag_label": FLAG_WORD[lang][a["flag"]],
                             "range": a["reference_range"], "meaning": meaning})
    summary = {
        "what_this_is": sections["what_this_is"],
        "key_findings": sections["key_findings"],
        "has_results": bool(data["results"]),
        "out_of_range": out_of_range,
        "medicines": [{"name": m["name"], "generic": m["generic"], "how_to_take": m["how_to_take"], "as_written": m["as_written"]} for m in data["medicines"]],
        "questions": sections["questions"],
        "notes": notes,
        "disclaimer": DISCLAIMER[lang],
    }
    summary["markdown"] = to_markdown(summary, lang)
    return summary


def _notes(doc: dict, ex, lang: str) -> list[str]:
    notes = []
    if medications(ex):
        view = medications_view(doc["patient_id"])
        names = {m.name.value for m in medications(ex)}
        for n in view["reconciliation_notes"]:
            if doc["_id"] in n["documents"] or names & {m["name"] for m in n["medicines"]}:
                notes.append(n["text_hi"] if lang == "hi" else n["text"])
    pending = len(doc.get("confirm_queue") or [])
    if pending:
        notes.append(f"{pending} जानकारी की पुष्टि बाकी है; पुष्टि से पहले कृपया इन्हें ध्यान से देखें।" if lang == "hi"
                     else f"{pending} detail(s) are waiting for your confirmation; please double-check them.")
    return notes


def generate(doc: dict, ex, lang: str) -> tuple[dict, str, int, list[str]]:
    s = get_settings()
    data = summary_input(ex, lang)
    notes = _notes(doc, ex, lang)
    errors: list[str] = []
    if s.summary_mode == "template" or (lang == "hi" and s.hindi_summary_mode == "template"):
        return assemble(ex, data, lang, template_sections(ex, data, lang), notes), "template", 0, errors
    try:
        res = get_llm().structured(
            s.text_model,
            SummaryLLM,
            SYSTEM[lang],
            USER[lang].replace("{data}", json.dumps(data, ensure_ascii=False, default=str)),
            extra_check=make_checker(data, lang),
        )
        errors = res.errors
        if res.obj is not None:
            meanings = {}
            for o in res.obj.out_of_range:
                a = _match_abnormal(o.name, data["abnormal_results"])
                if a:
                    meanings[a["name"]] = o.meaning
            sections = {"what_this_is": res.obj.what_this_is, "key_findings": res.obj.key_findings, "questions": res.obj.questions, "meanings": meanings}
            return assemble(ex, data, lang, sections, notes), "llm", res.attempts, errors
    except LLMUnavailable as exc:
        errors.append(f"llm unavailable: {exc}")
    return assemble(ex, data, lang, template_sections(ex, data, lang), notes), "template", 0, errors


def source_hash(doc: dict, lang: str) -> str:
    payload = json.dumps({"extraction": doc.get("extraction"), "queue": len(doc.get("confirm_queue") or []), "lang": lang}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_summary(doc_id: str, lang: str = "en", refresh: bool = False) -> dict:
    repo = get_repository()
    doc = repo.get("documents", doc_id)
    h = source_hash(doc, lang)
    key = f"{doc_id}:{lang}"
    cached = repo.get("summaries", key)
    if cached and cached.get("source_hash") == h and not refresh:
        return _public(cached)
    ex = load_extraction(doc)
    summary, method, attempts, errors = generate(doc, ex, lang)
    record = {
        "_id": key,
        "document_id": doc_id,
        "lang": lang,
        "source_hash": h,
        "method": method,
        "attempts": attempts,
        "errors": errors[:10],
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    repo.replace("summaries", record)
    return _public(record)


def _public(record: dict) -> dict:
    return {"document_id": record["document_id"], "lang": record["lang"], "method": record["method"], "attempts": record["attempts"],
            **record["summary"]}
