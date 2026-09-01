from datetime import datetime

from sqlalchemy import or_, and_

from models import db, User, Friendship, PlanAccess
from models.friendship_model import (
    STATUS_PENDING, STATUS_ACCEPTED, STATUS_DECLINED,
    ACCESS_EDITOR, ACCESS_COMMENTER, ACCESS_VIEWER, ALL_ACCESS_ROLES,
)


class FriendService:

    # ---------- wyszukiwanie ----------
    @staticmethod
    def search_users(query: str, current_user_id: int, limit: int = 20):
        query = (query or "").strip()
        if not query:
            return []
        like = f"%{query}%"
        return (
            User.query.filter(
                User.id != current_user_id,
                or_(User.username.ilike(like), User.email.ilike(like)),
            )
            .order_by(User.username.asc())
            .limit(limit)
            .all()
        )

    # ---------- relacje ----------
    @staticmethod
    def get_relationship(user_a_id: int, user_b_id: int) -> Friendship | None:
        return Friendship.query.filter(
            or_(
                and_(Friendship.requester_id == user_a_id, Friendship.addressee_id == user_b_id),
                and_(Friendship.requester_id == user_b_id, Friendship.addressee_id == user_a_id),
            )
        ).first()

    @staticmethod
    def send_request(requester_id: int, addressee_id: int) -> tuple[Friendship | None, str | None]:
        if requester_id == addressee_id:
            return None, "Nie możesz zaprosić samego siebie."
        existing = FriendService.get_relationship(requester_id, addressee_id)
        if existing:
            if existing.status == STATUS_ACCEPTED:
                return None, "Jesteście już znajomymi."
            if existing.status == STATUS_PENDING:
                return None, "Zaproszenie zostało już wysłane."
            existing.status = STATUS_PENDING
            existing.requester_id = requester_id
            existing.addressee_id = addressee_id
            existing.responded_at = None
            db.session.commit()
            return existing, None

        friendship = Friendship(requester_id=requester_id, addressee_id=addressee_id)
        db.session.add(friendship)
        db.session.commit()
        return friendship, None

    @staticmethod
    def respond_to_request(friendship_id: int, user_id: int, accept: bool) -> tuple[bool, str | None]:
        friendship = Friendship.query.get(friendship_id)
        if not friendship or friendship.addressee_id != user_id:
            return False, "Nie znaleziono zaproszenia."
        if friendship.status != STATUS_PENDING:
            return False, "To zaproszenie zostało już obsłużone."
        friendship.status = STATUS_ACCEPTED if accept else STATUS_DECLINED
        friendship.responded_at = datetime.utcnow()
        db.session.commit()
        return True, None

    @staticmethod
    def remove_friend(friendship_id: int, user_id: int) -> bool:
        friendship = Friendship.query.get(friendship_id)
        if not friendship or user_id not in (friendship.requester_id, friendship.addressee_id):
            return False
        # usuń też ewentualny nadany dostęp do planów w obie strony
        PlanAccess.query.filter(
            or_(
                and_(PlanAccess.owner_id == friendship.requester_id, PlanAccess.viewer_id == friendship.addressee_id),
                and_(PlanAccess.owner_id == friendship.addressee_id, PlanAccess.viewer_id == friendship.requester_id),
            )
        ).delete()
        db.session.delete(friendship)
        db.session.commit()
        return True

    @staticmethod
    def list_friends(user_id: int):
        rows = Friendship.query.filter(
            Friendship.status == STATUS_ACCEPTED,
            or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
        ).all()
        return rows

    @staticmethod
    def list_incoming_requests(user_id: int):
        return Friendship.query.filter_by(addressee_id=user_id, status=STATUS_PENDING).all()

    @staticmethod
    def list_outgoing_requests(user_id: int):
        return Friendship.query.filter_by(requester_id=user_id, status=STATUS_PENDING).all()

    @staticmethod
    def are_friends(user_a_id: int, user_b_id: int) -> bool:
        rel = FriendService.get_relationship(user_a_id, user_b_id)
        return bool(rel and rel.status == STATUS_ACCEPTED)

    # ---------- dostęp do planów ----------
    @staticmethod
    def grant_access(owner_id: int, viewer_id: int, role: str = ACCESS_VIEWER) -> tuple[bool, str | None]:
        if not FriendService.are_friends(owner_id, viewer_id):
            return False, "Dostęp do planu można nadać tylko znajomym."
        if role not in ALL_ACCESS_ROLES:
            role = ACCESS_VIEWER
        existing = PlanAccess.query.filter_by(owner_id=owner_id, viewer_id=viewer_id).first()
        if existing:
            existing.role = role
            db.session.commit()
            return True, None
        db.session.add(PlanAccess(owner_id=owner_id, viewer_id=viewer_id, role=role))
        db.session.commit()
        return True, None

    @staticmethod
    def update_access_role(owner_id: int, viewer_id: int, role: str) -> tuple[bool, str | None]:
        """Zmienia rolę już nadanego dostępu (bez konieczności odbierania/nadawania od nowa)."""
        if role not in ALL_ACCESS_ROLES:
            return False, "Nieprawidłowa rola."
        access = PlanAccess.query.filter_by(owner_id=owner_id, viewer_id=viewer_id).first()
        if not access:
            return False, "Nie nadano jeszcze dostępu tej osobie."
        access.role = role
        db.session.commit()
        return True, None

    @staticmethod
    def revoke_access(owner_id: int, viewer_id: int) -> None:
        PlanAccess.query.filter_by(owner_id=owner_id, viewer_id=viewer_id).delete()
        db.session.commit()

    @staticmethod
    def has_access(owner_id: int, viewer_id: int) -> bool:
        if owner_id == viewer_id:
            return True
        return PlanAccess.query.filter_by(owner_id=owner_id, viewer_id=viewer_id).first() is not None

    @staticmethod
    def get_access_role(owner_id: int, viewer_id: int) -> str | None:
        """Rola `viewer_id` w planie `owner_id`: 'editor' dla właściciela samego
        siebie, rola z PlanAccess dla znajomego z nadanym dostępem, albo None
        (brak dostępu)."""
        if owner_id == viewer_id:
            return ACCESS_EDITOR
        access = PlanAccess.query.filter_by(owner_id=owner_id, viewer_id=viewer_id).first()
        return access.role if access else None

    @staticmethod
    def list_viewers_for(owner_id: int):
        """Znajomi, którym nadano dostęp do MOJEGO planu."""
        return PlanAccess.query.filter_by(owner_id=owner_id).all()

    @staticmethod
    def list_accessible_owners_for(viewer_id: int):
        """Osoby, których plan mogę oglądać."""
        return PlanAccess.query.filter_by(viewer_id=viewer_id).all()
