"""
Import "planów" (egzaminów) z appki koloseum do planowca.

Mechanizm:
  1. Ustalamy lokalny user_id w koloseum dla obecnie zalogowanej osoby przez
     sso_client.resolve_local_user_id(app_slug="koloseum") — korzysta z tego
     samego ciasteczka SSO, którym planowiec już się loguje, tylko pyta hub
     o powiązanie z INNĄ appką niż ta, w której aktualnie jesteśmy.
  2. Pytamy koloseum bezpośrednio (nie przez hub) o listę egzaminów tego usera
     — endpoint /koloseum/api/my-exams, autoryzowany współdzielonym SSO_SECRET
     jako kluczem API (ten sam wzorzec co LoginHub /api/resolve).
  3. Zaznaczone przez użytkownika egzaminy zapisujemy jako Activity, do
     własnego planu albo do planu wybranej grupy. Ponowny import TEGO SAMEGO
     egzaminu (rozpoznawanego po `external_ref = "koloseum:exam:<id>"`)
     nadpisuje istniejący wpis, zamiast tworzyć duplikat.
"""
import os
from datetime import datetime, timedelta

import requests

from models import db, Activity, ActivityType

KOLOSEUM_TYPE_NAME = "Koloseum"
KOLOSEUM_TYPE_COLOR = "#be123c"
KOLOSEUM_TYPE_ICON = "book"

EXTERNAL_PREFIX = "koloseum:exam:"


class KoloseumImportService:

    @staticmethod
    def _base_url() -> str:
        return os.environ.get("KOLOSEUM_INTERNAL_URL", "http://host.docker.internal:5001").rstrip("/")

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("SSO_SECRET", "")

    @staticmethod
    def fetch_exams(koloseum_user_id: int) -> tuple[list[dict] | None, str | None]:
        """Pobiera listę egzaminów usera z koloseum. Zwraca (exams, błąd)."""
        try:
            resp = requests.get(
                f"{KoloseumImportService._base_url()}/koloseum/api/my-exams",
                params={"user_id": koloseum_user_id},
                headers={"X-SSO-Api-Key": KoloseumImportService._api_key()},
                timeout=5,
            )
        except requests.RequestException:
            return None, "Nie można połączyć się z koloseum. Sprawdź, czy appka działa i czy KOLOSEUM_INTERNAL_URL jest poprawny."
        if resp.status_code == 401:
            return None, "Odrzucono klucz API — SSO_SECRET w planowcu i koloseum się nie zgadzają."
        if resp.status_code != 200:
            return None, f"Koloseum zwróciło błąd ({resp.status_code})."
        try:
            return resp.json(), None
        except ValueError:
            return None, "Nieprawidłowa odpowiedź z koloseum."

    @staticmethod
    def already_imported_refs(owner_id: int, group_id: int | None) -> set[str]:
        """Zbiór external_ref egzaminów koloseum już zaimportowanych do danego
        planu (własnego albo grupowego) — do oznaczenia w UI "już zaimportowane"."""
        query = Activity.query.filter(
            Activity.owner_id == owner_id,
            Activity.external_ref.isnot(None),
            Activity.external_ref.like(f"{EXTERNAL_PREFIX}%"),
        )
        query = query.filter(Activity.group_id == group_id) if group_id is not None \
            else query.filter(Activity.group_id.is_(None))
        return {a.external_ref for a in query.all()}

    @staticmethod
    def _get_or_create_type(owner_id: int | None, group_id: int | None) -> ActivityType:
        query = ActivityType.query.filter(ActivityType.name.ilike(KOLOSEUM_TYPE_NAME))
        query = query.filter(ActivityType.group_id == group_id) if group_id is not None \
            else query.filter(ActivityType.group_id.is_(None), ActivityType.owner_id == owner_id)
        activity_type = query.first()
        if activity_type:
            return activity_type
        activity_type = ActivityType(
            name=KOLOSEUM_TYPE_NAME,
            color=KOLOSEUM_TYPE_COLOR,
            icon=KOLOSEUM_TYPE_ICON,
            owner_id=owner_id if group_id is None else None,
            group_id=group_id,
        )
        db.session.add(activity_type)
        db.session.flush()
        return activity_type

    @staticmethod
    def import_exams(exams: list[dict], owner_id: int, group_id: int | None = None) -> int:
        """Tworzy/nadpisuje aktywności w planowcu na podstawie wybranych
        egzaminów z koloseum. `owner_id` to zawsze osoba wykonująca import;
        `group_id` ustawione = wpis trafia do planu grupy zamiast prywatnego."""
        if not exams:
            return 0

        activity_type = KoloseumImportService._get_or_create_type(owner_id, group_id)
        count = 0

        for exam in exams:
            external_ref = f"{EXTERNAL_PREFIX}{exam['id']}"

            query = Activity.query.filter(
                Activity.owner_id == owner_id,
                Activity.external_ref == external_ref,
            )
            query = query.filter(Activity.group_id == group_id) if group_id is not None \
                else query.filter(Activity.group_id.is_(None))
            activity = query.first()

            try:
                start = datetime.fromisoformat(exam["exam_date"])
            except (KeyError, ValueError, TypeError):
                continue
            end = start + timedelta(hours=1)

            title = (exam.get("title") or "Egzamin").strip()
            subject = (exam.get("subject") or "").strip()
            description = (exam.get("description") or "").strip()
            if subject:
                description = f"Przedmiot: {subject}" + (f"\n\n{description}" if description else "")

            if activity:
                activity.title = title
                activity.description = description
                activity.location = exam.get("location") or ""
                activity.start_time = start
                activity.end_time = end
                activity.activity_type_id = activity_type.id
            else:
                activity = Activity(
                    title=title,
                    description=description,
                    location=exam.get("location") or "",
                    start_time=start,
                    end_time=end,
                    activity_type_id=activity_type.id,
                    owner_id=owner_id,
                    group_id=group_id,
                    external_ref=external_ref,
                )
                db.session.add(activity)
            count += 1

        db.session.commit()
        return count
