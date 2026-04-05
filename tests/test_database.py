import unittest
from unittest.mock import Mock, patch

from flask import Flask

from app.database import init_db


class DatabaseInitTestCase(unittest.TestCase):
    def test_init_db_uses_pooled_postgres_with_env_settings(self):
        app = Flask(__name__)
        fake_pool = Mock()
        fake_proxy = Mock()

        with patch.dict(
            "os.environ",
            {
                "DATABASE_NAME": "pool_db",
                "DATABASE_HOST": "db-host",
                "DATABASE_PORT": "6543",
                "DATABASE_USER": "pool-user",
                "DATABASE_PASSWORD": "pool-pass",
                "DATABASE_POOL_MAX_CONNECTIONS": "48",
                "DATABASE_POOL_STALE_TIMEOUT": "120",
                "DATABASE_POOL_TIMEOUT": "15",
            },
            clear=False,
        ):
            with patch(
                "app.database.PooledPostgresqlDatabase", return_value=fake_pool
            ) as pooled_db:
                with patch("app.database.db", fake_proxy):
                    init_db(app)

        pooled_db.assert_called_once_with(
            "pool_db",
            host="db-host",
            port=6543,
            user="pool-user",
            password="pool-pass",
            max_connections=48,
            stale_timeout=120,
            timeout=15,
        )
        fake_proxy.initialize.assert_called_once_with(fake_pool)

    def test_init_db_registers_connection_hooks(self):
        app = Flask(__name__)
        fake_pool = Mock()
        fake_pool.is_closed.return_value = False
        fake_proxy = Mock()
        fake_proxy.connect = fake_pool.connect
        fake_proxy.is_closed = fake_pool.is_closed
        fake_proxy.close = fake_pool.close

        with patch("app.database.PooledPostgresqlDatabase", return_value=fake_pool):
            with patch("app.database.db", fake_proxy):
                init_db(app)
                before_request_hook = app.before_request_funcs[None][0]
                teardown_hook = app.teardown_appcontext_funcs[0]

                before_request_hook()
                teardown_hook(None)

        fake_pool.connect.assert_called_once_with(reuse_if_open=True)
        fake_pool.close.assert_called_once()
