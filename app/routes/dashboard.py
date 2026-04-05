import hmac

from flask import Blueprint, current_app, flash, render_template, request, session
from peewee import OperationalError

from app.auth import _login_required
from app.logging_config import read_recent_logs
from app.models.url import Url
from app.models.user import User

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/dashboard")
@_login_required
def dashboard(user: User):
    try:
        urls = Url.select().where(Url.user == user).order_by(Url.created_at.desc())
    except OperationalError:
        flash(
            "Database is temporarily unavailable. Cached redirects still work.", "error"
        )
        urls = []

    return render_template("dashboard.html", user=user, urls=urls)


def _logs_are_unlocked() -> bool:
    return bool(session.get("logs_unlocked"))


@dashboard_bp.route("/logs", methods=["GET", "POST"])
@_login_required
def logs(user: User):
    configured_password = current_app.config.get("LOG_VIEWER_PASSWORD", "")

    if request.method == "POST":
        submitted_password = request.form.get("password", "")
        if configured_password and hmac.compare_digest(
            submitted_password, configured_password
        ):
            session["logs_unlocked"] = True
        else:
            session.pop("logs_unlocked", None)
            flash("Incorrect logs password.", "error")

    if not configured_password:
        flash("Logs password is not configured.", "error")
        return render_template("logs_prompt.html", user=user), 503

    if not _logs_are_unlocked():
        return render_template("logs_prompt.html", user=user), 401

    requested_lines = request.args.get("lines", type=int)
    default_lines = current_app.config.get("LOG_VIEWER_TAIL_LINES", 200)
    lines = requested_lines if requested_lines is not None else default_lines
    lines = min(max(lines, 1), 500)

    entries = read_recent_logs(current_app.config["LOG_FILE_PATH"], lines)
    return render_template("logs.html", user=user, entries=entries, lines=lines)
