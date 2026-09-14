from datetime import datetime

from models import db

# Role w grupie — hierarchia od najwyższych uprawnień:
#   admin  – zarządza rolami członków, może wszystko (edycja planu, kategorie,
#            usuwanie/dodawanie członków, usunięcie grupy). Może być ich kilku.
#   editor – zarządza wszystkim poza użytkownikami/rolami: może edytować plan
#            grupy oraz dodawać/usuwać kategorie aktywności tej grupy.
#   viewer – tylko podgląd planu grupy (bez możliwości edycji).
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

# Zachowane dla zgodności wstecznej ze starszymi rekordami w bazie
# (dawna, jedyna rola "zwykłego" członka odpowiadała podglądowi).
ROLE_MEMBER = ROLE_VIEWER

ALL_ROLES = [ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER]
ROLE_LABELS = {
    ROLE_ADMIN: "Admin",
    ROLE_EDITOR: "Edytor",
    ROLE_VIEWER: "Viewer",
}
# Waga do sortowania / porównywania uprawnień (im wyżej, tym więcej uprawnień).
_ROLE_WEIGHT = {ROLE_ADMIN: 3, ROLE_EDITOR: 2, ROLE_VIEWER: 1}


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    # Twórca grupy — historyczne pole, zachowane m.in. jako "ostatni admin",
    # którego nie można usunąć/zdegradować, gdyby został sam. Uprawnienia
    # w praktyce wynikają z roli w GroupMember, nie z tego pola.
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship("User", foreign_keys=[admin_id])
    members = db.relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    activities = db.relationship(
        "Activity", back_populates="group", cascade="all, delete-orphan"
    )
    activity_types = db.relationship(
        "ActivityType", back_populates="group", cascade="all, delete-orphan"
    )

    @property
    def member_count(self) -> int:
        return len(self.members)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "code": self.code,
            "admin_id": self.admin_id,
            "member_count": self.member_count,
        }

    def __repr__(self) -> str:
        return f"<Group {self.name} ({self.code})>"


class GroupMember(db.Model):
    __tablename__ = "group_members"
    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default=ROLE_VIEWER, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Czy TEN użytkownik chce dostawać powiadomienia push o nowych
    # aktywnościach dodanych w planie TEJ grupy. Ma znaczenie tylko, gdy
    # User.group_notification_pref danego użytkownika == "selected" — przy
    # "all"/"none" ta flaga jest ignorowana (patrz NotificationService).
    notifications_enabled = db.Column(db.Boolean, default=True, nullable=False)

    group = db.relationship("Group", back_populates="members")
    user = db.relationship("User")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_editor(self) -> bool:
        return self.role == ROLE_EDITOR

    @property
    def is_viewer(self) -> bool:
        return self.role == ROLE_VIEWER

    @property
    def can_manage_roles(self) -> bool:
        """Zarządzanie rolami i członkami — tylko admin."""
        return self.role == ROLE_ADMIN

    @property
    def can_edit_plan(self) -> bool:
        """Edycja planu grupy (aktywności) — admin i editor."""
        return self.role in (ROLE_ADMIN, ROLE_EDITOR)

    @property
    def can_manage_categories(self) -> bool:
        """Dodawanie/usuwanie kategorii aktywności grupy — admin i editor."""
        return self.role in (ROLE_ADMIN, ROLE_EDITOR)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def role_weight(self) -> int:
        return _ROLE_WEIGHT.get(self.role, 0)

    def __repr__(self) -> str:
        return f"<GroupMember user={self.user_id} group={self.group_id} role={self.role}>"
