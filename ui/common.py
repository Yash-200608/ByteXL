import io
import json

import streamlit as st
from PIL import Image, ImageDraw

import api_client as api

FLAG_STYLE = {
    "low": ("#1d4ed8", "#dbeafe", "Low"),
    "high": ("#b91c1c", "#fee2e2", "High"),
    "critical": ("#7f1d1d", "#fecaca", "Far outside range"),
    "normal": ("#166534", "#dcfce7", "Normal"),
    "unknown": ("#475569", "#e2e8f0", "No range"),
}
FLAG_HI = {"low": "कम", "high": "अधिक", "critical": "सीमा से बहुत बाहर", "normal": "सामान्य", "unknown": "सीमा नहीं"}
TYPE_LABEL = {"lab_report": "Lab report", "prescription": "Prescription", "discharge_summary": "Discharge summary"}
TYPE_ICON = {"lab_report": "🧪", "prescription": "💊", "discharge_summary": "🏥"}
STAGES = [
    ("stored", "File received"),
    ("ocr", "Reading the text"),
    ("classify", "Identifying the document"),
    ("extract", "Extracting details"),
    ("normalize", "Checking values"),
    ("fhir", "Building the health record"),
    ("summarize", "Writing the summary"),
    ("done", "Done"),
]

CSS = """
<style>
.block-container, [data-testid="stMainBlockContainer"] {padding-top: 4.6rem !important; max-width: 1200px;}
.bx-chip {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.82rem; font-weight:600; margin:2px 4px 2px 0;}
.bx-card {border:1px solid rgba(128,128,128,0.25); border-radius:12px; padding:14px 16px; margin-bottom:12px;}
.bx-muted {opacity:0.7; font-size:0.88rem;}
.bx-header {display:flex; flex-wrap:wrap; gap:12px 28px; align-items:baseline; padding:10px 14px; border-radius:12px;
            background: rgba(14,116,144,0.08); margin-bottom:10px;}
.bx-header b {font-size:1.15rem;}
.bx-disclaimer {border-left:4px solid #b45309; background: rgba(245,158,11,0.10); padding:10px 12px; border-radius:6px; font-size:0.9rem;}
.bx-warn {border-left:4px solid #b91c1c; background: rgba(239,68,68,0.08); padding:8px 12px; border-radius:6px; margin:4px 0;}
@media (max-width: 640px) { .bx-header {flex-direction:column; gap:4px;} .block-container {padding-left:0.8rem; padding-right:0.8rem;} }
</style>
"""


def setup(title: str):
    st.markdown(CSS, unsafe_allow_html=True)
    patient = patient_sidebar()
    if patient:
        patient_header(patient)
    st.subheader(title)
    return patient


def chip(text: str, flag: str = "unknown") -> str:
    fg, bg, _ = FLAG_STYLE.get(flag, FLAG_STYLE["unknown"])
    return f'<span class="bx-chip" style="color:{fg};background:{bg}">{text}</span>'


def flag_label(flag: str, lang: str = "en") -> str:
    return FLAG_HI.get(flag, flag) if lang == "hi" else FLAG_STYLE.get(flag, FLAG_STYLE["unknown"])[2]


def safe(fn, *args, default=None, **kwargs):
    try:
        return fn(*args, **kwargs)
    except api.ApiError as exc:
        st.error(str(exc))
        return default


def patient_sidebar() -> dict | None:
    with st.sidebar:
        st.markdown("### 🩺 ByteXL")
        st.caption("Your health records, explained.")
        try:
            patients = api.get("/patients")
        except api.ApiError as exc:
            st.error(str(exc))
            return None
        if patients:
            ids = [p["_id"] for p in patients]
            current = st.session_state.get("patient_id")
            idx = ids.index(current) if current in ids else len(ids) - 1
            pid = st.selectbox("Patient", ids, index=idx, format_func=lambda i: next(p["name"] for p in patients if p["_id"] == i))
            st.session_state["patient_id"] = pid
        with st.expander("➕ New patient", expanded=not patients):
            with st.form("new_patient", clear_on_submit=True):
                name = st.text_input("Full name")
                sex = st.selectbox("Sex", ["male", "female", "other"])
                year = st.number_input("Birth year", min_value=1900, max_value=2026, value=1980)
                if st.form_submit_button("Create") and name.strip():
                    p = safe(api.post, "/patients", json={"name": name, "sex": sex, "birth_year": int(year)})
                    if p:
                        st.session_state["patient_id"] = p["_id"]
                        st.rerun()
        health_badge()
    pid = st.session_state.get("patient_id")
    if not pid:
        st.info("Create a patient profile in the sidebar to get started.")
        return None
    return safe(api.get, f"/patients/{pid}")


def health_badge():
    try:
        h = api.health()
    except api.ApiError:
        st.caption("🔴 API offline")
        return
    ok = h["ollama"]["reachable"] and h["models"]["vision_available"] and h["models"]["text_available"]
    st.caption(f"{'🟢' if ok else '🟠'} AI models {'ready' if ok else 'unavailable – basic reader will be used'} · storage: {h['store']['backend']}")


def patient_header(p: dict):
    linked = "linked" if p.get("abha_linked") else "mock"
    st.markdown(
        f'<div class="bx-header"><b>{p["name"]}</b>'
        f'<span>ABHA No. <code>{p.get("abha_number", "—")}</code> <span class="bx-muted">({linked})</span></span>'
        f'<span>ABHA address <code>{p.get("abha_address", "—")}</code></span></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Prepare FHIR export", width="stretch"):
            data = safe(api.get, f"/patients/{p['_id']}/export", timeout=60)
            if data:
                st.session_state["export_json"] = json.dumps(data, indent=2, ensure_ascii=False)
    with c2:
        if st.session_state.get("export_json"):
            st.download_button("⬇ Download FHIR Bundle", st.session_state["export_json"], file_name=f"{p['_id']}_fhir.json",
                               mime="application/fhir+json", width="stretch")
    with c3:
        with st.popover("Link an existing ABHA (mock)"):
            num = st.text_input("ABHA number", placeholder="91-XXXX-XXXX-XXXX")
            addr = st.text_input("ABHA address", placeholder="name@abdm")
            if st.button("Link"):
                if safe(api.post, f"/patients/{p['_id']}/abha/link", json={"abha_number": num, "abha_address": addr or None}):
                    st.success("Linked.")
                    st.rerun()


@st.cache_data(show_spinner=False, ttl=600)
def page_image(doc_id: str, index: int, updated: str) -> bytes | None:
    try:
        return api.get(f"/documents/{doc_id}/pages/{index}", timeout=30)
    except api.ApiError:
        return None


def crop(img_bytes: bytes, box: dict, pad_x: int = 320, pad_y: int = 36) -> Image.Image:
    im = highlight(img_bytes, box)
    x0, y0, x1, y1 = box["x0"], box["y0"], box["x1"], box["y1"]
    return im.crop((max(0, x0 - pad_x), max(0, y0 - pad_y), min(im.width, x1 + pad_x), min(im.height, y1 + pad_y)))


def highlight(img_bytes: bytes, box: dict | None) -> Image.Image:
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if box:
        d = ImageDraw.Draw(im, "RGBA")
        d.rectangle((box["x0"] - 6, box["y0"] - 4, box["x1"] + 6, box["y1"] + 4), outline=(220, 38, 38, 255), width=5, fill=(250, 204, 21, 70))
    return im


def doc_label(d: dict, docs: list[dict] | None = None) -> str:
    t = TYPE_LABEL.get(d.get("document_type"), "Processing…")
    date = d.get("document_date") or "date unknown"
    base = f"{TYPE_ICON.get(d.get('document_type'), '📄')} {t} · {date} · {d.get('filename', '')}"
    did = d.get("id") or d.get("_id")
    twins = [x for x in docs or [] if (x.get("id") or x.get("_id")) != did and x.get("filename") == d.get("filename")
             and x.get("document_date") == d.get("document_date") and x.get("document_type") == d.get("document_type")]
    return f"{base} · #{did[-4:]}" if twins else base


def conf_badge(c: float | None) -> str:
    if c is None:
        return ""
    if c >= 0.85:
        return "🟢"
    if c >= 0.6:
        return "🟠"
    return "🔴"


def summary_card(doc_id: str, key: str):
    lang_label = st.segmented_control("Language", ["English", "हिंदी"], default="English", key=f"lang_{key}")
    lang = "hi" if lang_label == "हिंदी" else "en"
    with st.spinner("Preparing the summary…" if lang == "en" else "सारांश तैयार हो रहा है…"):
        s = safe(api.get, f"/documents/{doc_id}/summary?lang={lang}", timeout=900)
    if not s:
        return
    with st.container(border=True):
        h = {"en": ("What this document is", "Key findings", "Values outside the reference range", "Medicines — how to take them (as written)",
                    "Questions to ask your doctor", "Please note", "No values were outside the reference range."),
             "hi": ("यह दस्तावेज़ क्या है", "मुख्य बातें", "सामान्य सीमा से बाहर के मान", "दवाएं — कैसे लेनी हैं (जैसा लिखा है)",
                    "अपने डॉक्टर से पूछने के लिए सवाल", "कृपया ध्यान दें", "कोई भी मान सामान्य सीमा से बाहर नहीं है।")}[lang]
        st.markdown(f"**{h[0]}**  \n{s['what_this_is']}")
        if s.get("key_findings"):
            st.markdown(f"**{h[1]}**")
            st.markdown("\n".join(f"- {k}" for k in s["key_findings"]))
        if s.get("has_results"):
            st.markdown(f"**{h[2]}**")
            if s["out_of_range"]:
                for o in s["out_of_range"]:
                    rng = f" <span class='bx-muted'>(range {o['range']})</span>" if o.get("range") else ""
                    st.markdown(f"{chip(flag_label(o['flag'], lang), o['flag'])} <b>{o['name']}: {o['value']}</b>{rng}<br>"
                                f"<span class='bx-muted'>{o['meaning']}</span>", unsafe_allow_html=True)
            else:
                st.markdown(h[6])
        if s.get("medicines"):
            st.markdown(f"**{h[3]}**")
            for m in s["medicines"]:
                generic = f" <span class='bx-muted'>({m['generic']})</span>" if m.get("generic") else ""
                written = f"<br><span class='bx-muted'>✍ {m['as_written']}</span>" if m.get("as_written") else ""
                st.markdown(f"💊 <b>{m['name']}</b>{generic} — {m['how_to_take']}{written}", unsafe_allow_html=True)
        if s.get("questions"):
            st.markdown(f"**{h[4]}**")
            st.markdown("\n".join(f"- {q}" for q in s["questions"]))
        if s.get("notes"):
            st.markdown(f"**{h[5]}**")
            for n in s["notes"]:
                st.markdown(f"<div class='bx-warn'>{n}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='bx-disclaimer'>⚠️ {s['disclaimer']}</div>", unsafe_allow_html=True)
        st.caption(("Written by the local AI model and safety-checked." if s["method"] == "llm" else "Generated from a safe template (AI wording unavailable or rejected).")
                   if lang == "en" else ("स्थानीय AI मॉडल द्वारा लिखा और सुरक्षा-जांच किया गया।" if s["method"] == "llm" else "सुरक्षित टेम्पलेट से बनाया गया।"))
