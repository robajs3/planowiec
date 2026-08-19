from datetime import datetime

from models import db

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship("User", foreign_keys=[admin_id])
    members = db.relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    activities = db.relationship(
        "Activity", back_populates="group", cascade="all, delete-orphan"
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
    role = db.Column(db.String(20), default=ROLE_MEMBER, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    group = db.relationship("Group", back_populates="members")
    user = db.relationship("User")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def __repr__(self) -> str:
        return f"<GroupMember user={self.user_id} group={self.group_id} role={self.role}>"
