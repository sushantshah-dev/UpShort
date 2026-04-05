from flask import Blueprint, flash, redirect, render_template, request, url_for
from peewee import IntegrityError, OperationalError

from app.auth import _login_required
from app.cache import short_url_cache
from app.models.url import Url
from app.models.user import User
from app.utils import (
    _prefers_json_response,
    _utcnow,
    cache_url,
    generate_slug,
    json_error,
)
from app.validation import _validate_url_form, _validate_url_json

urls_bp = Blueprint("urls", __name__)


def _serialize_url(url_obj: Url) -> dict:
    return {
        "id": url_obj.id,
        "slug": url_obj.slug,
        "target_url": url_obj.target_url,
        "is_active": url_obj.is_active,
        "expires_at": (
            url_obj.expires_at.isoformat() + "Z" if url_obj.expires_at else None
        ),
        "metadata_title": url_obj.metadata_title,
        "metadata_description": url_obj.metadata_description,
        "metadata_tags": url_obj.metadata_tags,
    }


def _is_same_url_request(url_obj: Url, user: User, form: dict[str, str | bool]) -> bool:
    return (
        getattr(url_obj, "user_id", None) == user.id
        and url_obj.target_url == form["target_url"]
        and url_obj.is_active == form["is_active"]
        and url_obj.expires_at == form["expires_at"]
        and (url_obj.metadata_title or None) == (form["metadata_title"] or None)
        and (url_obj.metadata_description or None)
        == (form["metadata_description"] or None)
        and (url_obj.metadata_tags or None) == (form["metadata_tags"] or None)
    )


def _create_url_with_retries(
    user: User, form: dict[str, str | bool], *, max_attempts: int = 4
):
    generated_slug = not bool(form.get("slug"))
    attempted_form = dict(form)
    last_error = None

    for _ in range(max_attempts):
        if generated_slug:
            attempted_form["slug"] = generate_slug()

        try:
            url_obj = Url.create(
                user=user,
                slug=attempted_form["slug"],
                target_url=attempted_form["target_url"],
                is_active=attempted_form["is_active"],
                expires_at=attempted_form["expires_at"],
                metadata_title=attempted_form["metadata_title"] or None,
                metadata_description=attempted_form["metadata_description"] or None,
                metadata_tags=attempted_form["metadata_tags"] or None,
            )
            return url_obj, False, None
        except IntegrityError as exc:
            last_error = exc
            try:
                existing = Url.get_or_none(Url.slug == attempted_form["slug"])
            except OperationalError:
                return None, False, exc
            if existing is not None and _is_same_url_request(
                existing, user, attempted_form
            ):
                return existing, True, None
            if not generated_slug:
                return None, False, exc
        except OperationalError as exc:
            return None, False, exc

    return None, False, last_error


@urls_bp.route("/urls/new", methods=["GET", "POST"])
@_login_required
def create_url(user: User):
    if request.method == "GET":
        return render_template("url_form.html", form_mode="create", form={})

    if request.is_json:
        form, error, response = _validate_url_json()
        if response:
            return response
    else:
        form, error = _validate_url_form()

    if error:
        if _prefers_json_response():
            return json_error(error, 400)
        flash(error, "error")
        return render_template("url_form.html", form_mode="create", form=form), 400

    url_obj, reused_existing, create_error = _create_url_with_retries(user, form)
    if isinstance(create_error, IntegrityError):
        if _prefers_json_response():
            return json_error(
                "Slug already exists. Try a different one.", 409, error_type="conflict"
            )
        flash("Slug already exists. Try a different one.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 409
    if isinstance(create_error, OperationalError):
        if _prefers_json_response():
            return json_error(
                "Database is temporarily unavailable. Please try again.",
                503,
                error_type="database_unavailable",
            )
        flash("Database is temporarily unavailable. Please try again.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 503

    cache_url(url_obj)
    if _prefers_json_response():
        status_code = 200 if reused_existing else 201
        return _serialize_url(url_obj), status_code
    flash("Short URL created.", "success")
    return redirect(url_for("dashboard.dashboard"))


@urls_bp.route("/urls/<int:url_id>/edit", methods=["GET", "POST"])
@_login_required
def edit_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        if _prefers_json_response():
            return json_error(
                "Database is temporarily unavailable. Please try again.",
                503,
                error_type="database_unavailable",
            )
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if url_obj is None:
        if _prefers_json_response():
            return json_error("URL not found.", 404, error_type="not_found")
        flash("URL not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "GET":
        return render_template(
            "url_form.html",
            form_mode="edit",
            url_obj=url_obj,
            form={
                "target_url": url_obj.target_url,
                "slug": url_obj.slug,
                "is_active": url_obj.is_active,
                "expires_at": (
                    url_obj.expires_at.strftime("%Y-%m-%dT%H:%M")
                    if url_obj.expires_at
                    else ""
                ),
                "metadata_title": url_obj.metadata_title or "",
                "metadata_description": url_obj.metadata_description or "",
                "metadata_tags": url_obj.metadata_tags or "",
            },
        )

    old_slug = url_obj.slug
    if request.is_json:
        form, error, response = _validate_url_json()
        if response:
            return response
        if not form.get("slug"):
            form["slug"] = old_slug
    else:
        form, error = _validate_url_form()

    if error:
        if _prefers_json_response():
            return json_error(error, 400)
        flash(error, "error")
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            400,
        )

    url_obj.slug = form["slug"]
    url_obj.target_url = form["target_url"]
    url_obj.is_active = form["is_active"]
    url_obj.expires_at = form["expires_at"]
    url_obj.metadata_title = form["metadata_title"] or None
    url_obj.metadata_description = form["metadata_description"] or None
    url_obj.metadata_tags = form["metadata_tags"] or None
    url_obj.updated_at = _utcnow()

    try:
        url_obj.save()
    except IntegrityError:
        if _prefers_json_response():
            return json_error(
                "Slug already exists. Try a different one.", 409, error_type="conflict"
            )
        flash("Slug already exists. Try a different one.", "error")
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            409,
        )
    except OperationalError:
        if _prefers_json_response():
            return json_error(
                "Database is temporarily unavailable. Please try again.",
                503,
                error_type="database_unavailable",
            )
        flash("Database is temporarily unavailable. Please try again.", "error")
        return (
            render_template(
                "url_form.html", form_mode="edit", url_obj=url_obj, form=form
            ),
            503,
        )

    if old_slug != url_obj.slug:
        short_url_cache.delete(old_slug)

    cache_url(url_obj)
    if _prefers_json_response():
        return _serialize_url(url_obj), 200
    flash("Short URL updated.", "success")
    return redirect(url_for("dashboard.dashboard"))


@urls_bp.post("/urls/<int:url_id>/delete")
@_login_required
def delete_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        if _prefers_json_response():
            return json_error(
                "Database is temporarily unavailable. Please try again.",
                503,
                error_type="database_unavailable",
            )
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if url_obj is None:
        if _prefers_json_response():
            return json_error("URL not found.", 404, error_type="not_found")
        flash("URL not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    old_slug = url_obj.slug
    try:
        url_obj.delete_instance()
    except OperationalError:
        if _prefers_json_response():
            return json_error(
                "Database is temporarily unavailable. Please try again.",
                503,
                error_type="database_unavailable",
            )
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    short_url_cache.delete(old_slug)
    if _prefers_json_response():
        return "", 204
    flash("Short URL deleted.", "success")
    return redirect(url_for("dashboard.dashboard"))
