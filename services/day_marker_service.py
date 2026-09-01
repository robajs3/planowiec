from datetime import date, datetime

from models import db, DayMarker, DayMarkerAssignment

# Domyślna paleta podpowiadana przy tworzeniu nowego znacznika dnia — czysto
# kosmetyczne, użytkownik i tak może wybrać dowolny, własny kolor.
SUGGESTED_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899"]


class DayMarkerService:
    """
    Osobny, niezależny od typów/kategorii aktywności system "znaczników dnia":
    użytkownik (albo grupa) definiuje własną legendę (nazwa + kolor) i przypisuje co najwyżej jeden
    znacznik do danego dnia w kalendarzu — dzień dostaje wtedy kolorową ramkę
    w tym kolorze. Nie ma to żadnego związku z aktywnościami/typami.
    """

    # ---------- znaczniki (legenda) ----------
    @staticmethod
    def list_markers(owner_id: int | None, group_id: int | None):
        query = DayMarker.query
        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter_by(owner_id=owner_id, group_id=None)
        return query.order_by(DayMarker.created_at.asc()).all()

    @staticmethod
    def create_marker(owner_id: int | None, group_id: int | None, name: str, color: str):
        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę znacznika dnia."
        if len(name) > 60:
            return None, "Nazwa jest zbyt długa."
        exists = DayMarkerService.list_markers(owner_id, group_id)
        if any(m.name.lower() == name.lower() for m in exists):
            return None, "Taki znacznik dnia już istnieje."
        marker = DayMarker(name=name, color=color or "#ef4444", owner_id=owner_id, group_id=group_id)
        db.session.add(marker)
        db.session.commit()
        return marker, None

    @staticmethod
    def update_marker(owner_id: int | None, group_id: int | None, marker_id: int, name: str, color: str):
        marker = DayMarker.query.get(marker_id)
        if not marker or marker.owner_id != owner_id or marker.group_id != group_id:
            return None, "Nie można edytować tego znacznika."
        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę znacznika dnia."
        marker.name = name
        marker.color = color or marker.color
        db.session.commit()
        return marker, None

    @staticmethod
    def delete_marker(owner_id: int | None, group_id: int | None, marker_id: int):
        marker = DayMarker.query.get(marker_id)
        if not marker or marker.owner_id != owner_id or marker.group_id != group_id:
            return False, "Nie można usunąć tego znacznika."
        DayMarkerAssignment.query.filter_by(day_marker_id=marker.id).delete()
        db.session.delete(marker)
        db.session.commit()
        return True, None

    # ---------- przypisania dni ----------
    @staticmethod
    def get_assignments(owner_id: int | None, group_id: int | None, start: date, end: date):
        query = DayMarkerAssignment.query.filter(
            DayMarkerAssignment.date >= start, DayMarkerAssignment.date < end
        )
        if group_id is not None:
            query = query.filter_by(group_id=group_id)
        else:
            query = query.filter_by(owner_id=owner_id, group_id=None)
        return query.all()

    @staticmethod
    def set_assignment(owner_id: int | None, group_id: int | None, day: date, marker_id: int):
        marker = DayMarker.query.get(marker_id)
        if not marker or marker.owner_id != owner_id or marker.group_id != group_id:
            return None, "Nieprawidłowy znacznik dnia."
        query = DayMarkerAssignment.query.filter_by(date=day)
        query = query.filter_by(group_id=group_id) if group_id is not None else query.filter_by(owner_id=owner_id, group_id=None)
        existing = query.first()
        if existing:
            existing.day_marker_id = marker.id
            db.session.commit()
            return existing, None
        assignment = DayMarkerAssignment(owner_id=owner_id, group_id=group_id, date=day, day_marker_id=marker.id)
        db.session.add(assignment)
        db.session.commit()
        return assignment, None

    @staticmethod
    def clear_assignment(owner_id: int | None, group_id: int | None, day: date) -> bool:
        query = DayMarkerAssignment.query.filter_by(date=day)
        query = query.filter_by(group_id=group_id) if group_id is not None else query.filter_by(owner_id=owner_id, group_id=None)
        deleted = query.delete()
        db.session.commit()
        return deleted > 0
