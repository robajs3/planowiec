from datetime import datetime

from models import db


class Notification(db.Model):
    """
    Historia powiadomień pokazywana w zakładce „Powiadomienia" (lista
    poprzednich powiadomień). Zapisywana przez NotificationService przy
    każdej próbie wysłania powiadomienia push (przypomnienie o aktywności,
    nowa aktywność w grupie itd.) — NIEZALEŻNIE od tego, czy sama wysyłka
    push się powiodła (np. user nie ma zapisanej subskrypcji, albo ma
    chwilowo wyciszone powiadomienia), żeby historia w appce była kompletna
    nawet bez włączonego web pusha.
    """
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=True)
    link = db.Column(db.String(300), nullable=True)

    # "reminder" (przypomnienie o własnej aktywności), "group_activity"
    # (nowa aktywność w grupie) — miejsce na kolejne rodzaje w przyszłości.
    kind = db.Column(db.String(30), nullable=False, default="reminder")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body or "",
            "link": self.link,
            "kind": self.kind,
            "created_at": self.created_at.isoformat() + "Z",
            "read": self.is_read,
        }

    def __repr__(self) -> str:
        return f"<Notification {self.id} user={self.user_id} '{self.title}'>"
