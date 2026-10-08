import html

import streamlit as st

import api_client as api
from common import TYPE_LABEL, safe, setup

patient = setup("Medications")
if not patient:
    st.stop()

data = safe(api.get, f"/patients/{patient['_id']}/medications", default=None)
if data is None:
    st.stop()
active = data.get("active", [])
notes = data.get("reconciliation_notes", [])

if not active:
    st.markdown('<div class="p-card p-empty"><b>No medications found in your records.</b><br>'
                "When you upload a prescription or discharge summary, PERRY lists the medicines here exactly as written.</div>",
                unsafe_allow_html=True)
    st.stop()

st.caption(f"Medicines that are current as of {data.get('as_of')}, exactly as written by your doctor. "
           "PERRY never changes doses — please ask your doctor about any change.")
for n in notes:
    st.markdown(f'<div class="bx-warn">⚠️ {html.escape(n["text"])}</div>', unsafe_allow_html=True)

cols = st.columns(2)
for i, m in enumerate(active):
    with cols[i % 2]:
        generic = f' <span class="bx-muted">({html.escape(m["generic"])})</span>' if m.get("generic") else ""
        how = html.escape(m.get("how_to_take") or "")
        written = html.escape(m.get("as_written") or "")
        source = f'{TYPE_LABEL.get(m.get("document_type"), "Document")} · {m.get("date") or "—"}'
        st.markdown(f'<div class="bx-card"><div style="font-size:1.1rem;font-weight:700">💊 {html.escape(m["name"] or "")}{generic}</div>'
                    f'<div style="margin-top:6px">{how}</div>'
                    f'<div class="bx-muted" style="margin-top:4px">✍ As written: {written or "—"}</div>'
                    f'<div class="bx-muted" style="margin-top:4px">📄 {source}</div></div>', unsafe_allow_html=True)
