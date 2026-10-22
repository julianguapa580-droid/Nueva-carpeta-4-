import re
from datetime import datetime
from functools import wraps
from flask import abort, redirect, request, url_for
from flask_login import current_user
from .extensions import db
from .models import AuditLog


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return decorator


def audit(action, entity=None, entity_id=None, detail=None):
    """Registra una acción en el log de auditoría."""
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else "anónimo",
            action=action, entity=entity, entity_id=entity_id, detail=detail,
            ip=request.remote_addr if request else None,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def validate_password(pw, username=""):
    errors = []
    if len(pw) < 10:
        errors.append("mínimo 10 caracteres")
    if not re.search(r"[A-Z]", pw):
        errors.append("una letra mayúscula")
    if not re.search(r"[a-z]", pw):
        errors.append("una letra minúscula")
    if not re.search(r"\d", pw):
        errors.append("un número")
    if not re.search(r"[^\w\s]", pw):
        errors.append("un símbolo (!@#$…)")
    if username and username.lower() in pw.lower():
        errors.append("no debe contener el nombre de usuario")
    return errors


def compute_hours(start, end):
    """Calcula horas entre dos `time`, contemplando turnos nocturnos."""
    if not start or not end:
        return None
    base = datetime(2000, 1, 1)
    delta = (datetime.combine(base.date(), end) - datetime.combine(base.date(), start)).total_seconds() / 3600
    if delta < 0:
        delta += 24
    return round(delta, 2)