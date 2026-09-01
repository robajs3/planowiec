import uuid
from datetime import datetime, timedelta

from models import db, ActivityType, Activity, DEFAULT_ACTIVITY_TYPES

RECURRENCE_NONE = "none"
RECURRENCE_DAILY = "daily"
RECURRENCE_WEEKLY = "weekly"
RECURRENCE_MONTHLY = "monthly"
ALL_RECURRENCES = [RECURRENCE_DAILY, RECURRENCE_WEEKLY, RECURRENCE_MONTHLY]

# Bezpiecznik, żeby literówka w dacie zakończenia serii (albo jej brak przy
# cyklu dziennym) nie wygenerowała nieograniczonej liczby wpisów.
MAX_RECURRENCE_OCCURRENCES = 366


def _add_interval(dt: datetime, rule: str, step: int) -> datetime:
    if rule == RECURRENCE_DAILY:
        return dt + timedelta(days=step)
    if rule == RECURRENCE_WEEKLY:
        return dt + timedelta(weeks=step)
    if rule == RECURRENCE_MONTHLY:
        # Przesunięcie o `step` miesięcy z zachowaniem dnia miesiąca (obcinane
        # do ostatniego dnia miesiąca docelowego, gdy oryginalny nie istnieje,
        # np. 31 stycznia + 1 miesiąc -> 28/29 lutego).
        month_index = dt.month - 1 + step
        year = dt.year + month_index // 12
        month = month_index % 12 + 1
        import calendar
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)
    return dt


class ActivityService:

    # ---------- typy aktywności: globalne / prywatne (własny plan) ----------
    @staticmethod
    def ensure_default_types() -> None:
        """Tworzy globalne typy domyślne, jeśli jeszcze nie istnieją (wołane raz przy starcie)."""
        if ActivityType.query.filter_by(is_default=True, group_id=None).first():
            return
        for name, color, icon in DEFAULT_ACTIVITY_TYPES:
            db.session.add(ActivityType(name=name, color=color, icon=icon, owner_id=None, group_id=None, is_default=True))
        db.session.commit()

    @staticmethod
    def get_types_for_user(user_id: int):
        """Typy domyślne (globalne) + własne typy użytkownika."""
        return (
            ActivityType.query.filter(
                ActivityType.group_id.is_(None),
                (ActivityType.owner_id == user_id) | (ActivityType.is_default.is_(True)),
            )
            .order_by(ActivityType.is_default.desc(), ActivityType.name.asc())
            .all()
        )

    @staticmethod
    def create_type(user_id: int, name: str, color: str, icon: str = "circle"):
        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę typu aktywności."
        exists = ActivityType.query.filter(
            ActivityType.group_id.is_(None),
            (ActivityType.owner_id == user_id) | (ActivityType.is_default.is_(True)),
            ActivityType.name.ilike(name),
        ).first()
        if exists:
            return None, "Taki typ aktywności już istnieje."
        activity_type = ActivityType(name=name, color=color or "#4f46e5", icon=icon or "circle", owner_id=user_id)
        db.session.add(activity_type)
        db.session.commit()
        return activity_type, None

    @staticmethod
    def update_type(user_id: int, type_id: int, name: str, color: str):
        activity_type = ActivityType.query.get(type_id)
        if not activity_type or activity_type.group_id is not None:
            return None, "Nie można edytować tego typu."
        # Typy domyślne są globalne (wspólne dla wszystkich) — każdy zalogowany
        # użytkownik może je edytować, ale nie może ich usunąć (patrz delete_type).
        # Własne typy może edytować tylko ich właściciel.
        if not activity_type.is_default and activity_type.owner_id != user_id:
            return None, "Nie można edytować tego typu."

        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę typu aktywności."

        exists = ActivityType.query.filter(
            ActivityType.group_id.is_(None),
            (ActivityType.owner_id == user_id) | (ActivityType.is_default.is_(True)),
            ActivityType.name.ilike(name),
            ActivityType.id != type_id,
        ).first()
        if exists:
            return None, "Taki typ aktywności już istnieje."

        activity_type.name = name
        activity_type.color = color or activity_type.color
        db.session.commit()
        return activity_type, None

    @staticmethod
    def delete_type(user_id: int, type_id: int) -> tuple[bool, str | None]:
        activity_type = ActivityType.query.get(type_id)
        if not activity_type or activity_type.group_id is not None or activity_type.is_default or activity_type.owner_id != user_id:
            return False, "Nie można usunąć tego typu."
        if activity_type.activities:
            return False, "Nie można usunąć typu, który jest używany przez aktywności."
        db.session.delete(activity_type)
        db.session.commit()
        return True, None

    # ---------- typy aktywności: grupowe (kategorie planu grupy) ----------
    @staticmethod
    def seed_group_defaults(group_id: int) -> None:
        """Kopiuje domyślne kategorie do nowo utworzonej grupy — od tej pory
        to własne, niezależne rekordy tej grupy (edytowalne/usuwalne przez
        jej admina/editora, bez wpływu na inne grupy)."""
        for name, color, icon in DEFAULT_ACTIVITY_TYPES:
            db.session.add(ActivityType(
                name=name, color=color, icon=icon,
                owner_id=None, group_id=group_id, is_default=True,
            ))
        db.session.commit()

    @staticmethod
    def get_types_for_group(group_id: int):
        return (
            ActivityType.query.filter_by(group_id=group_id)
            .order_by(ActivityType.is_default.desc(), ActivityType.name.asc())
            .all()
        )

    @staticmethod
    def create_group_type(group_id: int, name: str, color: str, icon: str = "circle"):
        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę kategorii."
        exists = ActivityType.query.filter(
            ActivityType.group_id == group_id,
            ActivityType.name.ilike(name),
        ).first()
        if exists:
            return None, "Taka kategoria już istnieje w tej grupie."
        activity_type = ActivityType(
            name=name, color=color or "#4f46e5", icon=icon or "circle",
            group_id=group_id, owner_id=None, is_default=False,
        )
        db.session.add(activity_type)
        db.session.commit()
        return activity_type, None

    @staticmethod
    def update_group_type(group_id: int, type_id: int, name: str, color: str):
        activity_type = ActivityType.query.get(type_id)
        if not activity_type or activity_type.group_id != group_id:
            return None, "Nie można edytować tej kategorii."

        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę kategorii."

        exists = ActivityType.query.filter(
            ActivityType.group_id == group_id,
            ActivityType.name.ilike(name),
            ActivityType.id != type_id,
        ).first()
        if exists:
            return None, "Taka kategoria już istnieje w tej grupie."

        activity_type.name = name
        activity_type.color = color or activity_type.color
        db.session.commit()
        return activity_type, None

    @staticmethod
    def delete_group_type(group_id: int, type_id: int) -> tuple[bool, str | None]:
        """Editor/admin grupy może usunąć DOWOLNĄ kategorię tej grupy —
        również jedną z domyślnych (Inne, Nauka, Odpoczynek itd.), ponieważ
        to niezależna kopia należąca tylko do tej grupy."""
        activity_type = ActivityType.query.get(type_id)
        if not activity_type or activity_type.group_id != group_id:
            return False, "Nie można usunąć tej kategorii."
        if activity_type.activities:
            return False, "Nie można usunąć kategorii, która jest używana przez aktywności."
        db.session.delete(activity_type)
        db.session.commit()
        return True, None

    # ---------- aktywności ----------
    @staticmethod
    def get_activities(owner_id: int | None, group_id: int | None,
                        start: datetime, end: datetime, type_ids: list[int] | None = None):
        query = Activity.query.filter(Activity.start_time < end, Activity.end_time >= start)
        if group_id is not None:
            query = query.filter(Activity.group_id == group_id)
        else:
            query = query.filter(Activity.owner_id == owner_id, Activity.group_id.is_(None))
        if type_ids:
            query = query.filter(Activity.activity_type_id.in_(type_ids))
        return query.order_by(Activity.start_time.asc()).all()

    @staticmethod
    def create_activity(owner_id: int, data: dict, group_id: int | None = None) -> tuple[Activity | None, str | None]:
        title = (data.get("title") or "").strip()
        if not title:
            return None, "Podaj tytuł aktywności."
        try:
            start = datetime.fromisoformat(data["start"])
            end = datetime.fromisoformat(data["end"])
        except (KeyError, ValueError):
            return None, "Nieprawidłowy format daty."
        if end < start:
            return None, "Data zakończenia nie może być wcześniejsza niż rozpoczęcia."
        type_id = data.get("activity_type_id")
        activity_type = ActivityType.query.get(type_id) if type_id else None
        if not activity_type:
            return None, "Wybierz poprawny typ aktywności."

        recurrence_rule = data.get("recurrence") or RECURRENCE_NONE
        if recurrence_rule not in ALL_RECURRENCES:
            recurrence_rule = RECURRENCE_NONE

        occurrences = [(start, end)]
        recurrence_id = None

        if recurrence_rule != RECURRENCE_NONE:
            until_raw = (data.get("recurrence_until") or "").strip()
            count_raw = data.get("recurrence_count")
            duration = end - start

            until = None
            if until_raw:
                try:
                    until = datetime.fromisoformat(until_raw)
                except ValueError:
                    return None, "Nieprawidłowa data zakończenia cyklu."

            try:
                count = int(count_raw) if count_raw else None
            except (TypeError, ValueError):
                count = None

            if not until and not count:
                return None, "Podaj datę zakończenia cyklu albo liczbę powtórzeń."

            recurrence_id = uuid.uuid4().hex
            occurrences = []
            cur_start = start
            i = 0
            while i < MAX_RECURRENCE_OCCURRENCES:
                if until and cur_start.date() > until.date():
                    break
                if count and i >= count:
                    break
                occurrences.append((cur_start, cur_start + duration))
                i += 1
                cur_start = _add_interval(cur_start, recurrence_rule, 1)
            if not occurrences:
                return None, "Zakres cyklu nie zawiera żadnego wystąpienia."
            if len(occurrences) == 1:
                # Tylko jedno wystąpienie mieści się w podanym zakresie —
                # traktujemy to jak zwykłą, jednorazową aktywność.
                recurrence_id = None

        created = []
        for occ_start, occ_end in occurrences:
            activity = Activity(
                title=title,
                description=(data.get("description") or "").strip(),
                location=(data.get("location") or "").strip(),
                start_time=occ_start,
                end_time=occ_end,
                all_day=bool(data.get("all_day")),
                activity_type_id=activity_type.id,
                owner_id=owner_id,
                group_id=group_id,
                recurrence_id=recurrence_id,
            )
            db.session.add(activity)
            created.append(activity)
        db.session.commit()
        # Zwracamy pierwsze wystąpienie — front dostaje natychmiastowe
        # potwierdzenie, a resztę serii i tak pobierze przy kolejnym
        # odświeżeniu widoku kalendarza.
        return created[0], None

    @staticmethod
    def update_activity(activity: Activity, data: dict) -> tuple[bool, str | None]:
        title = (data.get("title") or "").strip()
        if not title:
            return False, "Podaj tytuł aktywności."
        try:
            start = datetime.fromisoformat(data["start"])
            end = datetime.fromisoformat(data["end"])
        except (KeyError, ValueError):
            return False, "Nieprawidłowy format daty."
        if end < start:
            return False, "Data zakończenia nie może być wcześniejsza niż rozpoczęcia."
        type_id = data.get("activity_type_id")
        activity_type = ActivityType.query.get(type_id) if type_id else None
        if not activity_type:
            return False, "Wybierz poprawny typ aktywności."

        activity.title = title
        activity.description = (data.get("description") or "").strip()
        activity.location = (data.get("location") or "").strip()
        activity.start_time = start
        activity.end_time = end
        activity.all_day = bool(data.get("all_day"))
        activity.activity_type_id = activity_type.id
        db.session.commit()
        return True, None

    @staticmethod
    def delete_activity(activity: Activity, scope: str = "single") -> int:
        """Usuwa pojedynczą aktywność albo (gdy scope='series' i aktywność
        należy do wydarzenia cyklicznego) wszystkie jej wystąpienia z tej
        samej serii. Zwraca liczbę usuniętych wpisów."""
        if scope == "series" and activity.recurrence_id:
            rows = Activity.query.filter_by(recurrence_id=activity.recurrence_id).all()
            count = len(rows)
            for row in rows:
                db.session.delete(row)
            db.session.commit()
            return count
        db.session.delete(activity)
        db.session.commit()
        return 1

    @staticmethod
    def clear_day(owner_id: int | None, group_id: int | None, day: datetime) -> int:
        """Usuwa WSZYSTKIE aktywności danego (pojedynczego) dnia w planie
        prywatnym (owner_id) albo grupowym (group_id) — używane przez opcję
        "Wyczyść dzień" w trybie edycji. Usuwa tylko wystąpienia tego dnia,
        nie całe serie cykliczne, do których mogą należeć."""
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        query = Activity.query.filter(Activity.start_time < day_end, Activity.end_time >= day_start)
        if group_id is not None:
            query = query.filter(Activity.group_id == group_id)
        else:
            query = query.filter(Activity.owner_id == owner_id, Activity.group_id.is_(None))
        rows = query.all()
        count = len(rows)
        for row in rows:
            db.session.delete(row)
        db.session.commit()
        return count
