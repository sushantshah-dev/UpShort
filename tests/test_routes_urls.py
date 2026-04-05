import unittest
from unittest.mock import Mock, patch

from peewee import OperationalError

from tests.support import create_test_app


class UrlRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def test_dashboard_handles_database_unavailable(self):
        query = Mock()
        query.where.side_effect = OperationalError()

        with patch("app.auth._current_user", return_value=Mock(id=1)):
            with patch("app.routes.dashboard.Url.select", return_value=query):
                response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)

    def test_create_url_get_renders_form(self):
        with patch("app.auth._current_user", return_value=Mock(id=1)):
            response = self.client.get("/urls/new")

        self.assertEqual(response.status_code, 200)

    def test_create_url_post_validation_error_returns_400(self):
        with patch("app.auth._current_user", return_value=Mock(id=1)):
            with patch(
                "app.routes.urls._validate_url_form",
                return_value=({"slug": "bad"}, "bad input"),
            ):
                response = self.client.post("/urls/new", data={})

        self.assertEqual(response.status_code, 400)

    def test_create_url_post_success_redirects(self):
        user = Mock(id=1)
        url_obj = Mock()
        with patch("app.auth._current_user", return_value=user):
            with patch(
                "app.routes.urls._validate_url_form",
                return_value=(
                    {
                        "slug": "goodslug",
                        "target_url": "https://example.com",
                        "is_active": True,
                        "expires_at": None,
                        "metadata_title": "",
                        "metadata_description": "",
                        "metadata_tags": "",
                    },
                    None,
                ),
            ):
                with patch("app.routes.urls.Url.create", return_value=url_obj):
                    with patch("app.routes.urls.cache_url") as cache_url:
                        response = self.client.post("/urls/new", data={})

        self.assertEqual(response.status_code, 302)
        cache_url.assert_called_once_with(url_obj)

    def test_create_url_post_handles_integrity_error(self):
        user = Mock(id=1)
        with patch("app.auth._current_user", return_value=user):
            with patch(
                "app.routes.urls._validate_url_form",
                return_value=(
                    {
                        "slug": "goodslug",
                        "target_url": "https://example.com",
                        "is_active": True,
                        "expires_at": None,
                        "metadata_title": "",
                        "metadata_description": "",
                        "metadata_tags": "",
                    },
                    None,
                ),
            ):
                with patch("app.routes.urls.Url.create", side_effect=OperationalError()):
                    response = self.client.post("/urls/new", data={})

        self.assertEqual(response.status_code, 503)

    def test_edit_url_get_renders_form(self):
        user = Mock(id=1)
        url_obj = Mock(
            slug="abc",
            target_url="https://example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                response = self.client.get("/urls/1/edit")

        self.assertEqual(response.status_code, 200)

    def test_edit_url_post_success_updates_and_redirects(self):
        user = Mock(id=1)
        url_obj = Mock(
            slug="oldslug",
            target_url="https://old.example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                with patch(
                    "app.routes.urls._validate_url_form",
                    return_value=(
                        {
                            "slug": "newslug",
                            "target_url": "https://example.com",
                            "is_active": False,
                            "expires_at": None,
                            "metadata_title": "",
                            "metadata_description": "",
                            "metadata_tags": "",
                        },
                        None,
                    ),
                ):
                    with patch("app.routes.urls.cache_url") as cache_url:
                        response = self.client.post("/urls/1/edit", data={})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(url_obj.slug, "newslug")
        cache_url.assert_called_once_with(url_obj)

    def test_edit_url_post_handles_missing_object(self):
        user = Mock(id=1)
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=None):
                response = self.client.post("/urls/1/edit", data={})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.location)

    def test_delete_url_success_redirects(self):
        user = Mock(id=1)
        url_obj = Mock(slug="abc")
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                with patch("app.routes.urls.short_url_cache.delete") as cache_delete:
                    response = self.client.post("/urls/1/delete")

        self.assertEqual(response.status_code, 302)
        cache_delete.assert_called_once_with("abc")

    def test_delete_url_missing_redirects(self):
        user = Mock(id=1)
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=None):
                response = self.client.post("/urls/1/delete")

        self.assertEqual(response.status_code, 302)
