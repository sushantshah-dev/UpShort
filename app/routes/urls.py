from flask import Blueprint, flash, redirect, render_template, request, url_for
from peewee import IntegrityError, OperationalError

from app.auth import _login_required
from app.cache import short_url_cache
from app.models.url import Url
from app.models.user import User
from app.utils import _utcnow, cache_url
from app.validation import _validate_url_form

urls_bp = Blueprint("urls", __name__)


@urls_bp.route("/urls/new", methods=["GET", "POST"])
@_login_required
def create_url(user: User):
    if request.method == "GET":
        return render_template("url_form.html", form_mode="create", form={})

    form, error = _validate_url_form()
    if error:
        flash(error, "error")
        return render_template("url_form.html", form_mode="create", form=form), 400

    try:
        url_obj = Url.create(
            user=user,
            slug=form["slug"],
            target_url=form["target_url"],
            is_active=form["is_active"],
            expires_at=form["expires_at"],
            metadata_title=form["metadata_title"] or None,
            metadata_description=form["metadata_description"] or None,
            metadata_tags=form["metadata_tags"] or None,
        )
    except IntegrityError:
        flash("Slug already exists. Try a different one.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 409
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return render_template("url_form.html", form_mode="create", form=form), 503

    cache_url(url_obj)
    flash("Short URL created.", "success")
    return redirect(url_for("dashboard.dashboard"))


@urls_bp.route("/urls/<int:url_id>/edit", methods=["GET", "POST"])
@_login_required
def edit_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if url_obj is None:
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
    form, error = _validate_url_form()
    if error:
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

    cache_url(url_obj)
    flash("Short URL updated.", "success")
    return redirect(url_for("dashboard.dashboard"))


@urls_bp.post("/urls/<int:url_id>/delete")
@_login_required
def delete_url(user: User, url_id: int):
    try:
        url_obj = Url.get_or_none((Url.id == url_id) & (Url.user == user))
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if url_obj is None:
        flash("URL not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    old_slug = url_obj.slug
    try:
        url_obj.delete_instance()
    except OperationalError:
        flash("Database is temporarily unavailable. Please try again.", "error")
        return redirect(url_for("dashboard.dashboard"))

    short_url_cache.delete(old_slug)
    flash("Short URL deleted.", "success")
    return redirect(url_for("dashboard.dashboard"))
