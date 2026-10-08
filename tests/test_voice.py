import io
import json
import sys
import wave
from types import SimpleNamespace

import pytest

from app.agent import speech
from app.agent.language import LANGUAGES
from tests.conftest import ROOT
from tests.test_perry import world


def wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeWhisper:
    def __init__(self, text: str, language: str = "en"):
        self.text, self.language, self.calls = text, language, 0

    def transcribe(self, audio, vad_filter=True, beam_size=1, initial_prompt=None):
        self.prompt = initial_prompt
        self.calls += 1
        segments = [SimpleNamespace(text=" " + part) for part in self.text.split("|") if part]
        return iter(segments), SimpleNamespace(language=self.language, language_probability=0.97)


@pytest.fixture
def heard():
    def set_text(text, language="en"):
        model = FakeWhisper(text, language)
        speech.set_model(model)
        return model

    yield set_text
    speech.set_model(None)


def _voice(world, text_or_bytes=None, pid=None, history="[]", name="q.wav", mime="audio/wav"):
    data = text_or_bytes if isinstance(text_or_bytes, bytes) else wav()
    return world["client"].post(f"/patients/{pid or world['a']}/perry/voice",
                                files={"audio": (name, data, mime)}, data={"history": history})


def test_voice_question_answered_from_records(world, heard):
    model = heard("What was my latest|HbA1c?")
    r = _voice(world)
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "What was my latest HbA1c?" and body["heard_language"] == "en"
    assert body["tools"] == ["get_my_labs"] and "6.6%" in body["reply"] and model.calls == 1


@pytest.mark.parametrize("text, lang, code", [
    ("मेरी दवाइयां दिखाओ", "hi", "hi"),
    ("Meri latest HbA1c kya hai?", "hi", "hinglish"),
])
def test_voice_hindi_and_hinglish(world, heard, text, lang, code):
    heard(text, lang)
    body = _voice(world).json()
    assert body["language"] == code and body["state"] == "ok"


def test_voice_is_scoped_to_the_current_user(world, heard):
    heard("What medicines are in my records?")
    body = _voice(world, pid=world["b"]).json()
    assert "Tab Montair LC" in body["reply"] and "Glycomet" not in body["reply"]


def test_voice_treatment_question_gets_safety_reply(world, heard):
    heard("Should I stop taking Glycomet?")
    body = _voice(world).json()
    assert body["intent"] == "treatment" and "can't make that decision" in body["reply"] and "BD PC x 1 month" in body["reply"]


def test_voice_history_is_used_and_validated(world, heard):
    heard("What was my latest HbA1c?")
    ok = _voice(world, history=json.dumps([{"role": "user", "content": "hello"}, {"role": "perry", "content": "Hi!"}]))
    assert ok.status_code == 200
    assert _voice(world, history="not json").status_code == 422
    assert _voice(world, history=json.dumps([{"role": "system", "content": "x"}])).status_code == 422


def test_no_speech(world, heard):
    heard("")
    body = _voice(world).json()
    assert body["state"] == "no_speech" and body["transcript"] == "" and body["tools"] == []


def test_speech_engine_missing_returns_503(world, monkeypatch):
    def missing():
        raise speech.SpeechUnavailable("Local speech recognition is not installed (pip install faster-whisper).")

    monkeypatch.setattr(speech, "get_model", missing)
    r = _voice(world)
    assert r.status_code == 503 and "Voice isn't set up" in r.json()["detail"]


def test_voice_rejects_bad_uploads(world, heard):
    heard("What was my latest HbA1c?")
    assert _voice(world, b"ID3not a wav file at all", name="q.mp3", mime="audio/mpeg").status_code == 415
    assert _voice(world, b"RIFF" + b"\x00" * (10 * 1024 * 1024 + 10)).status_code == 413
    assert _voice(world, wav(seconds=61)).status_code == 413
    assert _voice(world, pid="pat_doesnotexist").status_code == 404


def test_wav_seconds():
    assert speech.wav_seconds(wav(2.5)) == pytest.approx(2.5)
    assert speech.wav_seconds(b"RIFF....WAVEjunk") is None


@pytest.fixture
def voice_ui(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "ui"))
    sys.modules.pop("perry_voice", None)
    import perry_voice

    yield perry_voice
    sys.modules.pop("perry_voice", None)


def test_clean_for_speech(voice_ui):
    md = ("Your latest **HbA1c** was **6.6%** (high), according to your lab report dated 20 Sep 2024.\n"
          "- 💊 **Tab Glycomet 500** (metformin) — BD PC x 1 month · _prescription, 22 Sep 2024_\n"
          "- **Prescription** · 22 Sep 2024 · prescription_handwritten_2024_09.png · ⏳ 10\n"
          "> ⚠️ Metformin appears on 2 of your documents\n\n"
          "_(I couldn't answer in Kannada right now, so here it is in English.)_")
    out = voice_ui.clean_for_speech(md)
    assert "**" not in out and "💊" not in out and "⚠" not in out and "⏳" not in out and ".png" not in out
    assert "couldn't answer in Kannada" not in out
    assert "H b A 1 c was 6.6 percent" in out and "Tablet Glycomet 500 (metformin), B D P C for 1 month" in out
    assert "20 September 2024" in out and "Metformin appears" in out
    assert len(voice_ui.clean_for_speech("word. " * 1000)) <= voice_ui.MAX_SPEECH_CHARS


def test_speech_languages_cover_perry_languages(voice_ui):
    assert set(LANGUAGES) | {"en", "hinglish"} <= set(voice_ui.SPEECH_LANG)
    assert set(voice_ui.RECOGNITION_LANGS.values()) <= set(voice_ui.SPEECH_LANG.values())


def test_pronunciation(voice_ui):
    out = voice_ui.clean_for_speech("Sodium 132 mmol/L, TSH 5.8 µIU/mL, sugar 118 mg/dL · Tab Ecosprin 75 — 0-1-0 PC x 6 wks (as of 2024-09-22)")
    assert "132 millimoles per litre" in out and "5.8 micro international units per millilitre" in out
    assert "118 milligrams per decilitre" in out and "Tablet Ecosprin 75" in out and "0, 1, 0" in out
    assert "P C for 6 weeks" in out and "22 September 2024" in out


VOICES = [
    {"name": "Microsoft David - English (United States)", "lang": "en-US", "local": True, "default": True},
    {"name": "Microsoft Heera - English (India)", "lang": "en-IN", "local": True, "default": False},
    {"name": "Microsoft Neerja Online (Natural) - English (India)", "lang": "en-IN", "local": False, "default": False},
    {"name": "Google UK English Female", "lang": "en-GB", "local": False, "default": False},
    {"name": "Microsoft Swara Online (Natural) - Hindi (India)", "lang": "hi-IN", "local": False, "default": False},
    {"name": "Microsoft Kalpana - Hindi (India)", "lang": "hi_IN", "local": True, "default": False},
]


def test_indian_voices_ranked_first(voice_ui):
    assert voice_ui.pick_voice(VOICES, "en") == "Microsoft Neerja Online (Natural) - English (India)"
    assert voice_ui.pick_voice(VOICES, "hinglish") == "Microsoft Neerja Online (Natural) - English (India)"
    assert voice_ui.pick_voice(VOICES, "en", allow_online=False) == "Microsoft Heera - English (India)"
    assert voice_ui.pick_voice(VOICES, "hi") == "Microsoft Swara Online (Natural) - Hindi (India)"
    assert voice_ui.pick_voice(VOICES, "hi", allow_online=False) == "Microsoft Kalpana - Hindi (India)"
    assert voice_ui.pick_voice(VOICES, "ta") is None
    assert voice_ui.pick_voice(VOICES, "en", preferred="Google UK English Female") == "Google UK English Female"
    assert voice_ui.pick_voice(VOICES, "hi", preferred="Google UK English Female") == "Microsoft Swara Online (Natural) - Hindi (India)"
    us_only = [VOICES[0]]
    assert voice_ui.pick_voice(us_only, "en") == VOICES[0]["name"] and not voice_ui.has_indian_voice(us_only)
    assert voice_ui.has_indian_voice(VOICES, allow_online=False)


def test_correct_terms_uses_only_known_vocabulary():
    vocab = ["Dolo", "Glycomet", "Rosuvas", "rosuvastatin", "Thyronorm", "Ecosprin", "HbA1c"]
    assert speech.correct_terms("When should I take thyronorm and raziovas?", vocab) == (
        "When should I take thyronorm and Rosuvas?", [{"heard": "raziovas", "corrected": "Rosuvas"}])
    for sentence in ["Should I stop taking my sugar tablets?", "Show my latest records please", "What about Paracetamol?"]:
        assert speech.correct_terms(sentence, vocab) == (sentence, [])
    assert speech.correct_terms("raziovas", []) == ("raziovas", [])


def test_vocabulary_prompt_puts_user_terms_first():
    p = speech.vocabulary_prompt(["Rosuvas", "Thyronorm", "HbA1c"])
    assert p.index("Rosuvas") < p.index("Tests:") and p.count("Rosuvas") == 1


def test_voice_route_corrects_with_users_own_medicines(world, heard):
    model = heard("When should I take|raziovas?")
    body = _voice(world).json()
    assert body["transcript"] == "When should I take Rosuvas?" and body["heard_raw"] == "When should I take raziovas?"
    assert body["corrections"] == [{"heard": "raziovas", "corrected": "Rosuvas"}]
    assert "Rosuvas" in model.prompt
    other = heard("When should I take|raziovas?")
    body_b = _voice(world, pid=world["b"]).json()
    assert body_b["corrections"] == [] and "Rosuvas" not in other.prompt
