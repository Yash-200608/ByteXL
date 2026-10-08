import pytest

from app.store.json_store import JsonFileRepository


def test_health_ok(client, fake_llm):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["store"]["backend"] == "json"
    assert body["store"]["ok"] is True
    assert body["ollama"]["reachable"] is True
    assert body["models"]["text_available"] is True


def test_health_reports_ollama_down(client, fake_llm):
    fake_llm.up = False
    body = client.get("/health").json()
    assert body["ollama"]["reachable"] is False
    assert body["models"]["vision_available"] is False


def _exercise(repo):
    repo.insert("patients", {"_id": "p1", "name": "A", "sex": "male"})
    repo.insert("patients", {"_id": "p2", "name": "B", "sex": "female"})
    assert repo.get("patients", "p1")["name"] == "A"
    assert repo.get("patients", "missing") is None
    repo.update("patients", "p1", {"name": "AA"})
    assert repo.get("patients", "p1")["name"] == "AA"
    assert [d["_id"] for d in repo.find("patients", {"sex": "female"})] == ["p2"]
    assert len(repo.find("patients", {"_id": {"$in": ["p1", "p2"]}})) == 2
    repo.replace("patients", {"_id": "p2", "name": "BB", "sex": "female"})
    assert repo.get("patients", "p2")["name"] == "BB"
    assert repo.delete_many("patients", {"sex": "male"}) == 1
    assert repo.ping()


def test_json_store(tmp_path):
    _exercise(JsonFileRepository(tmp_path))


def test_json_store_duplicate(tmp_path):
    r = JsonFileRepository(tmp_path)
    r.insert("documents", {"_id": "d1"})
    with pytest.raises(KeyError):
        r.insert("documents", {"_id": "d1"})


def test_mongo_store_or_fallback(settings_tmp, monkeypatch):
    from app.store import build_repository

    try:
        from app.store.mongo_store import MongoRepository

        r = MongoRepository(settings_tmp.mongo_uri, "bytexl_test", 800)
    except Exception:
        monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:1")
        assert build_repository("auto").backend == "json"
        pytest.skip("MongoDB not running; fallback verified")
    r.client.drop_database("bytexl_test")
    _exercise(r)
    r.client.drop_database("bytexl_test")


def test_auto_falls_back_to_json(settings_tmp, monkeypatch):
    from app.config import get_settings
    from app.store import build_repository

    get_settings.cache_clear()
    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:1")
    monkeypatch.setenv("MONGO_TIMEOUT_MS", "200")
    assert build_repository("auto").backend == "json"
    get_settings.cache_clear()
