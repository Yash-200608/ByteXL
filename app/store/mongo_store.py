from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.store.base import Repository


class MongoRepository(Repository):
    backend = "mongo"

    def __init__(self, uri: str, db: str, timeout_ms: int = 1500):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, tz_aware=False)
        self.client.admin.command("ping")
        self.db = self.client[db]
        self.db.documents.create_index([("patient_id", ASCENDING)])
        self.db.bundles.create_index([("document_id", ASCENDING)])
        self.db.observations_index.create_index([("patient_id", ASCENDING), ("loinc", ASCENDING), ("date", ASCENDING)])
        self.db.summaries.create_index([("document_id", ASCENDING)])

    def insert(self, collection: str, doc: dict) -> dict:
        self.db[collection].insert_one(dict(doc))
        return doc

    def get(self, collection: str, doc_id: str) -> dict | None:
        return self.db[collection].find_one({"_id": doc_id})

    def replace(self, collection: str, doc: dict) -> dict:
        self.db[collection].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return doc

    def update(self, collection: str, doc_id: str, patch: dict) -> dict | None:
        res = self.db[collection].find_one_and_update({"_id": doc_id}, {"$set": patch}, return_document=True)
        return res

    def find(self, collection: str, query: dict | None = None, sort: str | None = None) -> list[dict]:
        cur = self.db[collection].find(query or {})
        if sort:
            cur = cur.sort(sort, ASCENDING)
        return list(cur)

    def delete_many(self, collection: str, query: dict) -> int:
        return self.db[collection].delete_many(query).deleted_count

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except PyMongoError:
            return False
