from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.home import home_bp
from app.routes.redirects import redirects_bp
from app.routes.urls import urls_bp


def register_routes(app):
    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(urls_bp)
    app.register_blueprint(redirects_bp)
