from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from peewee import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user import User
from app.utils import _prefers_json_response, json_error
from app.validation import (
    _validate_login_form,
    _validate_login_json,
    _validate_registration_form,
    _validate_registration_json,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    if request.is_json:
        form, error, response = _validate_registration_json()
        if response:
            return response
    else:
        form, error = _validate_registration_form()

    if error:
        if _prefers_json_response():
            return json_error(error, 400)
        flash(error, "error")
        return render_template("register.html", email=form.get("email", "")), 400

    try:
        user = User.create(
            email=form["email"],
            password_hash=generate_password_hash(form["password"]),
        )
    except IntegrityError:
        if _prefers_json_response():
            return json_error("That email is already registered.", 409, error_type="conflict")
        flash("That email is already registered.", "error")
        return render_template("register.html", email=form["email"]), 409

    session["user_id"] = user.id
    if _prefers_json_response():
        return {"id": user.id, "email": form["email"]}, 201
    flash("Account created. Welcome!", "success")
    return redirect(url_for("dashboard.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    if request.is_json:
        form, error, response = _validate_login_json()
        if response:
            return response
    else:
        form, error = _validate_login_form()

    if error:
        if _prefers_json_response():
            return json_error(error, 400)
        flash(error, "error")
        return render_template("login.html", email=form.get("email", "")), 400

    user = User.get_or_none(User.email == form["email"])
    if user is None or not check_password_hash(user.password_hash, form["password"]):
        if _prefers_json_response():
            return json_error("Invalid email or password.", 401, error_type="authentication_failed")
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=form["email"]), 401

    session["user_id"] = user.id
    if _prefers_json_response():
        return {"id": user.id, "email": form["email"]}, 200
    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("dashboard.dashboard"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login"))
