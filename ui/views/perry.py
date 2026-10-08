import html
import json
import re

import streamlit as st

import api_client as api
from common import CSS as BASE_CSS, patient_sidebar
from perry_mascot import CSS, mascot
from perry_voice import (RECOGNITION_LANGS, SAMPLE, SPEECH_LANG, browser_mic, browser_voices, has_indian_voice, pick_voice,
                         rank_voices, speak, stop_speaking, voice_label)

QUICK_ACTIONS = [
    ("📄 Latest report", "Explain my latest report"),
    ("💊 My medicines", "What medicines are in my records?"),
    ("📈 What changed?", "What changed in my health records?"),
    ("🗓️ My timeline", "Show me my timeline"),
    ("📂 Recent documents", "What documents did I upload recently?"),
    ("⏳ Pending confirmations", "Do I have anything waiting for confirmation?"),
]
HINGLISH = re.compile(r"\b(meri|mera|mere|kya|hai|dikhao|batao|samjhao|dawai|dawa|mujhe|kaise|kitna|pichl\w*)\b", re.I)
ENGINES = {"device": "On this device (private)", "browser": "Browser (sends audio to Google/Microsoft)"}
LISTENING = "Listening to you, then checking your records"
NOT_SET_UP = "Voice isn't set up"
THINKING = {
    "en": "PERRY is checking your records",
    "hi": "PERRY आपके रिकॉर्ड देख रहा है",
    "hinglish": "PERRY aapke records dekh raha hai",
}
LANG_BADGE = {"hi": "हिंदी", "hinglish": "Hinglish", "ta": "தமிழ்", "te": "తెలుగు", "bn": "বাংলা", "mr": "मराठी", "gu": "ગુજરાતી",
              "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "pa": "ਪੰਜਾਬੀ", "or": "ଓଡ଼ିଆ", "ur": "اردو"}
LANGUAGE_STRIP = "English · हिंदी · Hinglish · বাংলা · मराठी · తెలుగు · தமிழ் · ગુજરાતી · اردو · ಕನ್ನಡ · ଓଡ଼ିଆ · മലയാളം"


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
            st.markdown(("🎙️ " if m.get("voice") else "") + html.escape(m["content"]))
            if m.get("corrections"):
                st.caption("Matched to your records: " + ", ".join(f"“{c['heard']}” → {c['corrected']}" for c in m["corrections"]))
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
        if not error and st.button("🔊", key=f"say-{i}", help="Read this answer aloud"):
            st.session_state["perry_speak"] = i


def _ask(pid: str, text: str, voice: bool = False):
    chat = st.session_state.setdefault(_state_key(pid), [])
    chat.append({"role": "user", "content": text.strip()[:1000], "voice": voice})
    st.session_state["perry_pending"] = text.strip()[:1000]
    st.session_state["perry_pending_voice"] = voice


def _ask_audio(pid: str, audio: bytes):
    chat = st.session_state.setdefault(_state_key(pid), [])
    chat.append({"role": "user", "content": "…", "voice": True})
    st.session_state["perry_pending_audio"] = audio


def _thinking(text: str):
    with st.container(key="pmsg-perry-thinking"):
        st.markdown(f'<div class="perry-thinking-row">{mascot("thinking", 46)}<span>{text}'
                    f'</span><span class="perry-dots"><span></span><span></span><span></span></span></div>', unsafe_allow_html=True)


def _history(chat: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"][:2000]} for m in chat[:-1] if m["content"] != "…"][-12:]


def _reply(chat: list[dict], r: dict, voice: bool):
    state = "error" if r.get("state") in ("error", "no_speech") else r.get("state", "ok")
    chat.append({"role": "perry", "content": r["reply"], "sources": r.get("sources", []), "language": r.get("language"), "state": state})
    if voice and st.session_state.get("perry_autospeak", True) and state != "error":
        st.session_state["perry_speak"] = len(chat) - 1


def _answer_audio(pid: str, chat: list[dict]):
    audio = st.session_state.pop("perry_pending_audio")
    _thinking(LISTENING)
    try:
        r = api.post(f"/patients/{pid}/perry/voice", files={"audio": ("question.wav", audio, "audio/wav")},
                     data={"history": json.dumps(_history(chat), ensure_ascii=False)}, timeout=600)
        chat[-1]["content"] = r.get("transcript") or "(nothing heard)"
        chat[-1]["corrections"] = r.get("corrections") or []
        _reply(chat, r, voice=True)
    except api.ApiError as exc:
        chat[-1]["content"] = "(voice message)"
        if NOT_SET_UP in str(exc):
            msg = f"{exc} You can type your question, or switch to browser recognition under 🎙️ Voice."
        else:
            msg = "I couldn't process that recording right now. Please try again or type your question."
        chat.append({"role": "perry", "content": msg, "state": "error", "language": "en"})
    st.rerun()


def _answer_pending(pid: str):
    chat = st.session_state[_state_key(pid)]
    if "perry_pending_audio" in st.session_state:
        _answer_audio(pid, chat)
    text = st.session_state.pop("perry_pending")
    voice = st.session_state.pop("perry_pending_voice", False)
    lang = _lang(text)
    _thinking(THINKING[lang])
    try:
        r = api.post(f"/patients/{pid}/perry", json={"message": text, "history": _history(chat)}, timeout=600)
        _reply(chat, r, voice)
    except api.ApiError:
        msg = {"en": "I couldn't access that information right now. Please try again in a moment.",
               "hi": "मैं अभी यह जानकारी नहीं खोल पाया। कृपया थोड़ी देर बाद फिर कोशिश करें।",
               "hinglish": "Main abhi yeh jaankari access nahi kar paaya. Thodi der baad phir try kijiye."}[lang]
        chat.append({"role": "perry", "content": msg, "state": "error", "language": lang})
    st.rerun()


def _voice_settings(chat: list[dict]):
    with st.popover("🎙️ Voice", width="stretch"):
        engines = list(ENGINES)
        engine = st.radio("Speech recognition", engines, format_func=ENGINES.get, key="perry_voice_engine_w",
                          index=engines.index(st.session_state.get("perry_voice_engine", "device")))
        if engine != st.session_state.get("perry_voice_engine"):
            st.session_state["perry_voice_engine"] = engine
            st.rerun()
        if st.session_state.get("perry_voice_engine") == "browser":
            st.caption("⚠️ Your browser sends the recording to its speech service (Google in Chrome, Microsoft in Edge).")
            last = next((m.get("language") for m in reversed(chat) if m["role"] == "perry" and m.get("language")), "en")
            default = next((k for k, v in RECOGNITION_LANGS.items() if v == SPEECH_LANG.get(last)), "English")
            labels = list(RECOGNITION_LANGS)
            current = st.session_state.get("perry_voice_lang", default)
            st.session_state["perry_voice_lang"] = st.selectbox("Language you will speak", labels, key="perry_voice_lang_w",
                                                                index=labels.index(current) if current in labels else 0)
        else:
            st.caption("🔒 Recordings are transcribed on this device by Whisper and never leave it.")
        st.session_state["perry_autospeak"] = st.toggle("Read answers to voice questions aloud", key="perry_autospeak_w",
                                                        value=st.session_state.get("perry_autospeak", True))
        _voice_picker()
        c_hear, c_stop = st.columns(2)
        with c_hear:
            if st.button("▶ Hear PERRY", key="perry-preview", width="stretch"):
                st.session_state["perry_preview"] = True
        with c_stop:
            if st.button("⏹ Stop speaking", key="perry-stop", width="stretch"):
                stop_speaking()


def _voice_picker():
    st.markdown("**PERRY's voice**")
    voices = st.session_state.get("perry_voices", [])
    online = st.toggle("Natural online voices (best Indian accent)", key="perry_online_w",
                       value=st.session_state.get("perry_online", True),
                       help="Edge and Chrome speak these through Microsoft or Google, so the answer text is sent to them.")
    st.session_state["perry_online"] = online
    ranked = rank_voices(voices, "en", online)
    if not voices:
        st.caption("Checking which voices this browser has…")
        return
    names = ["auto"] + [v["name"] for v in ranked]
    current = st.session_state.get("perry_voice_name", "auto")
    choice = st.selectbox("English & Hinglish voice", names, key="perry_voice_name_w",
                          index=names.index(current) if current in names else 0,
                          format_func=lambda n: f"Auto · {voice_label(ranked[0])}" if n == "auto" and ranked else
                          ("Auto" if n == "auto" else voice_label(next(v for v in ranked if v["name"] == n))))
    st.session_state["perry_voice_name"] = choice
    if not has_indian_voice(voices, online):
        st.caption("No Indian-accent voice found here. Use Microsoft Edge (natural Indian voices built in), or on Windows add one: "
                   "Settings → Time & language → Speech → Add voices → English (India) and Hindi.")
    st.session_state["perry_rate"] = st.slider("Speed", 0.7, 1.3, st.session_state.get("perry_rate", 0.95), 0.05, key="perry_rate_w")
    st.session_state["perry_pitch"] = st.slider("Pitch", 0.8, 1.2, st.session_state.get("perry_pitch", 1.0), 0.05, key="perry_pitch_w")


def _say(text: str, lang: str):
    voices = st.session_state.get("perry_voices", [])
    online = st.session_state.get("perry_online", True)
    preferred = st.session_state.get("perry_voice_name")
    preferred = preferred if preferred != "auto" and lang in ("en", "hinglish") else None
    speak(text, lang, voice_name=pick_voice(voices, lang, online, preferred), rate=st.session_state.get("perry_rate", 0.95),
          pitch=st.session_state.get("perry_pitch", 1.0), allow_online=online)


st.markdown(BASE_CSS + CSS, unsafe_allow_html=True)
patient = patient_sidebar()
if not patient:
    st.markdown(f'<div class="perry-hero">{mascot("idle", 170)}<div class="perry-name">PERRY</div>'
                f'<div class="perry-tag">Your ByteXL assistant</div>'
                f'<div class="perry-say">Create or pick a profile in the sidebar and I\'ll get to know your records.</div></div>',
                unsafe_allow_html=True)
    st.stop()

st.session_state["perry_voices"] = browser_voices() or st.session_state.get("perry_voices", [])
pid = patient["_id"]
chat = st.session_state.setdefault(_state_key(pid), [])
st.session_state.setdefault("perry_voice_engine", "device")
st.session_state.setdefault("perry_autospeak", True)
first = (patient.get("name") or "there").split()[0]
pending = "perry_pending" in st.session_state or "perry_pending_audio" in st.session_state
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

speak_index = st.session_state.pop("perry_speak", None)
if speak_index is not None and 0 <= speak_index < len(chat) and chat[speak_index]["role"] == "perry":
    _say(chat[speak_index]["content"], chat[speak_index].get("language") or "en")
if st.session_state.pop("perry_preview", False):
    last = next((m.get("language") for m in reversed(chat) if m["role"] == "perry" and m.get("language")), "en")
    _say(SAMPLE["hi" if last == "hi" else "en"], "hi" if last == "hi" else "en")

st.markdown('<div class="perry-qa-label">Quick actions</div>', unsafe_allow_html=True)
cols = st.columns(3)
for n, (label, prompt) in enumerate(QUICK_ACTIONS):
    with cols[n % 3]:
        if st.button(label, key=f"qa-{n}", width="stretch"):
            _ask(pid, prompt)
            st.rerun()

device_mode = st.session_state.get("perry_voice_engine", "device") == "device"
if not device_mode:
    heard = browser_mic(RECOGNITION_LANGS.get(st.session_state.get("perry_voice_lang", "English"), "en-IN"), key="perry-mic")
    if heard and heard.get("text") and heard.get("nonce") != st.session_state.get("perry_mic_nonce"):
        st.session_state["perry_mic_nonce"] = heard.get("nonce")
        _ask(pid, heard["text"], voice=True)
        st.rerun()

c_langs, c_voice = st.columns([4, 1], vertical_alignment="center")
with c_langs:
    st.markdown(f'<div class="perry-langs">🌐 {LANGUAGE_STRIP}</div>', unsafe_allow_html=True)
with c_voice:
    _voice_settings(chat)
st.markdown('<div class="perry-foot">PERRY explains what is in your records. It is not a doctor and never changes your medicines.</div>',
            unsafe_allow_html=True)

placeholder = "Ask PERRY anything — type, or tap the mic to speak" if device_mode else "Ask PERRY anything about your records — in your language"
value = st.chat_input(placeholder, accept_audio=device_mode)
if value:
    text = value if isinstance(value, str) else (value.text or "")
    audio = None if isinstance(value, str) else getattr(value, "audio", None)
    if audio is not None:
        _ask_audio(pid, audio.getvalue())
        st.rerun()
    elif text.strip():
        _ask(pid, text)
        st.rerun()
