import secrets
import click
from datetime import date, timedelta
from flask.cli import with_appcontext
from .extensions import db
from .models import User, Intern, Category, Activity, set_setting


def register(app):
    app.cli.add_command(init_db)
    app.cli.add_command(seed_demo)


@click.command("init-db")
@with_appcontext
def init_db():
    """Crea las tablas y el usuario administrador inicial."""
    db.create_all()
    if not User.query.filter_by(role="admin").first():
        pwd = secrets.token_urlsafe(12)
        admin = User(username="admin", full_name="Administrador del sistema",
                     role="admin", must_change_password=True)
        admin.set_password(pwd)
        db.session.add(admin)
        for key, val in (("municipality", "Municipalidad Provincial"),
                         ("area", "Mesa de partes / Atención al ciudadano"),
                         ("default_target_hours", "400")):
            set_setting(key, val)
        db.session.commit()
        click.secho("\n  Usuario: admin", fg="green", bold=True)
        click.secho(f"  Contraseña temporal: {pwd}", fg="yellow", bold=True)
        click.secho("  (se pedirá cambiarla al primer ingreso)\n")
    else:
        click.echo("La base de datos ya estaba inicializada.")


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Carga datos de demostración."""
    for name, color in (("Atención al ciudadano", "#1769aa"),
                        ("Archivo y digitalización", "#198754"),
                        ("Apoyo administrativo", "#b45309"),
                        ("Campañas y field work", "#7c3aed")):
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, color=color))
    db.session.commit()
    click.echo("Categorías de demostración creadas.")