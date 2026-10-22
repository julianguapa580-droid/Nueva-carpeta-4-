import csv
import io
from datetime import date
from flask import Blueprint, render_template, request, Response, send_file
from flask_login import login_required, current_user
from ..models import Activity, Intern, Category, get_setting
from ..utils import role_required

bp = Blueprint("reports", __name__)


def _scope(intern_id=None):
    q = Activity.query
    if current_user.is_intern:
        iid = current_user.intern.id if current_user.intern else -1
        q = q.filter(Activity.intern_id == iid)
    elif current_user.is_supervisor:
        ids = [i.id for i in current_user.supervised_interns.all()] or [-1]
        q = q.filter(Activity.intern_id.in_(ids))
    if intern_id:
        q = q.filter(Activity.intern_id == intern_id)
    return q.order_by(Activity.activity_date, Activity.id)


def _interns_for_select():
    if current_user.is_admin:
        return Intern.query.order_by(Intern.full_name).all()
    if current_user.is_supervisor:
        return current_user.supervised_interns.order_by(Intern.full_name).all()
    return [current_user.intern] if current_user.intern else []


@bp.route("/")
@login_required
def index():
    intern_id = request.args.get("intern_id", type=int)
    status = request.args.get("status", "")
    q = _scope(intern_id)
    if status:
        q = q.filter(Activity.status == status)
    activities = q.all()
    totals = {
        "count": len(activities),
        "hours": round(sum(a.hours for a in activities), 2),
        "approved": round(sum(a.hours for a in activities if a.status == "Aprobada"), 2),
    }
    intern = Intern.query.get(intern_id) if intern_id else None
    return render_template("reports/report.html", activities=activities, totals=totals,
                           intern=intern, interns=_interns_for_select(),
                           status=status, municipality=get_setting("municipality"),
                           area=get_setting("area"),
                           footer=get_setting("report_footer"),
                           today=date.today())


@bp.route("/csv")
@login_required
def csv_export():
    activities = _scope(request.args.get("intern_id", type=int)).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ID", "Fecha", "Practicante", "Actividad", "Categoría",
                "Horas", "Estado", "Observaciones", "Revisado por"])
    for a in activities:
        w.writerow([a.id, a.activity_date, a.intern.full_name, a.title,
                    a.category.name if a.category else "",
                    a.hours, a.status, a.observations,
                    a.reviewer.full_name if a.reviewer else ""])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             "attachment; filename=actividades.csv"})


@bp.route("/pdf")
@login_required
def pdf_export():
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    activities = _scope(request.args.get("intern_id", type=int)).all()
    intern = Intern.query.get(request.args.get("intern_id", type=int))

    pdf = FPDF()
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "REPORTE DE ACTIVIDADES DE PRACTICAS",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _txt(get_setting("municipality")),
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _txt(get_setting("area")),
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    if intern:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, _txt(f"Practicante: {intern.full_name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 5, _txt(f"Area: {intern.area or '-'} | Meta: {intern.target_hours:g} h"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, f"Emitido: {date.today():%d/%m/%Y}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    widths = (20, 78, 30, 16, 24)
    headers = ("Fecha", "Actividad", "Categoria", "Horas", "Estado")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(18, 48, 74)
    pdf.set_text_color(255, 255, 255)
    for wd, h in zip(widths, headers):
        pdf.cell(wd, 7, h, border=1, align="C", fill=True,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 8)

    total = 0
    for a in activities:
        if a.status == "Aprobada":
            total += a.hours
        row = (
            a.activity_date.strftime("%d/%m/%Y"),
            _cut(a.title, 55),
            _cut(a.category.name if a.category else "-", 20),
            f"{a.hours:g}",
            a.status,
        )
        for wd, val in zip(widths, row):
            pdf.cell(wd, 6, _txt(val), border=1,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"Horas aprobadas: {total:g} h  |  Registros: {len(activities)}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(18)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(85, 5, "_____________________________", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(85, 5, "_____________________________", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(85, 5, "Supervisor / Responsable", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(85, 5, "Jefe de Area", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    out = pdf.output()
    return send_file(io.BytesIO(bytes(out)), mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"reporte_practicas_{date.today():%Y%m%d}.pdf")


def _txt(s):
    return str(s or "").encode("latin-1", "replace").decode("latin-1")


def _cut(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"