from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from models import db

AVATAR_PALETTE = [
    "#4f46e5", "#7c3aed", "#059669", "#d97706",
    "#dc2626", "#0284c7", "#db2777", "#65a30d",
]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(80), nullable=True)
    avatar_color = db.Column(db.String(7), default="#4f46e5")
    role = db.Column(db.String(20), default="user", nullable=False)  # user, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # Gdy True — widok "główny plan" (dashboard.index) domyślnie agreguje
    # własne aktywności razem z planami znajomych (którym dano dostęp)
    # i grup, do których użytkownik należy. Domyślnie wyłączone: widoczny
    # jest wtedy tylko własny, prywatny plan (zachowanie sprzed tej opcji).
    show_all_plans = db.Column(db.Boolean, default=False, nullable=False)

    activities = db.relationship(
        "Activity", back_populates="owner", cascade="all, delete-orphan",
        foreign_keys="Activity.owner_id",
    )
    activity_types = db.relationship(
        "ActivityType", back_populates="owner", cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def name(self) -> str:
        return self.display_name or self.username

    @property
    def initials(self) -> str:
        base = self.name.strip()
        parts = base.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return base[:2].upper() if base else "?"

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "avatar_color": self.avatar_color,
            "initials": self.initials,
        }

    def __repr__(self) -> str:
        return f"<User {self.username}>"
