import streamlit as st

import api_client as api
from common import crop, doc_label, empty_state, page_image, safe, setup

patient = setup("Pending Items")
if not patient:
    st.stop()

docs = safe(api.get, f"/patients/{patient['_id']}/documents", default=[])
docs = [d for d in docs if d["status"]["state"] == "done" and d.get("pending_confirmations")]
if not docs:
    empty_state("You're all clear.", "Nothing needs your confirmation right now.")
    st.stop()

st.write("Please check these details against the original. Handwritten medicine names and doses always need a quick check.")
ids = [d["id"] for d in docs]
current = st.session_state.get("doc_id")
doc_id = st.selectbox("Document", ids, index=ids.index(current) if current in ids else 0,
                      format_func=lambda i: f"{doc_label(next(d for d in docs if d['id'] == i), docs)} · {next(d for d in docs if d['id'] == i)['pending_confirmations']} to review")
doc = safe(api.get, f"/documents/{doc_id}")
if not doc:
    st.stop()
queue = doc.get("confirm_queue", [])

if st.button(f"✓ Accept all {len(queue)} as shown", width="stretch"):
    if safe(api.post, f"/documents/{doc_id}/confirm", json={"items": [{"path": q["path"], "action": "accept"} for q in queue]}, timeout=120):
        st.toast("All accepted")
        st.rerun()

for q in queue:
    with st.container(border=True):
        top = st.columns([3, 2])
        with top[0]:
            st.markdown(f"**{q['label']}**")
            value = q["value"]
            shown = f"{value:g}" if isinstance(value, float) else (value if value not in (None, "") else "—")
            st.markdown(f"Read as: `{shown}`")
            st.caption(" · ".join(q["reasons"]) or "Low confidence")
        with top[1]:
            if q.get("source_box"):
                img = page_image(doc_id, q["source_box"].get("page", 0), doc.get("updated_at") or "")
                if img:
                    st.image(crop(img, q["source_box"]), width=360)
            else:
                st.caption("Not located on the page.")
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("✓ Accept", key=f"acc_{q['path']}", type="primary", width="stretch"):
            if safe(api.post, f"/documents/{doc_id}/confirm", json={"items": [{"path": q["path"], "action": "accept"}]}, timeout=120):
                st.rerun()
        new = c2.text_input("Correct value", value="" if value is None else str(shown), key=f"edit_{q['path']}", label_visibility="collapsed")
        if c3.button("Save edit", key=f"save_{q['path']}", width="stretch"):
            if safe(api.post, f"/documents/{doc_id}/confirm", json={"items": [{"path": q["path"], "action": "edit", "value": new}]}, timeout=120):
                st.toast("Saved — the health record was updated.")
                st.rerun()
