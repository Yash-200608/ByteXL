from typing import Literal

import streamlit as st

from perry_mascot import HOLO, bubble, perry_avatar, state_cards

AvatarState = Literal["idle", "listening", "thinking", "searching", "speaking", "explaining", "celebrating", "error"]
KEY = "perry_state"
TRANSITIONS: dict[str, set[str]] = {
    "idle": {"listening", "thinking", "celebrating"},
    "listening": {"thinking", "idle"},
    "thinking": {"searching", "idle"},
    "searching": {"speaking", "explaining", "idle"},
    "speaking": {"idle", "explaining"},
    "explaining": {"idle", "listening", "thinking", "speaking", "celebrating"},
    "celebrating": {"idle", "listening", "thinking"},
    "error": {"idle"},
}


def get_state() -> str:
    return st.session_state.get(KEY, "idle")


def can_move(current: str, new: str) -> bool:
    return new == "error" or new == current or new in TRANSITIONS.get(current, set())


def set_state(new: str) -> bool:
    current = get_state()
    if not can_move(current, new):
        return False
    st.session_state[KEY] = new
    return True


def go(*path: str) -> str:
    for state in path:
        if not set_state(state) and get_state() != state:
            set_state("idle")
            set_state(state)
    return get_state()


def stage_html(state: str | None = None, size: int = 430) -> str:
    state = state or get_state()
    return (f'<div class="pv-stage">{" ".join(HOLO.split())}{bubble(state, live=True)}{perry_avatar(state, size, uid="live", live=True)}'
            f'{state_cards(state)}</div>')


def render(slot, state: str | None = None) -> None:
    slot.markdown(stage_html(state), unsafe_allow_html=True)
