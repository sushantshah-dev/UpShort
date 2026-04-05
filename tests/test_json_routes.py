import unittest
from unittest.mock import Mock, patch

from peewee import IntegrityError, OperationalError

from app.routes.urls import _create_url_with_retries
from tests.support import create_test_app


class JsonRouteBehaviorTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def test_register_json_success_returns_created_user(self):
        user = Mock(id=7)
        with patch("app.routes.auth.User.create", return_value=user):
            response = self.client.post(
                "/register",
                json={
                    "email": "User@example.com",
                    "password": "abc123",
                    "confirm_password": "abc123",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(),
            {"id": 7, "email": "user@example.com"},
        )

    def test_register_json_duplicate_email_returns_conflict(self):
        with patch("app.routes.auth.User.create", side_effect=IntegrityError()):
            response = self.client.post(
                "/register",
                json={
                    "email": "user@example.com",
                    "password": "abc123",
                    "confirm_password": "abc123",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["type"], "conflict")

    def test_login_json_success_returns_user_payload(self):
        user = Mock(id=5, password_hash="hashed")
        with patch("app.routes.auth.User.get_or_none", return_value=user):
            with patch("app.routes.auth.check_password_hash", return_value=True):
                response = self.client.post(
                    "/login",
                    json={"email": "user@example.com", "password": "abc123"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"id": 5, "email": "user@example.com"},
        )

    def test_login_json_invalid_credentials_return_json_error(self):
        with patch("app.routes.auth.User.get_or_none", return_value=None):
            response = self.client.post(
                "/login",
                json={"email": "user@example.com", "password": "bad"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["error"]["type"], "authentication_failed"
        )

    def test_create_url_json_returns_structured_validation_error(self):
        with patch("app.auth._current_user", return_value=Mock(id=1)):
            response = self.client.post(
                "/urls/new",
                json={"target_url": "https://example.com", "slug": 123},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"]["message"], "Slug must be text."
        )

    def test_create_url_json_returns_structured_malformed_json_error(self):
        with patch("app.auth._current_user", return_value=Mock(id=1)):
            response = self.client.post(
                "/urls/new",
                data='{"slug"',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"]["type"], "malformed_json"
        )

    def test_create_url_json_success_returns_created_payload(self):
        user = Mock(id=1)
        url_obj = Mock(
            id=9,
            slug="goodslug",
            target_url="https://example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        with patch("app.auth._current_user", return_value=user):
            with patch(
                "app.routes.urls._create_url_with_retries",
                return_value=(url_obj, False, None),
            ):
                with patch("app.routes.urls.cache_url") as cache_url:
                    response = self.client.post(
                        "/urls/new",
                        json={"target_url": "https://example.com", "slug": "goodslug"},
                    )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["slug"], "goodslug")
        cache_url.assert_called_once_with(url_obj)

    def test_create_url_json_returns_existing_payload_for_idempotent_retry(self):
        user = Mock(id=1)
        url_obj = Mock(
            id=9,
            slug="same-slug",
            target_url="https://example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        with patch("app.auth._current_user", return_value=user):
            with patch(
                "app.routes.urls._create_url_with_retries",
                return_value=(url_obj, True, None),
            ):
                with patch("app.routes.urls.cache_url"):
                    response = self.client.post(
                        "/urls/new",
                        json={"target_url": "https://example.com", "slug": "same-slug"},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["slug"], "same-slug")

    def test_create_url_with_generated_slug_retries_after_conflict(self):
        user = Mock(id=1)
        created = Mock(
            slug="freshslug",
            target_url="https://example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        form = {
            "target_url": "https://example.com",
            "slug": "",
            "is_active": True,
            "expires_at": None,
            "metadata_title": "",
            "metadata_description": "",
            "metadata_tags": "",
        }
        with patch("app.routes.urls.generate_slug", side_effect=["taken", "freshslug"]):
            with patch(
                "app.routes.urls.Url.create",
                side_effect=[IntegrityError(), created],
            ) as create_url:
                with patch("app.routes.urls.Url.get_or_none", return_value=None):
                    url_obj, reused_existing, error = _create_url_with_retries(
                        user, form
                    )

        self.assertIs(url_obj, created)
        self.assertFalse(reused_existing)
        self.assertIsNone(error)
        self.assertEqual(create_url.call_count, 2)

    def test_create_url_with_same_request_returns_existing_row(self):
        user = Mock(id=1)
        existing = Mock(
            user_id=1,
            target_url="https://example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        form = {
            "target_url": "https://example.com",
            "slug": "same-slug",
            "is_active": True,
            "expires_at": None,
            "metadata_title": "",
            "metadata_description": "",
            "metadata_tags": "",
        }
        with patch("app.routes.urls.Url.create", side_effect=IntegrityError()):
            with patch("app.routes.urls.Url.get_or_none", return_value=existing):
                url_obj, reused_existing, error = _create_url_with_retries(user, form)

        self.assertIs(url_obj, existing)
        self.assertTrue(reused_existing)
        self.assertIsNone(error)

    def test_edit_url_json_uses_existing_slug_when_omitted(self):
        user = Mock(id=1)
        url_obj = Mock(
            id=3,
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
                with patch("app.routes.urls.cache_url") as cache_url:
                    response = self.client.post(
                        "/urls/3/edit",
                        json={"target_url": "https://example.com", "is_active": False},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["slug"], "oldslug")
        self.assertFalse(url_obj.is_active)
        cache_url.assert_called_once_with(url_obj)

    def test_edit_url_json_handles_save_integrity_error(self):
        user = Mock(id=1)
        url_obj = Mock(
            id=3,
            slug="oldslug",
            target_url="https://old.example.com",
            is_active=True,
            expires_at=None,
            metadata_title=None,
            metadata_description=None,
            metadata_tags=None,
        )
        url_obj.save.side_effect = IntegrityError()
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                response = self.client.post(
                    "/urls/3/edit",
                    json={"target_url": "https://example.com", "slug": "taken"},
                )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["type"], "conflict")

    def test_edit_url_json_returns_not_found(self):
        user = Mock(id=1)
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=None):
                response = self.client.post(
                    "/urls/999/edit",
                    json={"target_url": "https://example.com"},
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["type"], "not_found")

    def test_delete_url_json_returns_no_content(self):
        user = Mock(id=1)
        url_obj = Mock(slug="gone")
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                with patch("app.routes.urls.short_url_cache.delete") as cache_delete:
                    response = self.client.post("/urls/1/delete", json={})

        self.assertEqual(response.status_code, 204)
        cache_delete.assert_called_once_with("gone")

    def test_delete_url_json_handles_database_error(self):
        user = Mock(id=1)
        url_obj = Mock(slug="gone")
        url_obj.delete_instance.side_effect = OperationalError()
        with patch("app.auth._current_user", return_value=user):
            with patch("app.routes.urls.Url.get_or_none", return_value=url_obj):
                response = self.client.post("/urls/1/delete", json={})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"]["type"], "database_unavailable"
        )
