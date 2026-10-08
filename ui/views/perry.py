import html
import re

import streamlit as st

import api_client as api
from common import setup
from perry_chat import ask, ask_audio, chat, now, pending
from perry_mascot import perry_head
from perry_state import get_state, go, render
from perry_voice import (RECOGNITION_LANGS, SAMPLE, SPEECH_LANG, browser_mic, browser_voices, has_indian_voice, pick_voice,
                         rank_voices, speak, stop_speaking, voice_label)

QUICK_ACTIONS = [
    ("Latest Report", ":material/description:", "Explain my latest report"),
    ("My Medicines", ":material/medication:", "What medicines are in my records?"),
    ("My Timeline", ":material/timeline:", "Show me my timeline"),
    ("Recent Documents", ":material/folder_open:", "What documents did I upload recently?"),
    ("Pending Confirmations", ":material/warning:", "Do I have anything waiting for confirmation?"),
    ("Compare Reports", ":material/bar_chart:", "Compare my last two lab reports"),
]
LANGS = {
    "auto": "Auto (match me)", "en": "English", "hi": "हिंदी (Hindi)", "hinglish": "Hinglish", "bn": "বাংলা (Bengali)",
    "mr": "मराठी (Marathi)", "te": "తెలుగు (Telugu)", "ta": "தமிழ் (Tamil)", "gu": "ગુજરાતી (Gujarati)", "ur": "اردو (Urdu)",
    "kn": "ಕನ್ನಡ (Kannada)", "or": "ଓଡ଼ିଆ (Odia)", "ml": "മലയാളം (Malayalam)", "pa": "ਪੰਜਾਬੀ (Punjabi)",
}
BADGE = {k: v.split(" (")[0] for k, v in LANGS.items() if k not in ("auto", "en")}
ENGINES = {"device": "On this device (private)", "browser": "Browser (sends audio to Google/Microsoft)"}
FLAG_CLASS = {
    "high": "v-high", "low": "v-low", "within range": "v-normal", "normal": "v-normal", "far outside range": "v-far",
    "अधिक": "v-high", "कम": "v-low", "सामान्य सीमा में": "v-normal", "सीमा से बहुत बाहर": "v-far",
    "normal range mein": "v-normal", "range se kaafi bahar": "v-far",
}
FLAG_RE = re.compile("|".join(sorted((re.escape(k) for k in FLAG_CLASS), key=len, reverse=True)))
THINKING_COPY = {"en": "Got it. Let me check your records", "hi": "ठीक है, मैं आपके रिकॉर्ड देख रहा हूं",
                 "hinglish": "Theek hai, main aapke records dekh raha hoon"}
ERROR_COPY = "Something went wrong while I was checking your records. Let's try that again."


def decorate(markdown: str) -> str:
    safe = html.escape(markdown or "", quote=False)

    def chips(group: re.Match) -> str:
        inner = FLAG_RE.sub(lambda m: f'<span class="vchip {FLAG_CLASS[m.group(0)]}">{m.group(0)}</span>', group.group(1))
        return f"({inner})"

    return re.sub(r"\(([^()\n]{1,60})\)", chips, safe)


def _lang_guess(text: str) -> str:
    if any("ऀ" <= c <= "ॿ" for c in text):
        return "hi"
    return "hinglish" if re.search(r"\b(meri|mera|mere|kya|hai|dikhao|batao|samjhao|dawai)\b", text, re.I) else "en"


def _history(msgs: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"][:2000]} for m in msgs[:-1] if m["content"] != "…"][-12:]


def _language_code() -> str | None:
    code = st.session_state.get("perry_lang", "auto")
    return None if code == "auto" else code


def _render_user(i: int, m: dict):
    with st.container(key=f"pmsg-user-{i}"):
        body = ("🎙️ " if m.get("voice") else "") + html.escape(m["content"], quote=False)
        st.markdown(body)
        if m.get("corrections"):
            st.caption("Matched to your records: " + ", ".join(f"“{c['heard']}” → {c['corrected']}" for c in m["corrections"]))
        st.markdown(f'<div class="p-time">{m.get("time", "")} ✓✓</div>', unsafe_allow_html=True)


def _render_perry(pid: str, i: int, m: dict, msgs: list[dict]):
    error = m.get("state") == "error"
    rtl = m.get("language") == "ur"
    key = f"pmsg-perry{'-error' if error else ''}{'-rtl' if rtl else ''}-{i}"
    with st.container(key=key):
        badge = f'<span class="p-lang">🌐 {BADGE[m["language"]]}</span>' if m.get("language") in BADGE else ""
        st.markdown(f'<div style="font-weight:800;letter-spacing:.06em;font-size:.8rem;opacity:.85">PERRY{badge}</div>',
                    unsafe_allow_html=True)
        st.markdown(decorate(m["content"]), unsafe_allow_html=True)
        st.markdown(f'<div class="p-time">{m.get("time", "")}</div>', unsafe_allow_html=True)
    if error:
        return
    sources = [s for s in m.get("sources") or [] if s.get("filename")]
    if sources:
        st.markdown('<div class="p-checked">✓ PERRY checked these records</div>', unsafe_allow_html=True)
    cols = st.columns([5, 0.55, 0.55, 0.55], vertical_alignment="center")
    with cols[0]:
        for j, s in enumerate(sources[:4]):
            label = f"📄 {s['filename']}\n{s.get('title') or 'Document'} • {s.get('date_text') or '—'}"
            if st.button(label, key=f"src-{i}-{j}", width="stretch", disabled=not s.get("document_id"),
                         help="Open this record in My Reports"):
                st.session_state["doc_id"] = s["document_id"]
                st.switch_page("views/document.py")
    for col, (rating, icon) in zip(cols[1:3], (("up", "👍"), ("down", "👎"))):
        with col:
            if st.button(icon, key=f"fb-{rating}-{i}", help="Helpful" if rating == "up" else "Not helpful"):
                question = next((x["content"] for x in reversed(msgs[:i]) if x["role"] == "user"), None)
                try:
                    api.post(f"/patients/{pid}/perry/feedback", json={"rating": rating, "reply": m["content"][:4000],
                                                                       "question": question, "language": m.get("language")})
                    st.toast("Thanks — PERRY noted your feedback.")
                except api.ApiError:
                    st.toast("Couldn't save feedback right now.")
    with cols[3]:
        if st.button("🔊", key=f"say-{i}", help="Read this answer aloud"):
            st.session_state["perry_speak"] = i


def _thinking(text: str):
    with st.container(key="pmsg-perry-thinking"):
        st.markdown(f'<div class="p-thinking">{perry_head(38, uid="think", state="thinking")}<span>{text}</span>'
                    f'<span class="p-dots"><span></span><span></span><span></span></span></div>', unsafe_allow_html=True)


def _reply(msgs: list[dict], r: dict, voice: bool):
    state = "error" if r.get("state") in ("error", "no_speech") else r.get("state", "ok")
    msgs.append({"role": "perry", "content": r["reply"], "sources": r.get("sources", []), "language": r.get("language"),
                 "state": state, "time": now(), "tools": r.get("tools", [])})
    if voice and st.session_state.get("perry_autospeak", True) and state != "error":
        st.session_state["perry_speak"] = len(msgs) - 1


def _fail(msgs: list[dict], text: str = ERROR_COPY):
    msgs.append({"role": "perry", "content": text, "state": "error", "language": "en", "time": now()})
    go("error")


def answer_pending(pid: str, slot):
    msgs = chat(pid)
    voice = False
    if "perry_pending_audio" in st.session_state:
        audio = st.session_state.pop("perry_pending_audio")
        go("listening", "thinking")
        render(slot)
        _thinking("Listening back to what you said")
        try:
            heard = api.post(f"/patients/{pid}/perry/transcribe", files={"audio": ("question.wav", audio, "audio/wav")}, timeout=600)
        except api.ApiError as exc:
            msgs[-1]["content"] = "(voice message)"
            _fail(msgs, f"{exc} You can type your question, or switch to browser recognition under Speak with PERRY."
                  if "Voice isn't set up" in str(exc) else "I couldn't process that recording. Please try again or type your question.")
            st.rerun()
        if heard.get("state") == "no_speech":
            msgs[-1]["content"] = "(nothing heard)"
            _fail(msgs, heard.get("message") or "I couldn't hear that clearly. Please try again.")
            st.rerun()
        msgs[-1]["content"] = heard["transcript"]
        msgs[-1]["corrections"] = heard.get("corrections") or []
        text, voice = heard["transcript"], True
    else:
        text = st.session_state.pop("perry_pending")
        voice = st.session_state.pop("perry_pending_voice", False)
        go("thinking")
        render(slot)
        _thinking(THINKING_COPY[_lang_guess(text)])
    go("searching")
    render(slot)
    try:
        r = api.post(f"/patients/{pid}/perry", json={"message": text, "history": _history(msgs), "language": _language_code()}, timeout=600)
        _reply(msgs, r, voice)
        go("error" if msgs[-1]["state"] == "error" else "explaining")
    except api.ApiError:
        _fail(msgs)
    st.rerun()


def say(text: str, lang: str):
    voices = st.session_state.get("perry_voices", [])
    online = st.session_state.get("perry_online", True)
    preferred = st.session_state.get("perry_voice_name")
    preferred = preferred if preferred != "auto" and lang in ("en", "hinglish") else None
    speak(text, lang, voice_name=pick_voice(voices, lang, online, preferred), rate=st.session_state.get("perry_rate", 0.95),
          pitch=st.session_state.get("perry_pitch", 1.0), allow_online=online)


def voice_picker():
    st.markdown("**PERRY's voice**")
    voices = st.session_state.get("perry_voices", [])
    online = st.toggle("Natural online voices (best Indian accent)", key="perry_online_w", value=st.session_state.get("perry_online", True),
                       help="Edge and Chrome speak these through Microsoft or Google, so the answer text is sent to them.")
    st.session_state["perry_online"] = online
    if not voices:
        st.caption("Checking which voices this browser has…")
        return
    ranked = rank_voices(voices, "en", online)
    names = ["auto"] + [v["name"] for v in ranked]
    current = st.session_state.get("perry_voice_name", "auto")
    choice = st.selectbox("English & Hinglish voice", names, key="perry_voice_name_w", index=names.index(current) if current in names else 0,
                          format_func=lambda n: (f"Auto · {voice_label(ranked[0])}" if ranked else "Auto") if n == "auto"
                          else voice_label(next(v for v in ranked if v["name"] == n)))
    st.session_state["perry_voice_name"] = choice
    if not has_indian_voice(voices, online):
        st.caption("No Indian-accent voice found here. Use Microsoft Edge (natural Indian voices built in), or on Windows add one: "
                   "Settings → Time & language → Speech → Add voices → English (India) and Hindi.")
    st.session_state["perry_rate"] = st.slider("Speed", 0.7, 1.3, st.session_state.get("perry_rate", 0.95), 0.05, key="perry_rate_w")
    st.session_state["perry_pitch"] = st.slider("Pitch", 0.8, 1.2, st.session_state.get("perry_pitch", 1.0), 0.05, key="perry_pitch_w")


def voice_menu(msgs: list[dict]):
    with st.container(key="p-speak"):
        with st.popover("Speak with PERRY", icon=":material/graphic_eq:", width="content"):
            engines = list(ENGINES)
            engine = st.radio("Speech recognition", engines, format_func=ENGINES.get, key="perry_voice_engine_w",
                              index=engines.index(st.session_state.get("perry_voice_engine", "device")))
            if engine != st.session_state.get("perry_voice_engine"):
                st.session_state["perry_voice_engine"] = engine
                st.rerun()
            if engine == "browser":
                st.caption("⚠️ Your browser sends the recording to its speech service (Google in Chrome, Microsoft in Edge).")
                last = _language_code() or next((m.get("language") for m in reversed(msgs) if m["role"] == "perry" and m.get("language")), "en")
                default = next((k for k, v in RECOGNITION_LANGS.items() if v == SPEECH_LANG.get(last)), "English")
                labels = list(RECOGNITION_LANGS)
                current = st.session_state.get("perry_voice_lang", default)
                st.session_state["perry_voice_lang"] = st.selectbox("Language you will speak", labels, key="perry_voice_lang_w",
                                                                    index=labels.index(current) if current in labels else 0)
            else:
                st.caption("🔒 Tap the mic in the message box. Recordings are transcribed on this device by Whisper and never leave it.")
            st.session_state["perry_autospeak"] = st.toggle("Read answers to voice questions aloud", key="perry_autospeak_w",
                                                            value=st.session_state.get("perry_autospeak", True))
            voice_picker()
            c_hear, c_stop = st.columns(2)
            with c_hear:
                if st.button("▶ Hear PERRY", key="perry-preview", width="stretch"):
                    st.session_state["perry_preview"] = True
            with c_stop:
                if st.button("⏹ Stop speaking", key="perry-stop", width="stretch"):
                    stop_speaking()


def language_menu(msgs: list[dict]):
    last = next((m.get("language") for m in reversed(msgs) if m["role"] == "perry" and m.get("language")), None)
    codes = list(LANGS)
    current = st.session_state.get("perry_lang", "auto")

    def label(code: str) -> str:
        if code == "auto" and last and last in LANGS and last != "auto":
            return f"🌐 Auto · {LANGS[last].split(' (')[0]}"
        return f"🌐 {LANGS[code]}"

    with st.container(key="p-lang"):
        st.session_state["perry_lang"] = st.selectbox("Reply language", codes, index=codes.index(current), key="perry_lang_w",
                                                      format_func=label, label_visibility="collapsed", width=230)


def upload_attachment(pid: str, f, msgs: list[dict]):
    msgs.append({"role": "user", "content": f"📎 {f.name}", "time": now()})
    try:
        api.post(f"/patients/{pid}/documents", files={"file": (f.name, f.getvalue(), f.type or "application/octet-stream")}, timeout=120)
        msgs.append({"role": "perry", "content": f"Got it — I'm reading **{f.name}** now. It'll appear in **My Reports** shortly, "
                     "and then you can ask me about it.", "language": "en", "state": "ok", "time": now()})
        go("celebrating")
    except api.ApiError as exc:
        msgs.append({"role": "perry", "content": f"I couldn't upload that file: {exc}", "language": "en", "state": "error", "time": now()})


patient = setup()
if not patient:
    st.stop()
pid = patient["_id"]
msgs = chat(pid)
st.session_state.setdefault("perry_voice_engine", "device")
st.session_state.setdefault("perry_autospeak", True)
st.session_state["perry_voices"] = browser_voices() or st.session_state.get("perry_voices", [])
if not pending() and get_state() in ("thinking", "searching", "listening", "speaking"):
    go("idle")

left, right = st.columns([1.55, 1], gap="large")
with right:
    with st.container(key="perry-stage"):
        slot = st.empty()
        render(slot)

with left:
    with st.container(key="perry-panel"):
        docs = []
        try:
            docs = api.get(f"/patients/{pid}/documents")
        except api.ApiError:
            pass
        extra = ("" if docs else "<br><b>PERRY is ready.</b> Upload your first health record under <b>Documents</b> "
                 "(or tap 📎 below) and I'll help you understand it.")
        st.markdown(f'<div class="p-welcome"><div class="face">{perry_head(84, uid="welcome")}</div><div class="say">'
                    f'<b>Hey there! 👋</b><br>I\'m <b>PERRY</b> — your personal health assistant.<br>'
                    f'Ask me anything about your reports, medicines, or health records. I can also speak in your language!{extra}</div></div>',
                    unsafe_allow_html=True)
        st.write("")
        with st.container(horizontal=True, wrap=True, gap="small", key="qa-row"):
            for n, (label, icon, prompt) in enumerate(QUICK_ACTIONS):
                if st.button(label, key=f"qa-{n}", icon=icon, width="content"):
                    ask(pid, prompt)
                    st.rerun()

        for i, m in enumerate(msgs):
            if m["role"] == "user":
                _render_user(i, m)
            else:
                _render_perry(pid, i, m, msgs)

        if pending():
            answer_pending(pid, slot)

        speak_index = st.session_state.pop("perry_speak", None)
        if speak_index is not None and 0 <= speak_index < len(msgs) and msgs[speak_index]["role"] == "perry":
            say(msgs[speak_index]["content"], msgs[speak_index].get("language") or "en")
        if st.session_state.pop("perry_preview", False):
            last = next((m.get("language") for m in reversed(msgs) if m["role"] == "perry" and m.get("language")), "en")
            say(SAMPLE["hi" if last == "hi" else "en"], "hi" if last == "hi" else "en")

        device_mode = st.session_state.get("perry_voice_engine", "device") == "device"
        if not device_mode:
            heard = browser_mic(RECOGNITION_LANGS.get(st.session_state.get("perry_voice_lang", "English"), "en-IN"), key="perry-mic")
            if heard and heard.get("text") and heard.get("nonce") != st.session_state.get("perry_mic_nonce"):
                st.session_state["perry_mic_nonce"] = heard.get("nonce")
                ask(pid, heard["text"], voice=True)
                st.rerun()

        value = st.chat_input("Ask PERRY anything about your health...", accept_audio=device_mode, accept_file=True,
                              file_type=["pdf", "png", "jpg", "jpeg"], key="perry-composer")
        if value:
            text = value if isinstance(value, str) else (value.text or "")
            audio = None if isinstance(value, str) else getattr(value, "audio", None)
            files = [] if isinstance(value, str) else list(getattr(value, "files", []) or [])
            for f in files:
                upload_attachment(pid, f, msgs)
            if audio is not None:
                ask_audio(pid, audio.getvalue())
            elif text.strip():
                ask(pid, text)
            st.rerun()

        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", key="p-controls"):
            language_menu(msgs)
            voice_menu(msgs)
        if msgs:
            if st.button("New chat", key="perry-reset", icon=":material/restart_alt:"):
                st.session_state[f"perry_chat_{pid}"] = []
                go("idle")
                st.rerun()
    st.markdown('<div style="text-align:center;font-size:.75rem;opacity:.55;margin-top:8px">PERRY explains what is in your records. '
                "It is not a doctor and never changes your medicines.</div>", unsafe_allow_html=True)
