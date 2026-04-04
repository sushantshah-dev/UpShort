from flask import Blueprint, flash, render_template
from peewee import OperationalError

from app.auth import _login_required
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
