from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from models.user_model import User  # noqa: E402
from models.friendship_model import Friendship, PlanAccess  # noqa: E402
from models.activity_model import ActivityType, Activity, DEFAULT_ACTIVITY_TYPES  # noqa: E402
from models.group_model import (  # noqa: E402
    Group,
    GroupMember,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    ALL_ROLES,
    ROLE_LABELS,
)
from models.announcement_model import Announcement  # noqa: E402

__all__ = [
    "db",
    "User",
    "Friendship",
    "PlanAccess",
    "ActivityType",
    "Activity",
    "DEFAULT_ACTIVITY_TYPES",
    "Group",
    "GroupMember",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
    "ALL_ROLES",
    "ROLE_LABELS",
    "Announcement",
]
