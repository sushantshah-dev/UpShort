import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from peewee import OperationalError

from app.database import db, init_db
from app.models import ALL_MODELS
from app.routes import register_routes
from app.seed import seed_database_if_empty


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    init_db(app)

    db_bootstrap_state = {"ready": False}

    def _bootstrap_database_if_possible() -> bool:
        if db_bootstrap_state["ready"]:
            return True

        try:
            db.connect(reuse_if_open=True)
            db.create_tables(ALL_MODELS, safe=True)
            seed_database_if_empty()
            db_bootstrap_state["ready"] = True
            return True
        except OperationalError:
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
        return jsonify(error="database temporarily unavailable"), 503

    @app.route("/health")
    def health():
        return jsonify(status="ok", db_ready=db_bootstrap_state["ready"])

    return app
