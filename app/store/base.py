from abc import ABC, abstractmethod
from typing import Any

COLLECTIONS = ("patients", "documents", "bundles", "observations_index", "summaries")


def matches(doc: dict, query: dict) -> bool:
    for key, expected in query.items():
        cur: Any = doc
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if isinstance(expected, dict) and "$in" in expected:
            if cur not in expected["$in"]:
                return False
        elif cur != expected:
            return False
    return True


class Repository(ABC):
    backend: str

    @abstractmethod
    def insert(self, collection: str, doc: dict) -> dict: ...

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> dict | None: ...

    @abstractmethod
    def replace(self, collection: str, doc: dict) -> dict: ...

    @abstractmethod
    def update(self, collection: str, doc_id: str, patch: dict) -> dict | None: ...

    @abstractmethod
    def find(self, collection: str, query: dict | None = None, sort: str | None = None) -> list[dict]: ...

    @abstractmethod
    def delete_many(self, collection: str, query: dict) -> int: ...

    @abstractmethod
    def ping(self) -> bool: ...

    def upsert(self, collection: str, doc: dict) -> dict:
        return self.replace(collection, doc)
