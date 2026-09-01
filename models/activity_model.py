from datetime import datetime

from models import db

DEFAULT_ACTIVITY_TYPES = [
    ("Praca", "#4f46e5", "briefcase"),
    ("Nauka", "#0284c7", "book"),
    ("Sport", "#059669", "activity"),
    ("Spotkanie", "#d97706", "users"),
    ("Odpoczynek", "#7c3aed", "coffee"),
    ("Inne", "#64748b", "circle"),
]


class ActivityType(db.Model):
    """
    Typ aktywności może być:
      - globalny (owner_id = None, group_id = None, is_default = True) —
        tworzony raz przy inicjalizacji bazy, widoczny w prywatnych planach
        wszystkich użytkowników; niedomyślne globalne typy nie istnieją.
      - prywatny (owner_id ustawione, group_id = None) — własny typ danego
        użytkownika, widoczny tylko w jego prywatnym planie.
      - grupowy (group_id ustawione, owner_id = None) — należy do konkretnej
        grupy; każda grupa dostaje przy utworzeniu własną kopię domyślnych
        kategorii, którymi zarządza (dodaje/usuwa, w tym te domyślne)
        wyłącznie admin lub editor tej grupy — bez wpływu na inne grupy
        ani na prywatne plany.
    """
    __tablename__ = "activity_types"
    __table_args__ = (
        db.UniqueConstraint("owner_id", "group_id", "name", name="uq_activity_type_scope_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#4f46e5")
    icon = db.Column(db.String(30), nullable=False, default="circle")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)
    is_default = db.Column(db.Boolean, default=False)

    owner = db.relationship("User", back_populates="activity_types")
    group = db.relationship("Group", back_populates="activity_types")
    activities = db.relationship("Activity", back_populates="activity_type")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "is_default": self.is_default,
            "group_id": self.group_id,
        }

    def __repr__(self) -> str:
        return f"<ActivityType {self.name}>"


class Activity(db.Model):
    """
    Pojedynczy wpis w kalendarzu. Może należeć do prywatnego planu użytkownika
    (group_id = None) albo do planu grupowego (group_id ustawione) — wtedy
    tworzyć/edytować może administrator lub editor grupy.
    """
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(150), nullable=True)

    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    all_day = db.Column(db.Boolean, default=False)

    activity_type_id = db.Column(db.Integer, db.ForeignKey("activity_types.id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)

    # Wspólny znacznik dla wszystkich wystąpień wydarzenia cyklicznego
    # wygenerowanych z jednego formularza (pozwala usunąć/rozpoznać "całą serię").
    recurrence_id = db.Column(db.String(36), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = db.relationship("User", back_populates="activities", foreign_keys=[owner_id])
    activity_type = db.relationship("ActivityType", back_populates="activities")
    group = db.relationship("Group", back_populates="activities")
    comments = db.relationship(
        "ActivityComment", back_populates="activity",
        cascade="all, delete-orphan", order_by="ActivityComment.created_at",
    )

    def to_dict(self, source: dict | None = None) -> dict:
        """
        `source` — opcjonalny znacznik pochodzenia, używany wyłącznie w widoku
        zagregowanym "Wszystkie plany" (kontekst "all"), żeby front mógł
        rozróżnić, z czyjego planu pochodzi dana aktywność, np.:
        {"kind": "own"|"friend"|"group", "id": .., "label": .., "can_edit": bool, "can_comment": bool}
        """
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "location": self.location or "",
            "start": self.start_time.isoformat(),
            "end": self.end_time.isoformat(),
            "all_day": self.all_day,
            "type": self.activity_type.to_dict() if self.activity_type else None,
            "owner": self.owner.to_public_dict() if self.owner else None,
            "group_id": self.group_id,
            "recurrence_id": self.recurrence_id,
            "comment_count": len(self.comments) if self.comments is not None else 0,
        }
        if source is not None:
            data["source"] = source
        return data

    def __repr__(self) -> str:
        return f"<Activity {self.title} @ {self.start_time}>"


class ActivityComment(db.Model):
    """Komentarz do wpisu w cudzym planie (np. znajomego, który udostępnił
    dostęp z rolą 'commenter'/'editor', lub członka grupy)."""
    __tablename__ = "activity_comments"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    activity = db.relationship("Activity", back_populates="comments")
    author = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "author": self.author.to_public_dict() if self.author else None,
        }

    def __repr__(self) -> str:
        return f"<ActivityComment {self.id} on activity={self.activity_id}>"


class DayMarker(db.Model):
    """
    Własny, niezależny od typów aktywności "znacznik dnia" — z własną nazwą i kolorem. Służy wyłącznie do
    kolorowego oznaczania CAŁYCH dni w kalendarzu (ramka) i pokazywania
    legendy; nie jest w żaden sposób powiązany z typami/wpisami aktywności.
    """
    __tablename__ = "day_markers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#ef4444")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User")
    group = db.relationship("Group")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "group_id": self.group_id}

    def __repr__(self) -> str:
        return f"<DayMarker {self.name}>"


class DayMarkerAssignment(db.Model):
    """Przypisanie jednego znacznika dnia (DayMarker) do konkretnego dnia w
    danym planie (własnym albo grupowym). Jeden znacznik na dzień na plan."""
    __tablename__ = "day_marker_assignments"
    __table_args__ = (
        db.UniqueConstraint("owner_id", "group_id", "date", name="uq_day_marker_assignment"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False)
    day_marker_id = db.Column(db.Integer, db.ForeignKey("day_markers.id", ondelete="CASCADE"), nullable=False)

    day_marker = db.relationship("DayMarker")

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "marker_id": self.day_marker_id,
            "name": self.day_marker.name if self.day_marker else None,
            "color": self.day_marker.color if self.day_marker else None,
        }

    def __repr__(self) -> str:
        return f"<DayMarkerAssignment {self.date} -> marker={self.day_marker_id}>"
