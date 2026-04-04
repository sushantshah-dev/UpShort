import types
import unittest
from unittest.mock import Mock, patch

from peewee import OperationalError

from app import create_app
from app.routes import register_routes


class AppFactoryTestCase(unittest.TestCase):
    def test_register_routes_registers_all_blueprints(self):
        app = Mock()
        register_routes(app)
        self.assertEqual(app.register_blueprint.call_count, 5)

    def test_create_app_bootstraps_database_and_health(self):
        fake_db = Mock()
        fake_db.is_closed.return_value = False
        fake_db.get_columns.return_value = []
        fake_migrator = Mock()
        fake_migrator.add_column.side_effect = ["add_is_active", "add_expires_at"]

        with patch("app.load_dotenv") as load_dotenv:
            with patch("app.init_db") as init_db:
                with patch("app.db", fake_db):
                    with patch("app.PostgresqlMigrator", return_value=fake_migrator):
                        with patch("app.migrate") as migrate:
                            with patch("app.seed_database_if_empty") as seed:
                                with patch("app.register_routes") as register:
                                    app = create_app()

        load_dotenv.assert_called_once()
        init_db.assert_called_once()
        fake_db.connect.assert_called_once_with(reuse_if_open=True)
        fake_db.create_tables.assert_called_once()
        migrate.assert_called_once_with("add_is_active", "add_expires_at")
        seed.assert_called_once()
        register.assert_called_once_with(app)

        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["db_ready"])

    def test_create_app_handles_bootstrap_failure_and_retries(self):
        fake_db = Mock()
        fake_db.connect.side_effect = [OperationalError(), None]
        fake_db.is_closed.return_value = True
        fake_db.get_columns.return_value = [
            types.SimpleNamespace(name="is_active"),
            types.SimpleNamespace(name="expires_at"),
        ]

        with patch("app.init_db"):
            with patch("app.db", fake_db):
                with patch("app.seed_database_if_empty"):
                    app = create_app()
                    health_response = app.test_client().get("/health")

        self.assertEqual(health_response.status_code, 200)
        self.assertTrue(health_response.get_json()["db_ready"])

    def test_database_operational_error_handler_returns_503(self):
        with patch("app.init_db"):
            with patch("app.db") as fake_db:
                fake_db.connect.side_effect = OperationalError()
                fake_db.is_closed.return_value = True
                app = create_app()

                @app.route("/boom")
                def boom():
                    raise OperationalError()

                response = app.test_client().get("/boom")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"error": "database temporarily unavailable"},
        )
