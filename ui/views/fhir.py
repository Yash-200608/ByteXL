import json

import streamlit as st

import api_client as api
from common import doc_label, patient_header, safe, setup

patient = setup("FHIR Record")
if not patient:
    st.stop()

st.caption("Every document you upload becomes an HL7 FHIR R4 record, shaped to India's ABDM / NRCeS profiles, "
           "so it can be shared with hospitals and health apps.")
patient_header(patient)

docs = [d for d in safe(api.get, f"/patients/{patient['_id']}/documents", default=[]) or [] if d["status"]["state"] == "done"]
if not docs:
    st.markdown('<div class="p-card p-empty"><b>No health records yet.</b><br>Upload a document and PERRY will build its FHIR record.</div>',
                unsafe_allow_html=True)
    st.stop()

ids = [d["id"] for d in docs]
current = st.session_state.get("doc_id")
c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
with c1:
    doc_id = st.selectbox("Document", ids, index=ids.index(current) if current in ids else 0,
                          format_func=lambda i: doc_label(next(d for d in docs if d["id"] == i), docs))
with c2:
    profile = st.segmented_control("Format", ["ABDM document", "Collection"], default="ABDM document", key="fhir_profile")
bundle = safe(api.get, f"/documents/{doc_id}/fhir", params={"profile": "abdm" if profile != "Collection" else "collection"}, timeout=60)
if bundle:
    kinds = {}
    for e in bundle.get("entry", []):
        t = e["resource"]["resourceType"]
        kinds[t] = kinds.get(t, 0) + 1
    st.markdown(" ".join(f'<span class="bx-chip" style="background:rgba(46,230,214,.15);color:#7DF9EC">{k} × {v}</span>'
                         for k, v in sorted(kinds.items())), unsafe_allow_html=True)
    st.download_button("⬇ Download this FHIR bundle", json.dumps(bundle, indent=2, ensure_ascii=False),
                       file_name=f"{doc_id}_{'abdm' if profile != 'Collection' else 'collection'}.json", mime="application/fhir+json")
    with st.expander("View the FHIR JSON"):
        st.json(bundle, expanded=1)
