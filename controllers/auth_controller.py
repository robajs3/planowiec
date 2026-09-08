from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response
from flask_login import login_user, logout_user, login_required, current_user

from services.auth_service import AuthService
import sso_client

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        error = AuthService.validate_registration(username, email, password, password2)
        if error:
            flash(error, "danger")
        else:
            user = AuthService.register_user(username, email, password, display_name)
            login_user(user)
            flash("Witaj w Planowcu! Twoje konto zostało utworzone.", "success")
            return redirect(url_for("dashboard.index"))

    return render_template("auth/register.html")


@auth_bp.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        user = AuthService.authenticate(identifier, password)
        if user:
            login_user(user, remember=bool(request.form.get("remember")))
            flash(f"Witaj z powrotem, {user.name}!", "success")
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        flash("Nieprawidłowy login lub hasło.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/auth/logout")
@login_required
def logout():
    # Wylogowanie musi być globalne (ze wszystkich appek naraz): oprócz
    # lokalnej sesji Flask-Login czyścimy ciasteczko SSO LoginHub i odsyłamy
    # na ekran logowania LOGINHUB (nie na lokalny /auth/login) — inaczej
    # ciasteczko sso_session i tak by zostało ważne i _sso_autologin
    # zalogowałby z powrotem przy następnym wejściu na dowolną appkę SSO.
    # next_path budujemy przez url_for (nie na sztywno "/planowiec/"),
    # żeby poprawnie uwzględniał PREFIX z PrefixMiddleware.
    next_path = url_for("dashboard.index")
    response = make_response(redirect(sso_client.login_url(next_path)))
    sso_client.clear_sso_cookie(response)
    logout_user()
    return response
