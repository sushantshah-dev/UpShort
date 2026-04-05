import os

from peewee import DatabaseProxy, Model
from playhouse.pool import PooledPostgresqlDatabase

db = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db


def init_db(app):
    database = PooledPostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
        max_connections=int(os.environ.get("DATABASE_POOL_MAX_CONNECTIONS", 64)),
        stale_timeout=int(os.environ.get("DATABASE_POOL_STALE_TIMEOUT", 300)),
        timeout=int(os.environ.get("DATABASE_POOL_TIMEOUT", 30)),
    )
    db.initialize(database)

    @app.before_request
    def _db_connect():
        try:
            db.connect(reuse_if_open=True)
        except Exception:
            pass

    @app.teardown_appcontext
    def _db_close(exc):
        if not db.is_closed():
            db.close()
