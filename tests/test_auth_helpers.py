import unittest
from types import SimpleNamespace
from unittest.mock import patch

from peewee import OperationalError

from app.auth import _current_user, _login_required

from tests.support import create_test_app


class AuthHelpersTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_test_app()

    def test_current_user_returns_none_without_session_user_id(self):
        with self.app.test_request_context("/"):
            self.assertIsNone(_current_user())

    def test_current_user_handles_operational_error(self):
        with patch("app.auth.User.get_or_none", side_effect=OperationalError()):
            with self.app.test_request_context("/"):
                from flask import session

                session["user_id"] = 123
                self.assertIsNone(_current_user())

    def test_login_required_redirects_when_unauthenticated(self):
        @_login_required
        def protected(_user):
            return "ok"

        with patch("app.auth._current_user", return_value=None):
            with self.app.test_request_context("/dashboard"):
                response = protected()

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        self.assertIn("next=/dashboard", response.location)

    def test_login_required_calls_handler_when_authenticated(self):
        user = SimpleNamespace(id=7)

        @_login_required
        def protected(passed_user):
            return f"ok:{passed_user.id}"

        with patch("app.auth._current_user", return_value=user):
            with self.app.test_request_context("/dashboard"):
                response = protected()

        self.assertEqual(response, "ok:7")
