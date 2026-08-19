from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from models import Group
from services.group_service import GroupService

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
    if not GroupService.is_member(current_user.id, group.id):
        abort(403)
    members = GroupService.list_members(group.id)
    is_admin = GroupService.is_admin(current_user.id, group.id)
    return render_template("groups/detail.html", group=group, members=members, is_admin=is_admin)


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
