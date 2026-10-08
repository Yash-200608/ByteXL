import json
import threading
from pathlib import Path

from app.store.base import COLLECTIONS, Repository, matches


class JsonFileRepository(Repository):
    backend = "json"

    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.RLock()
        for c in COLLECTIONS:
            (self.root / c).mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str, doc_id: str) -> Path:
        safe = doc_id.replace("/", "_").replace(":", "__")
        return self.root / collection / f"{safe}.json"

    def _write(self, collection: str, doc: dict) -> dict:
        path = self._path(collection, doc["_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, default=str))
        tmp.replace(path)
        return doc

    def insert(self, collection: str, doc: dict) -> dict:
        with self._lock:
            if self._path(collection, doc["_id"]).exists():
                raise KeyError(f"duplicate id {doc['_id']}")
            return self._write(collection, doc)

    def get(self, collection: str, doc_id: str) -> dict | None:
        path = self._path(collection, doc_id)
        with self._lock:
            if not path.exists():
                return None
            return json.loads(path.read_text())

    def replace(self, collection: str, doc: dict) -> dict:
        with self._lock:
            return self._write(collection, doc)

    def update(self, collection: str, doc_id: str, patch: dict) -> dict | None:
        with self._lock:
            doc = self.get(collection, doc_id)
            if doc is None:
                return None
            doc.update(patch)
            return self._write(collection, doc)

    def find(self, collection: str, query: dict | None = None, sort: str | None = None) -> list[dict]:
        query = query or {}
        out = []
        with self._lock:
            for path in (self.root / collection).glob("*.json"):
                doc = json.loads(path.read_text())
                if matches(doc, query):
                    out.append(doc)
        if sort:
            out.sort(key=lambda d: (d.get(sort) is None, d.get(sort) or ""))
        return out

    def delete_many(self, collection: str, query: dict) -> int:
        n = 0
        with self._lock:
            for doc in self.find(collection, query):
                self._path(collection, doc["_id"]).unlink(missing_ok=True)
                n += 1
        return n

    def ping(self) -> bool:
        return self.root.exists()
