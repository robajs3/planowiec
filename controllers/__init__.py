from controllers.auth_controller import auth_bp
from controllers.dashboard_controller import dashboard_bp
from controllers.friends_controller import friends_bp
from controllers.groups_controller import groups_bp
from controllers.profile_controller import profile_bp
from controllers.admin_controller import admin_bp
from controllers.import_controller import import_bp

__all__ = [
    "auth_bp",
    "dashboard_bp",
    "friends_bp",
    "groups_bp",
    "profile_bp",
    "admin_bp",
    "import_bp",
]
