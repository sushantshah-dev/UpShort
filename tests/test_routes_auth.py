import unittest
from unittest.mock import Mock, patch

from peewee import IntegrityError

from tests.support import create_test_app


class AuthRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()
        self.client = self.app.test_client()

    def test_home_redirects_to_login_when_signed_out(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_register_get_renders_page(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)

    def test_register_post_uses_validation_error(self):
        with patch(
            "app.routes.auth._validate_registration_form",
            return_value=({"email": "bad@example.com"}, "Email must be valid."),
        ):
            response = self.client.post("/register", data={})

        self.assertEqual(response.status_code, 400)

    def test_register_post_success_sets_session_and_redirects(self):
        user = Mock(id=7)
        with patch(
            "app.routes.auth._validate_registration_form",
            return_value=(
                {
                    "email": "user@example.com",
                    "password": "abc123",
                    "confirm_password": "abc123",
                },
                None,
            ),
        ):
            with patch("app.routes.auth.User.create", return_value=user):
                response = self.client.post("/register", data={})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.location)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 7)

    def test_register_post_handles_duplicate_email(self):
        with patch(
            "app.routes.auth._validate_registration_form",
            return_value=(
                {
                    "email": "user@example.com",
                    "password": "abc123",
                    "confirm_password": "abc123",
                },
                None,
            ),
        ):
            with patch("app.routes.auth.User.create", side_effect=IntegrityError()):
                response = self.client.post("/register", data={})

        self.assertEqual(response.status_code, 409)

    def test_login_get_renders_page(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

    def test_login_post_rejects_invalid_credentials(self):
        with patch(
            "app.routes.auth._validate_login_form",
            return_value=({"email": "user@example.com", "password": "bad"}, None),
        ):
            with patch("app.routes.auth.User.get_or_none", return_value=None):
                response = self.client.post("/login", data={})

        self.assertEqual(response.status_code, 401)

    def test_login_post_validation_error_returns_400(self):
        with patch(
            "app.routes.auth._validate_login_form",
            return_value=({"email": "bad@example.com"}, "Email must be valid."),
        ):
            response = self.client.post("/login", data={})

        self.assertEqual(response.status_code, 400)

    def test_login_post_success_redirects_to_next(self):
        user = Mock(id=5, password_hash="hashed")
        with patch(
            "app.routes.auth._validate_login_form",
            return_value=(
                {"email": "user@example.com", "password": "abc123"},
                None,
            ),
        ):
            with patch("app.routes.auth.User.get_or_none", return_value=user):
                with patch("app.routes.auth.check_password_hash", return_value=True):
                    response = self.client.post("/login?next=/dashboard", data={})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/dashboard"))

    def test_logout_clears_session_and_redirects(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 1

        response = self.client.post("/logout")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
