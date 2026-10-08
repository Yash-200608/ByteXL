import altair as alt
import pandas as pd
import streamlit as st

import api_client as api
from common import FLAG_STYLE, flag_label, safe, setup

patient = setup("Overview")
if not patient:
    st.stop()
pid = patient["_id"]

ov = safe(api.get, f"/patients/{pid}/overview", default={}) or {}
stats = [
    ("Health records", (ov.get("documents") or {}).get("total", 0)),
    ("Out of range (latest lab)", len(ov.get("latest_out_of_range") or [])),
    ("Current medicines", len(ov.get("current_medicines") or [])),
    ("Pending items", ov.get("pending_confirmations", 0)),
]
for col, (k, v) in zip(st.columns(4), stats):
    col.markdown(f'<div class="p-stat"><div class="k">{k}</div><div class="v">{v}</div></div>', unsafe_allow_html=True)
st.write("")
st.markdown("#### Trends")

tests = safe(api.get, f"/patients/{pid}/trends", default=[])
if not tests:
    st.markdown('<div class="p-card p-empty"><b>No lab results yet.</b><br>Upload lab reports to see how your values change over time.</div>',
                unsafe_allow_html=True)
    st.stop()

options = [t["loinc"] for t in tests]
label = {t["loinc"]: f"{t['name']} ({t['count']} result{'s' if t['count'] != 1 else ''})" for t in tests}
default = st.session_state.get("trend_loinc") if st.session_state.get("trend_loinc") in options else options[0]
loinc = st.selectbox("Test", options, index=options.index(default), format_func=lambda k: label[k])
st.session_state["trend_loinc"] = loinc
tr = safe(api.get, f"/patients/{pid}/trends/{loinc}")
if not tr or not tr["points"]:
    st.stop()

df = pd.DataFrame(tr["points"])
df["date"] = pd.to_datetime(df["date"])
df["status"] = df["flag"].map(lambda f: flag_label(f))
unit = tr.get("unit") or ""
lo, hi = tr.get("ref_low"), tr.get("ref_high")
values = df["value"].tolist() + [v for v in (lo, hi) if v is not None]
pad = (max(values) - min(values)) * 0.25 or max(abs(max(values)) * 0.2, 1)
ymin, ymax = min(values) - pad, max(values) + pad
xmin = df["date"].min() - pd.Timedelta(days=20)
xmax = df["date"].max() + pd.Timedelta(days=20)

layers = []
if lo is not None or hi is not None:
    band = pd.DataFrame({"x": [xmin, xmax], "lo": [lo if lo is not None else ymin] * 2, "hi": [hi if hi is not None else ymax] * 2})
    layers.append(alt.Chart(band).mark_area(opacity=0.18, color="#16a34a").encode(
        x=alt.X("x:T", title=None), y=alt.Y("lo:Q", title=unit, scale=alt.Scale(domain=[ymin, ymax])), y2="hi:Q"))
colors = alt.Scale(domain=[flag_label(k) for k in FLAG_STYLE], range=[v[0] for v in FLAG_STYLE.values()])
line = alt.Chart(df).mark_line(color="#0e7490", strokeWidth=2).encode(
    x=alt.X("date:T", title=None, scale=alt.Scale(domain=[xmin, xmax])), y=alt.Y("value:Q", title=unit, scale=alt.Scale(domain=[ymin, ymax])))
points = alt.Chart(df).mark_circle(size=140).encode(
    x="date:T", y="value:Q", color=alt.Color("status:N", scale=colors, legend=alt.Legend(title=None, orient="bottom")),
    tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("value:Q", title=f"Value ({unit})"), alt.Tooltip("status:N", title="Status")])
labels = alt.Chart(df).mark_text(dy=-14, fontSize=12).encode(x="date:T", y="value:Q", text=alt.Text("value:Q", format=".4~g"))
st.altair_chart(alt.layer(*layers, line, points, labels).properties(height=360), width="stretch")

rng = "–".join(f"{v:g}" for v in (lo, hi) if v is not None)
if lo is not None and hi is None:
    rng = f"above {lo:g}"
elif hi is not None and lo is None:
    rng = f"below {hi:g}"
st.caption(f"Green band = reference range ({rng} {unit}). Values are shown in a common unit so results from different labs can be compared.")
latest = tr["points"][-1]
first = tr["points"][0]
if len(tr["points"]) > 1:
    change = latest["value"] - first["value"]
    st.markdown(f"From **{first['value']:g}** on {first['date']} to **{latest['value']:g}** on {latest['date']} "
                f"({'+' if change >= 0 else ''}{change:.3g} {unit}). Talk to your doctor about what this trend means for you.")
