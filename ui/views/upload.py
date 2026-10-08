import time

import streamlit as st

import api_client as api
from common import STAGES, TYPE_LABEL, safe, setup, summary_card

patient = setup("Documents")
if not patient:
    st.stop()

st.write("Add a lab report, prescription or discharge summary. Photos and scans work too — keep the whole page in view and in focus.")
file = st.file_uploader("Drop a PDF, JPG or PNG here", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=False)

if file is not None and st.button("Process document", type="primary", width="stretch"):
    res = safe(api.post, f"/patients/{patient['_id']}/documents", files={"file": (file.name, file.getvalue(), file.type)}, timeout=120)
    if res:
        st.session_state["processing_doc"] = res["document_id"]

doc_id = st.session_state.get("processing_doc")
if doc_id:
    keys = [k for k, _ in STAGES]
    progress = st.progress(0.0)
    box = st.status("Processing… on a CPU-only computer this can take a few minutes.", expanded=True)
    lines = {k: box.empty() for k, _ in STAGES[1:]}
    doc = None
    started = time.time()
    while True:
        doc = safe(api.get, f"/documents/{doc_id}")
        if not doc:
            break
        status = doc["status"]
        idx = keys.index(status["stage"]) if status["stage"] in keys else 0
        timings = status.get("timings", {})
        for k, label in STAGES[1:]:
            i = keys.index(k)
            took = f" · {timings[k]:.0f}s" if k in timings else ""
            if status["state"] == "failed" and k == status["stage"]:
                lines[k].markdown(f"❌ {label}")
            elif i < idx or status["state"] == "done":
                lines[k].markdown(f"✅ {label}{took}")
            elif i == idx:
                lines[k].markdown(f"⏳ **{label}…** ({time.time() - started:.0f}s)")
            else:
                lines[k].markdown(f"▫️ {label}")
        progress.progress(min(1.0, idx / (len(keys) - 1)))
        if status["state"] in ("done", "failed"):
            break
        time.sleep(1.5)
    if doc and doc["status"]["state"] == "failed":
        box.update(label="We couldn't finish processing this document.", state="error", expanded=True)
        st.error(doc["status"].get("message") or "Something went wrong.")
        if st.button("Try again"):
            safe(api.post, f"/documents/{doc_id}/retry")
            st.rerun()
    elif doc:
        box.update(label=f"Done · {TYPE_LABEL.get(doc['document_type'], 'Document')}", state="complete", expanded=False)
        progress.progress(1.0)
        for w in doc.get("warnings", []):
            st.warning(w)
        n = len(doc.get("confirm_queue", []))
        c1, c2 = st.columns(2)
        if c1.button("Open document view", width="stretch"):
            st.session_state["doc_id"] = doc_id
            st.switch_page("views/document.py")
        if n and c2.button(f"Review {n} item(s) to confirm", type="primary", width="stretch"):
            st.session_state["doc_id"] = doc_id
            st.switch_page("views/confirm.py")
        summary_card(doc_id, "upload")
