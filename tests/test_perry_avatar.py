from html import escape

import pytest

from tests.conftest import ROOT

UI = ROOT / "ui"


@pytest.fixture
def ui_path(monkeypatch):
    monkeypatch.syspath_prepend(str(UI))


def test_state_machine_allows_the_designed_flow(ui_path):
    from perry_state import TRANSITIONS, can_move

    for a, b in [("idle", "listening"), ("listening", "thinking"), ("thinking", "searching"), ("searching", "explaining"),
                 ("explaining", "thinking"), ("searching", "speaking"), ("idle", "celebrating"), ("explaining", "idle")]:
        assert can_move(a, b), (a, b)
    for a, b in [("idle", "searching"), ("idle", "explaining"), ("listening", "speaking"), ("error", "thinking")]:
        assert not can_move(a, b), (a, b)
    assert all(can_move(s, "error") for s in TRANSITIONS)


def test_avatar_renders_every_state_with_its_art(ui_path):
    from perry_mascot import BUBBLE, STATES, avatar_css, bubble, perry_avatar, state_cards

    for s in STATES:
        html = perry_avatar(s, live=True)
        assert f'data-state="{s}"' in html and "perry_idle.png" in html and "pv-platform" in html
        cards = state_cards(s)
        assert cards.count('class="pv-card slot') == 3 and f"state_{s}.png" in cards
        assert cards.count(" on\"") == 1
        assert escape(BUBBLE[s]) in bubble(s)
    assert perry_avatar("nonsense").count('data-state="idle"') == 1
    css = avatar_css()
    assert "body.perry-speaking" in css and 'aria-label="Stop recording"' in css


def test_avatar_assets_exist(ui_path):
    from perry_mascot import STATES

    for n in ["perry_idle.png", "perry_head.png", "perry_lounge.png"] + [f"state_{s}.png" for s in STATES]:
        assert (UI / "static" / "perry" / n).is_file(), n
