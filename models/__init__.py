from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from models.user_model import User  # noqa: E402
from models.friendship_model import (  # noqa: E402
    Friendship,
    PlanAccess,
    ACCESS_EDITOR,
    ACCESS_COMMENTER,
    ACCESS_VIEWER,
    ALL_ACCESS_ROLES,
    ACCESS_ROLE_LABELS,
)
from models.activity_model import (  # noqa: E402
    ActivityType,
    Activity,
    ActivityComment,
    DayMarker,
    DayMarkerAssignment,
    DEFAULT_ACTIVITY_TYPES,
)
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
from models.notification_model import Notification  # noqa: E402

__all__ = [
    "db",
    "User",
    "Friendship",
    "PlanAccess",
    "ACCESS_EDITOR",
    "ACCESS_COMMENTER",
    "ACCESS_VIEWER",
    "ALL_ACCESS_ROLES",
    "ACCESS_ROLE_LABELS",
    "ActivityType",
    "Activity",
    "ActivityComment",
    "DayMarker",
    "DayMarkerAssignment",
    "DEFAULT_ACTIVITY_TYPES",
    "Group",
    "GroupMember",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
    "ALL_ROLES",
    "ROLE_LABELS",
    "Announcement",
    "Notification",
]
