from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

import sso_client
from services.koloseum_import_service import KoloseumImportService
from services.group_service import GroupService

import_bp = Blueprint("import_koloseum", __name__)


@import_bp.route("/import/koloseum", methods=["GET"])
@login_required
def index():
    koloseum_user_id = sso_client.resolve_local_user_id(app_slug="koloseum")
    if not koloseum_user_id:
        return render_template("import/koloseum.html", linked=False, exams=[], groups=[], already=set())

    exams, error = KoloseumImportService.fetch_exams(koloseum_user_id)
    if error:
        flash(error, "danger")
        exams = []

    groups = [
        g for g in GroupService.list_user_groups(current_user.id)
        if GroupService.can_edit_plan(current_user.id, g.id)
    ]
    already_own = KoloseumImportService.already_imported_refs(current_user.id, None)

    return render_template(
        "import/koloseum.html",
        linked=True,
        exams=exams or [],
        groups=groups,
        already=already_own,
    )


@import_bp.route("/import/koloseum", methods=["POST"])
@login_required
def do_import():
    koloseum_user_id = sso_client.resolve_local_user_id(app_slug="koloseum")
    if not koloseum_user_id:
        flash("Połącz najpierw konto koloseum w LoginHub.", "danger")
        return redirect(url_for("import_koloseum.index"))

    exams, error = KoloseumImportService.fetch_exams(koloseum_user_id)
    if error:
        flash(error, "danger")
        return redirect(url_for("import_koloseum.index"))

    selected_ids = {int(i) for i in request.form.getlist("exam_ids") if i.isdigit()}
    selected_exams = [e for e in (exams or []) if e.get("id") in selected_ids]
    if not selected_exams:
        flash("Nie wybrano żadnego egzaminu do importu.", "info")
        return redirect(url_for("import_koloseum.index"))

    target = request.form.get("target", "own")
    group_id = None
    if target == "group":
        group_id = request.form.get("group_id", type=int)
        if not group_id or not GroupService.can_edit_plan(current_user.id, group_id):
            flash("Nie masz uprawnień do edycji planu tej grupy (albo nie wybrano grupy).", "danger")
            return redirect(url_for("import_koloseum.index"))

    count = KoloseumImportService.import_exams(selected_exams, owner_id=current_user.id, group_id=group_id)
    flash(f"Zaimportowano {count} egzamin(ów) z koloseum.", "success")
    return redirect(url_for("dashboard.index"))
