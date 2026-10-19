"""
Import "planów" (egzaminów) z appki koloseum do planowca.

Mechanizm:
  1. Ustalamy lokalny user_id w koloseum dla obecnie zalogowanej osoby przez
     sso_client.resolve_local_user_id(app_slug="koloseum") — korzysta z tego
     samego ciasteczka SSO, którym planowiec już się loguje, tylko pyta hub
     o powiązanie z INNĄ appką niż ta, w której aktualnie jesteśmy.
  2. Pytamy koloseum bezpośrednio (nie przez hub) o listę egzaminów tego usera
     — endpoint /api/my-exams (koloseum, bez prefiksu — patrz komentarz w
     fetch_exams), autoryzowany współdzielonym SSO_SECRET jako kluczem API (ten sam wzorzec co LoginHub /api/resolve).
  3. Zaznaczone przez użytkownika egzaminy zapisujemy jako Activity, do
     własnego planu albo do planu wybranej grupy. Kategoria wpisu odpowiada
     typowi terminu w koloseum (Wykład, Egzamin, Laboratoria...) — jest
     znajdowana po nazwie w planie docelowym albo tworzona z kolorem z koloseum. Ponowny import TEGO SAMEGO
     egzaminu (rozpoznawanego po `external_ref = "koloseum:exam:<id>"`)
     nadpisuje istniejący wpis, zamiast tworzyć duplikat.
"""
import os
from datetime import datetime, timedelta

import requests

from sqlalchemy import or_

from models import db, Activity, ActivityType

# Kategoria zapasowa — używana tylko wtedy, gdy koloseum nie zwróciło typu
# terminu (bardzo stara wersja API).
KOLOSEUM_TYPE_NAME = "Koloseum"
KOLOSEUM_TYPE_COLOR = "#be123c"
KOLOSEUM_TYPE_ICON = "book"

# Zapasowy słownik typów koloseum (wartość → (nazwa, kolor)) na wypadek
# starszej wersji koloseum, która jeszcze nie zwraca `exam_type_label` i
# `exam_type_color`. Aktualne koloseum jest źródłem prawdy — te pola mają
# pierwszeństwo.
KOLOSEUM_KNOWN_TYPES = {
    "kolokwium":   ("Kolokwium",   "#4f46e5"),
    "egzamin":     ("Egzamin",     "#dc2626"),
    "kartkówka":   ("Kartkówka",   "#d97706"),
    "deadline":    ("Deadline",    "#059669"),
    "wyklad":      ("Wykład",      "#0284c7"),
    "cwiczenia":   ("Ćwiczenia",   "#0d9488"),
    "laboratoria": ("Laboratoria", "#c026d3"),
    "zajecia":     ("Zajęcia",     "#db2777"),
    "inne":        ("Inne",        "#64748b"),
}

EXTERNAL_PREFIX = "koloseum:exam:"


class KoloseumImportService:

    @staticmethod
    def _base_url() -> str:
        return os.environ.get("KOLOSEUM_INTERNAL_URL", "http://koloseum-web:5000").rstrip("/")

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("SSO_SECRET", "")

    @staticmethod
    def fetch_exams(koloseum_user_id: int) -> tuple[list[dict] | None, str | None]:
        """Pobiera listę egzaminów usera z koloseum. Zwraca (exams, błąd).

        UWAGA: wołamy koloseum bezpośrednio kontener-kontener (sso_net), nie
        przez Tailscale — więc NIE doklejamy prefiksu /koloseum do ścieżki.
        Ten prefiks istnieje tylko w routingu widzianym przez przeglądarkę
        (Tailscale Serve --set-path go ściera zanim żądanie trafi do samego
        Flaska koloseum — patrz PrefixMiddleware w koloseum/app.py). Trasy
        wewnątrz appki, w tym /api/my-exams, są zarejestrowane BEZ prefiksu.
        """
        try:
            resp = requests.get(
                f"{KoloseumImportService._base_url()}/api/my-exams",
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
    def _type_spec(exam: dict) -> tuple[str, str]:
        """(nazwa, kolor) kategorii planowca odpowiadającej typowi terminu
        w koloseum. Najpierw dane z API koloseum, potem zapasowy słownik."""
        raw = (exam.get("exam_type") or "").strip()
        known_name, known_color = KOLOSEUM_KNOWN_TYPES.get(raw, (None, None))
        name = (exam.get("exam_type_label") or known_name or raw.capitalize()).strip()
        color = exam.get("exam_type_color") or known_color or KOLOSEUM_TYPE_COLOR
        if not name:
            return KOLOSEUM_TYPE_NAME, KOLOSEUM_TYPE_COLOR
        return name[:60], color

    @staticmethod
    def _get_or_create_type(owner_id: int | None, group_id: int | None,
                            name: str = KOLOSEUM_TYPE_NAME,
                            color: str = KOLOSEUM_TYPE_COLOR) -> ActivityType:
        """Znajduje kategorię o danej nazwie w planie docelowym albo ją tworzy.

        Jeśli taka kategoria już jest (np. domyślne "Inne" albo własne
        "Wykład" użytkownika), używamy jej bez zmieniania koloru. W planie
        prywatnym szukamy też wśród globalnych kategorii domyślnych —
        inaczej powstałby duplikat np. "Inne"."""
        query = ActivityType.query.filter(ActivityType.name.ilike(name))
        if group_id is not None:
            candidates = query.filter(ActivityType.group_id == group_id).all()
        else:
            candidates = query.filter(
                ActivityType.group_id.is_(None),
                or_(ActivityType.owner_id == owner_id, ActivityType.owner_id.is_(None)),
            ).all()
            # własna kategoria usera ma pierwszeństwo przed globalną
            candidates.sort(key=lambda t: t.owner_id is None)
        if candidates:
            return candidates[0]
        activity_type = ActivityType(
            name=name,
            color=color,
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

        types_cache: dict[str, ActivityType] = {}
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

            type_name, type_color = KoloseumImportService._type_spec(exam)
            activity_type = types_cache.get(type_name.lower())
            if activity_type is None:
                activity_type = KoloseumImportService._get_or_create_type(
                    owner_id, group_id, type_name, type_color)
                types_cache[type_name.lower()] = activity_type

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
