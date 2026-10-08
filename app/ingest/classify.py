import re
from typing import Literal

from pydantic import BaseModel

from app.config import get_settings
from app.llm.client import LLMUnavailable, get_llm

DocType = Literal["lab_report", "prescription", "discharge_summary"]

RULES: dict[str, list[tuple[str, int]]] = {
    "lab_report": [
        (r"\bbio\.? ?ref", 3), (r"\breference (range|interval)", 3), (r"\bref\.? range", 2), (r"\binterval\b", 1),
        (r"\blab(oratory)? (no|id)\b", 2), (r"\bpathologist\b", 2), (r"\bpathology\b", 1), (r"\bnabl\b", 2),
        (r"\bsample (collected|type)\b", 2), (r"\bcollected\b", 1), (r"\breported\b", 1), (r"\bspecimen\b", 1),
        (r"\bhaemoglobin|hemoglobin\b", 1), (r"\bcholesterol\b", 1), (r"\bhba1c\b", 1), (r"\bend of report\b", 2),
        (r"\btest\s+(name\s+)?result\b", 2), (r"\bunits?\b", 1), (r"\bdiagnostics?\b", 1),
    ],
    "prescription": [
        (r"^\s*rx\b", 3), (r"\brx\b", 1), (r"\b(tab|cap|syp|inj)\.?\s+[a-z]", 2), (r"\b\d\s*-\s*\d\s*-\s*\d\b", 2),
        (r"\b(od|bd|tds|qid|sos|hs)\b", 1), (r"\bc/o\b", 2), (r"\bdx\b", 1), (r"\bx\s*\d+\s*(days?|wks?|weeks?|months?)\b", 2),
        (r"\b(after|before) (food|meals|breakfast)\b", 1), (r"\bfollow[- ]?up\b", 1), (r"\breview after\b", 1),
        (r"\badvice\b", 1), (r"\bclinic\b", 1),
    ],
    "discharge_summary": [
        (r"\bdischarge summary\b", 6), (r"\bdate of (admission|discharge)\b", 3), (r"\bdischarge\b", 1),
        (r"\badmitted\b", 1), (r"\b(course in hospital|hospital course)\b", 3), (r"\bfinal diagnosis\b", 2),
        (r"\bcondition (at|on) discharge\b", 2), (r"\b(ward|ipd|uhid|bed no)\b", 1), (r"\bmedications? on discharge\b", 3),
        (r"\bhospital\b", 1),
    ],
}


class ClassifierOutput(BaseModel):
    document_type: DocType
    reason: str = ""


class Classification(BaseModel):
    document_type: DocType
    method: Literal["rules", "llm", "rules_low_margin"]
    scores: dict[str, int]
    reason: str = ""


def rule_scores(text: str) -> dict[str, int]:
    low = text.lower()
    scores = {}
    for doc_type, rules in RULES.items():
        total = 0
        for pattern, weight in rules:
            hits = len(re.findall(pattern, low, flags=re.MULTILINE))
            total += weight * min(hits, 3)
        scores[doc_type] = total
    return scores


def classify(text: str, min_score: int = 4, min_margin: int = 3) -> Classification:
    scores = rule_scores(text)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top >= min_score and top - second >= min_margin:
        return Classification(document_type=best, method="rules", scores=scores)
    s = get_settings()
    system = (
        "You classify Indian medical documents. Answer with JSON only. "
        "document_type is one of: lab_report, prescription, discharge_summary."
    )
    try:
        res = get_llm().structured(s.text_model, ClassifierOutput, system, "Document text:\n" + text[:2000], num_predict=80)
        if res.obj is not None:
            return Classification(document_type=res.obj.document_type, method="llm", scores=scores, reason=res.obj.reason)
    except LLMUnavailable:
        pass
    return Classification(document_type=best, method="rules_low_margin", scores=scores)
