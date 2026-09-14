"""
Sprawdza co minutę, którym aktywnościom nadszedł czas przypomnienia push,
i wysyła je.

WAŻNE — bezpieczeństwo przy wielu procesach gunicorna: appka startuje z
`--workers 3`, więc ten scheduler faktycznie działa w 3 osobnych procesach
naraz, każdy sprawdzając tę samą bazę co minutę. Żeby nie wysłać tego
samego przypomnienia 3 razy, "zajęcie" aktywności do wysyłki robimy jednym
atomowym UPDATE z warunkiem `WHERE reminder_sent_at IS NULL` — tylko JEDEN
z procesów wygra ten wyścig (dostanie rowcount=1), reszta dostanie 0 i
pominie tę aktywność. To działa niezależnie od liczby workerów/schedulerów.
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from models import db, Activity
from services.notification_service import NotificationService

CHECK_INTERVAL_SECONDS = 60


def _claim_activity(activity_id: int) -> bool:
    """Atomowo oznacza aktywność jako 'przypomnienie wysłane'. Zwraca True
    tylko temu procesowi, który faktycznie wygrał wyścig o wysyłkę."""
    result = db.session.execute(
        text(
            "UPDATE activities SET reminder_sent_at = :now "
            "WHERE id = :id AND reminder_sent_at IS NULL"
        ),
        {"now": datetime.utcnow(), "id": activity_id},
    )
    db.session.commit()
    return result.rowcount > 0


def _check_and_send_due_reminders(app):
    with app.app_context():
        # Naiwny czas lokalny (patrz komentarz w Activity.start_time) — cały
        # projekt konsekwentnie trzyma start_time jako "wall clock", więc
        # tutaj też porównujemy z naiwnym "teraz", a nie z UTC.
        now = datetime.now()

        # Okno wyszukiwania: aktywności, których termin przypomnienia
        # (start_time - notify_before_minutes) już nadszedł, ale sama
        # aktywność jeszcze się nie zaczęła (nie ma sensu przypominać o
        # czymś, co już trwa/minęło — np. po dłuższym przestoju appki).
        candidates = (
            Activity.query
            .filter(
                Activity.notify_before_minutes.isnot(None),
                Activity.reminder_sent_at.is_(None),
                Activity.group_id.is_(None),  # patrz NotificationService.send_activity_reminder
                Activity.start_time > now,
            )
            .all()
        )

        for activity in candidates:
            trigger_at = activity.start_time - timedelta(minutes=activity.notify_before_minutes)
            if now < trigger_at:
                continue  # jeszcze nie pora
            if not _claim_activity(activity.id):
                continue  # inny worker już to wysyła/wysłał
            try:
                NotificationService.send_activity_reminder(activity)
            except Exception:
                app.logger.exception(f"Nie udało się wysłać przypomnienia dla aktywności {activity.id}")


def start_reminder_scheduler(app):
    """Startuje scheduler w tle. Bezpieczne do wywołania w każdym workerze
    gunicorna — patrz komentarz o atomowym _claim_activity wyżej."""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _check_and_send_due_reminders,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        args=[app],
        id="activity_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
