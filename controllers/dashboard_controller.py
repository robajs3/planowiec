from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user

from models import Activity, User, Group
from models.announcement_model import Announcement
from services.activity_service import ActivityService
from services.friend_service import FriendService
from services.group_service import GroupService

dashboard_bp = Blueprint("dashboard", __name__)


def _active_announcements():
    all_ann = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    return [a for a in all_ann if a.is_visible]


def _switcher_data():
    """Lista planów dostępnych do przełączenia w panelu bocznym kalendarza."""
    accessible = FriendService.list_accessible_owners_for(current_user.id)
    groups = GroupService.list_user_groups(current_user.id)
    return {
        "accessible_friends": [pa.owner for pa in accessible],
        "user_groups": groups,
    }


# ---------------------------------------------------------------------------
# Strony HTML
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/")
@login_required
def index():
    return render_template(
        "dashboard/index.html",
        context="own",
        context_id=current_user.id,
        can_edit=True,
        title="Mój plan",
        announcements=_active_announcements(),
        **_switcher_data(),
    )


@dashboard_bp.route("/dashboard/friend/<int:user_id>")
@login_required
def friend_calendar(user_id):
    owner = User.query.get_or_404(user_id)
    if not FriendService.has_access(owner_id=owner.id, viewer_id=current_user.id):
        abort(403)
    return render_template(
        "dashboard/index.html",
        context="friend",
        context_id=owner.id,
        can_edit=False,
        title=f"Plan: {owner.name}",
        **_switcher_data(),
    )


@dashboard_bp.route("/dashboard/group/<int:group_id>")
@login_required
def group_calendar(group_id):
    group = Group.query.get_or_404(group_id)
    if not GroupService.is_member(current_user.id, group.id):
        abort(403)
    can_edit = GroupService.is_admin(current_user.id, group.id)
    return render_template(
        "dashboard/index.html",
        context="group",
        context_id=group.id,
        can_edit=can_edit,
        title=f"Grupa: {group.name}",
        **_switcher_data(),
    )


# ---------------------------------------------------------------------------
# Pomocnicze — ustalanie kontekstu i uprawnień
# ---------------------------------------------------------------------------

def _resolve_context(context: str, context_id: int):
    """Zwraca (owner_id_lub_None, group_id_lub_None, can_edit) albo abort(403/404)."""
    if context == "own":
        if context_id != current_user.id:
            abort(403)
        return current_user.id, None, True

    if context == "friend":
        owner = User.query.get_or_404(context_id)
        if not FriendService.has_access(owner_id=owner.id, viewer_id=current_user.id):
            abort(403)
        return owner.id, None, False

    if context == "group":
        group = Group.query.get_or_404(context_id)
        if not GroupService.is_member(current_user.id, group.id):
            abort(403)
        can_edit = GroupService.is_admin(current_user.id, group.id)
        return None, group.id, can_edit

    abort(400)


@dashboard_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ---------------------------------------------------------------------------
# API: typy aktywności
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/types")
@login_required
def api_types():
    context = request.args.get("context", "own")
    context_id = request.args.get("id", type=int) or current_user.id

    if context == "group":
        group = Group.query.get_or_404(context_id)
        if not GroupService.is_member(current_user.id, group.id):
            abort(403)
        types = ActivityService.get_types_for_user(group.admin_id)
    else:
        owner_id, _, _ = _resolve_context(context, context_id)
        types = ActivityService.get_types_for_user(owner_id)

    return jsonify([t.to_dict() for t in types])


@dashboard_bp.route("/dashboard/api/types", methods=["POST"])
@login_required
def api_create_type():
    data = request.get_json(force=True, silent=True) or {}
    activity_type, error = ActivityService.create_type(
        current_user.id, data.get("name"), data.get("color"), data.get("icon", "circle")
    )
    if error:
        return jsonify({"error": error}), 400
    return jsonify(activity_type.to_dict()), 201


@dashboard_bp.route("/dashboard/api/types/<int:type_id>", methods=["PUT"])
@login_required
def api_update_type(type_id):
    data = request.get_json(force=True, silent=True) or {}
    activity_type, error = ActivityService.update_type(
        current_user.id, type_id, data.get("name"), data.get("color")
    )
    if error:
        return jsonify({"error": error}), 400
    return jsonify(activity_type.to_dict())


@dashboard_bp.route("/dashboard/api/types/<int:type_id>", methods=["DELETE"])
@login_required
def api_delete_type(type_id):
    ok, error = ActivityService.delete_type(current_user.id, type_id)
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API: aktywności (wpisy w kalendarzu)
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/activities")
@login_required
def api_list_activities():
    context = request.args.get("context", "own")
    context_id = request.args.get("id", type=int) or current_user.id
    owner_id, group_id, _ = _resolve_context(context, context_id)

    try:
        start = datetime.fromisoformat(request.args.get("start"))
        end = datetime.fromisoformat(request.args.get("end"))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowy zakres dat."}), 400

    type_ids_raw = request.args.get("types", "")
    type_ids = [int(x) for x in type_ids_raw.split(",") if x.strip().isdigit()] or None

    activities = ActivityService.get_activities(owner_id, group_id, start, end, type_ids)
    return jsonify([a.to_dict() for a in activities])


@dashboard_bp.route("/dashboard/api/activities", methods=["POST"])
@login_required
def api_create_activity():
    data = request.get_json(force=True, silent=True) or {}
    context = data.get("context", "own")
    context_id = data.get("id") or current_user.id
    owner_id, group_id, can_edit = _resolve_context(context, context_id)
    if not can_edit:
        abort(403)

    activity, error = ActivityService.create_activity(current_user.id, data, group_id=group_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(activity.to_dict()), 201


@dashboard_bp.route("/dashboard/api/activities/<int:activity_id>", methods=["PUT"])
@login_required
def api_update_activity(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    data = request.get_json(force=True, silent=True) or {}
    context = data.get("context", "own")
    context_id = data.get("id") or current_user.id
    _, _, can_edit = _resolve_context(context, context_id)
    if not can_edit:
        abort(403)
    if activity.group_id is None and activity.owner_id != current_user.id:
        abort(403)

    ok, error = ActivityService.update_activity(activity, data)
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify(activity.to_dict())


@dashboard_bp.route("/dashboard/api/activities/<int:activity_id>", methods=["DELETE"])
@login_required
def api_delete_activity(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    context = request.args.get("context", "own")
    context_id = request.args.get("id", type=int) or current_user.id
    _, _, can_edit = _resolve_context(context, context_id)
    if not can_edit:
        abort(403)
    if activity.group_id is None and activity.owner_id != current_user.id:
        abort(403)

    ActivityService.delete_activity(activity)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API: lista dostępnych "widoków" (znajomi z dostępem + grupy) do przełącznika
# ---------------------------------------------------------------------------

@dashboard_bp.route("/dashboard/api/views")
@login_required
def api_views():
    accessible = FriendService.list_accessible_owners_for(current_user.id)
    groups = GroupService.list_user_groups(current_user.id)
    return jsonify({
        "friends": [
            {"id": pa.owner.id, "name": pa.owner.name, "initials": pa.owner.initials,
             "avatar_color": pa.owner.avatar_color}
            for pa in accessible
        ],
        "groups": [
            {"id": g.id, "name": g.name, "code": g.code, "is_admin": g.admin_id == current_user.id}
            for g in groups
        ],
    })
