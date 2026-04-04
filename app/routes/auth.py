from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from peewee import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user import User
from app.validation import _validate_login_form, _validate_registration_form

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    form, error = _validate_registration_form()
    if error:
        flash(error, "error")
        return render_template("register.html", email=form.get("email", "")), 400

    try:
        user = User.create(
            email=form["email"],
            password_hash=generate_password_hash(form["password"]),
        )
    except IntegrityError:
        flash("That email is already registered.", "error")
        return render_template("register.html", email=form["email"]), 409

    session["user_id"] = user.id
    flash("Account created. Welcome!", "success")
    return redirect(url_for("dashboard.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    form, error = _validate_login_form()
    if error:
        flash(error, "error")
        return render_template("login.html", email=form.get("email", "")), 400

    user = User.get_or_none(User.email == form["email"])
    if user is None or not check_password_hash(user.password_hash, form["password"]):
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=form["email"]), 401

    session["user_id"] = user.id
    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("dashboard.dashboard"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login"))
