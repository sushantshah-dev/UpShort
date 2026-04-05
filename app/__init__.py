import os

from dotenv import load_dotenv
from flask import Flask
from peewee import BooleanField, DateTimeField, OperationalError
from playhouse.migrate import PostgresqlMigrator, migrate
from werkzeug.exceptions import HTTPException

from app.cache import short_url_cache
from app.database import db, init_db
from app.metrics import instrument_app, record_bootstrap_attempt, record_bootstrap_retry
from app.models import ALL_MODELS
from app.routes import register_routes
from app.seed import seed_database_if_empty
from app.utils import _prefers_json_response, json_error

HEALTH_BOOTSTRAP_INCOMPLETE = 1 << 0
HEALTH_DB_UNAVAILABLE = 1 << 1
HEALTH_CACHE_UNAVAILABLE = 1 << 2
HEALTH_CACHE_PING_FAILED = 1 << 3


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    init_db(app)
    instrument_app(app)

    db_bootstrap_state = {"ready": False}
    bootstrap_attempts = {"count": 0}

    def _ensure_url_state_columns() -> None:
        migrator = PostgresqlMigrator(db)
        existing_columns = {column.name for column in db.get_columns("short_urls")}
        operations = []

        if "is_active" not in existing_columns:
            operations.append(
                migrator.add_column(
                    "short_urls", "is_active", BooleanField(default=True)
                )
            )
        if "expires_at" not in existing_columns:
            operations.append(
                migrator.add_column(
                    "short_urls", "expires_at", DateTimeField(null=True)
                )
            )

        if operations:
            migrate(*operations)

    def _bootstrap_database_if_possible() -> bool:
        if db_bootstrap_state["ready"]:
            return True

        bootstrap_attempts["count"] += 1
        if bootstrap_attempts["count"] > 1:
            record_bootstrap_retry()

        try:
            db.connect(reuse_if_open=True)
            db.create_tables(ALL_MODELS, safe=True)
            _ensure_url_state_columns()
            seed_database_if_empty()
            db_bootstrap_state["ready"] = True
            record_bootstrap_attempt("success")
            return True
        except OperationalError:
            record_bootstrap_attempt("failure")
            return False
        finally:
            if not db.is_closed():
                db.close()

    _bootstrap_database_if_possible()

    @app.before_request
    def _retry_bootstrap_if_needed():
        if not db_bootstrap_state["ready"]:
            _bootstrap_database_if_possible()

    register_routes(app)

    @app.errorhandler(OperationalError)
    def _database_unavailable(_exc):
        return {"error": "database temporarily unavailable"}, 503

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        if _prefers_json_response():
            return json_error(exc.description, exc.code or 500, error_type="http_error")
        return exc

    @app.errorhandler(Exception)
    def _unexpected_error(_exc):
        return json_error(
            "An unexpected error occurred.",
            500,
            error_type="internal_error",
        )

    def _format_health_status(mask: int) -> str:
        return format(mask, "04b")

    def _collect_health_checks() -> tuple[dict, int]:
        bootstrap_code = (
            0 if db_bootstrap_state["ready"] else HEALTH_BOOTSTRAP_INCOMPLETE
        )
        checks = {
            "bootstrap": {
                "status": "ok" if db_bootstrap_state["ready"] else "error",
                "code": bootstrap_code,
                "message": (
                    "database bootstrap completed"
                    if db_bootstrap_state["ready"]
                    else "database bootstrap incomplete"
                ),
            }
        }

        db_ok = False
        db_code = 0
        try:
            db.connect(reuse_if_open=True)
            db.execute_sql("SELECT 1")
            db_ok = True
            checks["database"] = {
                "status": "ok",
                "code": db_code,
                "message": "database connection succeeded",
            }
        except (OperationalError, AttributeError):
            db_code = HEALTH_DB_UNAVAILABLE
            checks["database"] = {
                "status": "error",
                "code": db_code,
                "message": "database connection failed",
            }
        finally:
            try:
                if not db.is_closed():
                    db.close()
            except AttributeError:
                pass

        redis_client = short_url_cache.redis._ensure_client()
        cache_code = 0
        if redis_client is None:
            cache_code = HEALTH_CACHE_UNAVAILABLE
            checks["cache"] = {
                "status": "degraded",
                "code": cache_code,
                "message": "redis cache unavailable",
            }
            redis_ok = False
        else:
            try:
                redis_client.ping()
                checks["cache"] = {
                    "status": "ok",
                    "code": cache_code,
                    "message": "redis cache connection succeeded",
                }
                redis_ok = True
            except Exception:
                cache_code = HEALTH_CACHE_PING_FAILED
                checks["cache"] = {
                    "status": "degraded",
                    "code": cache_code,
                    "message": "redis cache ping failed",
                }
                redis_ok = False

        status_mask = 0
        state = "ok"
        status_code = 200
        message = "all health checks passed"

        if not db_ok:
            status_mask = bootstrap_code | db_code
            state = "error"
            status_code = 503
            message = "database unavailable"
        elif not db_bootstrap_state["ready"]:
            status_mask = bootstrap_code
            state = "error"
            status_code = 503
            message = "application startup incomplete"
        elif not redis_ok:
            status_mask = cache_code
            state = "degraded"
            message = "database available; cache unavailable"

        payload = {
            "status": _format_health_status(0),
            "state": state,
            "code": status_mask,
            "message": message,
            "checks": checks,
        }
        payload["status"] = _format_health_status(status_mask)
        return payload, status_code

    @app.route("/health")
    def health():
        payload, status_code = _collect_health_checks()
        return payload, status_code

    return app
