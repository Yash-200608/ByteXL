import base64
import hashlib
import logging
import re
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from rapidfuzz import fuzz

from app.config import get_settings
from app.extract.extract import extract
from app.extract.parse import strip_honorific
from app.fhir.builder import build_bundle
from app.ingest.classify import classify
from app.ingest.ingest import ingest_file, store_original
from app.ingest.models import PageData
from app.llm.client import LLMUnavailable
from app.normalize import normalize_extraction
from app.normalize.confirm import apply_confirmation_rules
from app.patients import now
from app.schemas import Prescription, document_date, lab_results, parse_extraction
from app.store import get_repository

log = logging.getLogger(__name__)
STAGES = ["stored", "ocr", "classify", "extract", "normalize", "fhir", "summarize", "done"]
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


class PipelineError(RuntimeError):
    pass


def create_document(patient_id: str, filename: str, data: bytes) -> dict:
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    path, ctype, sha = store_original(data, doc_id)
    doc = {
        "_id": doc_id,
        "patient_id": patient_id,
        "filename": filename,
        "content_type": ctype,
        "sha256": sha,
        "sha1_b64": base64.b64encode(hashlib.sha1(data).digest()).decode(),
        "size": len(data),
        "path": path.as_posix(),
        "status": {"stage": "stored", "state": "queued", "message": None, "timings": {}},
        "document_type": None,
        "classification": None,
        "pages": [],
        "extraction": None,
        "confirm_queue": [],
        "warnings": [],
        "document_date": None,
        "created_at": now(),
        "updated_at": now(),
    }
    return get_repository().insert("documents", doc)


def _set_status(doc_id: str, stage: str, state: str = "running", message: str | None = None, timings: dict | None = None):
    repo = get_repository()
    doc = repo.get("documents", doc_id)
    status = doc.get("status", {})
    status.update({"stage": stage, "state": state, "message": message})
    if timings:
        status.setdefault("timings", {}).update(timings)
    repo.update("documents", doc_id, {"status": status, "updated_at": now()})


def load_extraction(doc: dict):
    return parse_extraction(doc["extraction"]) if doc.get("extraction") else None


def load_pages(doc: dict) -> list[PageData]:
    return [PageData(**p) for p in doc.get("pages", [])]


def _is_handwritten(ex, pages: list[PageData]) -> bool:
    if not isinstance(ex, Prescription):
        return False
    if ex.is_handwritten:
        return True
    ocr_pages = [p for p in pages if p.source == "ocr" and p.lines]
    return bool(ocr_pages) and min(p.mean_confidence for p in ocr_pages) < get_settings().handwritten_ocr_conf


def _warnings(ex, patient: dict, pages: list[PageData]) -> list[str]:
    out = []
    doc_name = strip_honorific(ex.patient.name.value or "")
    if doc_name and patient.get("name") and fuzz.token_sort_ratio(doc_name.lower(), patient["name"].lower()) < 80:
        out.append(f"The name on this document ('{doc_name}') does not match the profile name ('{patient['name']}'). Please check it belongs to this patient.")
    if ex.meta.low_confidence:
        out.append("The AI reader was unavailable or unsure, so a basic fallback reader was used. Please review every field.")
    if _is_handwritten(ex, pages):
        out.append("Handwritten prescription: please confirm each medicine name and dosage.")
    return out


def finalize(doc: dict, ex, patient: dict) -> dict:
    pages = load_pages(doc)
    normalize_extraction(ex, sex=patient.get("sex") or None)
    queue = apply_confirmation_rules(ex, handwritten=_is_handwritten(ex, pages))
    d = document_date(ex)
    patch = {
        "document_type": ex.document_type,
        "extraction": ex.model_dump(mode="json"),
        "confirm_queue": queue,
        "warnings": _warnings(ex, patient, pages),
        "document_date": d.isoformat() if d else None,
    }
    doc.update(patch)
    return patch


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write_fhir_and_index(doc: dict, ex, patient: dict) -> dict:
    repo = get_repository()
    bundle = build_bundle(doc, patient, ex)
    bid = f"bun_{doc['_id']}"
    prev = repo.get("bundles", bid)
    repo.replace("bundles", {
        "_id": bid,
        "document_id": doc["_id"],
        "patient_id": doc["patient_id"],
        "document_type": ex.document_type,
        "version": (prev or {}).get("version", 0) + 1,
        "bundle": bundle,
        "created_at": now(),
    })
    repo.delete_many("observations_index", {"document_id": doc["_id"]})
    when = doc.get("document_date")
    for i, r in enumerate(lab_results(ex)):
        n = r.normalized
        if not n or n.value is None:
            continue
        name = n.canonical_name or r.test_name.value or "Unknown test"
        repo.insert("observations_index", {
            "_id": f"{doc['_id']}:{i}",
            "patient_id": doc["patient_id"],
            "document_id": doc["_id"],
            "loinc": n.loinc or f"local:{_slug(name)}",
            "name": name,
            "value": n.value,
            "unit": n.unit,
            "printed_value": r.value.value,
            "printed_unit": r.unit.value,
            "date": when,
            "flag": n.flag,
            "ref_low": n.ref_low,
            "ref_high": n.ref_high,
            "panel": n.panel,
        })
    return bundle


def rebuild(doc_id: str, ex=None, summarize: bool = False) -> dict:
    repo = get_repository()
    doc = repo.get("documents", doc_id)
    patient = repo.get("patients", doc["patient_id"]) or {"_id": doc["patient_id"]}
    ex = ex or load_extraction(doc)
    patch = finalize(doc, ex, patient)
    repo.update("documents", doc_id, {**patch, "updated_at": now()})
    write_fhir_and_index(doc, ex, patient)
    repo.delete_many("summaries", {"document_id": doc_id})
    if summarize:
        _summarize(doc_id)
    return repo.get("documents", doc_id)


def _summarize(doc_id: str):
    from app.summary.service import get_summary

    get_summary(doc_id, "en")


def run_pipeline(doc_id: str, from_stage: str = "ocr") -> dict:
    repo = get_repository()
    s = get_settings()
    doc = repo.get("documents", doc_id)
    if doc is None:
        raise PipelineError(f"document {doc_id} not found")
    stage = from_stage
    try:
        pages = load_pages(doc)
        if from_stage == "ocr" or not pages:
            stage = "ocr"
            _set_status(doc_id, "ocr")
            t = time.time()
            pages = ingest_file(doc["path"], doc_id)
            repo.update("documents", doc_id, {"pages": [p.model_dump() for p in pages]})
            _set_status(doc_id, "ocr", timings={"ocr": round(time.time() - t, 1)})
        text = "\n".join(p.text for p in pages)
        if not text.strip():
            raise PipelineError("No readable text was found. Try a sharper photo with the whole page in view.")
        stage = "classify"
        _set_status(doc_id, "classify")
        t = time.time()
        cls = classify(text)
        repo.update("documents", doc_id, {"document_type": cls.document_type, "classification": cls.model_dump()})
        _set_status(doc_id, "classify", timings={"classify": round(time.time() - t, 1)})
        stage = "extract"
        _set_status(doc_id, "extract")
        t = time.time()
        ex = extract(cls.document_type, pages)
        _set_status(doc_id, "extract", timings={"extract": round(time.time() - t, 1)})
        stage = "normalize"
        _set_status(doc_id, "normalize")
        stage = "fhir"
        rebuild(doc_id, ex)
        _set_status(doc_id, "fhir")
        if s.summary_on_upload:
            stage = "summarize"
            _set_status(doc_id, "summarize")
            t = time.time()
            try:
                _summarize(doc_id)
            except LLMUnavailable as exc:
                log.warning("summary deferred: %s", exc)
            _set_status(doc_id, "summarize", timings={"summarize": round(time.time() - t, 1)})
        _set_status(doc_id, "done", state="done")
    except PipelineError as exc:
        _set_status(doc_id, stage, state="failed", message=str(exc))
    except Exception as exc:
        log.error("pipeline failed at %s: %s\n%s", stage, exc, traceback.format_exc())
        _set_status(doc_id, stage, state="failed", message=f"Processing failed while {STAGE_TEXT.get(stage, stage)}. You can retry this document.")
    return repo.get("documents", doc_id)


STAGE_TEXT = {
    "ocr": "reading the text",
    "classify": "identifying the document type",
    "extract": "extracting the details",
    "normalize": "checking values",
    "fhir": "building the health record",
    "summarize": "writing the summary",
}


def submit(doc_id: str, from_stage: str = "ocr"):
    return _executor.submit(run_pipeline, doc_id, from_stage)
