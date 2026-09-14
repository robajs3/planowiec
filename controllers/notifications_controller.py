from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user

from models import db, GroupMember
from services.notification_service import NotificationService, MAX_MUTE_MINUTES
from services.group_service import GroupService

notifications_bp = Blueprint("notifications", __name__)

# Opcje czasu wyciszenia pokazywane w formularzu — (etykieta, minuty).
# Zgodnie z wymaganiem: maksymalnie 1 dzień (MAX_MUTE_MINUTES = 1440).
MUTE_OPTIONS = [
    ("30 minut", 30),
    ("1 godzina", 60),
    ("2 godziny", 120),
    ("4 godziny", 240),
    ("8 godzin", 480),
    ("1 dzień", MAX_MUTE_MINUTES),
]


@notifications_bp.route("/notifications/")
@login_required
def index():
    """Zakładka „Powiadomienia" — lista poprzednich powiadomień (historia)."""
    notifications = NotificationService.list_notifications(current_user)
    return render_template("notifications/history.html", notifications=notifications)


@notifications_bp.route("/notifications/settings")
@login_required
def settings():
    """Druga zakładka pod Powiadomieniami — wszystkie ustawienia
    powiadomień, przeniesione tutaj z Profilu."""
    groups = GroupService.list_user_groups(current_user.id)
    memberships = {
        m.group_id: m
        for m in GroupMember.query.filter_by(user_id=current_user.id).all()
    }
    return render_template(
        "notifications/settings.html",
        groups=groups,
        memberships=memberships,
        mute_options=MUTE_OPTIONS,
        max_mute_minutes=MAX_MUTE_MINUTES,
        is_muted=NotificationService.is_muted(current_user),
    )


# ---------------------------------------------------------------------------
# Web Push — subskrypcja (przeniesione z /profile/*)
# ---------------------------------------------------------------------------

@notifications_bp.route("/notifications/vapid-public-key")
@login_required
def vapid_public_key():
    return jsonify({"publicKey": current_app.config.get("VAPID_PUBLIC_KEY", "")})


@notifications_bp.route("/notifications/push-subscribe", methods=["POST"])
@login_required
def push_subscribe():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("endpoint"):
        return jsonify({"error": "Nieprawidłowa subskrypcja."}), 400
    NotificationService.save_subscription(current_user, data)
    return jsonify({"ok": True})


@notifications_bp.route("/notifications/push-unsubscribe", methods=["POST"])
@login_required
def push_unsubscribe():
    NotificationService.clear_subscription(current_user)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Ustawienia — powiadomienia o nowo dodanych aktywnościach (prywatny plan)
# ---------------------------------------------------------------------------

@notifications_bp.route("/notifications/settings/new-activities", methods=["POST"])
@login_required
def update_new_activities():
    current_user.notify_new_activities = request.form.get("enabled") == "on"
    db.session.commit()
    flash(
        "Włączono powiadomienia dla nowo dodawanych aktywności." if current_user.notify_new_activities
        else "Wyłączono powiadomienia dla nowo dodawanych aktywności.",
        "success",
    )
    return redirect(url_for("notifications.settings"))


@notifications_bp.route("/notifications/settings/new-activities/minutes", methods=["POST"])
@login_required
def update_new_activities_minutes():
    try:
        minutes = int(request.form.get("minutes", 30))
    except (TypeError, ValueError):
        minutes = 30
    if minutes > 0:
        current_user.notify_new_activities_minutes = minutes
        db.session.commit()
        flash("Zaktualizowano domyślny czas przypomnienia.", "success")
    return redirect(url_for("notifications.settings"))


# ---------------------------------------------------------------------------
# Ustawienia — powiadomienia o komentarzach
# ---------------------------------------------------------------------------

@notifications_bp.route("/notifications/settings/comments", methods=["POST"])
@login_required
def update_comments_pref():
    current_user.notify_comments = request.form.get("enabled") == "on"
    db.session.commit()
    flash(
        "Włączono powiadomienia o komentarzach." if current_user.notify_comments
        else "Wyłączono powiadomienia o komentarzach.",
        "success",
    )
    return redirect(url_for("notifications.settings"))


# ---------------------------------------------------------------------------
# Ustawienia — powiadomienia z grup
# ---------------------------------------------------------------------------

@notifications_bp.route("/notifications/settings/groups", methods=["POST"])
@login_required
def update_group_pref():
    """Master switch: włącza/wyłącza WSZYSTKIE powiadomienia z grup naraz.
    Gdy włączony, o każdej grupie z osobna nadal decyduje jej przełącznik
    (patrz groups.toggle_notifications) — ten switch jest nadrzędnym
    wyłącznikiem, a nie kolejnym trybem do wyboru."""
    current_user.group_notification_pref = "selected" if request.form.get("enabled") == "on" else "none"
    db.session.commit()
    flash(
        "Włączono powiadomienia z grup." if current_user.group_notification_pref != "none"
        else "Wyłączono wszystkie powiadomienia z grup.",
        "success",
    )
    return redirect(url_for("notifications.settings"))


# ---------------------------------------------------------------------------
# Chwilowe wyciszenie powiadomień (max 1 dzień) + anulowanie
# ---------------------------------------------------------------------------

@notifications_bp.route("/notifications/mute", methods=["POST"])
@login_required
def mute():
    try:
        minutes = int(request.form.get("minutes", 60))
    except (TypeError, ValueError):
        minutes = 60
    minutes = max(1, min(minutes, MAX_MUTE_MINUTES))
    NotificationService.mute(current_user, minutes)
    if minutes % 60 == 0:
        label = f"{minutes // 60} h"
    else:
        label = f"{minutes} min"
    flash(f"Powiadomienia wyciszone na {label}.", "success")
    return redirect(url_for("notifications.settings"))


@notifications_bp.route("/notifications/unmute", methods=["POST"])
@login_required
def unmute():
    NotificationService.unmute(current_user)
    flash("Wyciszenie powiadomień anulowane.", "info")
    return redirect(url_for("notifications.settings"))
