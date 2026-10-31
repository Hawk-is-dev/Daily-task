"""State storage: MongoDB (MONGODB_URI) or a local JSON file for testing."""
import json
import os

import core


class Store:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI")
        self.col = None
        self.path = os.getenv("STATE_FILE", "state.json")
        if self.uri:
            from motor.motor_asyncio import AsyncIOMotorClient
            db = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=10000)[os.getenv("MONGODB_DB", "studybot")]
            self.col = db["state"]

    async def load(self):
        st = None
        if self.col is not None:
            st = await self.col.find_one({"_id": "state"})
            if st:
                st.pop("_id", None)
        elif os.path.exists(self.path):
            st = json.load(open(self.path, encoding="utf-8"))
        base = core.new_state()
        base.update(st or {})
        return base

    async def save(self, st):
        if self.col is not None:
            await self.col.replace_one({"_id": "state"}, {"_id": "state", **st}, upsert=True)
        else:
            json.dump(st, open(self.path, "w", encoding="utf-8"))
