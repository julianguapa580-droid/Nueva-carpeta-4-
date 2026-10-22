from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager

ROLES = ("admin", "supervisor", "practicante")
STATUSES = ("Pendiente", "Aprobada", "Rechazada")

DEFAULTS = {
    "municipality": "Municipalidad Provincial",
    "area": "Mesa de partes / Atención al ciudadano",
    "report_footer": "",
    "default_target_hours": "400",
}


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    email = db.Column(db.String(160), unique=True)
    full_name = db.Column(db.String(160), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="practicante")
    active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)

    intern = db.relationship("Intern", foreign_keys="Intern.user_id",
                             back_populates="user", uselist=False)

    # --- Password ---
    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    # --- Flask-Login ---
    @property
    def is_active(self):
        return self.active

    # --- Helpers ---
    def is_locked(self):
        return self.locked_until is not None and self.locked_until > datetime.utcnow()

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_supervisor(self):
        return self.role == "supervisor"

    @property
    def is_intern(self):
        return self.role == "practicante"

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Intern(TimestampMixin, db.Model):
    __tablename__ = "interns"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    full_name = db.Column(db.String(160), nullable=False)
    dni = db.Column(db.String(20))
    career = db.Column(db.String(120))
    institution = db.Column(db.String(160))
    area = db.Column(db.String(160))
    supervisor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    target_hours = db.Column(db.Float, nullable=False, default=400)
    active = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", foreign_keys=[user_id], back_populates="intern")
    supervisor = db.relationship("User", foreign_keys=[supervisor_id],
                                 backref=db.backref("supervised_interns", lazy="dynamic"))
    activities = db.relationship("Activity", back_populates="intern",
                                 cascade="all, delete-orphan")

    @property
    def approved_hours(self):
        return round(sum(a.hours for a in self.activities if a.status == "Aprobada"), 2)

    @property
    def total_hours(self):
        return round(sum(a.hours for a in self.activities), 2)

    @property
    def progress(self):
        if not self.target_hours:
            return 0
        return min(100, round(self.approved_hours / self.target_hours * 100, 1))


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    color = db.Column(db.String(9), default="#1769aa")


class Activity(TimestampMixin, db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("interns.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"))
    activity_date = db.Column(db.Date, nullable=False, default=date.today)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    hours = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Pendiente")
    observations = db.Column(db.Text, default="")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    review_note = db.Column(db.Text, default="")

    intern = db.relationship("Intern", back_populates="activities")
    category = db.relationship("Category")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(60))
    action = db.Column(db.String(60), nullable=False)
    entity = db.Column(db.String(40))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text, default="")


def get_setting(key, default=None):
    row = db.session.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, default)


def set_setting(key, value):
    row = db.session.get(Setting, key)
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def intern_scope(self, intern_id):
    return any(i.id == intern_id for i in self.supervised_interns.all())