import datetime as dt
import unittest
from unittest.mock import Mock, patch

from app.cache import InMemoryCache, RedisCache, UrlCache


class InMemoryCacheTestCase(unittest.TestCase):
    def test_get_returns_copy_and_set_evicts_oldest(self):
        cache = InMemoryCache(max_items=1)
        cache.set("first", {"value": 1})
        returned = cache.get("first")
        returned["value"] = 9
        cache.set("second", {"value": 2})

        self.assertIsNone(cache.get("first"))
        self.assertEqual(cache.get("second"), {"value": 2})

    def test_delete_removes_key(self):
        cache = InMemoryCache()
        cache.set("abc", {"value": 1})
        cache.delete("abc")
        self.assertIsNone(cache.get("abc"))


class RedisCacheTestCase(unittest.TestCase):
    def test_build_client_returns_none_on_failure(self):
        with patch("app.cache.Redis", side_effect=RuntimeError("boom")):
            self.assertIsNone(RedisCache._build_client())

    def test_get_returns_none_when_client_missing_or_empty(self):
        cache = RedisCache(ttl_seconds=10)
        cache._client = None
        with patch.object(cache, "_build_client", return_value=None):
            self.assertIsNone(cache.get("abc"))

        cache._client = Mock()
        cache._client.get.return_value = ""
        self.assertIsNone(cache.get("abc"))

    def test_get_clears_client_on_exception_and_handles_bad_json(self):
        cache = RedisCache(ttl_seconds=10)
        cache._client = Mock()
        cache._client.get.side_effect = RuntimeError("boom")
        self.assertIsNone(cache.get("abc"))
        self.assertIsNone(cache._client)

        cache._client = Mock()
        cache._client.get.return_value = "{bad json"
        self.assertIsNone(cache.get("abc"))

    def test_set_and_delete_clear_client_on_exception(self):
        cache = RedisCache(ttl_seconds=10)
        cache._client = Mock()
        cache._client.setex.side_effect = RuntimeError("boom")
        cache.set("abc", {"x": 1})
        self.assertIsNone(cache._client)

        cache._client = Mock()
        cache._client.delete.side_effect = RuntimeError("boom")
        cache.delete("abc")
        self.assertIsNone(cache._client)


class UrlCacheTestCase(unittest.TestCase):
    def test_get_prefers_memory_then_redis(self):
        cache = UrlCache()
        with patch.object(cache.memory, "get", return_value={"slug": "abc"}):
            payload, source = cache.get("abc")
        self.assertEqual(source, "memory")
        self.assertEqual(payload["slug"], "abc")

        with patch.object(cache.memory, "get", return_value=None):
            with patch.object(cache.redis, "get", return_value={"slug": "abc"}):
                with patch.object(cache.memory, "set") as memory_set:
                    payload, source = cache.get("abc")
        self.assertEqual(source, "redis")
        memory_set.assert_called_once()
        self.assertEqual(payload["slug"], "abc")

    def test_set_delete_and_increment_click_count(self):
        cache = UrlCache()
        created_at = dt.datetime(2026, 1, 1, 0, 0, 0)

        with patch.object(cache.memory, "set") as memory_set:
            with patch.object(cache.redis, "set") as redis_set:
                cache.set(
                    slug="abc",
                    target_url="https://example.com",
                    click_count=2,
                    created_at=created_at,
                    is_active=False,
                    expires_at=created_at,
                    metadata_title="Title",
                )

        memory_payload = memory_set.call_args.args[1]
        self.assertEqual(memory_payload["click_count"], 2)
        self.assertFalse(memory_payload["is_active"])
        self.assertEqual(memory_payload["expires_at"], created_at.isoformat() + "Z")
        redis_set.assert_called_once()

        with patch.object(cache.memory, "delete") as memory_delete:
            with patch.object(cache.redis, "delete") as redis_delete:
                cache.delete("abc")
        memory_delete.assert_called_once_with("abc")
        redis_delete.assert_called_once_with("abc")

        with patch.object(cache.memory, "get", return_value={"click_count": 1}):
            with patch.object(cache.memory, "set") as memory_set:
                with patch.object(cache.redis, "get", return_value={"click_count": 3}):
                    with patch.object(cache.redis, "set") as redis_set:
                        cache.increment_click_count("abc")
        self.assertEqual(memory_set.call_args.args[1]["click_count"], 2)
        self.assertEqual(redis_set.call_args.args[1]["click_count"], 4)

    def test_increment_click_count_skips_missing_redis_payload(self):
        cache = UrlCache()
        with patch.object(cache.memory, "get", return_value=None):
            with patch.object(cache.redis, "get", return_value=None):
                with patch.object(cache.redis, "set") as redis_set:
                    cache.increment_click_count("abc")
        redis_set.assert_not_called()
