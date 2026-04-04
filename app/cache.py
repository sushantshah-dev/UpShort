from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Any

from redis import Redis


class InMemoryCache:
    def __init__(self, max_items: int = 5000):
        self.max_items = max_items
        self._store: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._store.get(key)
            if value is None:
                return None

            self._store.move_to_end(key)
            return dict(value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._store[key] = dict(value)
            self._store.move_to_end(key)

            while len(self._store) > self.max_items:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class RedisCache:
    def __init__(self, ttl_seconds: int, prefix: str = "shorturl:"):
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self._client = self._build_client()

    @staticmethod
    def _build_client() -> Redis | None:
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", 6379))

        try:
            client = Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _ensure_client(self) -> Redis | None:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _key(self, slug: str) -> str:
        return f"{self.prefix}{slug}"

    def get(self, slug: str) -> dict[str, Any] | None:
        client = self._ensure_client()
        if client is None:
            return None

        try:
            raw = client.get(self._key(slug))
        except Exception:
            self._client = None
            return None

        if not raw:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set(self, slug: str, payload: dict[str, Any]) -> None:
        client = self._ensure_client()
        if client is None:
            return

        try:
            client.setex(self._key(slug), self.ttl_seconds, json.dumps(payload))
        except Exception:
            self._client = None

    def delete(self, slug: str) -> None:
        client = self._ensure_client()
        if client is None:
            return

        try:
            client.delete(self._key(slug))
        except Exception:
            self._client = None


class UrlCache:
    def __init__(self):
        ttl_seconds = int(os.environ.get("CACHE_TTL_SECONDS", 300))
        max_items = int(os.environ.get("CACHE_MAX_ITEMS", 5000))

        self.ttl_seconds = ttl_seconds
        self.memory = InMemoryCache(max_items=max_items)
        self.redis = RedisCache(ttl_seconds=ttl_seconds)

    def get(self, slug: str) -> tuple[dict[str, Any] | None, str | None]:
        in_memory = self.memory.get(slug)
        if in_memory is not None:
            return in_memory, "memory"

        from_redis = self.redis.get(slug)
        if from_redis is None:
            return None, None

        self.memory.set(slug, from_redis)
        return from_redis, "redis"

    def set(self, slug: str, target_url: str, click_count: int, created_at: datetime) -> None:
        payload = {
            "slug": slug,
            "target_url": target_url,
            "click_count": click_count,
            "created_at": created_at.isoformat() + "Z",
        }

        self.memory.set(slug, payload)
        self.redis.set(slug, payload)

    def delete(self, slug: str) -> None:
        self.memory.delete(slug)
        self.redis.delete(slug)

    def increment_click_count(self, slug: str) -> None:
        cached = self.memory.get(slug)
        if cached is not None:
            cached["click_count"] = int(cached.get("click_count", 0)) + 1
            self.memory.set(slug, cached)

        payload = self.redis.get(slug)
        if payload is None:
            return
        payload["click_count"] = int(payload.get("click_count", 0)) + 1
        self.redis.set(slug, payload)


short_url_cache = UrlCache()
