from datetime import datetime

from models import db

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"

# Rola nadawana znajomemu wraz z dostępem do własnego planu (PlanAccess.role):
#   editor    – może dodawać/edytować/usuwać wpisy w Twoim planie oraz komentować
#   commenter – nie może edytować planu, ale może dodawać komentarze do wpisów
#   viewer    – wyłącznie podgląd, bez możliwości edycji ani komentowania
ACCESS_EDITOR = "editor"
ACCESS_COMMENTER = "commenter"
ACCESS_VIEWER = "viewer"

ALL_ACCESS_ROLES = [ACCESS_EDITOR, ACCESS_COMMENTER, ACCESS_VIEWER]
ACCESS_ROLE_LABELS = {
    ACCESS_EDITOR: "Może edytować",
    ACCESS_COMMENTER: "Może komentować",
    ACCESS_VIEWER: "Tylko podgląd",
}


class Friendship(db.Model):
    """
    Jeden rekord reprezentuje relację między dwoma użytkownikami.
    requester_id -> osoba, która wysłała zaproszenie
    addressee_id -> osoba, która je otrzymuje i akceptuje/odrzuca
    """
    __tablename__ = "friendships"
    __table_args__ = (
        db.UniqueConstraint("requester_id", "addressee_id", name="uq_friend_pair"),
    )

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    addressee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default=STATUS_PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)

    requester = db.relationship("User", foreign_keys=[requester_id])
    addressee = db.relationship("User", foreign_keys=[addressee_id])

    def other(self, user_id: int):
        return self.addressee if self.requester_id == user_id else self.requester

    def __repr__(self) -> str:
        return f"<Friendship {self.requester_id}->{self.addressee_id} ({self.status})>"


class PlanAccess(db.Model):
    """
    Nadanie dostępu do własnego planu (kalendarza) innemu użytkownikowi, wraz
    z rolą określającą zakres uprawnień (patrz ACCESS_* powyżej). Domyślnie
    (i dla rekordów sprzed wprowadzenia ról) — wyłącznie podgląd.
    """
    __tablename__ = "plan_access"
    __table_args__ = (
        db.UniqueConstraint("owner_id", "viewer_id", name="uq_plan_access_pair"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    viewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default=ACCESS_VIEWER, nullable=False)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", foreign_keys=[owner_id])
    viewer = db.relationship("User", foreign_keys=[viewer_id])

    @property
    def role_label(self) -> str:
        return ACCESS_ROLE_LABELS.get(self.role, self.role)
