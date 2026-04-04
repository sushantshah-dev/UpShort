import unittest
from unittest.mock import Mock, patch

from peewee import OperationalError

from tests.support import create_test_app


class RedirectRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.client = self.app.test_client()

    def test_resolve_short_url_returns_404_for_missing_link(self):
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(None, None),
        ):
            response = self.client.get("/missing")

        self.assertEqual(response.status_code, 404)

    def test_resolve_short_url_returns_404_for_disabled_link(self):
        payload = {
            "slug": "off",
            "target_url": "https://example.com/off",
            "is_active": False,
            "expires_at": None,
        }
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            response = self.client.get("/off")

        self.assertEqual(response.status_code, 404)

    def test_resolve_short_url_returns_410_for_expired_link(self):
        payload = {
            "slug": "gone",
            "target_url": "https://example.com/gone",
            "is_active": True,
            "expires_at": "2025-01-01T00:00:00Z",
        }
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            response = self.client.get("/gone")

        self.assertEqual(response.status_code, 410)

    def test_resolve_short_url_redirects_and_tracks_cached_only_path(self):
        payload = {
            "slug": "abc",
            "target_url": "https://example.com/abc",
            "is_active": True,
            "expires_at": None,
            "metadata_title": "Title",
            "metadata_description": "Desc",
            "metadata_tags": "one,two",
        }
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            with patch("app.routes.redirects.Url.get_or_none", return_value=None):
                with patch(
                    "app.routes.redirects.short_url_cache.increment_click_count"
                ) as increment_click_count:
                    response = self.client.get("/abc")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://example.com/abc")
        increment_click_count.assert_called_once_with("abc")

    def test_resolve_short_url_redirects_and_records_visit(self):
        payload = {
            "slug": "abc",
            "target_url": "https://example.com/abc",
            "is_active": True,
            "expires_at": None,
        }
        url_obj = Mock(is_active=True, expires_at=None)
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            with patch("app.routes.redirects.Url.get_or_none", return_value=url_obj):
                with patch("app.routes.redirects.record_redirect_visit") as record_visit:
                    response = self.client.get("/abc")

        self.assertEqual(response.status_code, 302)
        record_visit.assert_called_once_with(url_obj)

    def test_resolve_short_url_handles_operational_error_with_fallback(self):
        payload = {
            "slug": "abc",
            "target_url": "https://example.com/abc",
            "is_active": True,
            "expires_at": None,
        }
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            with patch(
                "app.routes.redirects.Url.get_or_none",
                side_effect=OperationalError(),
            ):
                with patch(
                    "app.routes.redirects.short_url_cache.increment_click_count"
                ) as increment_click_count:
                    response = self.client.get("/abc")

        self.assertEqual(response.status_code, 302)
        increment_click_count.assert_called_once_with("abc")

    def test_resolve_short_url_aborts_when_db_resource_is_inactive(self):
        payload = {
            "slug": "abc",
            "target_url": "https://example.com/abc",
            "is_active": True,
            "expires_at": None,
        }
        url_obj = Mock(is_active=False, expires_at=None)
        with patch(
            "app.routes.redirects._hydrate_cache_from_db",
            return_value=(payload, "memory"),
        ):
            with patch("app.routes.redirects.Url.get_or_none", return_value=url_obj):
                with patch("app.routes.redirects.cache_url") as cache_url:
                    response = self.client.get("/abc")

        self.assertEqual(response.status_code, 404)
        cache_url.assert_called_once_with(url_obj)
