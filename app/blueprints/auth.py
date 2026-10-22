from datetime import datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from ..extensions import db, limiter
from ..models import User
from ..utils import audit, validate_password

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.username) == username).first()

        if user is None:
            audit("LOGIN_FAIL", "user", None, f"usuario inexistente: {username}")
            flash("Usuario o contraseña incorrectos.", "danger")
            return render_template("auth/login.html"), 401

        if user.is_locked():
            flash(f"Cuenta bloqueada hasta las {user.locked_until:%H:%M} "
                  "por intentos fallidos.", "danger")
            return render_template("auth/login.html"), 423

        if not user.check_password(password):
            user.failed_attempts += 1
            if user.failed_attempts >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
                user.locked_until = datetime.utcnow() + timedelta(
                    minutes=current_app.config["LOGIN_LOCK_MINUTES"])
                user.failed_attempts = 0
                db.session.commit()
                audit("LOGIN_LOCK", "user", user.id, "bloqueo por intentos fallidos")
                flash("Cuenta bloqueada temporalmente por seguridad.", "danger")
            else:
                db.session.commit()
                flash("Usuario o contraseña incorrectos.", "danger")
            return render_template("auth/login.html"), 401

        if not user.active:
            flash("La cuenta está deshabilitada. Contacta al administrador.", "danger")
            return render_template("auth/login.html"), 403

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(user)
        audit("LOGIN_OK", "user", user.id)

        if user.must_change_password:
            flash("Por seguridad, debes cambiar tu contraseña antes de continuar.", "warning")
            return redirect(url_for("auth.change_password"))

        nxt = request.args.get("next")
        if nxt and nxt.startswith("/") and not nxt.startswith("//"):
            return redirect(nxt)
        return redirect(url_for("main.dashboard"))

    return render_template("auth/login.html")


@bp.before_app_request
def enforce_password_change():
    if not current_user.is_authenticated:
        return
    allowed = {"auth.change_password", "auth.logout", "static"}
    if current_user.must_change_password and request.endpoint not in allowed:
        return redirect(url_for("auth.change_password"))


@bp.route("/logout")
@login_required
def logout():
    audit("LOGOUT", "user", current_user.id)
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current_user.check_password(old):
            flash("La contraseña actual no coincide.", "danger")
        elif new != confirm:
            flash("La confirmación no coincide con la nueva contraseña.", "danger")
        else:
            errors = validate_password(new, current_user.username)
            if errors:
                flash("La nueva contraseña necesita: " + ", ".join(errors) + ".", "danger")
            elif current_user.check_password(new):
                flash("La nueva contraseña no puede ser igual a la anterior.", "danger")
            else:
                current_user.set_password(new)
                current_user.must_change_password = False
                db.session.commit()
                audit("PASSWORD_CHANGE", "user", current_user.id)
                flash("Contraseña actualizada correctamente.", "success")
                return redirect(url_for("main.dashboard"))

    return render_template("auth/password.html")