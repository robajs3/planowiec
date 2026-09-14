"""
Web Push (VAPID) — powiadomienia o zbliżających się aktywnościach.

Ten plik odpowiada za: zapisywanie subskrypcji, wysyłkę pojedynczego
powiadomienia, chwilowe wyciszenie powiadomień oraz historię powiadomień
(lista w zakładce „Powiadomienia"). O tym, KIEDY wysłać przypomnienie o
aktywności (sprawdzanie czasu, zapobieganie podwójnej wysyłce) odpowiada
services/reminder_scheduler.py.
"""
import json
from datetime import datetime, timedelta

from flask import current_app
from pywebpush import webpush, WebPushException

from models import db, Notification, GroupMember

# Maksymalny czas chwilowego wyciszenia powiadomień — 1 dzień (patrz
# NotificationService.mute i /notifications/mute).
MAX_MUTE_MINUTES = 24 * 60


class NotificationService:

    @staticmethod
    def save_subscription(user, subscription_info: dict) -> None:
        user.push_subscription = json.dumps(subscription_info)
        db.session.commit()

    @staticmethod
    def clear_subscription(user) -> None:
        user.push_subscription = None
        db.session.commit()

    # ---------- chwilowe wyciszenie powiadomień ----------
    @staticmethod
    def is_muted(user) -> bool:
        return bool(user and user.notifications_muted_until and user.notifications_muted_until > datetime.utcnow())

    @staticmethod
    def mute(user, minutes: int) -> None:
        """Wycisza powiadomienia push na `minutes` minut (max 1 dzień —
        wartości spoza zakresu są przycinane, nie odrzucane)."""
        minutes = max(1, min(int(minutes), MAX_MUTE_MINUTES))
        user.notifications_muted_until = datetime.utcnow() + timedelta(minutes=minutes)
        db.session.commit()

    @staticmethod
    def unmute(user) -> None:
        user.notifications_muted_until = None
        db.session.commit()

    # ---------- historia powiadomień ----------
    @staticmethod
    def log_notification(user, title: str, body: str | None = None,
                          link: str | None = None, kind: str = "reminder") -> Notification:
        entry = Notification(user_id=user.id, title=title, body=body, link=link, kind=kind)
        db.session.add(entry)
        db.session.commit()
        return entry

    @staticmethod
    def list_notifications(user, limit: int = 100):
        return (
            Notification.query.filter_by(user_id=user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def unread_count(user) -> int:
        return Notification.query.filter_by(user_id=user.id, read_at=None).count()

    @staticmethod
    def mark_all_read(user) -> None:
        Notification.query.filter_by(user_id=user.id, read_at=None).update({"read_at": datetime.utcnow()})
        db.session.commit()

    @staticmethod
    def send_push(user, title: str, body: str, link: str | None = None,
                   kind: str = "reminder", log: bool = True) -> bool:
        """Wysyła pojedyncze powiadomienie push do danego usera.
        Zwraca True, jeśli faktycznie wysłano (user miał aktywną subskrypcję,
        nie ma aktywnego wyciszenia, a serwer push ją zaakceptował).

        Zapisuje wpis w historii powiadomień (Notification) niezależnie od
        tego, czy sama wysyłka push się powiodła — dzięki temu lista w
        zakładce „Powiadomienia" jest kompletna nawet bez włączonego web
        pusha. Wyjątek: gdy powiadomienia są chwilowo WYCISZONE, w ogóle nie
        próbujemy wysyłki push, ale wpis w historii i tak zostaje zapisany."""
        if not user:
            return False
        if log:
            NotificationService.log_notification(user, title, body, link, kind=kind)

        if NotificationService.is_muted(user):
            return False
        if not user.push_subscription:
            return False

        vapid_private = current_app.config.get("VAPID_PRIVATE_KEY")
        vapid_public = current_app.config.get("VAPID_PUBLIC_KEY")
        if not vapid_private or not vapid_public:
            current_app.logger.warning("Push pominięty — brak VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY w konfiguracji.")
            return False

        try:
            subscription_info = json.loads(user.push_subscription)
        except (TypeError, ValueError):
            NotificationService.clear_subscription(user)
            return False

        prefix = (current_app.config.get("PREFIX") or "").rstrip("/")
        vapid_claims = {"sub": f"mailto:{current_app.config.get('VAPID_CLAIMS_EMAIL', 'admin@planowiec.local')}"}

        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps({"title": title, "body": body, "link": link or f"{prefix}/"}),
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims,
            )
            return True
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # Subskrypcja wygasła / przeglądarka ją unregisterowała —
                # czyścimy, żeby nie próbować przy każdym kolejnym przypomnieniu.
                NotificationService.clear_subscription(user)
            current_app.logger.warning(f"Push notification failed for user {user.id}: {e}")
            return False
        except Exception as e:
            current_app.logger.warning(f"Push notification failed for user {user.id}: {e}")
            return False

    @staticmethod
    def send_activity_reminder(activity) -> bool:
        """Wysyła przypomnienie o konkretnej aktywności do jej właściciela
        (tylko plany prywatne — group_id is None; aktywności grupowe nie
        mają jednego właściciela do powiadomienia, patrz reminder_scheduler)."""
        if not activity.owner_id or activity.group_id is not None:
            return False
        prefix = (current_app.config.get("PREFIX") or "").rstrip("/")
        when = activity.start_time.strftime("%H:%M")
        body = f"{when}" + (f" — {activity.location}" if activity.location else "")
        return NotificationService.send_push(
            user=activity.owner,
            title=f"⏰ {activity.title}",
            body=body,
            link=f"{prefix}/dashboard/",
            kind="reminder",
        )

    @staticmethod
    def notify_group_new_activity(activity) -> int:
        """Powiadamia członków grupy o nowo dodanej aktywności w jej planie,
        zgodnie z indywidualnymi ustawieniami każdego z nich:
          - User.group_notification_pref == "none"     -> pomiń
          - User.group_notification_pref == "all"      -> powiadom
          - User.group_notification_pref == "selected" -> powiadom tylko,
            gdy GroupMember.notifications_enabled == True dla TEJ grupy
        Autor aktywności (activity.owner_id — dla wpisów grupowych to pole
        przechowuje twórcę, patrz komentarz w dashboard_controller) nie
        dostaje powiadomienia o własnym wpisie. Zwraca liczbę wysłanych push.
        """
        if activity.group_id is None:
            return 0
        prefix = (current_app.config.get("PREFIX") or "").rstrip("/")
        link = f"{prefix}/dashboard/group/{activity.group_id}"
        title = "🧩 Nowa aktywność w grupie"
        body = activity.title + (f" · {activity.location}" if activity.location else "")

        members = GroupMember.query.filter_by(group_id=activity.group_id).all()
        sent = 0
        for member in members:
            if member.user_id == activity.owner_id:
                continue
            user = member.user
            if not user:
                continue
            pref = user.group_notification_pref
            if pref == "none":
                continue
            if pref == "selected" and not member.notifications_enabled:
                continue
            if NotificationService.send_push(user, title, body, link=link, kind="group_activity"):
                sent += 1
        return sent
