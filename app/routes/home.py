from flask import Blueprint, redirect, url_for

from app.auth import _current_user

home_bp = Blueprint("home", __name__)


@home_bp.get("/")
def home():
    if _current_user() is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for("dashboard.dashboard"))
