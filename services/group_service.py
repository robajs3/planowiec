import random
import string

from models import db, Group, GroupMember
from models.group_model import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ALL_ROLES


def _random_block(length: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


class GroupService:

    @staticmethod
    def generate_unique_code() -> str:
        while True:
            code = f"PLAN-{_random_block()}-{_random_block()}-{_random_block()}"
            if not Group.query.filter_by(code=code).first():
                return code

    @staticmethod
    def create_group(admin_id: int, name: str, description: str = "") -> tuple[Group | None, str | None]:
        name = (name or "").strip()
        if not name:
            return None, "Podaj nazwę grupy."
        group = Group(
            name=name,
            description=(description or "").strip(),
            code=GroupService.generate_unique_code(),
            admin_id=admin_id,
        )
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=admin_id, role=ROLE_ADMIN))
        db.session.commit()

        # Każda grupa dostaje własną, niezależną kopię domyślnych kategorii —
        # admin/editor tej konkretnej grupy może je potem dowolnie edytować
        # lub usuwać, bez wpływu na inne grupy czy prywatne plany.
        from services.activity_service import ActivityService
        ActivityService.seed_group_defaults(group.id)

        return group, None

    @staticmethod
    def join_by_code(user_id: int, code: str) -> tuple[Group | None, str | None]:
        code = (code or "").strip().upper()
        group = Group.query.filter_by(code=code).first()
        if not group:
            return None, "Nie znaleziono grupy o podanym kodzie."
        existing = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first()
        if existing:
            return group, "Jesteś już członkiem tej grupy."
        db.session.add(GroupMember(group_id=group.id, user_id=user_id, role=ROLE_VIEWER))
        db.session.commit()
        return group, None

    @staticmethod
    def leave_group(user_id: int, group_id: int) -> tuple[bool, str | None]:
        group = Group.query.get(group_id)
        if not group:
            return False, "Nie znaleziono grupy."
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            return False, "Nie jesteś członkiem tej grupy."
        if membership.is_admin and GroupService.count_admins(group_id) <= 1:
            return False, "Jesteś jedynym adminem — nadaj rolę admina komuś innemu albo usuń grupę."
        db.session.delete(membership)
        db.session.commit()
        return True, None

    @staticmethod
    def delete_group(user_id: int, group_id: int) -> tuple[bool, str | None]:
        if not GroupService.is_admin(user_id, group_id):
            return False, "Brak uprawnień do usunięcia tej grupy."
        group = Group.query.get(group_id)
        if not group:
            return False, "Nie znaleziono grupy."
        db.session.delete(group)
        db.session.commit()
        return True, None

    @staticmethod
    def get_membership(user_id: int, group_id: int) -> GroupMember | None:
        return GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()

    @staticmethod
    def is_member(user_id: int, group_id: int) -> bool:
        return GroupService.get_membership(user_id, group_id) is not None

    @staticmethod
    def is_admin(user_id: int, group_id: int) -> bool:
        membership = GroupService.get_membership(user_id, group_id)
        return bool(membership and membership.is_admin)

    @staticmethod
    def can_edit_plan(user_id: int, group_id: int) -> bool:
        membership = GroupService.get_membership(user_id, group_id)
        return bool(membership and membership.can_edit_plan)

    @staticmethod
    def can_manage_categories(user_id: int, group_id: int) -> bool:
        membership = GroupService.get_membership(user_id, group_id)
        return bool(membership and membership.can_manage_categories)

    @staticmethod
    def count_admins(group_id: int) -> int:
        return GroupMember.query.filter_by(group_id=group_id, role=ROLE_ADMIN).count()

    @staticmethod
    def list_user_groups(user_id: int):
        return (
            Group.query.join(GroupMember, Group.id == GroupMember.group_id)
            .filter(GroupMember.user_id == user_id)
            .order_by(Group.name.asc())
            .all()
        )

    @staticmethod
    def list_members(group_id: int):
        members = (
            GroupMember.query.filter_by(group_id=group_id)
            .join(GroupMember.user)
            .all()
        )
        # Sortowanie wg wagi roli (admin > editor > viewer), potem alfabetycznie.
        return sorted(members, key=lambda m: (-m.role_weight, m.user.name.lower()))

    @staticmethod
    def set_member_role(actor_id: int, group_id: int, target_user_id: int, new_role: str) -> tuple[bool, str | None]:
        """Zmiana roli członka grupy — może to zrobić wyłącznie admin."""
        if new_role not in ALL_ROLES:
            return False, "Nieprawidłowa rola."
        if not GroupService.is_admin(actor_id, group_id):
            return False, "Tylko admin grupy może zarządzać rolami."

        membership = GroupService.get_membership(target_user_id, group_id)
        if not membership:
            return False, "Ta osoba nie jest członkiem grupy."

        if membership.role == ROLE_ADMIN and new_role != ROLE_ADMIN and GroupService.count_admins(group_id) <= 1:
            return False, "Nie można odebrać roli admina jedynemu adminowi grupy — nadaj ją najpierw komuś innemu."

        membership.role = new_role
        db.session.commit()
        return True, None

    @staticmethod
    def remove_member(actor_id: int, group_id: int, target_user_id: int) -> tuple[bool, str | None]:
        """Usunięcie członka z grupy — może to zrobić wyłącznie admin (nie siebie samego)."""
        if not GroupService.is_admin(actor_id, group_id):
            return False, "Tylko admin grupy może usuwać członków."
        if actor_id == target_user_id:
            return False, "Aby opuścić grupę, użyj przycisku „Opuść grupę”."

        membership = GroupService.get_membership(target_user_id, group_id)
        if not membership:
            return False, "Ta osoba nie jest członkiem grupy."

        db.session.delete(membership)
        db.session.commit()
        return True, None
