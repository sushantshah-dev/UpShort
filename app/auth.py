from __future__ import annotations

from functools import wraps

from flask import redirect, request, session, url_for
from peewee import OperationalError

from app.models.user import User


def _current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return User.get_or_none(User.id == user_id)
    except OperationalError:
        return None


def _login_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        return handler(user, *args, **kwargs)

    return wrapper
