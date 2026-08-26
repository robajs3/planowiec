from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for

from flask_login import login_required, current_user

from models import db, Activity, User, Group
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
    # Jeśli użytkownik włączył opcję "Wszystkie plany w widoku głównym",
    # główny plan domyślnie agreguje własne aktywności + znajomych (którym
    # dano dostęp) + grup, do których należy.
    if current_user.show_all_plans:
        return render_template(
            "dashboard/index.html",
            context="all",
            context_id=current_user.id,
            can_edit=True,
            title="Wszystkie plany",
            announcements=_active_announcements(),
            **_switcher_data(),
        )
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
    can_edit = GroupService.can_edit_plan(current_user.id, group.id)
    can_manage_categories = GroupService.can_manage_categories(current_user.id, group.id)
    return render_template(
        "dashboard/index.html",
        context="group",
        context_id=group.id,
        can_edit=can_edit,
        can_manage_categories=can_manage_categories,
        title=f"Grupa: {group.name}",
        **_switcher_data(),
    )


@dashboard_bp.route("/dashboard/settings/all-plans", methods=["POST"])
@login_required
def toggle_all_plans():
    """Włącza/wyłącza domyślną agregację 'Wszystkie plany' w widoku głównym."""
    current_user.show_all_plans = not current_user.show_all_plans
    db.session.commit()
    next_url = request.form.get("next") or url_for("dashboard.index")
    return redirect(next_url)


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
        can_edit = GroupService.can_edit_plan(current_user.id, group.id)
        return None, group.id, can_edit

    if context == "all":
        # Widok zagregowany jest tylko-do-odczytu na tym poziomie: edycja
        # zawsze przechodzi przez rzeczywisty kontekst (own/group) danej
        # aktywności, ustalany po stronie klienta na podstawie jej "source".
        if context_id != current_user.id:
            abort(403)
        return current_user.id, None, False

    abort(400)


@dashboard_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ---------------------------------------------------------------------------
# API: typy aktywności / kategorie
# ---------------------------------------------------------------------------

def _merge_types(*groups_of_types):
    seen = {}
    for types in groups_of_types:
        for t in types:
            seen[t.id] = t
    result = list(seen.values())
    result.sort(key=lambda t: (not t.is_default, t.name.lower()))
    return result


@dashboard_bp.route("/dashboard/api/types")
@login_required
def api_types():
    context = request.args.get("context", "own")
    context_id = request.args.get("id", type=int) or current_user.id

    if context == "group":
        group = Group.query.get_or_404(context_id)
        if not GroupService.is_member(current_user.id, group.id):
            abort(403)
        types = ActivityService.get_types_for_group(group.id)

    elif context == "all":
        if context_id != current_user.id:
            abort(403)
        own_types = ActivityService.get_types_for_user(current_user.id)
        friend_types = []
        for pa in FriendService.list_accessible_owners_for(current_user.id):
            friend_types.extend(ActivityService.get_types_for_user(pa.owner_id))
        group_types = []
        for g in GroupService.list_user_groups(current_user.id):
            group_types.extend(ActivityService.get_types_for_group(g.id))
        types = _merge_types(own_types, friend_types, group_types)

    else:
        owner_id, _, _ = _resolve_context(context, context_id)
        types = ActivityService.get_types_for_user(owner_id)

    return jsonify([t.to_dict() for t in types])


@dashboard_bp.route("/dashboard/api/types", methods=["POST"])
@login_required
def api_create_type():
    data = request.get_json(force=True, silent=True) or {}
    context = data.get("context", "own")

    if context == "group":
        group_id = data.get("id")
        if not group_id or not GroupService.can_manage_categories(current_user.id, group_id):
            abort(403)
        activity_type, error = ActivityService.create_group_type(
            group_id, data.get("name"), data.get("color"), data.get("icon", "circle")
        )
    else:
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
    context = data.get("context", "own")

    if context == "group":
        group_id = data.get("id")
        if not group_id or not GroupService.can_manage_categories(current_user.id, group_id):
            abort(403)
        activity_type, error = ActivityService.update_group_type(
            group_id, type_id, data.get("name"), data.get("color")
        )
    else:
        activity_type, error = ActivityService.update_type(
            current_user.id, type_id, data.get("name"), data.get("color")
        )

    if error:
        return jsonify({"error": error}), 400
    return jsonify(activity_type.to_dict())


@dashboard_bp.route("/dashboard/api/types/<int:type_id>", methods=["DELETE"])
@login_required
def api_delete_type(type_id):
    context = request.args.get("context", "own")

    if context == "group":
        group_id = request.args.get("id", type=int)
        if not group_id or not GroupService.can_manage_categories(current_user.id, group_id):
            abort(403)
        ok, error = ActivityService.delete_group_type(group_id, type_id)
    else:
        ok, error = ActivityService.delete_type(current_user.id, type_id)

    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API: aktywności (wpisy w kalendarzu)
# ---------------------------------------------------------------------------

def _source_badge(kind: str, context_id: int, label: str, color: str, can_edit: bool) -> dict:
    # "kind" i "id" odpowiadają wprost wartościom context/id używanym przez
    # resztę API (own/friend/group), żeby front mógł po kliknięciu aktywności
    # z widoku zagregowanego wysłać PUT/DELETE do właściwego, rzeczywistego
    # kontekstu (a nie do samego "all", które jest tylko-do-odczytu).
    return {"kind": kind, "id": context_id, "label": label, "color": color, "can_edit": can_edit}


def _list_activities_all(start: datetime, end: datetime, type_ids: list[int] | None):
    results = []

    own = ActivityService.get_activities(current_user.id, None, start, end, type_ids)
    own_badge = _source_badge("own", current_user.id, "Mój plan", current_user.avatar_color, True)
    results.extend(a.to_dict(source=own_badge) for a in own)

    for pa in FriendService.list_accessible_owners_for(current_user.id):
        owner = pa.owner
        friend_activities = ActivityService.get_activities(owner.id, None, start, end, type_ids)
        badge = _source_badge("friend", owner.id, owner.name, owner.avatar_color, False)
        results.extend(a.to_dict(source=badge) for a in friend_activities)

    for g in GroupService.list_user_groups(current_user.id):
        group_activities = ActivityService.get_activities(None, g.id, start, end, type_ids)
        can_edit = GroupService.can_edit_plan(current_user.id, g.id)
        badge = _source_badge("group", g.id, g.name, "#0284c7", can_edit)
        results.extend(a.to_dict(source=badge) for a in group_activities)

    results.sort(key=lambda a: a["start"])
    return results


@dashboard_bp.route("/dashboard/api/activities")
@login_required
def api_list_activities():
    context = request.args.get("context", "own")
    context_id = request.args.get("id", type=int) or current_user.id

    try:
        start = datetime.fromisoformat(request.args.get("start"))
        end = datetime.fromisoformat(request.args.get("end"))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowy zakres dat."}), 400

    type_ids_raw = request.args.get("types", "")
    type_ids = [int(x) for x in type_ids_raw.split(",") if x.strip().isdigit()] or None

    if context == "all":
        if context_id != current_user.id:
            abort(403)
        return jsonify(_list_activities_all(start, end, type_ids))

    owner_id, group_id, _ = _resolve_context(context, context_id)
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
            {"id": g.id, "name": g.name, "code": g.code,
             "can_edit": GroupService.can_edit_plan(current_user.id, g.id)}
            for g in groups
        ],
        "show_all_plans": current_user.show_all_plans,
    })
