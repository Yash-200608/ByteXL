import logging
import threading

from app.config import get_settings
from app.store.base import Repository
from app.store.json_store import JsonFileRepository

log = logging.getLogger(__name__)
_repo: Repository | None = None
_lock = threading.Lock()


def build_repository(backend: str | None = None) -> Repository:
    s = get_settings()
    backend = backend or s.store_backend
    if backend in ("auto", "mongo"):
        try:
            from app.store.mongo_store import MongoRepository

            return MongoRepository(s.mongo_uri, s.mongo_db, s.mongo_timeout_ms)
        except Exception as exc:
            if backend == "mongo":
                raise
            log.warning("MongoDB unreachable (%s); using JSON-file store", exc)
    return JsonFileRepository(s.store_dir)


def get_repository() -> Repository:
    global _repo
    with _lock:
        if _repo is None:
            _repo = build_repository()
        return _repo


def set_repository(repo: Repository | None) -> None:
    global _repo
    with _lock:
        _repo = repo
