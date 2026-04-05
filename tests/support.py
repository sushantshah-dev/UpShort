from pathlib import Path

from flask import Flask

from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.home import home_bp
from app.routes.redirects import redirects_bp
from app.routes.urls import urls_bp

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "app" / "templates"


def create_test_app() -> Flask:
    app = Flask(__name__, template_folder=str(_TEMPLATES_DIR))
    app.config["SECRET_KEY"] = "test-secret"
    app.config["LOG_VIEWER_PASSWORD"] = "test-log-password"
    app.config["LOG_FILE_PATH"] = str(Path(__file__).resolve().parents[1] / "logs" / "test.log")
    app.config["LOG_VIEWER_TAIL_LINES"] = 200
    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(urls_bp)
    app.register_blueprint(redirects_bp)
    return app
