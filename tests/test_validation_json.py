import unittest

from app.utils import _prefers_json_response, generate_slug, load_json_object
from app.validation import (
    _get_json_bool_value,
    _get_json_value,
    _validate_login_json,
    _validate_registration_json,
    _validate_url_json,
)
from tests.support import create_test_app


class JsonValidationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()

    def test_prefers_json_response_for_json_request(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            json={"target_url": "https://example.com"},
        ):
            self.assertTrue(_prefers_json_response())

    def test_prefers_json_response_for_accept_header(self):
        with self.app.test_request_context(
            "/missing",
            headers={"Accept": "application/json"},
        ):
            self.assertTrue(_prefers_json_response())

    def test_load_json_object_rejects_wrong_content_type(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            data="{}",
            content_type="text/plain",
        ):
            payload, error_response = load_json_object()

        self.assertIsNone(payload)
        self.assertEqual(error_response[1], 415)

    def test_load_json_object_rejects_non_object_json(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            data="[]",
            content_type="application/json",
        ):
            payload, error_response = load_json_object()

        self.assertIsNone(payload)
        self.assertEqual(error_response[1], 400)

    def test_get_json_value_rejects_wrong_type(self):
        value, error = _get_json_value({"slug": 1}, "slug", label="Slug")
        self.assertIsNone(value)
        self.assertEqual(error, "Slug must be text.")

    def test_get_json_bool_value_rejects_wrong_type(self):
        value, error = _get_json_bool_value(
            {"is_active": "yes"}, "is_active", label="Link status"
        )
        self.assertFalse(value)
        self.assertEqual(error, "Link status must be true or false.")

    def test_validate_registration_json_rejects_missing_email(self):
        with self.app.test_request_context(
            "/register",
            method="POST",
            json={"password": "abc123", "confirm_password": "abc123"},
        ):
            form, error, response = _validate_registration_json()

        self.assertIsNone(response)
        self.assertEqual(form["email"], "")
        self.assertEqual(error, "Email is required.")

    def test_validate_login_json_rejects_invalid_email(self):
        with self.app.test_request_context(
            "/login",
            method="POST",
            json={"email": "bad", "password": "abc123"},
        ):
            form, error, response = _validate_login_json()

        self.assertIsNone(response)
        self.assertEqual(form["email"], "bad")
        self.assertEqual(error, "Email must be valid.")

    def test_validate_url_json_accepts_optional_null_fields(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            json={
                "target_url": "https://example.com",
                "metadata_title": None,
                "metadata_description": None,
                "metadata_tags": None,
                "expires_at": None,
            },
        ):
            form, error, response = _validate_url_json()

        self.assertIsNone(response)
        self.assertIsNone(error)
        self.assertEqual(form["slug"], "")
        self.assertIsNone(form["expires_at"])

    def test_validate_url_json_rejects_invalid_slug(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            json={"target_url": "https://example.com", "slug": "bad slug"},
        ):
            form, error, response = _validate_url_json()

        self.assertIsNone(response)
        self.assertEqual(form["slug"], "bad slug")
        self.assertIn("Slug must be 3-64 characters", error)

    def test_validate_url_json_rejects_invalid_expiration(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            json={"target_url": "https://example.com", "expires_at": "tomorrow"},
        ):
            _form, error, response = _validate_url_json()

        self.assertIsNone(response)
        self.assertEqual(error, "Expiration must be a valid date and time.")

    def test_generate_slug_returns_valid_slug(self):
        slug = generate_slug()
        self.assertGreaterEqual(len(slug), 3)
        self.assertTrue(slug.isalnum())
