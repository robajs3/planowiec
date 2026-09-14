from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

from flask_login import login_required, current_user

from models import db, Group, ALL_ROLES, ROLE_LABELS
from services.group_service import GroupService
from services.activity_service import ActivityService

groups_bp = Blueprint("groups", __name__)


@groups_bp.route("/groups/")
@login_required
def index():
    groups = GroupService.list_user_groups(current_user.id)
    return render_template("groups/list.html", groups=groups, current_user_id=current_user.id)


@groups_bp.route("/groups/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        group, error = GroupService.create_group(current_user.id, name, description)
        if error:
            flash(error, "danger")
        else:
            flash(f'Grupa "{group.name}" utworzona! Kod dołączenia: {group.code}', "success")
            return redirect(url_for("groups.detail", group_id=group.id))
    return render_template("groups/create.html")


@groups_bp.route("/groups/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        group, error = GroupService.join_by_code(current_user.id, code)
        if group and not error:
            flash(f'Dołączono do grupy "{group.name}".', "success")
            return redirect(url_for("groups.detail", group_id=group.id))
        flash(error or "Nie udało się dołączyć do grupy.", "danger")
    return render_template("groups/create.html", join_mode=True)


@groups_bp.route("/groups/<int:group_id>")
@login_required
def detail(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupService.get_membership(current_user.id, group.id)
    if not membership:
        abort(403)
    members = GroupService.list_members(group.id)
    categories = ActivityService.get_types_for_group(group.id)
    return render_template(
        "groups/detail.html",
        group=group,
        members=members,
        categories=categories,
        membership=membership,
        is_admin=membership.can_manage_roles,
        can_manage_categories=membership.can_manage_categories,
        all_roles=ALL_ROLES,
        role_labels=ROLE_LABELS,
    )


@groups_bp.route("/groups/<int:group_id>/notifications", methods=["POST"])
@login_required
def toggle_notifications(group_id):
    """Włącza/wyłącza powiadomienia o nowych aktywnościach w TEJ grupie dla
    zalogowanego użytkownika. Ma znaczenie tylko, gdy jego globalna
    preferencja (Profil → Powiadomienia → Ustawienia) to „tylko wybrane
    grupy" — przy „wszystkie"/„brak" ta flaga jest ignorowana."""
    membership = GroupService.get_membership(current_user.id, group_id)
    if not membership:
        abort(403)
    membership.notifications_enabled = not membership.notifications_enabled
    db.session.commit()
    flash(
        "Włączono powiadomienia dla tej grupy." if membership.notifications_enabled
        else "Wyłączono powiadomienia dla tej grupy.",
        "success",
    )
    next_url = request.form.get("next") or url_for("groups.detail", group_id=group_id)
    return redirect(next_url)


@groups_bp.route("/groups/<int:group_id>/leave", methods=["POST"])
@login_required
def leave(group_id):
    ok, error = GroupService.leave_group(current_user.id, group_id)
    flash("Opuszczono grupę." if ok else (error or "Błąd."), "info" if ok else "danger")
    return redirect(url_for("groups.index"))


@groups_bp.route("/groups/<int:group_id>/delete", methods=["POST"])
@login_required
def delete(group_id):
    ok, error = GroupService.delete_group(current_user.id, group_id)
    flash("Grupa usunięta." if ok else (error or "Błąd."), "info" if ok else "danger")
    return redirect(url_for("groups.index"))


# ---------------------------------------------------------------------------
# Zarządzanie rolami / członkami (tylko admin)
# ---------------------------------------------------------------------------

@groups_bp.route("/groups/<int:group_id>/members/<int:user_id>/role", methods=["POST"])
@login_required
def set_role(group_id, user_id):
    new_role = request.form.get("role", "")
    ok, error = GroupService.set_member_role(current_user.id, group_id, user_id, new_role)
    flash("Zaktualizowano rolę." if ok else (error or "Błąd."), "success" if ok else "danger")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/members/<int:user_id>/remove", methods=["POST"])
@login_required
def remove_member(group_id, user_id):
    ok, error = GroupService.remove_member(current_user.id, group_id, user_id)
    flash("Usunięto członka z grupy." if ok else (error or "Błąd."), "info" if ok else "danger")
    return redirect(url_for("groups.detail", group_id=group_id))


# ---------------------------------------------------------------------------
# Zarządzanie kategoriami aktywności grupy (admin i editor)
# ---------------------------------------------------------------------------

@groups_bp.route("/groups/<int:group_id>/categories/create", methods=["POST"])
@login_required
def create_category(group_id):
    if not GroupService.can_manage_categories(current_user.id, group_id):
        abort(403)
    name = request.form.get("name", "")
    color = request.form.get("color", "#4f46e5")
    _, error = ActivityService.create_group_type(group_id, name, color)
    if error:
        flash(error, "danger")
    else:
        flash("Dodano kategorię.", "success")
    return redirect(url_for("groups.detail", group_id=group_id))


@groups_bp.route("/groups/<int:group_id>/categories/<int:type_id>/delete", methods=["POST"])
@login_required
def delete_category(group_id, type_id):
    if not GroupService.can_manage_categories(current_user.id, group_id):
        abort(403)
    ok, error = ActivityService.delete_group_type(group_id, type_id)
    flash("Usunięto kategorię." if ok else (error or "Błąd."), "info" if ok else "danger")
    return redirect(url_for("groups.detail", group_id=group_id))
