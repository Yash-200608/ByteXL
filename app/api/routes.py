from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import pipeline, records
from app.fhir.abdm import to_document_bundle
from app.fhir.builder import embed_source, merge_bundles
from app.ingest.ingest import UnsupportedFile, sniff_type
from app.patients import create_patient, link_abha
from app.store import get_repository

router = APIRouter()
MAX_UPLOAD = 25 * 1024 * 1024


class PatientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sex: Literal["male", "female", "other"] | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100)


class AbhaLinkIn(BaseModel):
    abha_number: str
    abha_address: str | None = None


class ConfirmItem(BaseModel):
    path: str
    action: Literal["accept", "edit"] = "accept"
    value: str | float | int | None = None


class ConfirmIn(BaseModel):
    items: list[ConfirmItem]


class HandwrittenIn(BaseModel):
    handwritten: bool


class PerryTurn(BaseModel):
    role: Literal["user", "perry"]
    content: str = Field(max_length=4000)


class PerryIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[PerryTurn] = Field(default_factory=list, max_length=20)
    language: str | None = Field(default=None, max_length=16)


def _patient(pid: str) -> dict:
    p = get_repository().get("patients", pid)
    if p is None:
        raise HTTPException(404, "Patient not found")
    return p


def _document(did: str) -> dict:
    d = get_repository().get("documents", did)
    if d is None:
        raise HTTPException(404, "Document not found")
    return d


def _public_doc(d: dict) -> dict:
    return {
        "id": d["_id"],
        "patient_id": d["patient_id"],
        "filename": d.get("filename"),
        "content_type": d.get("content_type"),
        "status": d.get("status"),
        "document_type": d.get("document_type"),
        "classification": d.get("classification"),
        "document_date": d.get("document_date"),
        "extraction": d.get("extraction"),
        "confirm_queue": d.get("confirm_queue", []),
        "warnings": d.get("warnings", []),
        "pages": [{"index": p["index"], "width": p["width"], "height": p["height"], "source": p["source"],
                   "line_count": len(p.get("lines", [])), "deskew_angle": p.get("deskew_angle", 0)} for p in d.get("pages", [])],
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


@router.post("/patients", status_code=201)
def post_patient(body: PatientIn):
    return create_patient(body.name, body.sex, body.birth_year)


@router.get("/patients")
def list_patients():
    return sorted(get_repository().find("patients"), key=lambda p: p.get("created_at", ""))


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    return _patient(patient_id)


@router.post("/patients/{patient_id}/abha/link")
def post_abha_link(patient_id: str, body: AbhaLinkIn):
    _patient(patient_id)
    try:
        return link_abha(patient_id, body.abha_number, body.abha_address)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/patients/{patient_id}/documents", status_code=202)
async def upload_document(patient_id: str, file: UploadFile = File(...), sync: bool = Query(False)):
    _patient(patient_id)
    data = await file.read()
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "The file is larger than 25 MB.")
    try:
        sniff_type(data[:16])
    except UnsupportedFile as exc:
        raise HTTPException(415, str(exc)) from exc
    doc = pipeline.create_document(patient_id, file.filename or "upload", data)
    if sync:
        doc = pipeline.run_pipeline(doc["_id"])
        return _public_doc(doc)
    pipeline.submit(doc["_id"])
    return {"document_id": doc["_id"], "status": doc["status"]}


@router.get("/patients/{patient_id}/documents")
def list_documents(patient_id: str):
    _patient(patient_id)
    docs = get_repository().find("documents", {"patient_id": patient_id})
    docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return [{"id": d["_id"], "filename": d.get("filename"), "document_type": d.get("document_type"), "document_date": d.get("document_date"),
             "status": d.get("status"), "pending_confirmations": len(d.get("confirm_queue") or [])} for d in docs]


@router.get("/documents/{document_id}")
def get_document(document_id: str):
    return _public_doc(_document(document_id))


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: str):
    d = _document(document_id)
    return FileResponse(d["path"], media_type=d.get("content_type"), filename=d.get("filename"))


@router.get("/documents/{document_id}/pages/{index}")
def get_page_image(document_id: str, index: int):
    d = _document(document_id)
    pages = d.get("pages", [])
    if index < 0 or index >= len(pages) or not Path(pages[index]["image_path"]).exists():
        raise HTTPException(404, "Page not found")
    return FileResponse(pages[index]["image_path"], media_type="image/png")


@router.get("/documents/{document_id}/fhir")
def get_document_fhir(document_id: str, profile: Literal["collection", "abdm"] = "collection"):
    d = _document(document_id)
    b = get_repository().get("bundles", f"bun_{document_id}")
    if b is None:
        raise HTTPException(409, "The FHIR record is not ready yet.")
    bundle = embed_source(b["bundle"], d)
    if profile == "abdm":
        return to_document_bundle(bundle, d["document_type"], d.get("filename"))
    return bundle


@router.get("/documents/{document_id}/summary")
def get_document_summary(document_id: str, lang: Literal["en", "hi"] = "en"):
    d = _document(document_id)
    if not d.get("extraction"):
        raise HTTPException(409, "The document has not been processed yet.")
    from app.summary.service import get_summary

    return get_summary(document_id, lang)


@router.post("/documents/{document_id}/confirm")
def post_confirm(document_id: str, body: ConfirmIn):
    d = _document(document_id)
    if not d.get("extraction"):
        raise HTTPException(409, "The document has not been processed yet.")
    try:
        doc = records.confirm(document_id, [i.model_dump() for i in body.items])
    except (KeyError, IndexError, AttributeError, ValueError) as exc:
        raise HTTPException(422, f"Unknown field path: {exc}") from exc
    return _public_doc(doc)


@router.post("/documents/{document_id}/handwritten")
def post_handwritten(document_id: str, body: HandwrittenIn):
    d = _document(document_id)
    if not d.get("extraction"):
        raise HTTPException(409, "The document has not been processed yet.")
    try:
        return _public_doc(records.set_handwritten(document_id, body.handwritten))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/documents/{document_id}/retry", status_code=202)
def post_retry(document_id: str, sync: bool = Query(False)):
    d = _document(document_id)
    stage = "extract" if d.get("pages") else "ocr"
    if sync:
        return _public_doc(pipeline.run_pipeline(document_id, stage))
    pipeline.submit(document_id, stage)
    return {"document_id": document_id, "status": d.get("status")}


@router.get("/patients/{patient_id}/timeline")
def get_timeline(patient_id: str, type: str | None = None):
    _patient(patient_id)
    return records.timeline(patient_id, type)


@router.get("/patients/{patient_id}/trends")
def get_trend_list(patient_id: str):
    _patient(patient_id)
    return records.available_trends(patient_id)


@router.get("/patients/{patient_id}/trends/{loinc}")
def get_trend(patient_id: str, loinc: str):
    _patient(patient_id)
    return records.trends(patient_id, loinc)


@router.get("/patients/{patient_id}/medications")
def get_medications(patient_id: str):
    _patient(patient_id)
    return records.medications_view(patient_id)


@router.get("/patients/{patient_id}/export")
def export_patient(patient_id: str, profile: Literal["collection", "abdm"] = "collection"):
    _patient(patient_id)
    bundles = get_repository().find("bundles", {"patient_id": patient_id})
    bundles.sort(key=lambda b: b.get("created_at", ""))
    repo = get_repository()
    sources = {b["document_id"]: repo.get("documents", b["document_id"]) or {} for b in bundles}
    embedded = [(b, embed_source(b["bundle"], sources[b["document_id"]])) for b in bundles]
    if profile == "abdm":
        docs = {b["document_id"]: (b, e) for b, e in embedded}
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [{"resource": to_document_bundle(e, b["document_type"])} for b, e in docs.values()],
        }
    return merge_bundles([e for _, e in embedded], patient_id)


def _language(code: str | None) -> str | None:
    from app.agent.language import SUPPORTED_CODES

    if code in (None, "", "auto"):
        return None
    if code not in SUPPORTED_CODES:
        raise HTTPException(422, f"language must be one of: auto, {', '.join(SUPPORTED_CODES)}")
    return code


@router.post("/patients/{patient_id}/perry")
def post_perry(patient_id: str, body: PerryIn):
    from app.agent import Perry

    _patient(patient_id)
    reply = Perry(patient_id).respond(body.message, [t.model_dump() for t in body.history], language=_language(body.language))
    return reply.to_dict()


MAX_VOICE_UPLOAD = 10 * 1024 * 1024
NO_SPEECH = "I couldn't hear that clearly. Please try again, or type your question."


def _turns(history: str) -> list[dict]:
    import json

    from pydantic import TypeAdapter, ValidationError

    try:
        turns = TypeAdapter(list[PerryTurn]).validate_python(json.loads(history or "[]"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "history must be a JSON list of {role, content} turns") from exc
    return [t.model_dump() for t in turns[-20:]]


async def _heard(patient_id: str, audio: UploadFile) -> dict:
    from app.agent.speech import SpeechUnavailable, transcribe, wav_seconds
    from app.config import get_settings

    data = await audio.read()
    if len(data) > MAX_VOICE_UPLOAD:
        raise HTTPException(413, "The recording is larger than 10 MB.")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise HTTPException(415, "Please send the recording as a WAV file.")
    seconds = wav_seconds(data)
    if seconds is not None and seconds > get_settings().max_voice_seconds:
        raise HTTPException(413, f"Recordings can be at most {get_settings().max_voice_seconds} seconds long.")
    try:
        return transcribe(data, _voice_vocabulary(patient_id))
    except SpeechUnavailable as exc:
        raise HTTPException(503, f"Voice isn't set up on this device yet: {exc}") from exc


def _heard_fields(heard: dict) -> dict:
    return {"transcript": heard["text"], "heard_raw": heard.get("raw_text"), "corrections": heard.get("corrections", []),
            "heard_language": heard["language"], "stt_seconds": heard["duration_s"]}


@router.post("/patients/{patient_id}/perry/transcribe")
async def post_perry_transcribe(patient_id: str, audio: UploadFile = File(...)):
    _patient(patient_id)
    heard = await _heard(patient_id, audio)
    return {**_heard_fields(heard), "state": "ok" if heard["text"] else "no_speech", "message": None if heard["text"] else NO_SPEECH}


@router.post("/patients/{patient_id}/perry/voice")
async def post_perry_voice(patient_id: str, audio: UploadFile = File(...), history: str = Form("[]"), language: str = Form("auto")):
    from app.agent import Perry

    _patient(patient_id)
    turns = _turns(history)
    code = _language(language)
    heard = await _heard(patient_id, audio)
    if not heard["text"]:
        return {"reply": NO_SPEECH, "language": "en", "language_name": "English", "method": "composed", "intent": "voice",
                "state": "no_speech", "tools": [], "sources": [], "transcript": "", "heard_language": heard["language"]}
    reply = Perry(patient_id).respond(heard["text"], turns, language=code).to_dict()
    return {**reply, **_heard_fields(heard)}


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    reply: str = Field(min_length=1, max_length=4000)
    question: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=16)
    tools: list[str] = Field(default_factory=list, max_length=6)


@router.post("/patients/{patient_id}/perry/feedback", status_code=201)
def post_perry_feedback(patient_id: str, body: FeedbackIn):
    import uuid

    from app.patients import now

    _patient(patient_id)
    record = {"_id": f"fb_{uuid.uuid4().hex[:12]}", "patient_id": patient_id, "rating": body.rating, "reply": body.reply[:4000],
              "question": body.question, "language": body.language, "tools": body.tools, "created_at": now()}
    get_repository().insert("perry_feedback", record)
    return {"ok": True}


@router.get("/patients/{patient_id}/overview")
def get_overview(patient_id: str):
    from app.agent import PerryTools

    _patient(patient_id)
    return PerryTools(patient_id).call("get_my_overview")


def _voice_vocabulary(patient_id: str) -> list[str]:
    import re

    from app.agent import PerryTools, ToolError

    try:
        tools = PerryTools(patient_id)
        meds = tools.call("get_my_medications")["medicines"]
        labs = tools.call("get_my_labs", {"limit": 50})["results"]
    except ToolError:
        return []
    names = []
    for m in meds:
        brand = re.sub(r"^(?:Tab|Cap|Syp|Inj|Cream|Oint|Drops?)\.?\s+", "", m.get("name") or "", flags=re.I)
        names.append(re.sub(r"\s+\d.*$", "", brand).strip())
        if m.get("generic"):
            names.append(m["generic"])
    names += [r["name"] for r in labs]
    return [n for n in dict.fromkeys(names) if n][:40]
