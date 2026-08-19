import re
from datetime import datetime

from models import db, User

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthService:

    @staticmethod
    def validate_registration(username: str, email: str, password: str, password2: str):
        if not username or not email or not password:
            return "Wypełnij wszystkie wymagane pola."
        if not USERNAME_RE.match(username):
            return "Nazwa użytkownika może zawierać 3-32 znaki: litery, cyfry, '.', '_', '-'."
        if not EMAIL_RE.match(email):
            return "Podaj poprawny adres e-mail."
        if len(password) < 8:
            return "Hasło musi mieć co najmniej 8 znaków."
        if password != password2:
            return "Hasła nie są identyczne."
        if User.query.filter_by(username=username).first():
            return "Ta nazwa użytkownika jest już zajęta."
        if User.query.filter_by(email=email.lower()).first():
            return "Ten adres e-mail jest już zarejestrowany."
        return None

    @staticmethod
    def register_user(username: str, email: str, password: str, display_name: str | None = None):
        user = User(
            username=username.strip(),
            email=email.strip().lower(),
            display_name=(display_name or "").strip() or None,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def authenticate(identifier: str, password: str) -> User | None:
        identifier = (identifier or "").strip()
        user = User.query.filter(
            (User.email == identifier.lower()) | (User.username == identifier)
        ).first()
        if user and user.check_password(password):
            user.last_seen = datetime.utcnow()
            db.session.commit()
            return user
        return None
