import secrets
import json
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, Response, abort)
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db
from ..models import (User, Intern, Category, Activity, AuditLog,
                      Setting, ROLES, get_setting, set_setting)
from ..utils import role_required, audit, validate_password

bp = Blueprint("admin", __name__)


# ---------------- USUARIOS ----------------

@bp.route("/usuarios")
@login_required
@role_required("admin")
def users():
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        query = query.filter(User.username.ilike(f"%{q}%") |
                             User.full_name.ilike(f"%{q}%"))
    return render_template("admin/users.html",
                           users=query.order_by(User.full_name).all(), q=q)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:user_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def user_form(user_id=None):
    user = User.query.get_or_404(user_id) if user_id else None

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip() or None
        role = request.form.get("role", "practicante")
        active = request.form.get("active") == "on"
        pwd = request.form.get("password", "")

        if not username or not full_name:
            flash("Usuario y nombre completo son obligatorios.", "danger")
        elif role not in ROLES:
            flash("Rol inválido.", "danger")
        else:
            dup = User.query.filter(func.lower(User.username) == username).first()
            if dup and (user is None or dup.id != user.id):
                flash("Ese nombre de usuario ya existe.", "danger")
            else:
                if user is None:
                    user = User(username=username, role=role)
                    db.session.add(user)
                    if not pwd:
                        pwd = secrets.token_urlsafe(12)
                    errors = validate_password(pwd, username)
                    if errors:
                        flash("Contraseña temporal inválida: " + ", ".join(errors), "danger")
                        return render_template("admin/user_form.html", user=None,
                                               roles=ROLES, generated=None)
                    user.set_password(pwd)
                    user.must_change_password = True
                    flash(f"Usuario creado. Contraseña temporal: {pwd}", "success")
                else:
                    if pwd:
                        errors = validate_password(pwd, username)
                        if errors:
                            flash("Contraseña inválida: " + ", ".join(errors), "danger")
                            return render_template("admin/user_form.html", user=user,
                                                   roles=ROLES, generated=None)
                        user.set_password(pwd)
                        user.must_change_password = True

                user.username = username
                user.full_name = full_name
                user.email = email
                user.role = role
                user.active = active if user_id else True
                db.session.commit()
                audit("USER_SAVE", "user", user.id, f"{user.username} / {user.role}")
                return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", user=user, roles=ROLES, generated=None)


@bp.route("/usuarios/<int:user_id>/reset", methods=["POST"])
@login_required
@role_required("admin")
def user_reset(user_id):
    user = User.query.get_or_404(user_id)
    pwd = secrets.token_urlsafe(12)
    user.set_password(pwd)
    user.must_change_password = True
    user.failed_attempts = 0
    user.locked_until = None
    db.session.commit()
    audit("USER_RESET", "user", user.id)
    flash(f"Contraseña temporal de {user.username}: {pwd}", "success")
    return redirect(url_for("admin.users"))


@bp.route("/usuarios/<int:user_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def user_toggle(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes deshabilitar tu propia cuenta.", "danger")
    else:
        user.active = not user.active
        db.session.commit()
        audit("USER_TOGGLE", "user", user.id, str(user.active))
        flash("Estado actualizado.", "success")
    return redirect(url_for("admin.users"))


# ---------------- PRACTICANTES ----------------

@bp.route("/practicantes")
@login_required
@role_required("admin", "supervisor")
def interns():
    query = Intern.query
    if current_user.is_supervisor:
        query = query.filter(Intern.supervisor_id == current_user.id)
    return render_template("admin/interns.html",
                           interns=query.order_by(Intern.full_name).all())


@bp.route("/practicantes/nuevo", methods=["GET", "POST"])
@bp.route("/practicantes/<int:intern_id>", methods=["GET", "POST"])
@login_required
@role_required("admin", "supervisor")
def intern_form(intern_id=None):
    intern = Intern.query.get_or_404(intern_id) if intern_id else None
    if intern and current_user.is_supervisor and intern.supervisor_id != current_user.id:
        abort(403)

    supervisors = User.query.filter(User.role.in_(("admin", "supervisor")),
                                    User.active.is_(True)).all()
    free_users = User.query.filter(User.role == "practicante",
                                   ~User.id.in_(
                                       db.session.query(Intern.user_id).filter(Intern.user_id.isnot(None))
                                   )).all()
    if intern and intern.user_id:
        free_users.append(intern.user)

    if request.method == "POST":
        if intern is None:
            intern = Intern()
            db.session.add(intern)
        intern.full_name = request.form.get("full_name", "").strip()
        if not intern.full_name:
            flash("El nombre es obligatorio.", "danger")
        else:
            intern.dni = request.form.get("dni", "").strip()
            intern.career = request.form.get("career", "").strip()
            intern.institution = request.form.get("institution", "").strip()
            intern.area = request.form.get("area", "").strip()
            intern.user_id = request.form.get("user_id", type=int) or None
            intern.supervisor_id = (current_user.id if current_user.is_supervisor
                                    else request.form.get("supervisor_id", type=int)) or None
            intern.start_date = _d(request.form.get("start_date"))
            intern.end_date = _d(request.form.get("end_date"))
            intern.target_hours = request.form.get("target_hours", type=float) or 400
            intern.active = request.form.get("active") == "on"
            db.session.commit()
            audit("INTERN_SAVE", "intern", intern.id, intern.full_name)
            flash("Practicante guardado.", "success")
            return redirect(url_for("admin.interns"))

    return render_template("admin/intern_form.html", intern=intern,
                           supervisors=supervisors, free_users=free_users)


def _d(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").date() if v else None
    except ValueError:
        return None


# ---------------- CONFIGURACIÓN + CATEGORÍAS ----------------

@bp.route("/configuracion", methods=["GET", "POST"])
@login_required
@role_required("admin")
def settings():
    if request.method == "POST":
        for key in ("municipality", "area", "report_footer", "default_target_hours"):
            set_setting(key, request.form.get(key, "").strip())
        db.session.commit()
        audit("SETTINGS_SAVE", "settings")
        flash("Configuración guardada.", "success")
        return redirect(url_for("admin.settings"))
    data = {k: get_setting(k, "") for k in
            ("municipality", "area", "report_footer", "default_target_hours")}
    return render_template("admin/settings.html", data=data,
                           categories=Category.query.order_by(Category.name).all())


@bp.route("/categorias/nueva", methods=["POST"])
@login_required
@role_required("admin")
def category_create():
    name = request.form.get("name", "").strip()
    color = request.form.get("color", "#1769aa")
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name, color=color))
        db.session.commit()
        audit("CATEGORY_CREATE", "category", None, name)
        flash("Categoría creada.", "success")
    else:
        flash("Nombre vacío o ya existente.", "danger")
    return redirect(url_for("admin.settings"))


@bp.route("/categorias/<int:cat_id>/eliminar", methods=["POST"])
@login_required
@role_required("admin")
def category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    Activity.query.filter_by(category_id=cat.id).update({"category_id": None})
    db.session.delete(cat)
    db.session.commit()
    audit("CATEGORY_DELETE", "category", cat_id)
    flash("Categoría eliminada.", "success")
    return redirect(url_for("admin.settings"))


# ---------------- AUDITORÍA + RESPALDO ----------------

@bp.route("/auditoria")
@login_required
@role_required("admin")
def audit_view():
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=40, error_out=False)
    return render_template("admin/audit.html", pagination=pagination)


@bp.route("/respaldo.json")
@login_required
@role_required("admin")
def backup():
    data = {
        "exportado": datetime.utcnow().isoformat(timespec="seconds"),
        "settings": {s.key: s.value for s in Setting.query.all()},
        "users": [{"id": u.id, "username": u.username, "full_name": u.full_name,
                   "role": u.role, "active": u.active} for u in User.query.all()],
        "interns": [{"id": i.id, "full_name": i.full_name, "dni": i.dni,
                     "target_hours": i.target_hours, "area": i.area} for i in Intern.query.all()],
        "activities": [{"id": a.id, "intern_id": a.intern_id,
                        "date": a.activity_date.isoformat(),
                        "title": a.title, "hours": a.hours,
                        "status": a.status} for a in Activity.query.all()],
    }
    audit("BACKUP", "system")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition":
                             "attachment; filename=respaldo_practicas.json"})