import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug_enabled = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=debug_enabled,
        use_reloader=debug_enabled,
    )
