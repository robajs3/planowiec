import random
import string

from models import db, Group, GroupMember
from models.group_model import ROLE_ADMIN, ROLE_MEMBER


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
        db.session.add(GroupMember(group_id=group.id, user_id=user_id, role=ROLE_MEMBER))
        db.session.commit()
        return group, None

    @staticmethod
    def leave_group(user_id: int, group_id: int) -> tuple[bool, str | None]:
        group = Group.query.get(group_id)
        if not group:
            return False, "Nie znaleziono grupy."
        if group.admin_id == user_id:
            return False, "Administrator nie może opuścić grupy — usuń grupę zamiast tego."
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            return False, "Nie jesteś członkiem tej grupy."
        db.session.delete(membership)
        db.session.commit()
        return True, None

    @staticmethod
    def delete_group(user_id: int, group_id: int) -> tuple[bool, str | None]:
        group = Group.query.get(group_id)
        if not group or group.admin_id != user_id:
            return False, "Brak uprawnień do usunięcia tej grupy."
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
    def list_user_groups(user_id: int):
        return (
            Group.query.join(GroupMember, Group.id == GroupMember.group_id)
            .filter(GroupMember.user_id == user_id)
            .order_by(Group.name.asc())
            .all()
        )

    @staticmethod
    def list_members(group_id: int):
        return (
            GroupMember.query.filter_by(group_id=group_id)
            .join(GroupMember.user)
            .order_by(GroupMember.role.desc())
            .all()
        )
