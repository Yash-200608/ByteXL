import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
os.environ.setdefault("STORE_BACKEND", "json")


class FakeLLM:
    def __init__(self, responses=None, up=True, models=None):
        self.responses = list(responses or [])
        self.up = up
        self._models = models if models is not None else ["qwen2.5vl:3b", "qwen2.5vl:7b", "qwen2.5:7b"]
        self.calls = []
        self.handler = None

    def is_up(self):
        return self.up

    def models(self):
        return self._models if self.up else []

    def chat(self, model, messages, schema=None, num_predict=None):
        self.calls.append({"model": model, "messages": messages, "schema": schema})
        if self.handler is not None and not self.responses:
            return self.handler(model, messages, schema)
        if not self.responses:
            raise AssertionError("FakeLLM has no queued response")
        r = self.responses.pop(0)
        return r(messages) if callable(r) else r

    def structured(self, *args, **kwargs):
        from app.llm.client import OllamaClient

        return OllamaClient.structured(self, *args, **kwargs)


@pytest.fixture
def settings_tmp(tmp_path, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORE_BACKEND", "json")
    s = get_settings()
    yield s
    get_settings.cache_clear()


@pytest.fixture
def repo(settings_tmp):
    from app.store import set_repository
    from app.store.json_store import JsonFileRepository

    r = JsonFileRepository(settings_tmp.store_dir)
    set_repository(r)
    yield r
    set_repository(None)


@pytest.fixture
def fake_llm():
    from app.llm.client import set_llm

    llm = FakeLLM()
    llm.settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    set_llm(llm)
    yield llm
    set_llm(None)


@pytest.fixture
def client(repo, fake_llm):
    from fastapi.testclient import TestClient

    from app.api.main import app

    with TestClient(app) as c:
        yield c
