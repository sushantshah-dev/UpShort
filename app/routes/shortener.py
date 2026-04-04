from __future__ import annotations

import datetime as dt
import re
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from peewee import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.url import Url
from app.models.user import User

shortener_bp = Blueprint("shortener", __name__)

_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_RESERVED_SLUGS = {
    "api",
    "dashboard",
    "health",
    "login",
    "logout",
    "register",
    "urls",
    "static",
}


def _is_valid_url(candidate: str) -> bool:
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.fullmatch(slug)) and slug not in _RESERVED_SLUGS


def _current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.get_or_none(User.id == user_id)


def _login_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if user is None:
            return redirect(url_for("shortener.login", next=request.path))
        return handler(user, *args, **kwargs)

    return wrapper


@shortener_bp.get("/")
def home():
    if _current_user() is None:
        return redirect(url_for("shortener.login"))
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not email or not password:
        flash("Email and password are required.", "error")
        return render_template("register.html", email=email), 400

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("register.html", email=email), 400

    try:
        user = User.create(email=email, password_hash=generate_password_hash(password))
    except IntegrityError:
        flash("That email is already registered.", "error")
        return render_template("register.html", email=email), 409

    session["user_id"] = user.id
    flash("Account created. Welcome!", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = User.get_or_none(User.email == email)
    if user is None or not check_password_hash(user.password_hash, password):
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=email), 401

    session["user_id"] = user.id
    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("shortener.dashboard"))


@shortener_bp.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("shortener.login"))


@shortener_bp.get("/dashboard")
@_login_required
def dashboard(user: User):
    urls = Url.select().where(Url.user == user).order_by(Url.created_at.desc())
    return render_template("dashboard.html", user=user, urls=urls)


@shortener_bp.route("/urls/new", methods=["GET", "POST"])
@_login_required
def create_url(user: User):
    if request.method == "GET":
        return render_template("url_form.html", form_mode="create", form={})

    target_url = request.form.get("target_url", "").strip()
    slug = request.form.get("slug", "").strip()
    metadata_title = request.form.get("metadata_title", "").strip()
    metadata_description = request.form.get("metadata_description", "").strip()
    metadata_tags = request.form.get("metadata_tags", "").strip()

    form = {
        "target_url": target_url,
        "slug": slug,
        "metadata_title": metadata_title,
        "metadata_description": metadata_description,
        "metadata_tags": metadata_tags,
    }

    if not target_url or not slug:
        flash("Target URL and slug are required.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 400

    if not _is_valid_url(target_url):
        flash("Target URL must be an absolute http/https URL.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 400

    if not _is_valid_slug(slug):
        flash("Slug must be 3-64 characters and use letters, numbers, '_' or '-'.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 400

    try:
        Url.create(
            user=user,
            slug=slug,
            target_url=target_url,
            metadata_title=metadata_title or None,
            metadata_description=metadata_description or None,
            metadata_tags=metadata_tags or None,
        )
    except IntegrityError:
        flash("Slug already exists. Try a different one.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 409

    flash("Short URL created.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.route("/urls/<int:url_id>/edit", methods=["GET", "POST"])
@_login_required
def edit_url(user: User, url_id: int):
    url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    if url_obj is None:
        flash("URL not found.", "error")
        return redirect(url_for("shortener.dashboard"))

    if request.method == "GET":
        return render_template(
            "url_form.html",
            form_mode="edit",
            url_obj=url_obj,
            form={
                "target_url": url_obj.target_url,
                "slug": url_obj.slug,
                "metadata_title": url_obj.metadata_title or "",
                "metadata_description": url_obj.metadata_description or "",
                "metadata_tags": url_obj.metadata_tags or "",
            },
        )

    target_url = request.form.get("target_url", "").strip()
    slug = request.form.get("slug", "").strip()
    metadata_title = request.form.get("metadata_title", "").strip()
    metadata_description = request.form.get("metadata_description", "").strip()
    metadata_tags = request.form.get("metadata_tags", "").strip()

    form = {
        "target_url": target_url,
        "slug": slug,
        "metadata_title": metadata_title,
        "metadata_description": metadata_description,
        "metadata_tags": metadata_tags,
    }

    if not target_url or not slug:
        flash("Target URL and slug are required.", "error")
        return render_template("url_form.html", form_mode="edit", url_obj=url_obj, form=form), 400

    if not _is_valid_url(target_url):
        flash("Target URL must be an absolute http/https URL.", "error")
        return render_template("url_form.html", form_mode="edit", url_obj=url_obj, form=form), 400

    if not _is_valid_slug(slug):
        flash("Slug must be 3-64 characters and use letters, numbers, '_' or '-'.", "error")
        return render_template("url_form.html", form_mode="edit", url_obj=url_obj, form=form), 400

    url_obj.slug = slug
    url_obj.target_url = target_url
    url_obj.metadata_title = metadata_title or None
    url_obj.metadata_description = metadata_description or None
    url_obj.metadata_tags = metadata_tags or None
    url_obj.updated_at = dt.datetime.utcnow()

    try:
        url_obj.save()
    except IntegrityError:
        flash("Slug already exists. Try a different one.", "error")
        return render_template("url_form.html", form_mode="edit", url_obj=url_obj, form=form), 409

    flash("Short URL updated.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.post("/urls/<int:url_id>/delete")
@_login_required
def delete_url(user: User, url_id: int):
    url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    if url_obj is None:
        flash("URL not found.", "error")
        return redirect(url_for("shortener.dashboard"))

    url_obj.delete_instance()
    flash("Short URL deleted.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.get("/<string:slug>")
def resolve_short_url(slug: str):
    url_obj = Url.get_or_none(Url.slug == slug)
    if url_obj is None:
        flash("Short URL not found.", "error")
        return redirect(url_for("shortener.login"))

    url_obj.click_count += 1
    if url_obj.first_clicked_at is None:
        url_obj.first_clicked_at = dt.datetime.utcnow()
    url_obj.last_clicked_at = dt.datetime.utcnow()
    url_obj.updated_at = dt.datetime.utcnow()
    url_obj.save()

    return redirect(url_obj.target_url, code=302)
