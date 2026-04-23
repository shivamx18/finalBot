"""
config/database.py — MongoDB client & shared collection references.
"""

from typing import Optional
from pymongo import MongoClient
from config.settings import MONGO_URI

# BUG FIX: Use Optional[MongoClient] instead of MongoClient | None (works on Python 3.8+)
_client: Optional[MongoClient] = None

users_collection = None
guilds_collection = None
hunts_collection = None
hunt_claims_collection = None


def init_db() -> None:
    global _client, users_collection, guilds_collection
    global hunts_collection, hunt_claims_collection

    _client = MongoClient(MONGO_URI)
    db = _client["codeforces_bot"]

    users_collection       = db["users"]
    guilds_collection      = db["guilds"]
    hunts_collection       = db["hunts"]
    hunt_claims_collection = db["hunt_claims"]

    print("✅ MongoDB connected.")
