import json

import pandas as pd
import streamlit as st

import api_client as api
from common import TYPE_LABEL, conf_badge, crop, doc_label, flag_label, highlight, page_image, safe, setup, summary_card

patient = setup("Document")
if not patient:
    st.stop()

docs = safe(api.get, f"/patients/{patient['_id']}/documents", default=[])
docs = [d for d in docs if d["status"]["state"] == "done"]
if not docs:
    st.info("No processed documents yet. Upload one first.")
    st.stop()
ids = [d["id"] for d in docs]
current = st.session_state.get("doc_id")
doc_id = st.selectbox("Choose a document", ids, index=ids.index(current) if current in ids else 0,
                      format_func=lambda i: doc_label(next(d for d in docs if d["id"] == i), docs))
st.session_state["doc_id"] = doc_id
doc = safe(api.get, f"/documents/{doc_id}")
if not doc:
    st.stop()
ex = doc["extraction"]
if doc["document_type"] == "prescription":
    current_hw = bool(ex.get("is_handwritten"))
    hw = st.toggle("This prescription is handwritten (every medicine name and dose will need your confirmation)", value=current_hw, key=f"hw_{doc_id}")
    if hw != current_hw and safe(api.post, f"/documents/{doc_id}/handwritten", json={"handwritten": hw}, timeout=120):
        st.rerun()
for w in doc.get("warnings", []):
    st.warning(w)
pending = len(doc.get("confirm_queue", []))
if pending:
    c1, c2 = st.columns([3, 1])
    c1.info(f"{pending} detail(s) need your confirmation. Highlighted rows have lower confidence.")
    if c2.button("Review now", type="primary", width="stretch"):
        st.switch_page("views/confirm.py")


def val(f):
    v = (f or {}).get("value")
    if v is None:
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v)


def row_style(row):
    c = row.get("_conf", 1.0)
    needs = row.get("_needs", False)
    if needs or c < 0.6:
        color = "background-color: rgba(239,68,68,0.15)"
    elif c < 0.85:
        color = "background-color: rgba(245,158,11,0.15)"
    else:
        color = ""
    return [color] * len(row)


def table(rows: list[dict], key: str):
    if not rows:
        return None
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("_box", "_path")} for r in rows])
    styled = df.style.apply(row_style, axis=1)
    cfg = {"_conf": None, "_needs": None}
    sel = st.dataframe(styled, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                       column_config=cfg, key=key)
    picked = sel.selection.rows if sel and sel.selection else []
    return rows[picked[0]] if picked else None


def field_row(label, f, path):
    f = f or {}
    return {"Field": label, "Value": val(f), "✓": conf_badge(f.get("confidence")) if f.get("value") is not None else "",
            "_conf": f.get("confidence", 1.0) if f.get("value") is not None else 1.0, "_needs": f.get("needs_confirmation", False),
            "_box": f.get("source_box"), "_path": path}


left, right = st.columns([5, 6], gap="large")
selected = None
pickable: list[dict] = []
with right:
    st.markdown(f"#### {TYPE_LABEL.get(doc['document_type'], 'Document')}")
    p = ex["patient"]
    details = [field_row("Patient", p["name"], "patient.name"), field_row("Age", p["age_years"], "patient.age_years"),
               field_row("Sex", p["sex"], "patient.sex")]
    if doc["document_type"] == "lab_report":
        details += [field_row("Laboratory", ex["facility"], "facility"), field_row("Referred by", ex["referring_doctor"], "referring_doctor"),
                    field_row("Collected on", ex["collected_on"], "collected_on"), field_row("Reported on", ex["reported_on"], "reported_on")]
    elif doc["document_type"] == "prescription":
        details += [field_row("Doctor", ex["prescriber"], "prescriber"), field_row("Registration", ex["prescriber_registration"], "prescriber_registration"),
                    field_row("Clinic", ex["facility"], "facility"), field_row("Date", ex["date"], "date")]
        details += [field_row("Complaint", c, f"complaints.{i}") for i, c in enumerate(ex["complaints"])]
        details += [field_row("Diagnosis (as written)", c, f"diagnoses.{i}") for i, c in enumerate(ex["diagnoses"])]
        details += [field_row("Follow-up", ex["follow_up"], "follow_up")]
    else:
        details += [field_row("Hospital", ex["facility"], "facility"), field_row("Doctor", ex["attending_doctor"], "attending_doctor"),
                    field_row("Admitted", ex["admission_date"], "admission_date"), field_row("Discharged", ex["discharge_date"], "discharge_date")]
        details += [field_row("Diagnosis (as written)", c, f"diagnoses.{i}") for i, c in enumerate(ex["diagnoses"])]
        details += [field_row("Follow-up", ex["follow_up"], "follow_up")]
    details = [d for d in details if d["Value"]]

    results_key = "results" if doc["document_type"] == "lab_report" else "investigations"
    results = ex.get(results_key, [])
    if results:
        st.markdown("**Test results** — tap a row to see where it came from")
        rows = []
        for i, r in enumerate(results):
            n = r.get("normalized") or {}
            flag = n.get("flag", "unknown")
            rows.append({
                "Test": val(r["test_name"]), "Result": val(r["value"]) or val(r["value_text"]), "Unit": val(r["unit"]),
                "Range": val(r["reference_range"]), "Status": flag_label(flag), "✓": conf_badge(min(r["value"].get("confidence", 1), r["test_name"].get("confidence", 1))),
                "_conf": min(r["value"].get("confidence", 1) if r["value"].get("value") is not None else 1, r["test_name"].get("confidence", 1)),
                "_needs": r["value"].get("needs_confirmation") or r["test_name"].get("needs_confirmation"),
                "_box": r["value"].get("source_box") or r["test_name"].get("source_box"), "_path": f"{results_key}.{i}.value",
            })
        pick = table(rows, f"res_{doc_id}")
        selected = pick or selected
        pickable += [{**r, "_label": f"{r['Test']}: {r['Result']} {r['Unit']}".strip()} for r in rows]
    meds_key = "medications" if doc["document_type"] == "prescription" else "discharge_medications"
    meds = ex.get(meds_key, [])
    if meds:
        st.markdown("**Medicines** — tap a row to see where it came from")
        rows = []
        for i, m in enumerate(meds):
            n = m.get("normalized") or {}
            dosage = (n.get("dosage") or {}).get("text", "")
            written = " ".join(x for x in (val(m["dosage"]), val(m["timing"]), val(m["duration"])) if x)
            c = min(m["name"].get("confidence", 1), m["dosage"].get("confidence", 1) if m["dosage"].get("value") else 1)
            rows.append({"Medicine": val(m["name"]), "Generic": n.get("generic") or "not recognised", "How to take": dosage, "As written": written,
                         "✓": conf_badge(c), "_conf": c, "_needs": m["name"].get("needs_confirmation") or m["dosage"].get("needs_confirmation"),
                         "_box": m["name"].get("source_box"), "_path": f"{meds_key}.{i}.name"})
        pick = table(rows, f"med_{doc_id}")
        selected = pick or selected
        pickable += [{**r, "_label": r["Medicine"]} for r in rows]
    st.markdown("**Details**")
    pick = table(details, f"det_{doc_id}")
    selected = pick or selected
    pickable += [{**r, "_label": f"{r['Field']}: {r['Value']}"} for r in details]
    st.caption("🟢 high confidence · 🟠 check · 🔴 needs confirmation")
    labels = [r["_label"] for r in pickable]
    chosen = st.selectbox("Show where a value came from", labels, index=None, placeholder="Pick a value…", key=f"src_{doc_id}")
    if chosen and not selected:
        selected = pickable[labels.index(chosen)]

with left:
    page_idx = 0
    if selected and selected.get("_box"):
        page_idx = selected["_box"].get("page", 0)
    img = page_image(doc_id, page_idx, doc.get("updated_at") or "")
    if img:
        if selected and selected.get("_box"):
            st.markdown(f"**Source of:** {selected.get('Test') or selected.get('Medicine') or selected.get('Field')}")
            st.image(crop(img, selected["_box"]), width=420)
        elif selected:
            st.caption("This value could not be located on the page.")
        st.image(highlight(img, selected.get("_box") if selected else None), width="stretch",
                 caption=f"Page {page_idx + 1} of {len(doc['pages'])}")
    else:
        st.caption("Page image unavailable.")

st.markdown("#### Plain-language summary")
summary_card(doc_id, f"doc_{doc_id}")

with st.expander("Health record (FHIR R4) for developers and ABDM"):
    fhir = safe(api.get, f"/documents/{doc_id}/fhir")
    abdm = safe(api.get, f"/documents/{doc_id}/fhir?profile=abdm")
    if fhir:
        kinds = pd.Series([e["resource"]["resourceType"] for e in fhir["entry"]]).value_counts()
        st.write("Resources: " + ", ".join(f"{k} × {v}" for k, v in kinds.items()))
        c1, c2 = st.columns(2)
        c1.download_button("⬇ FHIR collection Bundle", json.dumps(fhir, indent=2), file_name=f"{doc_id}_bundle.json", mime="application/fhir+json")
        if abdm:
            c2.download_button("⬇ ABDM document Bundle", json.dumps(abdm, indent=2), file_name=f"{doc_id}_abdm.json", mime="application/fhir+json")
