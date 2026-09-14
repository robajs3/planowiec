"""
Web Push (VAPID) — powiadomienia o zbliżających się aktywnościach.

Ten plik odpowiada TYLKO za zapisywanie subskrypcji i wysyłkę pojedynczego
powiadomienia. O tym, KIEDY wysłać (sprawdzanie czasu, zapobieganie
podwójnej wysyłce) odpowiada services/reminder_scheduler.py.
"""
import json

from flask import current_app
from pywebpush import webpush, WebPushException

from models import db


class NotificationService:

    @staticmethod
    def save_subscription(user, subscription_info: dict) -> None:
        user.push_subscription = json.dumps(subscription_info)
        db.session.commit()

    @staticmethod
    def clear_subscription(user) -> None:
        user.push_subscription = None
        db.session.commit()

    @staticmethod
    def send_push(user, title: str, body: str, link: str | None = None) -> bool:
        """Wysyła pojedyncze powiadomienie push do danego usera.
        Zwraca True, jeśli faktycznie wysłano (user miał aktywną subskrypcję
        i serwer push ją zaakceptował)."""
        if not user or not user.push_subscription:
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
        )
