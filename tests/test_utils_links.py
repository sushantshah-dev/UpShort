import datetime as dt
import unittest
from unittest.mock import Mock, patch

import app.utils as links
from tests.support import create_test_app


class LinksUtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()

    def test_is_valid_url_accepts_http_and_https(self):
        self.assertTrue(links._is_valid_url("https://example.com/path"))
        self.assertTrue(links._is_valid_url("http://example.com"))

    def test_is_valid_url_rejects_invalid_candidates(self):
        self.assertFalse(links._is_valid_url("example.com"))
        self.assertFalse(links._is_valid_url("ftp://example.com"))
        self.assertFalse(links._is_valid_url("https:///missing-host"))

    def test_is_valid_slug_rules(self):
        self.assertTrue(links._is_valid_slug("good_slug-123"))
        self.assertFalse(links._is_valid_slug("ab"))
        self.assertFalse(links._is_valid_slug("bad slug"))
        self.assertFalse(links._is_valid_slug("login"))
        self.assertFalse(links._is_valid_slug("metrics"))

    def test_detect_device_type_mobile_desktop_other(self):
        self.assertEqual(links._detect_device_type("Mozilla/5.0 (iPhone)"), "mobile")
        self.assertEqual(
            links._detect_device_type("Mozilla/5.0 (X11; Linux x86_64)"),
            "desktop",
        )
        self.assertEqual(links._detect_device_type("Custom Agent"), "other")

    def test_parse_optional_expires_at_accepts_blank_and_valid_values(self):
        self.assertIsNone(links._parse_optional_expires_at(""))
        self.assertEqual(
            links._parse_optional_expires_at("2026-04-05T11:45"),
            dt.datetime(2026, 4, 5, 11, 45),
        )

    def test_parse_optional_expires_at_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            links._parse_optional_expires_at("not-a-date")

    def test_is_resource_inactive_for_disabled_links(self):
        inactive, status_code = links._is_resource_inactive(
            {"is_active": False, "expires_at": None}
        )

        self.assertTrue(inactive)
        self.assertEqual(status_code, 404)

    def test_is_resource_inactive_for_expired_links(self):
        inactive, status_code = links._is_resource_inactive(
            {"is_active": True, "expires_at": "2025-01-01T00:00:00Z"}
        )

        self.assertTrue(inactive)
        self.assertEqual(status_code, 410)

    def test_is_resource_inactive_for_active_non_expired_links(self):
        future = dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(days=1)
        inactive, status_code = links._is_resource_inactive(
            {"is_active": True, "expires_at": future.isoformat() + "Z"}
        )

        self.assertFalse(inactive)
        self.assertEqual(status_code, 200)

    def test_hydrate_cache_from_db_returns_cached_payload(self):
        payload = {"slug": "abc", "target_url": "https://example.com"}
        with patch(
            "app.utils.short_url_cache.get",
            return_value=(payload, "memory"),
        ):
            with patch("app.utils.Url.get_or_none") as get_or_none:
                result_payload, source = links._hydrate_cache_from_db("abc")

        self.assertEqual(result_payload, payload)
        self.assertEqual(source, "memory")
        get_or_none.assert_not_called()

    def test_hydrate_cache_from_db_fetches_and_sets_cache(self):
        created_at = dt.datetime(2026, 1, 1, 12, 0, 0)
        url_obj = Mock(
            slug="newslug",
            target_url="https://example.com/new",
            click_count=9,
            created_at=created_at,
            is_active=True,
            expires_at=None,
            metadata_title="Title",
            metadata_description="Desc",
            metadata_tags="one,two",
        )

        with patch(
            "app.utils.short_url_cache.get",
            return_value=(None, None),
        ):
            with patch("app.utils.Url.get_or_none", return_value=url_obj):
                with patch("app.utils.short_url_cache.set") as cache_set:
                    payload, source = links._hydrate_cache_from_db("newslug")

        self.assertEqual(source, "database")
        self.assertEqual(payload["slug"], "newslug")
        self.assertEqual(payload["target_url"], "https://example.com/new")
        self.assertEqual(payload["click_count"], 9)
        self.assertEqual(payload["created_at"], created_at.isoformat() + "Z")
        self.assertTrue(payload["is_active"])
        self.assertIsNone(payload["expires_at"])
        cache_set.assert_called_once()

    def test_cache_tier_header_value_maps_sources(self):
        self.assertEqual(links.cache_tier_header_value("memory"), "local")
        self.assertEqual(links.cache_tier_header_value("redis"), "shared")
        self.assertEqual(links.cache_tier_header_value("database"), "fresh")
        self.assertEqual(links.cache_tier_header_value(None), "fresh")

    def test_record_redirect_visit_uses_conflict_safe_upsert(self):
        url_obj = Mock(
            id=42,
            slug="abc",
            target_url="https://example.com/abc",
            click_count=3,
            unique_visitor_count=1,
            first_clicked_at=None,
            last_clicked_at=None,
            last_referrer=None,
            last_visitor_ip=None,
            last_user_agent=None,
            mobile_click_count=0,
            desktop_click_count=0,
            other_device_click_count=0,
            updated_at=None,
            created_at=dt.datetime(2026, 1, 1, 0, 0, 0),
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        cursor = Mock()
        cursor.fetchone.return_value = (True,)

        with self.app.test_request_context(
            "/abc",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
            environ_base={"REMOTE_ADDR": "203.0.113.5"},
        ):
            with patch("app.utils._upsert_visitor_visit", return_value=True) as upsert_visitor_visit:
                with patch("app.utils.cache_url") as cache_url:
                    links.record_redirect_visit(url_obj)

        upsert_visitor_visit.assert_called_once()
        self.assertEqual(url_obj.click_count, 4)
        self.assertEqual(url_obj.unique_visitor_count, 2)
        self.assertIsNotNone(url_obj.first_clicked_at)
        self.assertIsNotNone(url_obj.last_clicked_at)
        self.assertEqual(url_obj.last_visitor_ip, "203.0.113.5")
        self.assertEqual(url_obj.last_user_agent, "Mozilla/5.0 (X11; Linux x86_64)")
        cache_url.assert_called_once_with(url_obj)
