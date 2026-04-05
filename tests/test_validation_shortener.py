import unittest
from werkzeug.datastructures import MultiDict

from app.validation import (
    _get_checkbox_value,
    _get_form_value,
    _validate_form_content_type,
    _validate_login_form,
    _validate_registration_form,
    _validate_url_form,
)

from tests.support import create_test_app


class ShortenerValidationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()

    def test_validate_form_content_type_rejects_non_form_mimetype(self):
        with self.app.test_request_context(
            "/login", method="POST", content_type="application/json"
        ):
            self.assertEqual(
                _validate_form_content_type(),
                "Form submissions must use form encoding.",
            )

    def test_get_form_value_rejects_duplicate_values(self):
        with self.app.test_request_context("/", method="POST"):
            from flask import request

            request.form = MultiDict([("email", "a@example.com"), ("email", "b@example.com")])
            value, error = _get_form_value("email", label="Email")

        self.assertEqual(value, "")
        self.assertEqual(error, "Email must be provided only once.")

    def test_get_checkbox_value_rejects_invalid_value(self):
        with self.app.test_request_context("/", method="POST"):
            from flask import request

            request.form = MultiDict([("is_active", "yes")])
            value, error = _get_checkbox_value("is_active", label="Link status")

        self.assertFalse(value)
        self.assertEqual(error, "Link status must be a valid checkbox value.")

    def test_validate_registration_form_rejects_password_mismatch(self):
        with self.app.test_request_context(
            "/register",
            method="POST",
            data={
                "email": "user@example.com",
                "password": "abc123",
                "confirm_password": "mismatch",
            },
        ):
            form, error = _validate_registration_form()

        self.assertEqual(form["email"], "user@example.com")
        self.assertEqual(error, "Passwords do not match.")

    def test_validate_login_form_accepts_valid_input(self):
        with self.app.test_request_context(
            "/login",
            method="POST",
            data={"email": "USER@example.com", "password": "abc123"},
        ):
            form, error = _validate_login_form()

        self.assertEqual(error, None)
        self.assertEqual(form["email"], "user@example.com")
        self.assertEqual(form["password"], "abc123")

    def test_validate_url_form_rejects_invalid_url(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            data={"target_url": "example.com", "slug": "validslug"},
        ):
            form, error = _validate_url_form()

        self.assertEqual(form["slug"], "validslug")
        self.assertEqual(error, "Target URL must be an absolute http/https URL.")

    def test_validate_url_form_accepts_valid_input(self):
        with self.app.test_request_context(
            "/urls/new",
            method="POST",
            data={
                "target_url": "https://example.com/page",
                "slug": "validslug",
                "is_active": "on",
                "expires_at": "2026-04-05T11:45",
                "metadata_title": "Title",
                "metadata_description": "Description",
                "metadata_tags": "one,two",
            },
        ):
            form, error = _validate_url_form()

        self.assertEqual(error, None)
        self.assertTrue(form["is_active"])
        self.assertEqual(form["expires_at"].year, 2026)
