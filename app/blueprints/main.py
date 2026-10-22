from datetime import date
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db
from ..models import Activity, Intern, get_setting

bp = Blueprint("main", __name__)

MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
          "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


@bp.route("/")
@login_required
def dashboard():
    if current_user.is_intern:
        intern = current_user.intern
        interns = [intern] if intern else []
    elif current_user.is_supervisor:
        interns = current_user.supervised_interns.all()
    else:
        interns = Intern.query.filter_by(active=True).all()

    ids = [i.id for i in interns]
    q = Activity.query.filter(Activity.intern_id.in_(ids)) if ids else Activity.query.filter(db.false())

    total = q.count()
    approved = q.filter(Activity.status == "Aprobada").count()
    pending = q.filter(Activity.status == "Pendiente").count()
    hours = db.session.query(func.coalesce(func.sum(Activity.hours), 0.0)) \
        .filter(Activity.intern_id.in_(ids) if ids else db.false(),
                Activity.status == "Aprobada").scalar()

    target = sum(i.target_hours for i in interns) or float(
        get_setting("default_target_hours", "400"))
    pct = min(100, round(hours / target * 100, 1)) if target else 0

    # Actividad por mes (últimos 6 meses, solo aprobadas)
    monthly = []
    today = date.today()
    for i in range(5, -1, -1):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((i - today.month + 1) // 12 + (1 if today.month - i <= 0 else 0))
        h = db.session.query(func.coalesce(func.sum(Activity.hours), 0.0)).filter(
            Activity.intern_id.in_(ids) if ids else db.false(),
            Activity.status == "Aprobada",
            func.strftime("%Y-%m", Activity.activity_date) == f"{y:04d}-{m:02d}"
        ).scalar()
        monthly.append({"label": f"{MONTHS[m-1]} {str(y)[2:]}", "hours": round(h, 1)})
    max_h = max([m["hours"] for m in monthly] + [1])

    recent = (q.order_by(Activity.activity_date.desc(), Activity.id.desc()).limit(8).all())

    return render_template("main/dashboard.html", interns=interns, total=total,
                           approved=approved, pending=pending, hours=round(hours, 1),
                           target=target, pct=pct, recent=recent,
                           monthly=monthly, max_h=max_h)