def register_routes(app):
    from app.routes.shortener import shortener_bp

    app.register_blueprint(shortener_bp)
