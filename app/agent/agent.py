import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.language import ENGLISH, Language, detect_language, language_from_code, reply_instruction
from app.agent.prompts import ANSWER, GENERAL, PLANNER, SYSTEM
from app.agent.tools import STOPWORDS, TEST_SYNONYMS, TOOLS, PerryTools, ToolError
from app.agent.translate import from_english, target_name, to_english
from app.config import get_settings
from app.llm.client import LLMUnavailable, get_llm
from app.normalize.labs import resolve_lab
from app.summary.safety import HEDGED_INFERENCE, devanagari_ratio, numbers_in, ungrounded_conditions, ungrounded_months, ungrounded_numbers

log = logging.getLogger(__name__)

ToolName = Literal[tuple(TOOLS)]
PERRY_BANNED = [
    "you should stop", "stop taking", "you should start", "start taking", "you should take", "you must take", "you need to take",
    "increase your dose", "increase the dose", "decrease your dose", "reduce your dose", "reduce the dose", "double the dose",
    "skip your dose", "skip the dose", "change your dose", "safe to stop", "you are suffering", "you suffer from", "this confirms",
    "this means you have", "you may have", "you might have", "cured", "guarantee", "guaranteed", "definitely", "nothing to worry",
    "no need to see", "don't need a doctor", "do not need a doctor", "dawa band", "dawai band", "band kar do", "band kar dein",
    "दवा बंद", "खुराक बढ़ा", "खुराक कम",
]
INTERNAL_ID = re.compile(r"\b(doc|pat|bun)_[0-9a-f]{12}\b")
TREATMENT = [
    re.compile(r"\b(should|can|shall|could|may|must)\s+i\b.*\b(stop|start|skip|increase|decrease|reduce|double|change|quit|continue|take)\b"),
    re.compile(r"\b(do|does)\s+i\s+(need|have)\s+to\s+(stop|start|take|continue|change)\b"),
    re.compile(r"\b(band|kam|zyada|jyada|badha|chhod|shuru)\w*\b.*\b(kar|karu|karun|karoon|du|doon|dun|sakta|sakti|lu|loon)\w*\b"),
    re.compile(r"(बंद|कम|ज़्यादा|ज्यादा|बढ़ा|छोड़|शुरू).*(करूं|करूँ|करू|कर दूं|कर दूँ|सकता|सकती|लूं|लूँ)"),
]
GREETING = re.compile(r"^\s*(hi+|hello|hey|hii+|namaste|namaskar|thanks|thank you|thankyou|shukriya|dhanyavad|good (morning|evening|afternoon)|"
                      r"नमस्ते|नमस्कार|धन्यवाद|शुक्रिया|हेलो)\b[\s!.,?]*\w*[\s!.,?]*$")
CAPABILITIES = re.compile(r"\b(what can you do|who are you|help me|how do you work|kya kar sakte|aap kaun)\b|आप क्या कर|तुम कौन")


class PlannedCall(BaseModel):
    tool: ToolName
    args: dict = Field(default_factory=dict)


class Plan(BaseModel):
    calls: list[PlannedCall] = Field(default_factory=list, max_length=3)


@dataclass
class ToolResult:
    tool: str
    args: dict
    ok: bool
    data: dict | None = None
    error: str | None = None


@dataclass
class PerryReply:
    reply: str
    language: Language
    method: str
    intent: str
    results: list[ToolResult] = field(default_factory=list)
    state: str = "ok"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "reply": self.reply,
            "language": self.language.code,
            "language_name": self.language.name,
            "method": self.method,
            "intent": self.intent,
            "state": self.state,
            "tools": [r.tool for r in self.results],
            "sources": sources(self.results),
        }


def sources(results: list[ToolResult]) -> list[dict]:
    seen, out = set(), []

    def visit(node):
        if isinstance(node, dict):
            fn = node.get("filename") or (node.get("source") if isinstance(node.get("source"), str) and "." in node.get("source", "") else None)
            if fn and fn not in seen:
                seen.add(fn)
                out.append({"filename": fn, "title": node.get("title") or node.get("source_type"), "date_text": node.get("date_text"),
                            "document_id": node.get("document_id")})
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    for r in results:
        if r.ok:
            visit(r.data)
    return out[:6]


def _detect_test(text: str) -> str | None:
    low = text.lower()
    words = [w for w in re.findall(r"[a-z0-9%]+", low)]
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            gram = words[i:i + n]
            if n == 1 and (gram[0] in STOPWORDS or len(gram[0]) < 2):
                continue
            ref, score = resolve_lab(" ".join(gram))
            if ref and score >= 98:
                return ref.canonical_name
    for word in sorted(TEST_SYNONYMS, key=len, reverse=True):
        if re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", low):
            return word
    return None


REGIONAL = {
    "medications": ["दवा", "दवाई", "औषध", "ওষুধ", "ঔষধ", "మందు", "மருந்து", "દવા", "دوا", "ದವಾ", "ಔಷಧ", "ଔଷଧ", "മരുന്ന", "ਦਵਾਈ", "ਦਵਾ"],
    "compare": ["बदल", "परिवर्तन", "পরিবর্তন", "బదల", "మార్పు", "மாற்ற", "ફેરફાર", "બદલ", "تبدیل", "ಬದಲ", "ପରିବର୍ତ୍ତନ", "ବଦଳ", "മാറ്റ", "ਬਦਲ"],
    "pending": ["पुष्टि", "पुष्टी", "নিশ্চিত", "నిర్ధార", "உறுதி", "પુષ્ટિ", "تصدیق", "ದೃಢ", "ନିଶ୍ଚିତ", "സ്ഥിരീകര", "ਪੁਸ਼ਟੀ"],
    "labs": ["जांच", "चाचणी", "পরীক্ষা", "పరీక్ష", "பரிசோதனை", "சோதனை", "તપાસ", "ٹیسٹ", "ಪರೀಕ್ಷೆ", "ପରୀକ୍ଷା", "പരിശോധന", "ਟੈਸਟ", "ਜਾਂਚ"],
    "documents": ["रिपोर्ट", "अहवाल", "রিপোর্ট", "প্রতিবেদন", "నివేదిక", "రిపోర్ట", "அறிக்கை", "ரிப்போர்ட", "રિપોર્ટ", "અહેવાલ", "رپورٹ",
                  "ವರದಿ", "ರಿಪೋರ್ಟ", "ରିପୋର୍ଟ", "ବିବରଣୀ", "റിപ്പോർട്ട", "റിപ്പോര്ട്ട", "ਰਿਪੋਰਟ", "दस्तावेज़", "दस्तऐवज"],
}
REGIONAL_TOOLS = {"medications": ("get_my_medications", {}), "compare": ("compare_my_reports", {}), "pending": ("get_pending_confirmations", {}),
                  "labs": ("get_my_labs", {"limit": 10}), "documents": ("get_my_documents", {"limit": 8})}


def _regional_intent(message: str) -> tuple[str, list[tuple[str, dict]]] | None:
    for intent, words in REGIONAL.items():
        if any(w in message for w in words):
            name, args = REGIONAL_TOOLS[intent]
            return intent, [(name, dict(args))]
    return None


def route(message: str, lang: Language) -> tuple[str, list[tuple[str, dict]]]:
    m = message.lower().strip()
    has = lambda *words: any(re.search(rf"(?<![\w]){w}", m) for w in words)
    test = _detect_test(m)
    summary_lang = "hi" if lang.code == "hi" else "en"
    if any(p.search(m) for p in TREATMENT):
        return "treatment", [("get_my_medications", {})]
    if GREETING.match(m) or CAPABILITIES.search(m):
        return "general", []
    if has("what do you know", "overview", "everything", "what else", "summar\\w* my (recent )?(health )?records", "about my records",
           "records? ke baare", "sab kuch", "sabkuch", "रिकॉर्ड के बारे", "सब कुछ", "मेरे बारे"):
        return "overview", [("get_my_overview", {})]
    if has("confirm", "pending", "waiting", "verify", "पुष्टि", "confirmation"):
        return "pending", [("get_pending_confirmations", {})]
    if has("change", "changed", "compare", "comparison", "difference", "differ", "improv", "badla", "badlav", "badal", "farak", "fark",
           "बदला", "बदलाव", "फर्क", "अंतर", "trend"):
        return "compare", [("compare_my_reports", {"test": test} if test else {})]
    if has("explain", "samjha", "samjhao", "samjhaiye", "समझा", "मतलब", "summary of", "summarise", "summarize", "what does my", "kya kehta", "kya kehti"):
        target = "latest_lab_report" if has("lab", "blood", "test") else "latest_prescription" if has("prescription", "parcha", "पर्चा") \
            else "latest_discharge_summary" if has("discharge", "डिस्चार्ज") else "latest"
        return "summary", [("get_my_summary", {"document_id": target, "language": summary_lang})]
    if has("discharge", "hospital", "admission", "admitted", "डिस्चार्ज", "अस्पताल", "भर्ती"):
        return "document", [("get_my_document", {"document_id": "latest_discharge_summary"})]
    if has("medicine", "medication", "meds", "tablet", "drug", "dawa", "dawai", "दवा", "दवाई", "दवाइयां", "pill", "prescribed"):
        if has("most recent", "recently", "latest", "last", "newest", "aakhri", "akhri", "pichl", "हाल", "आखिरी") and has("prescri"):
            return "document", [("get_my_document", {"document_id": "latest_prescription"})]
        return "medications", [("get_my_medications", {})]
    if has("prescription", "parcha", "पर्चा"):
        return "document", [("get_my_document", {"document_id": "latest_prescription"})]
    if has("mention", "which document", "which report", "find", "search", "look for", "where", "kahan", "kahaan", "कहां", "ढूंढ"):
        return "search", [("search_my_records", {"query": message.strip()[:200]})]
    if test:
        return "labs", [("get_my_labs", {"test": test, "limit": 5})]
    if has("upload", "documents", "files", "दस्तावेज़", "reports"):
        return "documents", [("get_my_documents", {"limit": 8})]
    if has("timeline", "history", "itihas", "इतिहास"):
        return "timeline", [("get_my_timeline", {"limit": 8})]
    if has("latest report", "last report", "recent report", "new report", "report", "रिपोर्ट"):
        return "document", [("get_my_document", {"document_id": "latest"})]
    if has("my name", "profile", "abha", "my age", "who am i", "mera naam", "मेरा नाम"):
        return "profile", [("get_my_profile", {})]
    regional = _regional_intent(message)
    if regional:
        return regional
    return "search", [("search_my_records", {"query": message.strip()[:200]})]


INTENT_OF_TOOL = {"get_my_overview": "overview", "get_pending_confirmations": "pending", "compare_my_reports": "compare",
                  "get_my_summary": "summary", "get_my_document": "document", "get_my_medications": "medications",
                  "get_my_labs": "labs", "get_my_documents": "documents", "get_my_timeline": "timeline", "get_my_profile": "profile",
                  "search_my_records": "search"}


def _history_text(history: list[dict]) -> str:
    lines = []
    for h in history:
        who = "User" if h.get("role") == "user" else "PERRY"
        lines.append(f"{who}: {str(h.get('content', ''))[:400]}")
    return "\n".join(lines) or "(no earlier messages)"


def _strip_ids(node):
    if isinstance(node, dict):
        return {k: _strip_ids(v) for k, v in node.items() if k != "document_id"}
    if isinstance(node, list):
        return [_strip_ids(v) for v in node]
    return node


def _script_ratio(text: str, lang: Language) -> float:
    from app.agent.language import SCRIPTS

    lo, hi = SCRIPTS[lang.code][1]
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters) if letters else 0.0


class Perry:
    def __init__(self, patient_id: str):
        self.tools = PerryTools(patient_id)
        self.settings = get_settings()

    def respond(self, message: str, history: list[dict] | None = None, language: str | None = None) -> PerryReply:
        message = (message or "").strip()[:1000]
        history = (history or [])[-self.settings.perry_history_turns * 2:]
        lang = language_from_code(language) if language else detect_language(message)
        if not self._translates(lang):
            return self._respond(message, history, lang)
        english = to_english(message, lang) if self.settings.perry_indic_mode == "translate" else None
        reply = self._respond(english or message, history, ENGLISH)
        if self.settings.perry_indic_mode == "translate":
            text, quality = from_english(reply.reply, lang)
        else:
            text, quality = reply.reply, 0.0
        name = target_name(lang)
        if quality == 0.0:
            text += f"\n\n_(I couldn't answer in {name} right now, so here it is in English.)_"
        elif quality < 1.0:
            text += "\n\n_(Some lines are kept in English so that values and names stay exact.)_"
        reply.reply = text
        reply.language = lang
        reply.method = f"{reply.method}+translated" if quality > 0 else reply.method
        return reply

    def _translates(self, lang: Language) -> bool:
        if lang.code in ("en", "hinglish") or self.settings.perry_indic_mode == "llm":
            return False
        if lang.code == "hi":
            return self.settings.perry_hindi_mode == "translate"
        return True

    def _respond(self, message: str, history: list[dict], lang: Language) -> PerryReply:
        intent, routed = route(message, lang)
        errors: list[str] = []
        use_llm = self.settings.perry_mode == "llm"
        calls = routed
        if use_llm and intent not in ("treatment",):
            planned, plan_errors = self._plan(message, history)
            errors.extend(plan_errors)
            if planned is not None and (planned or intent == "general"):
                calls = planned
                intent = INTENT_OF_TOOL.get(planned[0][0], "search") if planned else "general"
        results = [self._run(name, args) for name, args in calls[: self.settings.perry_max_tool_calls]]
        if results and not any(r.ok for r in results):
            return PerryReply(compose_error(results, lang), lang, "composed", intent, results, "error", errors)
        if intent == "treatment":
            return PerryReply(compose(intent, results, lang, message), lang, "composed", intent, results, "ok", errors)
        if use_llm and not (lang.code == "hi" and self.settings.perry_hindi_mode == "template"):
            text, answer_errors = self._answer(message, history, lang, results)
            errors.extend(answer_errors)
            if text:
                return PerryReply(text, lang, "llm", intent, results, _state(results), errors)
        return PerryReply(compose(intent, results, lang, message), lang, "composed", intent, results, _state(results), errors)

    def _run(self, name: str, args: dict) -> ToolResult:
        try:
            return ToolResult(name, args, True, self.tools.call(name, args))
        except ToolError as exc:
            return ToolResult(name, args, False, error=str(exc))

    def _plan(self, message: str, history: list[dict]) -> tuple[list[tuple[str, dict]] | None, list[str]]:
        catalog = "\n".join(f"- {t['name']}({', '.join(t['args']) or ''}): {t['description']}" for t in PerryTools.specs())
        prompt = PLANNER.format(tools=catalog, max_calls=self.settings.perry_max_tool_calls, history=_history_text(history), message=message)

        def check(plan: Plan) -> list[str]:
            problems = []
            for c in plan.calls:
                model, _ = TOOLS[c.tool]
                try:
                    model.model_validate(c.args)
                except Exception as exc:
                    problems.append(f"{c.tool} args invalid: {str(exc).splitlines()[0]}; allowed args: {list(model.model_fields)}")
            return problems

        try:
            res = get_llm().structured(self.settings.text_model, Plan, SYSTEM, prompt, extra_check=check, num_predict=200)
        except LLMUnavailable as exc:
            return None, [f"planner unavailable: {exc}"]
        if res.obj is None:
            return None, [f"planner rejected: {e}" for e in res.errors[:4]]
        return [(c.tool, c.args) for c in res.obj.calls], [f"planner: {e}" for e in res.errors[:4]]

    def _answer(self, message: str, history: list[dict], lang: Language, results: list[ToolResult]) -> tuple[str | None, list[str]]:
        if results:
            payload = [{"tool": r.tool, **({"data": _strip_ids(r.data)} if r.ok else {"error": r.error})} for r in results]
            data = json.dumps(payload, ensure_ascii=False, default=str)[: self.settings.perry_result_chars]
            user = ANSWER.format(language=reply_instruction(lang), history=_history_text(history), data=data, message=message)
        else:
            data = ""
            user = GENERAL.format(language=reply_instruction(lang), history=_history_text(history), message=message)
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        errors: list[str] = []
        for _ in range(2):
            try:
                text = get_llm().chat(self.settings.text_model, messages, num_predict=500)
            except LLMUnavailable as exc:
                return None, [f"answer unavailable: {exc}"]
            text = (text or "").strip()
            problems = check_answer(text, lang, data, message, history)
            if not problems:
                return text, errors
            errors.extend(problems)
            messages = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": "Rewrite your answer. Problems: " + "; ".join(problems)
                                    + ". Use only the data given, keep the same language, and answer briefly."}]
        return None, errors


def _state(results: list[ToolResult]) -> str:
    for r in results:
        if r.ok and r.data and r.data.get("note") and not any(r.data.get(k) for k in ("results", "matches", "lab_changes", "medicines", "items")):
            return "not_found"
    return "ok"


def check_answer(text: str, lang: Language, data: str, message: str, history: list[dict]) -> list[str]:
    problems = []
    if not text or text[:1] in "{[" or len(text) < 2:
        return ["the answer was empty or not plain text"]
    low = text.lower()
    hits = [m.group(0) for m in HEDGED_INFERENCE.finditer(text)] + [p for p in PERRY_BANNED if p in low]
    if hits:
        problems.append(f"remove speculation or treatment advice ({', '.join(sorted(set(hits)))})")
    context = data + " " + message + " " + " ".join(str(h.get("content", "")) for h in history if h.get("role") == "user")
    extra = ungrounded_numbers(text, numbers_in(context))
    if extra:
        problems.append(f"numbers not in the data: {extra}")
    months = ungrounded_months(text, data)
    if months:
        problems.append(f"months that do not match the data: {months}")
    cond = ungrounded_conditions(text, context, "hi" if lang.is_hindi_family else "en")
    if cond:
        problems.append(f"conditions not written in the records: {cond}")
    if INTERNAL_ID.search(text):
        problems.append("do not show internal ids")
    if lang.code == "en" and devanagari_ratio(text) > 0.2:
        problems.append("reply in English")
    if lang.code == "hinglish" and devanagari_ratio(text) > 0.2:
        problems.append("reply in Hinglish using Roman letters, not Devanagari")
    if lang.code not in ("en", "hinglish") and _script_ratio(text, lang) < 0.3:
        problems.append(f"reply in {lang.name} script")
    return problems


PH = {
    "en": {
        "not_found": "I couldn't find that information in your health records.",
        "error": "I couldn't access that part of your records right now. Please try again in a moment.",
        "greeting": "Hi! I'm PERRY, your personal health assistant. Ask me about your reports, lab values, medicines, your timeline, or anything waiting for confirmation.",
        "treatment": "I can't make that decision for you — starting, stopping or changing a medicine is something to decide with your doctor. Here's what your records show, exactly as written:",
        "treatment_none": "I can't make that decision for you — starting, stopping or changing a medicine is something to decide with your doctor. I couldn't find medicines in your health records.",
        "latest_lab": "Your latest **{name}** was **{value}**{flag}, according to your {stype} dated {date}.",
        "earlier": "Earlier: {items}.",
        "labs_head": "Here are your most recent lab results:",
        "meds_head": "Here are the medicines in your records, exactly as written:",
        "meds_current": "Currently active (as of {date}):",
        "meds_older": "Also recorded earlier:",
        "docs_head": "You have {count} document(s) in PERRY. Most recent first:",
        "timeline_head": "Here's your health timeline, newest first:",
        "pending_head": "{count} detail(s) are waiting for your confirmation:",
        "pending_none": "Good news — nothing is waiting for your confirmation.",
        "compare_head": "Here's what changed between your two most recent measurements:",
        "compare_none": "Nothing to compare yet — no lab test appears on two different dates in your records.",
        "overview_head": "Here's a quick overview of your health records, {name}:",
        "ov_docs": "**{total}** documents ({types}), from {first} to {last}.",
        "ov_latest": "Latest: {items}.",
        "ov_abn": "Out of range in your latest lab report ({date}): {items}.",
        "ov_meds": "Current medicines: {items}.",
        "ov_pending": "{count} detail(s) waiting for your confirmation.",
        "ov_dupes": "Note: {text}",
        "search_head": "Here's what I found for “{query}”:",
        "profile": "Your profile: **{name}**{age}{sex}. ABHA number {abha} ({status}), ABHA address {addr}.",
        "rx_head": "Your {stype} from **{who}** dated {date}:",
        "dx": "Your records list: {items}.",
        "lab_doc_head": "Your lab report from **{who}** dated {date} has {n} results.",
        "lab_doc_abn": "Outside the reference range: {items}.",
        "lab_doc_ok": "All results with a reference range are within it.",
        "ds_head": "Your discharge summary from **{who}**: admitted {admitted}, discharged {discharged}.",
        "followup": "Follow-up: {text}",
        "advice": "Advice: {text}",
        "summary_note": "This is an explanation of your document, not a diagnosis — please discuss it with your doctor.",
        "flag": {"high": "high", "low": "low", "critical": "far outside range", "normal": "within range", "unknown": "no reference range"},
        "dir": {"up": "up", "down": "down", "same": "unchanged"},
        "current": "current",
        "source": "{stype}, {date}",
    },
    "hi": {
        "not_found": "मुझे यह जानकारी आपके हेल्थ रिकॉर्ड में नहीं मिली।",
        "error": "मैं अभी आपके रिकॉर्ड का यह हिस्सा नहीं खोल पाया। कृपया थोड़ी देर बाद फिर कोशिश करें।",
        "greeting": "नमस्ते! मैं PERRY हूं, आपका पर्सनल हेल्थ असिस्टेंट। अपनी रिपोर्ट, लैब मान, दवाएं, टाइमलाइन या पुष्टि के लिए बाकी जानकारी के बारे में पूछिए।",
        "treatment": "यह फैसला मैं नहीं ले सकता — कोई दवा शुरू करना, बंद करना या बदलना अपने डॉक्टर से तय करें। आपके रिकॉर्ड में जैसा लिखा है, वैसा यहां है:",
        "treatment_none": "यह फैसला मैं नहीं ले सकता — कोई दवा शुरू करना, बंद करना या बदलना अपने डॉक्टर से तय करें। आपके रिकॉर्ड में कोई दवा नहीं मिली।",
        "latest_lab": "आपका सबसे हाल का **{name}** **{value}** था{flag}, आपकी {stype} ({date}) के अनुसार।",
        "earlier": "पहले: {items}।",
        "labs_head": "आपके सबसे हाल के लैब परिणाम:",
        "meds_head": "आपके रिकॉर्ड में दवाएं, जैसा लिखा है:",
        "meds_current": "अभी चल रही ({date} तक):",
        "meds_older": "पहले लिखी गई:",
        "docs_head": "PERRY में आपके {count} दस्तावेज़ हैं। सबसे नए पहले:",
        "timeline_head": "आपकी हेल्थ टाइमलाइन, सबसे नई पहले:",
        "pending_head": "{count} जानकारी आपकी पुष्टि का इंतज़ार कर रही है:",
        "pending_none": "अच्छी खबर — पुष्टि के लिए कुछ भी बाकी नहीं है।",
        "compare_head": "आपकी पिछली दो जांचों के बीच यह बदला:",
        "compare_none": "अभी तुलना के लिए कुछ नहीं है — कोई भी जांच दो अलग तारीखों पर नहीं है।",
        "overview_head": "{name}, आपके हेल्थ रिकॉर्ड का छोटा सा सार:",
        "ov_docs": "**{total}** दस्तावेज़ ({types}), {first} से {last} तक।",
        "ov_latest": "सबसे नए: {items}।",
        "ov_abn": "आपकी सबसे नई लैब रिपोर्ट ({date}) में सीमा से बाहर: {items}।",
        "ov_meds": "अभी चल रही दवाएं: {items}।",
        "ov_pending": "{count} जानकारी आपकी पुष्टि का इंतज़ार कर रही है।",
        "ov_dupes": "ध्यान दें: {text}",
        "search_head": "“{query}” के लिए मुझे यह मिला:",
        "profile": "आपकी प्रोफ़ाइल: **{name}**{age}{sex}। ABHA नंबर {abha} ({status}), ABHA पता {addr}।",
        "rx_head": "**{who}** की आपकी {stype} ({date}):",
        "dx": "आपके रिकॉर्ड में लिखा है: {items}।",
        "lab_doc_head": "**{who}** की आपकी लैब रिपोर्ट ({date}) में {n} परिणाम हैं।",
        "lab_doc_abn": "सामान्य सीमा से बाहर: {items}।",
        "lab_doc_ok": "जिन परिणामों की सीमा दी है, वे सभी सीमा के अंदर हैं।",
        "ds_head": "**{who}** का आपका डिस्चार्ज सारांश: भर्ती {admitted}, छुट्टी {discharged}।",
        "followup": "फॉलो-अप: {text}",
        "advice": "सलाह: {text}",
        "summary_note": "यह आपके दस्तावेज़ की व्याख्या है, निदान नहीं — कृपया अपने डॉक्टर से बात करें।",
        "flag": {"high": "अधिक", "low": "कम", "critical": "सीमा से बहुत बाहर", "normal": "सामान्य सीमा में", "unknown": "सीमा नहीं दी"},
        "dir": {"up": "बढ़ा", "down": "घटा", "same": "बराबर"},
        "current": "चालू",
        "source": "{stype}, {date}",
    },
    "hinglish": {
        "not_found": "Mujhe yeh jaankari aapke health records mein nahi mili.",
        "error": "Main abhi aapke records ka yeh hissa access nahi kar paaya. Thodi der baad phir try kijiye.",
        "greeting": "Namaste! Main PERRY hoon, aapka personal health assistant. Apni reports, lab values, medicines, timeline ya pending confirmations ke baare mein kuch bhi poochiye.",
        "treatment": "Yeh faisla main nahi le sakta — koi dawa shuru karni hai, band karni hai ya badalni hai, yeh apne doctor se tay kijiye. Aapke records mein jaisa likha hai, woh yeh hai:",
        "treatment_none": "Yeh faisla main nahi le sakta — dawa ke baare mein apne doctor se baat kijiye. Aapke records mein koi dawa nahi mili.",
        "latest_lab": "Aapka latest **{name}** **{value}** tha{flag}, aapki {stype} ({date}) ke hisaab se.",
        "earlier": "Pehle: {items}.",
        "labs_head": "Yeh rahe aapke latest lab results:",
        "meds_head": "Aapke records mein yeh medicines hain, bilkul jaisa likha hai:",
        "meds_current": "Abhi chal rahi ({date} tak):",
        "meds_older": "Pehle likhi gayi:",
        "docs_head": "PERRY mein aapke {count} documents hain. Sabse naye pehle:",
        "timeline_head": "Yeh rahi aapki health timeline, sabse nayi pehle:",
        "pending_head": "{count} details aapke confirmation ka wait kar rahi hain:",
        "pending_none": "Good news — kuch bhi confirmation ke liye pending nahi hai.",
        "compare_head": "Aapki pichhli do measurements ke beech yeh badla:",
        "compare_none": "Abhi compare karne ke liye kuch nahi hai — koi bhi test do alag dates par nahi hai.",
        "overview_head": "{name}, yeh raha aapke health records ka quick overview:",
        "ov_docs": "**{total}** documents ({types}), {first} se {last} tak.",
        "ov_latest": "Sabse naye: {items}.",
        "ov_abn": "Aapki latest lab report ({date}) mein range se bahar: {items}.",
        "ov_meds": "Abhi chal rahi medicines: {items}.",
        "ov_pending": "{count} details confirmation ke liye pending hain.",
        "ov_dupes": "Dhyan dein: {text}",
        "search_head": "“{query}” ke liye mujhe yeh mila:",
        "profile": "Aapki profile: **{name}**{age}{sex}. ABHA number {abha} ({status}), ABHA address {addr}.",
        "rx_head": "**{who}** ki aapki {stype} ({date}):",
        "dx": "Aapke records mein likha hai: {items}.",
        "lab_doc_head": "**{who}** ki aapki lab report ({date}) mein {n} results hain.",
        "lab_doc_abn": "Range se bahar: {items}.",
        "lab_doc_ok": "Jin results ki range di hai, woh sab range ke andar hain.",
        "ds_head": "**{who}** ka aapka discharge summary: admit {admitted}, discharge {discharged}.",
        "followup": "Follow-up: {text}",
        "advice": "Salah: {text}",
        "summary_note": "Yeh aapke document ka explanation hai, diagnosis nahi — please apne doctor se discuss kijiye.",
        "summary_head": "Yeh rahi aapki latest {stype} ({date}) ki simple explanation:",
        "flag": {"high": "high", "low": "low", "critical": "range se kaafi bahar", "normal": "normal range mein", "unknown": "range nahi di"},
        "dir": {"up": "badha", "down": "ghata", "same": "same raha"},
        "current": "chalu",
        "source": "{stype}, {date}",
    },
}
STYPE_HI = {"Lab report": "लैब रिपोर्ट", "Prescription": "पर्चा", "Discharge summary": "डिस्चार्ज सारांश"}


def _ph(lang: Language) -> tuple[dict, str]:
    key = lang.code if lang.code in PH else "en"
    return PH[key], key


def _val(v, unit) -> str:
    return f"{v} {unit}".strip() if unit and unit != "%" else f"{v}{unit or ''}"


def _stype(stype: str | None, key: str) -> str:
    stype = stype or "document"
    if key == "hi":
        return STYPE_HI.get(stype, stype)
    return stype.lower() if key == "en" else stype.lower()


def _flag(flag: str | None, P: dict) -> str:
    return P["flag"].get(flag or "unknown", flag or "")


def compose_error(results: list[ToolResult], lang: Language) -> str:
    P, _ = _ph(lang)
    msgs = [r.error for r in results if r.error and not r.error.startswith(("Invalid arguments", "Unknown tool"))]
    specific = [m for m in msgs if "couldn't access" not in m]
    if lang.code == "en" and specific:
        return specific[0]
    return P["not_found"] if specific else P["error"]


def compose(intent: str, results: list[ToolResult], lang: Language, message: str = "") -> str:
    P, key = _ph(lang)
    if intent == "general" or not results:
        return P["greeting"]
    blocks = []
    for r in results:
        if not r.ok:
            continue
        fn = RENDER.get(r.tool)
        if fn:
            text = fn(r.data, P, key, intent)
            if text:
                blocks.append(text)
    if intent == "treatment":
        meds = next((r.data for r in results if r.ok and r.tool == "get_my_medications"), None)
        if not meds or not meds.get("medicines"):
            return P["treatment_none"]
        named = _named_medicines(meds["medicines"], message)
        if named:
            return P["treatment"] + "\n\n" + "\n".join(_med_line(m, P, key) for m in named)
        return P["treatment"] + "\n\n" + _render_meds(meds, P, key, intent, only_current=True)
    if not blocks:
        return P["not_found"]
    text = "\n\n".join(blocks)
    if lang.code not in PH:
        text += "\n\n_(Sorry, I can only answer in English, Hindi or Hinglish right now.)_"
    return text


def _named_medicines(meds: list[dict], message: str) -> list[dict]:
    from rapidfuzz import fuzz

    words = [w for w in re.findall(r"[a-z0-9]+", message.lower()) if len(w) >= 4 and w not in STOPWORDS]
    out = []
    for m in meds:
        hay = f"{m.get('name') or ''} {m.get('generic') or ''}".lower()
        if any(fuzz.partial_ratio(w, hay) >= 90 for w in words):
            out.append(m)
    return out


def _render_labs(d: dict, P: dict, key: str, intent: str) -> str:
    rows = d.get("results") or []
    if not rows:
        return P["not_found"]
    if d.get("test"):
        latest = rows[0]
        flag = f" ({_flag(latest['flag'], P)})" if latest.get("flag") else ""
        lines = [P["latest_lab"].format(name=latest["name"], value=_val(latest["value"], latest.get("unit")), flag=flag,
                                        stype=_stype(latest.get("source_type"), key), date=latest.get("date_text") or "—")]
        same = [x for x in rows[1:] if x["name"] == latest["name"]][:3]
        if same:
            lines.append(P["earlier"].format(items=", ".join(f"{_val(x['value'], x.get('unit'))} ({x.get('date_text')})" for x in same)))
        others = [x for x in rows[1:] if x["name"] != latest["name"]]
        seen = set()
        for x in others:
            if x["name"] in seen:
                continue
            seen.add(x["name"])
            lines.append(f"- **{x['name']}**: {_val(x['value'], x.get('unit'))} ({_flag(x.get('flag'), P)}) · {x.get('date_text')}")
        return "\n".join(lines)
    lines = [P["labs_head"]] + [f"- **{x['name']}**: {_val(x['value'], x.get('unit'))} ({_flag(x.get('flag'), P)}) · {x.get('date_text')}" for x in rows]
    return "\n".join(lines)


def _med_line(m: dict, P: dict, key: str) -> str:
    generic = f" ({m['generic']})" if m.get("generic") else ""
    written = " ".join(x for x in (m.get("dosage"), m.get("timing"), m.get("duration"), m.get("instructions")) if x)
    how = written or m.get("how_to_take") or ""
    src = P["source"].format(stype=_stype(m.get("source_type"), key), date=m.get("date_text") or "—")
    return f"- **{m['name']}**{generic} — {how} · _{src}_"


def _render_meds(d: dict, P: dict, key: str, intent: str, only_current: bool = False) -> str:
    meds = d.get("medicines") or []
    if not meds:
        return P["not_found"]
    current = [m for m in meds if m.get("current")]
    older = [m for m in meds if not m.get("current")]
    lines = [P["meds_head"]]
    if current:
        lines.append(P["meds_current"].format(date=d.get("as_of")))
        lines += [_med_line(m, P, key) for m in current]
    if older and not only_current:
        lines.append(P["meds_older"])
        lines += [_med_line(m, P, key) for m in older[:8]]
    if not current and only_current:
        lines += [_med_line(m, P, key) for m in older[:8]]
    for n in d.get("duplicate_medicine_notes") or []:
        lines.append(f"\n> ⚠️ {n}")
    return "\n".join(lines)


def _render_docs(d: dict, P: dict, key: str, intent: str) -> str:
    docs = d.get("documents") or []
    if not docs:
        return P["not_found"]
    lines = [P["docs_head"].format(count=d.get("count", len(docs)))]
    for x in docs:
        pending = f" · ⏳ {x['pending_confirmations']}" if x.get("pending_confirmations") else ""
        lines.append(f"- **{_stype(x.get('title'), key).capitalize() if key != 'hi' else _stype(x.get('title'), key)}** · {x.get('date_text') or '—'} · {x.get('filename')}{pending}")
    return "\n".join(lines)


def _render_timeline(d: dict, P: dict, key: str, intent: str) -> str:
    items = d.get("timeline") or []
    if not items:
        return P["not_found"]
    lines = [P["timeline_head"]]
    for t in items:
        hl = ", ".join(t.get("highlights") or [])
        who = f" · {t['source']}" if t.get("source") else ""
        lines.append(f"- **{t.get('date_text') or '—'}** — {_stype(t.get('title'), key)}{who}" + (f": {hl}" if hl else ""))
    return "\n".join(lines)


def _render_pending(d: dict, P: dict, key: str, intent: str) -> str:
    if not d.get("count"):
        return P["pending_none"]
    lines = [P["pending_head"].format(count=d["count"])]
    for q in d.get("items", [])[:8]:
        lines.append(f"- {q.get('label')}: **{q.get('value')}** · _{_stype(q.get('source_type'), key)}, {q.get('date_text') or '—'}_")
    return "\n".join(lines)


def _render_compare(d: dict, P: dict, key: str, intent: str) -> str:
    changes = d.get("lab_changes") or []
    if not changes:
        return P["compare_none"]
    lines = [P["compare_head"]]
    for c in changes[:10]:
        prev, cur = c["previous"], c["latest"]
        flags = f" ({_flag(prev.get('flag'), P)} → {_flag(cur.get('flag'), P)})" if c.get("flag_changed") else f" ({_flag(cur.get('flag'), P)})"
        lines.append(f"- **{c['name']}**: {_val(prev['value'], prev.get('unit'))} → **{_val(cur['value'], cur.get('unit'))}** "
                     f"{P['dir'][c['direction']]}{flags} · {prev.get('date_text')} → {cur.get('date_text')}")
    return "\n".join(lines)


def _render_overview(d: dict, P: dict, key: str, intent: str) -> str:
    docs = d.get("documents") or {}
    if not docs.get("total"):
        return P["not_found"]
    types = ", ".join(f"{n} {_stype(t, key)}" for t, n in docs.get("by_type", {}).items())
    rng = d.get("date_range") or {}
    lines = [P["overview_head"].format(name=d.get("name") or ""),
             "- " + P["ov_docs"].format(total=docs["total"], types=types, first=rng.get("first") or "—", last=rng.get("last") or "—")]
    latest = d.get("latest_documents") or []
    if latest:
        lines.append("- " + P["ov_latest"].format(items="; ".join(f"{_stype(x.get('title'), key)} ({x.get('date_text') or '—'})" for x in latest)))
    abn = d.get("latest_out_of_range") or []
    if abn:
        lines.append("- " + P["ov_abn"].format(date=(d.get("latest_lab_report") or {}).get("date_text") or "—",
                                               items=", ".join(f"{a['name']} {_val(a['value'], a.get('unit'))} ({_flag(a['flag'], P)})" for a in abn)))
    if d.get("current_medicines"):
        lines.append("- " + P["ov_meds"].format(items=", ".join(d["current_medicines"])))
    if d.get("pending_confirmations"):
        lines.append("- " + P["ov_pending"].format(count=d["pending_confirmations"]))
    for n in d.get("duplicate_medicine_notes") or []:
        lines.append("\n> ⚠️ " + P["ov_dupes"].format(text=n))
    return "\n".join(lines)


def _render_search(d: dict, P: dict, key: str, intent: str) -> str:
    if d.get("overview"):
        return _render_overview(d["overview"], P, key, intent)
    matches = d.get("matches") or []
    if not matches:
        return P["not_found"]
    lines = [P["search_head"].format(query=d.get("query"))]
    for m in matches[:8]:
        src = f" · _{_stype(m.get('source_type'), key)}, {m.get('date_text') or '—'}_" if m.get("source_type") else ""
        kind = m["kind"]
        if kind == "lab_result":
            body = f"**{m['name']}**: {_val(m['value'], m.get('unit'))} ({_flag(m.get('flag'), P)})"
        elif kind == "medicine":
            body = f"💊 **{m['name']}**" + (f" ({m['generic']})" if m.get("generic") else "") + (f" — {m['as_written']}" if m.get("as_written") else "")
        elif kind == "document":
            body = f"📄 {_stype(m.get('title'), key)} · {m.get('filename')}"
        elif kind == "summary":
            body = m.get("what_this_is") or ""
        elif kind == "pending_confirmation":
            body = f"⏳ {m.get('label')}: {m.get('value')}"
        else:
            body = m.get("text") or m.get("label") or ""
        lines.append(f"- {body}{src}")
    return "\n".join(lines)


def _render_profile(d: dict, P: dict, key: str, intent: str) -> str:
    age = f", ~{d['approx_age']}" if d.get("approx_age") else ""
    sex = f", {d['sex']}" if d.get("sex") else ""
    return P["profile"].format(name=d.get("name"), age=age, sex=sex, abha=d.get("abha_number") or "—", status=d.get("abha_status"),
                               addr=d.get("abha_address") or "—")


def _render_document(d: dict, P: dict, key: str, intent: str) -> str:
    if d.get("note") and not d.get("type"):
        return d["note"]
    t = d.get("type")
    lines = []
    if t == "lab_report":
        results = d.get("results") or []
        lines.append(P["lab_doc_head"].format(who=d.get("lab") or "—", date=d.get("date_text") or "—", n=len(results)))
        abn = [r for r in results if r.get("flag") in ("high", "low", "critical")]
        if abn:
            lines.append(P["lab_doc_abn"].format(items=", ".join(f"**{r['name']}** {_val(r['value'], r.get('unit'))} ({_flag(r['flag'], P)})" for r in abn)))
        else:
            lines.append(P["lab_doc_ok"])
    elif t == "prescription":
        lines.append(P["rx_head"].format(stype=_stype("Prescription", key), who=d.get("doctor") or d.get("clinic") or "—", date=d.get("date_text") or "—"))
        lines += [_med_line({**m, "source_type": None, "date_text": None}, P, key).split(" · _")[0] for m in d.get("medicines") or []]
        if d.get("diagnoses_as_written"):
            lines.append(P["dx"].format(items=", ".join(d["diagnoses_as_written"])))
        if d.get("follow_up"):
            lines.append(P["followup"].format(text=d["follow_up"]))
    elif t == "discharge_summary":
        lines.append(P["ds_head"].format(who=d.get("hospital") or "—", admitted=d.get("admitted") or "—", discharged=d.get("discharged") or "—"))
        if d.get("diagnoses_as_written"):
            lines.append(P["dx"].format(items=", ".join(d["diagnoses_as_written"])))
        abn = [r for r in d.get("investigations") or [] if r.get("flag") in ("high", "low", "critical")]
        if abn:
            lines.append(P["lab_doc_abn"].format(items=", ".join(f"**{r['name']}** {_val(r['value'], r.get('unit'))} ({_flag(r['flag'], P)})" for r in abn)))
        lines += [_med_line({**m, "source_type": None, "date_text": None}, P, key).split(" · _")[0] for m in d.get("discharge_medicines") or []]
        if d.get("follow_up"):
            lines.append(P["followup"].format(text=d["follow_up"]))
        if d.get("advice"):
            lines.append(P["advice"].format(text="; ".join(d["advice"])))
    if d.get("note"):
        lines.append(d["note"])
    return "\n".join(lines)


def _render_summary(d: dict, P: dict, key: str, intent: str) -> str:
    lines = [P["summary_head"].format(stype=_stype(d.get("title"), key), date=d.get("date_text") or "—")] if P.get("summary_head") else []
    lines.append(d.get("what_this_is") or "")
    lines += [f"- {k}" for k in d.get("key_findings") or []]
    for o in d.get("out_of_range") or []:
        rng = f", range {o['range']}" if o.get("range") else ""
        lines.append(f"- **{o['name']}: {o['value']}** ({_flag(o['flag'], P)}{rng}) — {o['meaning']}")
    for m in d.get("medicines") or []:
        lines.append(f"- 💊 **{m['name']}**" + (f" ({m['generic']})" if m.get("generic") else "") + f" — {m.get('how_to_take') or ''}")
    for n in d.get("notes") or []:
        lines.append(f"\n> ⚠️ {n}")
    lines.append(f"\n_{P['summary_note']}_")
    return "\n".join(x for x in lines if x is not None)


RENDER = {
    "get_my_labs": _render_labs,
    "get_my_medications": _render_meds,
    "get_my_documents": _render_docs,
    "get_my_timeline": _render_timeline,
    "get_pending_confirmations": _render_pending,
    "compare_my_reports": _render_compare,
    "get_my_overview": _render_overview,
    "search_my_records": _render_search,
    "get_my_profile": _render_profile,
    "get_my_document": _render_document,
    "get_my_summary": _render_summary,
}
