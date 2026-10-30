import json
import os
from datetime import datetime, timezone
from pymongo import MongoClient
import redis

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
audit_collection = mongo_client["task_demo"]["audit_events"]
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

CACHE_TTL_SECONDS = 60

def write_audit(action: str, task_id: int, payload: dict | None = None):
    """Сохраняет событие аудита как документ MongoDB."""
    audit_collection.insert_one({
        "action": action,
        "task_id": task_id,
        "payload": payload or {},
        "created_at": datetime.now(timezone.utc),
    })

def cache_key(task_id: int) -> str:
    return f"task:{task_id}"

def invalidate_task_cache(task_id: int):
    redis_client.delete(cache_key(task_id))

def get_cached_task(task_id: int):
    raw = redis_client.get(cache_key(task_id))
    return json.loads(raw) if raw else None

def set_cached_task(task_id: int, data: dict):
    redis_client.setex(cache_key(task_id), CACHE_TTL_SECONDS, json.dumps(data, default=str))

def cache_stats():
    info = redis_client.info("stats")
    return {
        "redis_key_count": redis_client.dbsize(),
        "keyspace_hits": info.get("keyspace_hits", 0),
        "keyspace_misses": info.get("keyspace_misses", 0),
        "ttl_seconds": CACHE_TTL_SECONDS,
    }
