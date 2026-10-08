from datetime import datetime

import streamlit as st


def chat_key(pid: str) -> str:
    return f"perry_chat_{pid}"


def chat(pid: str) -> list[dict]:
    return st.session_state.setdefault(chat_key(pid), [])


def now() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


def ask(pid: str, text: str, voice: bool = False) -> None:
    text = (text or "").strip()[:1000]
    if not text:
        return
    chat(pid).append({"role": "user", "content": text, "voice": voice, "time": now()})
    st.session_state["perry_pending"] = text
    st.session_state["perry_pending_voice"] = voice


def ask_audio(pid: str, audio: bytes) -> None:
    chat(pid).append({"role": "user", "content": "…", "voice": True, "time": now()})
    st.session_state["perry_pending_audio"] = audio


def pending() -> bool:
    return "perry_pending" in st.session_state or "perry_pending_audio" in st.session_state
