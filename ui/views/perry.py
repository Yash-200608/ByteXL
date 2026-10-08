import html
import re

import streamlit as st

import api_client as api
from common import CSS as BASE_CSS, patient_sidebar
from perry_mascot import CSS, mascot

QUICK_ACTIONS = [
    ("📄 Latest report", "Explain my latest report"),
    ("💊 My medicines", "What medicines are in my records?"),
    ("📈 What changed?", "What changed in my health records?"),
    ("🗓️ My timeline", "Show me my timeline"),
    ("📂 Recent documents", "What documents did I upload recently?"),
    ("⏳ Pending confirmations", "Do I have anything waiting for confirmation?"),
]
HINGLISH = re.compile(r"\b(meri|mera|mere|kya|hai|dikhao|batao|samjhao|dawai|dawa|mujhe|kaise|kitna|pichl\w*)\b", re.I)
THINKING = {
    "en": "PERRY is checking your records",
    "hi": "PERRY आपके रिकॉर्ड देख रहा है",
    "hinglish": "PERRY aapke records dekh raha hai",
}
LANG_BADGE = {"hi": "हिंदी", "hinglish": "Hinglish", "ta": "தமிழ்", "te": "తెలుగు", "bn": "বাংলা", "mr": "मराठी", "gu": "ગુજરાતી",
              "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "pa": "ਪੰਜਾਬੀ", "or": "ଓଡ଼ିଆ"}


def _lang(text: str) -> str:
    if any("ऀ" <= c <= "ॿ" for c in text):
        return "hi"
    return "hinglish" if HINGLISH.search(text) else "en"


def _state_key(pid: str) -> str:
    return f"perry_chat_{pid}"


def _who(state: str = "idle") -> str:
    return f'<div class="perry-who">{mascot(state, 30)} PERRY</div>'


def _render_message(i: int, m: dict):
    if m["role"] == "user":
        with st.container(key=f"pmsg-user-{i}"):
            st.markdown(html.escape(m["content"]))
        return
    error = m.get("state") == "error"
    with st.container(key=f"pmsg-perry{'-error' if error else ''}-{i}"):
        badge = f'<span class="perry-lang">{LANG_BADGE[m["language"]]}</span>' if m.get("language") in LANG_BADGE else ""
        st.markdown(_who("error" if error else "idle").replace("PERRY</div>", f"PERRY{badge}</div>"), unsafe_allow_html=True)
        st.markdown(m["content"])
        if m.get("sources"):
            chips = "".join(
                f'<span class="perry-src">📄 {html.escape(s.get("title") or "Document")} · {html.escape(s.get("date_text") or "—")} · '
                f'{html.escape(s.get("filename") or "")}</span>' for s in m["sources"])
            st.markdown(chips, unsafe_allow_html=True)


def _ask(pid: str, text: str):
    chat = st.session_state.setdefault(_state_key(pid), [])
    chat.append({"role": "user", "content": text.strip()[:1000]})
    st.session_state["perry_pending"] = text.strip()[:1000]


def _answer_pending(pid: str):
    chat = st.session_state[_state_key(pid)]
    text = st.session_state.pop("perry_pending")
    lang = _lang(text)
    with st.container(key="pmsg-perry-thinking"):
        st.markdown(f'<div class="perry-thinking-row">{mascot("thinking", 46)}<span>{THINKING[lang]}'
                    f'</span><span class="perry-dots"><span></span><span></span><span></span></span></div>', unsafe_allow_html=True)
    history = [{"role": m["role"], "content": m["content"][:2000]} for m in chat[:-1]][-12:]
    try:
        r = api.post(f"/patients/{pid}/perry", json={"message": text, "history": history}, timeout=600)
        chat.append({"role": "perry", "content": r["reply"], "sources": r.get("sources", []), "language": r.get("language"),
                     "state": r.get("state", "ok")})
    except api.ApiError:
        msg = {"en": "I couldn't access that information right now. Please try again in a moment.",
               "hi": "मैं अभी यह जानकारी नहीं खोल पाया। कृपया थोड़ी देर बाद फिर कोशिश करें।",
               "hinglish": "Main abhi yeh jaankari access nahi kar paaya. Thodi der baad phir try kijiye."}[lang]
        chat.append({"role": "perry", "content": msg, "state": "error", "language": lang})
    st.rerun()


st.markdown(BASE_CSS + CSS, unsafe_allow_html=True)
patient = patient_sidebar()
if not patient:
    st.markdown(f'<div class="perry-hero">{mascot("idle", 170)}<div class="perry-name">PERRY</div>'
                f'<div class="perry-tag">Your ByteXL assistant</div>'
                f'<div class="perry-say">Create or pick a profile in the sidebar and I\'ll get to know your records.</div></div>',
                unsafe_allow_html=True)
    st.stop()

pid = patient["_id"]
chat = st.session_state.setdefault(_state_key(pid), [])
first = (patient.get("name") or "there").split()[0]
pending = "perry_pending" in st.session_state
last_state = chat[-1].get("state") if chat and chat[-1]["role"] == "perry" else "idle"
face = "thinking" if pending else ("error" if last_state == "error" else "idle")

if not chat:
    st.markdown(
        f'<div class="perry-hero">{mascot(face, 180)}<div class="perry-name">PERRY</div>'
        f'<div class="perry-tag">Your ByteXL assistant</div>'
        f'<div class="perry-say">Hi {html.escape(first)}! What can I help you find in your records?</div><br>'
        f'<span class="perry-scope">🔒 Only {html.escape(patient.get("name", ""))}\'s ByteXL records</span></div>',
        unsafe_allow_html=True)
else:
    status = {"thinking": "Looking through your records…", "error": "I couldn't access that information right now.",
              "idle": "Ready when you are"}[face]
    c1, c2 = st.columns([6, 1], vertical_alignment="center")
    with c1:
        st.markdown(f'<div class="perry-bar">{mascot(face, 58)}<div><div class="perry-mini-name">PERRY</div>'
                    f'<div class="perry-status"><span class="perry-dot"></span>{status} · {html.escape(patient.get("name", ""))}\'s records</div>'
                    f'</div></div>', unsafe_allow_html=True)
    with c2:
        if st.button("New chat", key="perry-reset", width="stretch"):
            st.session_state[_state_key(pid)] = []
            st.rerun()

for i, m in enumerate(chat):
    _render_message(i, m)

if pending:
    _answer_pending(pid)

st.markdown('<div class="perry-qa-label">Quick actions</div>', unsafe_allow_html=True)
cols = st.columns(3)
for n, (label, prompt) in enumerate(QUICK_ACTIONS):
    with cols[n % 3]:
        if st.button(label, key=f"qa-{n}", width="stretch"):
            _ask(pid, prompt)
            st.rerun()

st.markdown('<div class="perry-foot">PERRY explains what is in your records. It is not a doctor and never changes your medicines.</div>',
            unsafe_allow_html=True)

text = st.chat_input("Ask PERRY anything about your records… (English, हिंदी, Hinglish)")
if text and text.strip():
    _ask(pid, text)
    st.rerun()
