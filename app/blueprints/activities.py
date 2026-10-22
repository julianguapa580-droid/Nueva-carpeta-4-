from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user
from sqlalchemy import or_
from ..extensions import db
from ..models import Activity, Intern, Category, STATUSES
from ..utils import audit, compute_hours, role_required

bp = Blueprint("activities", __name__)


def _visible_query():
    q = Activity.query
    if current_user.is_intern:
        intern = current_user.intern
        q = q.filter(Activity.intern_id == (intern.id if intern else -1))
    elif current_user.is_supervisor:
        ids = [i.id for i in current_user.supervised_interns.all()]
        q = q.filter(Activity.intern_id.in_(ids or [-1]))
    return q


def _can_edit(activity):
    if current_user.is_admin:
        return True
    if current_user.is_intern:
        return (current_user.intern and activity.intern_id == current_user.intern.id
                and activity.status != "Aprobada")
    return False


@bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    cat = request.args.get("category", type=int)
    df = request.args.get("from", "")
    dt = request.args.get("to", "")

    query = _visible_query()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Activity.title.ilike(like),
                                 Activity.description.ilike(like),
                                 Activity.observations.ilike(like)))
    if status in STATUSES:
        query = query.filter(Activity.status == status)
    if cat:
        query = query.filter(Activity.category_id == cat)
    if df:
        query = query.filter(Activity.activity_date >= df)
    if dt:
        query = query.filter(Activity.activity_date <= dt)

    pagination = query.order_by(Activity.activity_date.desc(),
                                Activity.id.desc()).paginate(
        page=page, per_page=15, error_out=False)

    return render_template("activities/list.html", pagination=pagination,
                           categories=Category.query.order_by(Category.name).all(),
                           statuses=STATUSES, q=q, status=status,
                           cat=cat, df=df, dt=dt)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
def create():
    if current_user.is_supervisor:
        abort(403)

    interns = _selectable_interns()
    if not interns:
        flash("No hay un practicante asociado a tu cuenta. Contacta al administrador.", "warning")
        return redirect(url_for("activities.index"))

    if request.method == "POST":
        ok, msg = _save(None)
        flash(msg, "success" if ok else "danger")
        if ok:
            return redirect(url_for("activities.index"))

    return render_template("activities/form.html", activity=None, interns=interns,
                           categories=Category.query.order_by(Category.name).all(),
                           statuses=STATUSES)


@bp.route("/<int:activity_id>")
@login_required
def detail(activity_id):
    act = _visible_query().filter(Activity.id == activity_id).first_or_404()
    return render_template("activities/detail.html", activity=act)


@bp.route("/<int:activity_id>/editar", methods=["GET", "POST"])
@login_required
def edit(activity_id):
    act = Activity.query.get_or_404(activity_id)
    if not _can_edit(act):
        abort(403)
    if request.method == "POST":
        ok, msg = _save(act)
        flash(msg, "success" if ok else "danger")
        if ok:
            return redirect(url_for("activities.index"))
    return render_template("activities/form.html", activity=act,
                           interns=_selectable_interns(),
                           categories=Category.query.order_by(Category.name).all(),
                           statuses=STATUSES)


@bp.route("/<int:activity_id>/eliminar", methods=["POST"])
@login_required
def delete(activity_id):
    act = Activity.query.get_or_404(activity_id)
    if not _can_edit(act):
        abort(403)
    db.session.delete(act)
    db.session.commit()
    audit("ACTIVITY_DELETE", "activity", activity_id, act.title)
    flash("Registro eliminado.", "success")
    return redirect(url_for("activities.index"))


@bp.route("/<int:activity_id>/revisar", methods=["POST"])
@login_required
@role_required("admin", "supervisor")
def review(activity_id):
    act = Activity.query.get_or_404(activity_id)
    if current_user.is_supervisor:
        if not current_user.intern_scope(act.intern_id):
            abort(403)
    decision = request.form.get("decision")
    note = request.form.get("review_note", "").strip()
    if decision not in ("Aprobada", "Rechazada"):
        abort(400)
    act.status = decision
    act.reviewed_by = current_user.id
    act.reviewed_at = datetime.utcnow()
    act.review_note = note
    db.session.commit()
    audit("ACTIVITY_REVIEW", "activity", act.id, f"{decision} — {note}")
    flash(f"Actividad marcada como «{decision}».", "success")
    return redirect(request.referrer or url_for("activities.index"))


# ---------- helpers ----------

def _selectable_interns():
    if current_user.is_admin:
        return Intern.query.filter_by(active=True).order_by(Intern.full_name).all()
    if current_user.is_intern and current_user.intern:
        return [current_user.intern]
    return []


def _save(act):
    try:
        title = request.form.get("title", "").strip()
        if not title:
            return False, "El nombre de la actividad es obligatorio."

        intern_id = request.form.get("intern_id", type=int)
        if not intern_id:
            return False, "Debes seleccionar un practicante."
        allowed = {i.id for i in _selectable_interns()}
        if intern_id not in allowed:
            return False, "Practicante no válido para tu usuario."

        date_str = request.form.get("activity_date", "")
        try:
            adate = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return False, "Fecha inválida."

        start = _parse_time(request.form.get("start_time"))
        end = _parse_time(request.form.get("end_time"))
        hours = compute_hours(start, end)
        if hours is None:
            hours = request.form.get("hours", type=float) or 0
        if hours < 0 or hours > 24:
            return False, "Las horas deben estar entre 0 y 24."

        if act is None:
            act = Activity()
            db.session.add(act)

        act.intern_id = intern_id
        act.activity_date = adate
        act.start_time = start
        act.end_time = end
        act.title = title[:180]
        act.description = request.form.get("description", "").strip()
        act.observations = request.form.get("observations", "").strip()
        act.category_id = request.form.get("category_id", type=int) or None
        act.hours = hours

        if current_user.is_admin:
            st = request.form.get("status", "Pendiente")
            act.status = st if st in STATUSES else "Pendiente"
        elif act.id is None:
            act.status = "Pendiente"

        db.session.commit()
        audit("ACTIVITY_SAVE", "activity", act.id, act.title)
        return True, "Registro guardado correctamente."
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return False, f"No se pudo guardar: {exc}"


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None