import types
import unittest
from unittest.mock import Mock, patch

from peewee import OperationalError

from app import (
    HEALTH_BOOTSTRAP_INCOMPLETE,
    HEALTH_CACHE_UNAVAILABLE,
    HEALTH_DB_UNAVAILABLE,
    create_app,
)
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
        fake_db.execute_sql.return_value = None
        fake_migrator = Mock()
        fake_migrator.add_column.side_effect = ["add_is_active", "add_expires_at"]
        fake_redis_client = Mock()

        with patch("app.load_dotenv") as load_dotenv:
            with patch("app.init_db") as init_db:
                with patch("app.configure_logging") as configure_logging:
                    with patch("app.db", fake_db):
                        with patch("app.PostgresqlMigrator", return_value=fake_migrator):
                            with patch("app.migrate") as migrate:
                                with patch("app.seed_database_if_empty") as seed:
                                    with patch("app.register_routes") as register:
                                        with patch(
                                            "app.short_url_cache.redis._ensure_client",
                                            return_value=fake_redis_client,
                                        ):
                                            app = create_app()
                                            response = app.test_client().get("/health")

        load_dotenv.assert_called_once()
        configure_logging.assert_called_once_with(app)
        init_db.assert_called_once()
        fake_db.connect.assert_called_with(reuse_if_open=True)
        fake_db.create_tables.assert_called_once()
        migrate.assert_called_once_with("add_is_active", "add_expires_at")
        seed.assert_called_once()
        register.assert_called_once_with(app)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "0000")
        self.assertEqual(response.get_json()["state"], "ok")
        self.assertEqual(response.get_json()["code"], 0)
        self.assertEqual(response.get_json()["checks"]["bootstrap"]["code"], 0)
        self.assertEqual(response.get_json()["checks"]["database"]["code"], 0)
        self.assertEqual(response.get_json()["checks"]["cache"]["code"], 0)
        self.assertEqual(response.get_json()["checks"]["database"]["status"], "ok")
        self.assertEqual(response.get_json()["checks"]["cache"]["status"], "ok")

    def test_create_app_exposes_prometheus_metrics(self):
        fake_db = Mock()
        fake_db.is_closed.return_value = True
        fake_db.get_columns.return_value = [
            types.SimpleNamespace(name="is_active"),
            types.SimpleNamespace(name="expires_at"),
        ]
        fake_db.execute_sql.return_value = None

        with patch("app.init_db"):
            with patch("app.db", fake_db):
                with patch("app.seed_database_if_empty"):
                    with patch("app.short_url_cache.redis._ensure_client", return_value=None):
                        app = create_app()
                        response = app.test_client().get("/metrics")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("upshort_http_requests_total", body)
        self.assertIn("upshort_cache_operations_total", body)
        self.assertIn("upshort_process_cpu_usage_percent", body)
        self.assertIn("upshort_process_resident_memory_bytes", body)

    def test_create_app_handles_bootstrap_failure_and_retries(self):
        fake_db = Mock()
        fake_db.connect.side_effect = [OperationalError(), None, None]
        fake_db.is_closed.return_value = True
        fake_db.execute_sql.return_value = None
        fake_db.get_columns.return_value = [
            types.SimpleNamespace(name="is_active"),
            types.SimpleNamespace(name="expires_at"),
        ]
        fake_redis_client = Mock()

        with patch("app.init_db"):
            with patch("app.db", fake_db):
                with patch("app.seed_database_if_empty"):
                    with patch(
                        "app.short_url_cache.redis._ensure_client",
                        return_value=fake_redis_client,
                    ):
                        app = create_app()
                        health_response = app.test_client().get("/health")

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.get_json()["status"], "0000")
        self.assertEqual(health_response.get_json()["state"], "ok")
        self.assertEqual(health_response.get_json()["code"], 0)

    def test_health_returns_degraded_when_cache_is_unavailable(self):
        fake_db = Mock()
        fake_db.is_closed.return_value = True
        fake_db.get_columns.return_value = [
            types.SimpleNamespace(name="is_active"),
            types.SimpleNamespace(name="expires_at"),
        ]
        fake_db.execute_sql.return_value = None

        with patch("app.init_db"):
            with patch("app.db", fake_db):
                with patch("app.seed_database_if_empty"):
                    with patch("app.short_url_cache.redis._ensure_client", return_value=None):
                        app = create_app()
                        response = app.test_client().get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "0100")
        self.assertEqual(response.get_json()["state"], "degraded")
        self.assertEqual(response.get_json()["code"], HEALTH_CACHE_UNAVAILABLE)
        self.assertEqual(
            response.get_json()["checks"]["cache"]["code"], HEALTH_CACHE_UNAVAILABLE
        )
        self.assertEqual(response.get_json()["checks"]["cache"]["status"], "degraded")

    def test_health_returns_503_when_database_is_unavailable(self):
        fake_db = Mock()
        fake_db.connect.side_effect = OperationalError()
        fake_db.is_closed.return_value = True

        with patch("app.init_db"):
            with patch("app.db", fake_db):
                with patch("app.short_url_cache.redis._ensure_client", return_value=None):
                    app = create_app()
                    response = app.test_client().get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "0011")
        self.assertEqual(response.get_json()["state"], "error")
        self.assertEqual(
            response.get_json()["code"],
            HEALTH_BOOTSTRAP_INCOMPLETE | HEALTH_DB_UNAVAILABLE,
        )
        self.assertEqual(
            response.get_json()["checks"]["bootstrap"]["code"],
            HEALTH_BOOTSTRAP_INCOMPLETE,
        )
        self.assertEqual(
            response.get_json()["checks"]["database"]["code"], HEALTH_DB_UNAVAILABLE
        )
        self.assertEqual(response.get_json()["checks"]["database"]["status"], "error")

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
