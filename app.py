import secrets

from flask import Flask, render_template, redirect, url_for, send_from_directory, jsonify
from flask_login import LoginManager, current_user, login_user

from config import Config
from models import db, User
from controllers import auth_bp, dashboard_bp, friends_bp, groups_bp, profile_bp, admin_bp, import_bp, notifications_bp
from services.activity_service import ActivityService
from services.reminder_scheduler import start_reminder_scheduler
import sso_client


def _create_planowiec_user(hub_username: str):
    """Zakłada w Planowcu nowe lokalne konto dla usera z LoginHub, który
    jeszcze nie miał tu żadnego konta (wywoływane przez
    sso_client.resolve_or_create_local_user przy pierwszej wizycie).
    Hasło jest losowe i nieznane nikomu — logowanie idzie wyłącznie przez SSO.
    get-or-create po username, żeby nie tworzyć duplikatu przy ewentualnym
    powtórnym wywołaniu (np. gdy zgłoszenie do Huba nie doszło za pierwszym razem).
    """
    existing = User.query.filter_by(username=hub_username).first()
    if existing:
        return existing.id, existing.username

    username = hub_username
    suffix = 1
    while User.query.filter_by(username=username).first():
        suffix += 1
        username = f"{hub_username}{suffix}"

    # email jest w Planowcu wymagany i unikalny, a Hub go nie zna —
    # generujemy placeholder, user może go później zmienić w profilu.
    email = f"{username}@sso.local"
    while User.query.filter_by(email=email).first():
        suffix += 1
        email = f"{hub_username}{suffix}@sso.local"

    user = User(username=username, email=email, display_name=hub_username)
    user.set_password(secrets.token_urlsafe(24))
    db.session.add(user)
    db.session.commit()
    return user.id, user.username


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

    # --- SSO (LoginHub) ---------------------------------------------------
    # Jeśli user nie jest zalogowany lokalnie, sprawdź czy ma ważne ciasteczko
    # LoginHub. Jeśli jego konto jest już połączone z planowcem — zaloguj go
    # lokalnie (login_user). Jeśli NIE jest jeszcze połączone —
    # resolve_or_create_local_user samo zakłada tu dla niego nowe konto
    # (_create_planowiec_user) i zgłasza połączenie do Huba, więc nie trzeba
    # czekać na ręczne sparowanie kont w panelu /admin Huba. Zwykłe logowanie
    # hasłem (/auth/login, /auth/register) zostaje bez zmian jako plan B.
    @app.before_request
    def _sso_autologin():
        if current_user.is_authenticated:
            return
        local_id = sso_client.resolve_or_create_local_user(
            app_slug="planowiec", create_user=_create_planowiec_user
        )
        if local_id:
            user = User.query.get(local_id)
            if user:
                login_user(user)

    @login_manager.unauthorized_handler
    def _unauthorized():
        from flask import request
        # UWAGA: Tailscale Serve/Funnel z --set-path ścina prefiks (np. /planowiec)
        # zanim żądanie trafi do Flaska, więc request.path go NIE zawiera (patrz
        # docstring PrefixMiddleware niżej w tym pliku). PrefixMiddleware wpisuje
        # prefiks do SCRIPT_NAME, więc request.script_root go ma — doklejamy
        # ręcznie, inaczej LoginHub po zalogowaniu odeśle poza appkę (np. na
        # /dashboard/ zamiast /planowiec/dashboard/).
        next_path = request.script_root + request.path
        return redirect(sso_client.login_url(next_path))

    # Blueprinty — wszystkie prefiksy URL po angielsku
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(notifications_bp)

    @app.route("/")
    def root():
        return redirect(url_for("dashboard.index"))

    # Service Worker — musi być serwowany z roota (nie z /static/js/...),
    # żeby jego scope obejmował całą appkę, w tym ewentualny PREFIX
    # (patrz PrefixMiddleware niżej). Bez tego nagłówka przeglądarka
    # ograniczyłaby scope tylko do /static/js/.
    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory("static/js", "sw.js")
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    # Web App Manifest — generowany dynamicznie, bo start_url/scope MUSZĄ
    # być bezwzględnymi ścieżkami widzianymi przez przeglądarkę (z ewentualnym
    # prefiksem, np. /planowiec pod Tailscale Serve --set-path), inaczej
    # instalacja jako PWA się nie powiedzie. Statyczny plik nie mógłby
    # zawrzeć PREFIX bez przebudowy przy każdej zmianie konfiguracji.
    @app.route("/manifest.json")
    def web_app_manifest():
        prefix = (app.config.get("PREFIX") or "").rstrip("/")
        manifest = {
            "name": "Planowiec",
            "short_name": "Planowiec",
            "description": "Planuj czas z przyjaciółmi — kalendarz osobisty, znajomi i grupy.",
            "start_url": f"{prefix}/",
            "scope": f"{prefix}/",
            "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#0f172a",
            "theme_color": "#2563eb",
            "icons": [
                {"src": f"{prefix}/static/img/icon-72.png", "sizes": "72x72", "type": "image/png", "purpose": "any"},
                {"src": f"{prefix}/static/img/icon-96.png", "sizes": "96x96", "type": "image/png", "purpose": "any"},
                {"src": f"{prefix}/static/img/icon-144.png", "sizes": "144x144", "type": "image/png", "purpose": "any"},
                {"src": f"{prefix}/static/img/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": f"{prefix}/static/img/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        response = jsonify(manifest)
        response.headers["Content-Type"] = "application/manifest+json"
        return response

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


def _ensure_new_columns(app: Flask) -> None:
    """
    Lekka, poor-man's migracja: projekt nie używa Alembica, a `db.create_all()`
    tworzy WYŁĄCZNIE brakujące tabele — nie dokłada nowych kolumn do tabel,
    które już istnieją w bazie. Żeby aktualizacja do wersji z rolami grup /
    "Wszystkie plany" / kategoriami grupowymi nie wymagała ręcznych ALTER-ów
    ani kasowania bazy, sprawdzamy tu brakujące kolumny i dodajemy je sami.
    Bezpieczne do wielokrotnego uruchamiania (sprawdza istnienie przed dodaniem).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    additions = {
        "users": [
            ("show_all_plans", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("push_subscription", "TEXT"),
            ("notify_new_activities", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("notify_new_activities_minutes", "INTEGER NOT NULL DEFAULT 30"),
            ("group_notification_pref", "VARCHAR(20) NOT NULL DEFAULT 'all'"),
            ("notifications_muted_until", "TIMESTAMP"),
            ("notify_comments", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ],
        "activity_types": [("group_id", "INTEGER")],
        "activities": [
            ("recurrence_id", "VARCHAR(36)"),
            ("external_ref", "VARCHAR(120)"),
            ("notify_before_minutes", "INTEGER"),
            ("reminder_sent_at", "TIMESTAMP"),
        ],
        "plan_access": [("role", "VARCHAR(20) NOT NULL DEFAULT 'viewer'")],
        "group_members": [("notifications_enabled", "BOOLEAN NOT NULL DEFAULT TRUE")],
    }

    with db.engine.begin() as conn:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_def in columns:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def init_db(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        _ensure_new_columns(app)
        ActivityService.ensure_default_types()
    start_reminder_scheduler(app)


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
