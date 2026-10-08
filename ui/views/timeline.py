import streamlit as st

import api_client as api
from common import TYPE_ICON, TYPE_LABEL, chip, flag_label, safe, setup

patient = setup("Timeline")
if not patient:
    st.stop()
pid = patient["_id"]

meds = safe(api.get, f"/patients/{pid}/medications", default=None)
if meds and (meds["active"] or meds["reconciliation_notes"]):
    with st.container(border=True):
        st.markdown(f"**💊 Current medicines** <span class='bx-muted'>(as of {meds['as_of']})</span>", unsafe_allow_html=True)
        for n in meds["reconciliation_notes"]:
            st.markdown(f"<div class='bx-warn'>⚠️ {n['text']}</div>", unsafe_allow_html=True)
        for m in meds["active"]:
            generic = f" <span class='bx-muted'>({m['generic']})</span>" if m.get("generic") else ""
            st.markdown(f"- **{m['name']}**{generic} — {m.get('how_to_take') or m.get('as_written')}", unsafe_allow_html=True)

types = st.pills("Show", ["lab_report", "prescription", "discharge_summary"], selection_mode="multi",
                 default=["lab_report", "prescription", "discharge_summary"], format_func=lambda t: f"{TYPE_ICON[t]} {TYPE_LABEL[t]}")
items = safe(api.get, f"/patients/{pid}/timeline", default=[])
items = [i for i in items if i["document_type"] in (types or []) or i["status"].get("state") != "done"]
if not items:
    st.markdown("<div class='p-card p-empty'><b>PERRY is ready.</b><br>Upload your first health record under Documents and I'll build your timeline.</div>", unsafe_allow_html=True)
    st.stop()

for it in items:
    state = it["status"].get("state")
    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        with c1:
            title = TYPE_LABEL.get(it["document_type"], "Document")
            icon = TYPE_ICON.get(it["document_type"], "📄")
            st.markdown(f"**{icon} {title}** · {it['date'] or 'date unknown'}")
            if it.get("source"):
                st.caption(it["source"])
            if state != "done":
                st.caption(f"⏳ {it['status'].get('stage')} — {state}")
            chips = ""
            if it["document_type"] in ("lab_report", "discharge_summary") and it.get("abnormal"):
                chips += "".join(chip(f"{a['name']} {flag_label(a['flag']).lower()}", a["flag"]) for a in it["abnormal"][:8])
            elif it["document_type"] == "lab_report":
                chips += chip("All values within range", "normal")
            if it.get("diagnoses"):
                chips += "".join(chip(d, "unknown") for d in it["diagnoses"][:3])
            if it["document_type"] == "prescription" and it.get("highlights"):
                chips += "".join(chip(f"💊 {h}", "unknown") for h in it["highlights"])
            if chips:
                st.markdown(chips, unsafe_allow_html=True)
            if it.get("pending_confirmations"):
                st.caption(f"🔴 {it['pending_confirmations']} detail(s) to confirm")
        with c2:
            if state == "done" and st.button("Open", key=f"open_{it['document_id']}", width="stretch"):
                st.session_state["doc_id"] = it["document_id"]
                st.switch_page("views/document.py")
