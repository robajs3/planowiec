from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

import re

from models import db, User
from models.user_model import AVATAR_PALETTE

profile_bp = Blueprint("profile", __name__)

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@profile_bp.route("/profile/")
@login_required
def index():
    return render_template("profile/profile.html", palette=AVATAR_PALETTE)


@profile_bp.route("/pomoc/instalacja")
@login_required
def install_app():
    return render_template("profile/install_app.html")


@profile_bp.route("/profile/update", methods=["POST"])
@login_required
def update():
    display_name = request.form.get("display_name", "").strip()
    avatar_color = request.form.get("avatar_color", "").strip()

    current_user.display_name = display_name or None
    # Dopuszczamy każdy poprawny kolor hex (#rrggbb) — nie tylko te z
    # domyślnej palety — żeby użytkownik mógł ustawić dowolny, customowy kolor.
    if _HEX_COLOR_RE.match(avatar_color):
        current_user.avatar_color = avatar_color.lower()
    db.session.commit()
    flash("Zaktualizowano profil.", "success")
    return redirect(url_for("profile.index"))


@profile_bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    old = request.form.get("old_password", "")
    new = request.form.get("new_password", "")
    new2 = request.form.get("new_password2", "")

    if not current_user.check_password(old):
        flash("Stare hasło jest nieprawidłowe.", "danger")
    elif len(new) < 8:
        flash("Nowe hasło musi mieć co najmniej 8 znaków.", "danger")
    elif new != new2:
        flash("Nowe hasła nie są identyczne.", "danger")
    else:
        current_user.set_password(new)
        db.session.commit()
        flash("Hasło zostało zmienione.", "success")
    return redirect(url_for("profile.index"))
