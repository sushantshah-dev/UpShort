from __future__ import annotations

import datetime as dt
import hashlib
import re
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from peewee import IntegrityError, OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from app.cache import short_url_cache
from app.models.url import Url
from app.models.user import User
from app.models.visitor import Visitor

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


def _extract_client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    return (request.remote_addr or "")[:64] or None


def _detect_device_type(user_agent: str) -> str:
    user_agent_lower = user_agent.lower()
    mobile_tokens = ["mobile", "android", "iphone", "ipad", "ipod"]
    desktop_tokens = ["windows", "macintosh", "linux", "x11"]

    if any(token in user_agent_lower for token in mobile_tokens):
        return "mobile"
    if any(token in user_agent_lower for token in desktop_tokens):
        return "desktop"
    return "other"


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
            return redirect(url_for("shortener.login", next=request.path))
        return handler(user, *args, **kwargs)

    return wrapper


def _hydrate_cache_from_db(slug: str) -> tuple[dict, str] | tuple[None, None]:
    cached, source = short_url_cache.get(slug)
    if cached is not None:
        return cached, source

    try:
        url_obj = Url.get_or_none(Url.slug == slug)
    except OperationalError:
        return None, None

    if url_obj is None:
        return None, None

    short_url_cache.set(
        slug=url_obj.slug,
        target_url=url_obj.target_url,
        click_count=url_obj.click_count,
        created_at=url_obj.created_at,
    )
    return (
        {
            "slug": url_obj.slug,
            "target_url": url_obj.target_url,
            "click_count": url_obj.click_count,
            "created_at": url_obj.created_at.isoformat() + "Z",
        },
        "database",
    )


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
    try:
        urls = Url.select().where(Url.user == user).order_by(Url.created_at.desc())
    except OperationalError:
        flash(
            "Database is temporarily unavailable. Cached redirects still work.", "error"
        )
        urls = []

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
        flash(
            "Slug must be 3-64 characters and use letters, numbers, '_' or '-'.",
            "error",
        )
        return render_template("url_form.html", form_mode="create", form=form), 400

    try:
        url_obj = Url.create(
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
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 503

    short_url_cache.set(
        slug=url_obj.slug,
        target_url=url_obj.target_url,
        click_count=url_obj.click_count,
        created_at=url_obj.created_at,
    )

    flash("Short URL created.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.route("/urls/<int:url_id>/edit", methods=["GET", "POST"])
@_login_required
def edit_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("shortener.dashboard"))

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

    old_slug = url_obj.slug

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
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            400,
        )

    if not _is_valid_url(target_url):
        flash("Target URL must be an absolute http/https URL.", "error")
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            400,
        )

    if not _is_valid_slug(slug):
        flash(
            "Slug must be 3-64 characters and use letters, numbers, '_' or '-'.",
            "error",
        )
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            400,
        )

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
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            409,
        )
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            503,
        )

    if old_slug != url_obj.slug:
        short_url_cache.delete(old_slug)

    short_url_cache.set(
        slug=url_obj.slug,
        target_url=url_obj.target_url,
        click_count=url_obj.click_count,
        created_at=url_obj.created_at,
    )

    flash("Short URL updated.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.post("/urls/<int:url_id>/delete")
@_login_required
def delete_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("shortener.dashboard"))

    if url_obj is None:
        flash("URL not found.", "error")
        return redirect(url_for("shortener.dashboard"))

    old_slug = url_obj.slug
    try:
        url_obj.delete_instance()
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("shortener.dashboard"))

    short_url_cache.delete(old_slug)
    flash("Short URL deleted.", "success")
    return redirect(url_for("shortener.dashboard"))


@shortener_bp.get("/<string:slug>")
def resolve_short_url(slug: str):
    url_payload, _source = _hydrate_cache_from_db(slug)
    if url_payload is None:
        flash("Short URL not found.", "error")
        return redirect(url_for("shortener.login"))

    try:
        url_obj = Url.get_or_none(Url.slug == slug)
        if url_obj is not None:
            now = dt.datetime.utcnow()
            client_ip = _extract_client_ip()
            user_agent = (request.headers.get("User-Agent") or "")[:512]
            referrer = (request.referrer or "")[:512] or None
            device_type = _detect_device_type(user_agent)

            fingerprint_source = f"{client_ip or 'unknown'}|{user_agent}"
            visitor_fingerprint = hashlib.sha256(
                fingerprint_source.encode("utf-8")
            ).hexdigest()

            new_visitor = False
            try:
                Visitor.create(
                    short_url=url_obj,
                    fingerprint=visitor_fingerprint,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                new_visitor = True
            except IntegrityError:
                (
                    Visitor.update(last_seen_at=now)
                    .where(
                        (Visitor.short_url == url_obj)
                        & (Visitor.fingerprint == visitor_fingerprint)
                    )
                    .execute()
                )

            url_obj.click_count += 1
            if new_visitor:
                url_obj.unique_visitor_count += 1
            if url_obj.first_clicked_at is None:
                url_obj.first_clicked_at = now
            url_obj.last_clicked_at = now
            url_obj.last_referrer = referrer
            url_obj.last_visitor_ip = client_ip
            url_obj.last_user_agent = user_agent or None
            if device_type == "mobile":
                url_obj.mobile_click_count += 1
            elif device_type == "desktop":
                url_obj.desktop_click_count += 1
            else:
                url_obj.other_device_click_count += 1
            url_obj.updated_at = now
            url_obj.save()

            short_url_cache.set(
                slug=url_obj.slug,
                target_url=url_obj.target_url,
                click_count=url_obj.click_count,
                created_at=url_obj.created_at,
            )
        else:
            short_url_cache.increment_click_count(slug)
    except OperationalError:
        short_url_cache.increment_click_count(slug)

    return redirect(url_payload["target_url"], code=302)
