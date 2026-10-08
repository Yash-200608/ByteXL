import logging
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rapidfuzz import fuzz

from app.normalize.labs import alias_key, resolve_lab
from app.store import get_repository

log = logging.getLogger(__name__)

TYPE_TITLE = {"lab_report": "Lab report", "prescription": "Prescription", "discharge_summary": "Discharge summary"}
DOCUMENT_SELECTORS = {
    "latest": None,
    "latest_report": None,
    "latest_document": None,
    "latest_lab_report": "lab_report",
    "latest_prescription": "prescription",
    "latest_discharge_summary": "discharge_summary",
}
TEST_SYNONYMS = {
    "sugar": ["glucose"], "glucose": ["glucose"], "diabetes": ["glucose", "hba1c"], "a1c": ["hba1c"],
    "cholesterol": ["cholesterol"], "lipid": ["lipid"], "lipids": ["lipid"], "thyroid": ["thyroid"],
    "kidney": ["kft"], "renal": ["kft"], "liver": ["lft"], "blood count": ["cbc"], "cbc": ["cbc"],
    "vitamin": ["vitamins"], "urine": ["urine routine"], "electrolytes": ["electrolytes"], "iron": ["iron"],
    "haemoglobin": ["haemoglobin"], "hemoglobin": ["haemoglobin"], "hb": ["haemoglobin"], "शुगर": ["glucose"],
}
STOPWORDS = {
    "what", "whats", "is", "are", "was", "were", "my", "me", "the", "a", "an", "of", "in", "on", "for", "to", "show", "find",
    "all", "any", "records", "record", "about", "do", "does", "did", "i", "have", "has", "which", "mention", "mentions",
    "mentioned", "tell", "please", "can", "you", "your", "there", "and", "or", "with", "from", "that", "this", "it", "give",
    "list", "anything", "everything", "where", "when", "how", "much", "many", "value", "values", "result", "results",
    "latest", "last", "recent", "recently", "newest", "current", "most", "documents", "document", "health", "data",
    "meri", "mera", "mere", "kya", "hai", "hain", "mein", "ka", "ki", "ke", "ko", "se", "dikhao", "batao", "samjhao",
    "wala", "wali", "konsi", "kaunsi", "aakhri", "akhri", "pichla", "pichli", "sab", "sabhi", "know", "else", "overview",
    "summarize", "summarise", "kuch", "bare", "baare", "bataiye", "account", "information", "info",
}
RECENCY_WORDS = {"latest", "last", "recent", "recently", "newest", "current", "aakhri", "akhri", "pichla", "pichli", "naya", "nayi"}


class ToolError(RuntimeError):
    pass


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class LimitArgs(_Args):
    limit: int = Field(10, ge=1, le=25)


class SearchArgs(_Args):
    query: str = Field(min_length=1, max_length=200)


class LabsArgs(_Args):
    test: str | None = Field(None, max_length=80)
    limit: int = Field(10, ge=1, le=50)


class DocumentArgs(_Args):
    document_id: str = Field(min_length=1, max_length=64)


class SummaryArgs(_Args):
    document_id: str = Field(min_length=1, max_length=64)
    language: Literal["en", "hi"] = "en"


class CompareArgs(_Args):
    test: str | None = Field(None, max_length=80)


SELECTOR_HELP = ("a document id from an earlier result, or one of: latest, latest_lab_report, latest_prescription, "
                 "latest_discharge_summary")
TOOLS: dict[str, tuple[type[_Args], str]] = {
    "get_my_overview": (NoArgs, "Compact overview of the whole account: document counts, latest documents, latest out-of-range "
                                "lab values, current medicines and pending confirmations. Use for broad questions."),
    "search_my_records": (SearchArgs, "Search all of the user's records (lab results, medicines, diagnoses, documents, "
                                      "advice, summaries, confirmations) for a topic, e.g. 'cholesterol'."),
    "get_my_labs": (LabsArgs, "Lab results, newest first. 'test' filters by test or panel name, e.g. 'HbA1c', 'cholesterol', "
                              "'thyroid'. Leave empty for all recent results."),
    "get_my_medications": (NoArgs, "Medicines in the records, exactly as written, with generic names, current medicines and "
                                   "duplicate-medicine notes."),
    "get_my_documents": (LimitArgs, "List of uploaded documents (type, date, filename, status), newest first."),
    "get_my_timeline": (LimitArgs, "Health timeline: documents in date order with highlights and out-of-range values."),
    "get_my_document": (DocumentArgs, f"Structured details of one document. document_id is {SELECTOR_HELP}."),
    "get_my_summary": (SummaryArgs, f"Plain-language explanation of one document. document_id is {SELECTOR_HELP}; "
                                    "language is 'en' or 'hi'."),
    "compare_my_reports": (CompareArgs, "What changed: lab values that differ between the two most recent reports that "
                                        "measured them, plus the newest documents. 'test' optionally narrows to one test."),
    "get_pending_confirmations": (NoArgs, "Details from uploaded documents that are still waiting for the user's confirmation."),
    "get_my_profile": (NoArgs, "The user's profile: name, sex, age and ABHA details."),
}


def _fmt(d: str | None) -> str | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d[:10]).strftime("%d %b %Y")
    except ValueError:
        return d


def _range_text(low, high) -> str | None:
    if low is not None and high is not None:
        return f"{_num(low)}-{_num(high)}"
    if high is not None:
        return f"below {_num(high)}"
    if low is not None:
        return f"above {_num(low)}"
    return None


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


class PerryTools:
    def __init__(self, patient_id: str):
        self._patient_id = patient_id
        self._repo = get_repository()
        self._patient = self._repo.get("patients", patient_id)
        if not self._patient:
            raise ToolError("This ByteXL account could not be found.")

    @staticmethod
    def specs() -> list[dict]:
        out = []
        for name, (model, desc) in TOOLS.items():
            props = {k: {kk: vv for kk, vv in v.items() if kk in ("type", "enum", "anyOf", "default")}
                     for k, v in model.model_json_schema().get("properties", {}).items()}
            out.append({"name": name, "description": desc, "args": props})
        return out

    def call(self, name: str, args: dict | None = None) -> dict:
        if name not in TOOLS:
            raise ToolError(f"Unknown tool {name!r}.")
        model, _ = TOOLS[name]
        try:
            parsed = model.model_validate(args or {})
        except ValidationError as exc:
            raise ToolError(f"Invalid arguments for {name}: {exc.errors()[0]['msg']}") from exc
        try:
            return getattr(self, name)(**parsed.model_dump())
        except ToolError:
            raise
        except Exception as exc:
            log.exception("PERRY tool %s failed", name)
            raise ToolError("I couldn't access that part of your records right now.") from exc

    def _documents(self, processed_only: bool = True) -> list[dict]:
        docs = self._repo.find("documents", {"patient_id": self._patient_id})
        if processed_only:
            docs = [d for d in docs if d.get("extraction")]
        docs.sort(key=lambda d: (d.get("document_date") or "0000", d.get("created_at") or ""), reverse=True)
        return docs

    def _owned_document(self, doc_id: str) -> dict:
        d = self._repo.get("documents", doc_id)
        if not d or d.get("patient_id") != self._patient_id:
            raise ToolError("I couldn't find that document in your records.")
        return d

    def _resolve(self, selector: str) -> dict:
        key = selector.strip().lower()
        if key in DOCUMENT_SELECTORS:
            wanted = DOCUMENT_SELECTORS[key]
            docs = [d for d in self._documents() if wanted is None or d.get("document_type") == wanted]
            if not docs:
                kind = TYPE_TITLE.get(wanted, "document").lower()
                raise ToolError(f"There is no {kind} in your records yet.")
            return docs[0]
        return self._owned_document(selector.strip())

    @staticmethod
    def _source(d: dict) -> dict:
        return {"document_id": d["_id"], "type": d.get("document_type"), "title": TYPE_TITLE.get(d.get("document_type"), "Document"),
                "filename": d.get("filename"), "date": d.get("document_date"), "date_text": _fmt(d.get("document_date"))}

    @staticmethod
    def _extraction(d: dict):
        from app.pipeline import load_extraction

        return load_extraction(d) if d.get("extraction") else None

    def get_my_profile(self) -> dict:
        p = self._patient
        age = date.today().year - p["birth_year"] if p.get("birth_year") else None
        return {"name": p.get("name"), "sex": p.get("sex"), "birth_year": p.get("birth_year"), "approx_age": age,
                "abha_number": p.get("abha_number"), "abha_address": p.get("abha_address"),
                "abha_status": "linked" if p.get("abha_linked") else "mock (not linked)",
                "documents": len(self._documents(processed_only=False))}

    def get_my_documents(self, limit: int = 10) -> dict:
        docs = self._documents(processed_only=False)
        items = []
        for d in docs[:limit]:
            items.append({**self._source(d), "uploaded_on": _fmt(d.get("created_at")),
                          "status": (d.get("status") or {}).get("state"),
                          "pending_confirmations": len(d.get("confirm_queue") or [])})
        return {"count": len(docs), "documents": items}

    def get_my_timeline(self, limit: int = 10) -> dict:
        from app.records import timeline

        items = []
        for t in timeline(self._patient_id)[:limit]:
            items.append({"date": t["date"], "date_text": _fmt(t["date"]), "type": t["document_type"], "title": t["title"],
                          "source": t["source"], "filename": t["filename"], "highlights": t["highlights"],
                          "diagnoses": t.get("diagnoses", []),
                          "out_of_range": [{**a, "value": _num(a["value"])} for a in t["abnormal"]],
                          "pending_confirmations": t["pending_confirmations"], "document_id": t["document_id"]})
        return {"count": len(items), "timeline": items}

    def _lab_rows(self) -> list[dict]:
        rows = self._repo.find("observations_index", {"patient_id": self._patient_id})
        rows.sort(key=lambda r: (r.get("date") or "0000", r["_id"]), reverse=True)
        return rows

    @staticmethod
    def _test_filter(test: str | None):
        if not test:
            return lambda r: True
        key = alias_key(test)
        ref, score = resolve_lab(test)
        if ref and score >= 90:
            return lambda r: r.get("loinc") == ref.loinc
        targets = []
        for word, expansions in TEST_SYNONYMS.items():
            if word in key:
                targets.extend(expansions)
        targets = targets or [key]

        def match(r):
            hay = f"{alias_key(r.get('name') or '')} {(r.get('panel') or '').lower()}"
            return any(t in hay or fuzz.partial_ratio(t, hay) >= 90 for t in targets)

        return match

    def _lab_item(self, r: dict, sources: dict) -> dict:
        src = sources.get(r["document_id"], {})
        item = {"name": r["name"], "value": _num(r["value"]), "unit": r.get("unit"), "flag": r.get("flag"),
                "reference_range": _range_text(r.get("ref_low"), r.get("ref_high")),
                "date": r.get("date"), "date_text": _fmt(r.get("date")), "document_id": r["document_id"],
                "source": src.get("filename"), "source_type": src.get("title")}
        if r.get("printed_value") is not None and (r.get("printed_unit") != r.get("unit") or r.get("printed_value") != r.get("value")):
            item["as_printed"] = f"{_num(r['printed_value'])} {r.get('printed_unit') or ''}".strip()
        return item

    def get_my_labs(self, test: str | None = None, limit: int = 10) -> dict:
        sources = {d["_id"]: self._source(d) for d in self._documents()}
        rows = [r for r in self._lab_rows() if self._test_filter(test)(r)]
        results = [self._lab_item(r, sources) for r in rows[:limit]]
        out = {"test": test, "count": len(rows), "results": results}
        if not rows:
            out["note"] = f"No lab results{' for ' + test if test else ''} were found in the records."
        return out

    def compare_my_reports(self, test: str | None = None) -> dict:
        sources = {d["_id"]: self._source(d) for d in self._documents()}
        groups: dict[str, list[dict]] = {}
        for r in self._lab_rows():
            if self._test_filter(test)(r) and r.get("date"):
                groups.setdefault(r["loinc"], []).append(r)
        changes = []
        for rows in groups.values():
            dated = {}
            for r in rows:
                dated.setdefault(r["date"], r)
            if len(dated) < 2:
                continue
            latest, previous = [dated[k] for k in sorted(dated, reverse=True)[:2]]
            direction = "up" if latest["value"] > previous["value"] else "down" if latest["value"] < previous["value"] else "same"
            changes.append({"name": latest["name"], "direction": direction, "flag_changed": latest.get("flag") != previous.get("flag"),
                            "previous": self._lab_item(previous, sources), "latest": self._lab_item(latest, sources)})
        changes.sort(key=lambda c: (not c["flag_changed"], c["name"]))
        newest = [self._source(d) for d in self._documents()[:3]]
        out = {"test": test, "lab_changes": changes, "newest_documents": newest}
        if not changes:
            out["note"] = "No lab test was measured on two different dates, so there is nothing to compare yet."
        return out

    def get_my_medications(self) -> dict:
        from app.records import as_of_date, medication_entries
        from app.normalize.reconcile import active_medications, reconcile

        entries = medication_entries(self._patient_id)
        as_of = as_of_date(entries)
        active_keys = {(e.document_id, e.index) for e in active_medications(entries, as_of)}
        sources = {d["_id"]: self._source(d) for d in self._documents()}
        items = []
        for e in sorted(entries, key=lambda e: (e.document_date or date.min, e.document_id, -e.index), reverse=True):
            m, n = e.item, e.item.normalized
            src = sources.get(e.document_id, {})
            items.append({
                "name": m.name.value, "generic": n.generic if n else None,
                "strength": m.strength.value or (n.strength if n else None),
                "dosage": m.dosage.value, "timing": m.timing.value, "duration": m.duration.value, "instructions": m.instructions.value,
                "how_to_take": n.dosage.text if n and n.dosage else None,
                "current": (e.document_id, e.index) in active_keys,
                "date": e.document_date.isoformat() if e.document_date else None, "date_text": src.get("date_text"),
                "source": src.get("filename"), "source_type": src.get("title"), "document_id": e.document_id,
            })
        notes = [n.text("en") for n in reconcile(entries, as_of)]
        return {"as_of": as_of.isoformat(), "count": len(items), "current_count": sum(i["current"] for i in items),
                "medicines": items[:30], "duplicate_medicine_notes": notes}

    def get_my_document(self, document_id: str) -> dict:
        from app.schemas import DischargeSummary, LabReport, Prescription

        d = self._resolve(document_id)
        ex = self._extraction(d)
        out = {**self._source(d), "status": (d.get("status") or {}).get("state"),
               "pending_confirmations": len(d.get("confirm_queue") or [])}
        if ex is None:
            out["note"] = "This document has not finished processing yet."
            return out

        def med(m):
            n = m.normalized
            return {"name": m.name.value, "generic": n.generic if n else None, "dosage": m.dosage.value, "timing": m.timing.value,
                    "duration": m.duration.value, "instructions": m.instructions.value,
                    "how_to_take": n.dosage.text if n and n.dosage else None}

        def lab(r):
            n = r.normalized
            return {"name": (n.canonical_name if n and n.canonical_name else None) or r.test_name.value,
                    "value": _num(r.value.value) if r.value.value is not None else r.value_text.value, "unit": r.unit.value,
                    "flag": n.flag if n else "unknown", "reference_range": r.reference_range.value}

        if isinstance(ex, LabReport):
            out.update({"lab": ex.facility.value, "referring_doctor": ex.referring_doctor.value,
                        "collected_on": _fmt(str(ex.collected_on.value) if ex.collected_on.value else None),
                        "results": [lab(r) for r in ex.results]})
        elif isinstance(ex, Prescription):
            out.update({"doctor": ex.prescriber.value, "clinic": ex.facility.value, "complaints": [c.value for c in ex.complaints if c.value],
                        "diagnoses_as_written": [c.value for c in ex.diagnoses if c.value], "medicines": [med(m) for m in ex.medications],
                        "advice": [a.value for a in ex.advice if a.value], "follow_up": ex.follow_up.value,
                        "handwritten": ex.is_handwritten})
        elif isinstance(ex, DischargeSummary):
            course = ex.hospital_course.value or ""
            out.update({"hospital": ex.facility.value, "doctor": ex.attending_doctor.value,
                        "admitted": _fmt(str(ex.admission_date.value) if ex.admission_date.value else None),
                        "discharged": _fmt(str(ex.discharge_date.value) if ex.discharge_date.value else None),
                        "diagnoses_as_written": [c.value for c in ex.diagnoses if c.value],
                        "presenting_complaints": [c.value for c in ex.presenting_complaints if c.value],
                        "hospital_course": course[:600], "procedures": [p.value for p in ex.procedures if p.value],
                        "investigations": [lab(r) for r in ex.investigations], "discharge_medicines": [med(m) for m in ex.discharge_medications],
                        "follow_up": ex.follow_up.value, "advice": [a.value for a in ex.advice if a.value]})
        return out

    def get_my_summary(self, document_id: str, language: str = "en") -> dict:
        from app.summary.service import get_summary

        d = self._resolve(document_id)
        if not d.get("extraction"):
            raise ToolError("That document has not finished processing yet.")
        s = get_summary(d["_id"], language)
        return {**self._source(d), "language": language, "what_this_is": s["what_this_is"], "key_findings": s["key_findings"],
                "out_of_range": [{k: o[k] for k in ("name", "value", "flag", "range", "meaning")} for o in s["out_of_range"]],
                "medicines": s["medicines"], "notes": s["notes"], "disclaimer": s["disclaimer"]}

    def get_pending_confirmations(self) -> dict:
        items = []
        for d in self._documents(processed_only=False):
            for q in d.get("confirm_queue") or []:
                items.append({"label": q.get("label"), "value": q.get("value"), "reasons": q.get("reasons", [])[:2],
                              "source": d.get("filename"), "source_type": TYPE_TITLE.get(d.get("document_type"), "Document"),
                              "date_text": _fmt(d.get("document_date")), "document_id": d["_id"]})
        return {"count": len(items), "items": items[:20]}

    def get_my_overview(self) -> dict:
        docs = self._documents()
        by_type: dict[str, int] = {}
        for d in docs:
            by_type[TYPE_TITLE.get(d.get("document_type"), "Document")] = by_type.get(TYPE_TITLE.get(d.get("document_type"), "Document"), 0) + 1
        latest_lab = next((d for d in docs if d.get("document_type") == "lab_report"), None)
        latest_abnormal = []
        if latest_lab:
            sources = {latest_lab["_id"]: self._source(latest_lab)}
            latest_abnormal = [self._lab_item(r, sources) for r in self._lab_rows()
                               if r["document_id"] == latest_lab["_id"] and r.get("flag") in ("low", "high", "critical")]
        meds = self.get_my_medications()
        dates = [d["document_date"] for d in docs if d.get("document_date")]
        return {
            "name": self._patient.get("name"),
            "documents": {"total": len(docs), "by_type": by_type},
            "date_range": {"first": _fmt(min(dates)) if dates else None, "last": _fmt(max(dates)) if dates else None},
            "latest_documents": [self._source(d) for d in docs[:3]],
            "latest_lab_report": self._source(latest_lab) if latest_lab else None,
            "latest_out_of_range": latest_abnormal,
            "current_medicines": [m["name"] for m in meds["medicines"] if m["current"]],
            "duplicate_medicine_notes": meds["duplicate_medicine_notes"],
            "pending_confirmations": self.get_pending_confirmations()["count"],
        }

    def _corpus(self) -> list[dict]:
        from app.schemas import DischargeSummary, Prescription, lab_results, medications

        items = []
        for d in self._documents():
            src = self._source(d)
            ex = self._extraction(d)
            facility = getattr(getattr(ex, "facility", None), "value", None)
            items.append({"kind": "document", "date": d.get("document_date"), "source": src,
                          "text": f"{src['title']} report document {d.get('filename')} {facility or ''}",
                          "item": {"title": src["title"], "filename": d.get("filename"), "from": facility}})
            for r in lab_results(ex):
                n = r.normalized
                name = (n.canonical_name if n and n.canonical_name else None) or r.test_name.value or ""
                items.append({"kind": "lab_result", "date": d.get("document_date"), "source": src,
                              "text": f"{name} {r.test_name.value or ''} {(n.panel if n else '') or ''} lab test",
                              "item": {"name": name, "value": _num(r.value.value) if r.value.value is not None else r.value_text.value,
                                       "unit": r.unit.value, "flag": n.flag if n else "unknown"}})
            for m in medications(ex):
                n = m.normalized
                items.append({"kind": "medicine", "date": d.get("document_date"), "source": src,
                              "text": f"{m.name.value or ''} {(n.generic if n else '') or ''} {(n.drug_class if n else '') or ''} medicine tablet drug",
                              "item": {"name": m.name.value, "generic": n.generic if n else None,
                                       "as_written": " ".join(x for x in (m.dosage.value, m.timing.value, m.duration.value) if x)}})
            if isinstance(ex, (Prescription, DischargeSummary)):
                complaints = ex.complaints if isinstance(ex, Prescription) else ex.presenting_complaints
                for kind, values in (("diagnosis_as_written", ex.diagnoses), ("complaint", complaints), ("advice", ex.advice)):
                    for c in values:
                        if c.value:
                            items.append({"kind": kind, "date": d.get("document_date"), "source": src,
                                          "text": f"{c.value} {kind.replace('_', ' ')}", "item": {"text": c.value}})
                if ex.follow_up.value:
                    items.append({"kind": "follow_up", "date": d.get("document_date"), "source": src,
                                  "text": f"{ex.follow_up.value} follow up review", "item": {"text": ex.follow_up.value}})
            if isinstance(ex, DischargeSummary) and ex.hospital_course.value:
                items.append({"kind": "hospital_course", "date": d.get("document_date"), "source": src,
                              "text": f"{ex.hospital_course.value} hospital course admission",
                              "item": {"text": ex.hospital_course.value[:400]}})
            for q in d.get("confirm_queue") or []:
                items.append({"kind": "pending_confirmation", "date": d.get("document_date"), "source": src,
                              "text": f"{q.get('label')} pending confirmation confirm", "item": {"label": q.get("label"), "value": q.get("value")}})
            cached = self._repo.get("summaries", f"{d['_id']}:en")
            if cached:
                s = cached["summary"]
                items.append({"kind": "summary", "date": d.get("document_date"), "source": src,
                              "text": " ".join([s.get("what_this_is", ""), *s.get("key_findings", [])]),
                              "item": {"what_this_is": s.get("what_this_is"), "key_findings": s.get("key_findings", [])[:3]}})
        for note in self.get_my_medications()["duplicate_medicine_notes"]:
            items.append({"kind": "duplicate_medicine_note", "date": None, "source": None, "text": f"{note} duplicate medicine", "item": {"text": note}})
        return items

    def search_my_records(self, query: str) -> dict:
        words = re.findall(r"[\w%.\-]+", query.lower())
        recency = any(w in RECENCY_WORDS for w in words)
        tokens = [w for w in words if w not in STOPWORDS and len(w) >= 2 and (re.search(r"[a-z0-9]", w) or w in TEST_SYNONYMS)]
        expanded = []
        for t in tokens:
            expanded.append(t)
            for word, extra in TEST_SYNONYMS.items():
                if t == word:
                    expanded.extend(e for e in extra if e != t)
        if not expanded:
            return {"query": query, "count": 0, "matches": [], "overview": self.get_my_overview()}
        scored = []
        for it in self._corpus():
            hay = it["text"].lower()
            best = [max((fuzz.partial_ratio(t, hay) if len(t) >= 3 else (100 if re.search(rf"\b{re.escape(t)}\b", hay) else 0)), 0) for t in expanded]
            score = max(best) if len(tokens) == 1 else sum(sorted(best, reverse=True)[:max(1, len(tokens))]) / max(1, len(tokens))
            if score >= 85:
                scored.append((score, it))
        scored.sort(key=lambda x: (x[0], x[1]["date"] or ""), reverse=True)
        if recency:
            scored.sort(key=lambda x: (x[1]["date"] or "", x[0]), reverse=True)
        matches = []
        for score, it in scored[:12]:
            src = it["source"] or {}
            matches.append({"kind": it["kind"], **it["item"], "date_text": _fmt(it["date"]), "source": src.get("filename"),
                            "source_type": src.get("title"), "document_id": src.get("document_id")})
        out = {"query": query, "count": len(scored), "matches": matches}
        if not matches:
            out["note"] = f"Nothing matching '{query}' was found in the records."
        return out
