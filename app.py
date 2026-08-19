from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager

from config import Config
from models import db, User
from controllers import auth_bp, dashboard_bp, friends_bp, groups_bp, profile_bp, admin_bp
from services.activity_service import ActivityService


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Rozszerzenia
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Zaloguj się, aby uzyskać dostęp."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprinty — wszystkie prefiksy URL po angielsku
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def root():
        return redirect(url_for("dashboard.index"))

    # Obsługa błędów
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="Brak dostępu do tego zasobu."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Nie znaleziono strony."), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, message="Błąd serwera."), 500

    return app


def init_db(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        ActivityService.ensure_default_types()


def create_wsgi_app(config_class=Config):
    """
    Buduje finalną aplikację WSGI, uwzględniając ewentualny PREFIX
    (np. do wystawienia pod Tailscale Serve/Funnel pod ścieżką inną niż "/",
    żeby nie kolidować z inną appką na tej samej domenie).

    WAŻNE (zweryfikowane w praktyce): Tailscale Serve z opcją --set-path
    ŚCINA prefiks z URL-a zanim przekaże request dalej do backendu —
    backend dostaje ścieżkę BEZ prefiksu (np. /dashboard/... a nie
    /planowiec/dashboard/...). Dlatego routing we Flasku musi zostać
    bez zmian (blueprinty zarejestrowane bez prefiksu), a jedyne co
    trzeba doklejić to prefiks w generowanych linkach (url_for, redirecty,
    linki do plików statycznych) — inaczej przeglądarka "wypadnie"
    spod /planowiec przy pierwszym kliknięciu/przekierowaniu.

    Realizujemy to przez ustawienie WSGI environ["SCRIPT_NAME"] = PREFIX,
    NIE ruszając PATH_INFO. Flask użyje SCRIPT_NAME do generowania
    poprawnych, prefiksowanych adresów (url_for, request.script_root),
    a dopasowywanie tras dalej odbywa się na podstawie (nieprefiksowanego)
    PATH_INFO, dokładnie tak jak przychodzi z Tailscale.
    """
    flask_app = create_app(config_class)
    init_db(flask_app)

    prefix = (flask_app.config.get("PREFIX") or "").rstrip("/")
    if not prefix:
        return flask_app

    if not prefix.startswith("/"):
        prefix = "/" + prefix

    return PrefixMiddleware(flask_app, prefix)


class PrefixMiddleware:
    """Doklein prefiks do SCRIPT_NAME, nie ruszając PATH_INFO.

    Używane, gdy reverse proxy (Tailscale Serve --set-path) ścina prefiks
    z requestu, zanim ten trafi do appki, ale appka i tak ma generować
    linki/przekierowania z tym prefiksem, żeby przeglądarka została pod
    właściwym adresem.
    """

    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


if __name__ == "__main__":
    application = create_wsgi_app()
    if isinstance(application, Flask):
        application.run(host="0.0.0.0", port=5000, debug=True)
    else:
        # Aplikacja owinięta w PrefixMiddleware (ustawiony PREFIX) —
        # to już nie jest obiekt Flask, więc odpalamy ją przez werkzeug.
        from werkzeug.serving import run_simple
        run_simple("0.0.0.0", 5000, application, use_reloader=True, use_debugger=True)
