from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from models import User
from models.friendship_model import STATUS_ACCEPTED
from services.friend_service import FriendService

friends_bp = Blueprint("friends", __name__)


@friends_bp.route("/friends/")
@login_required
def index():
    query = request.args.get("q", "").strip()
    results = FriendService.search_users(query, current_user.id) if query else []

    # oznacz status relacji dla wyników wyszukiwania
    annotated = []
    for user in results:
        rel = FriendService.get_relationship(current_user.id, user.id)
        annotated.append({"user": user, "relationship": rel})

    friendships = FriendService.list_friends(current_user.id)
    friends = [f.other(current_user.id) for f in friendships]
    incoming = FriendService.list_incoming_requests(current_user.id)
    outgoing = FriendService.list_outgoing_requests(current_user.id)

    granted_to = {pa.viewer_id for pa in FriendService.list_viewers_for(current_user.id)}
    accessible_from = FriendService.list_accessible_owners_for(current_user.id)

    return render_template(
        "friends/list.html",
        query=query,
        results=annotated,
        friends=list(zip(friends, [f.id for f in friendships])),
        incoming=incoming,
        outgoing=outgoing,
        granted_to=granted_to,
        accessible_from=accessible_from,
    )


@friends_bp.route("/friends/request/<int:user_id>", methods=["POST"])
@login_required
def send_request(user_id):
    target = User.query.get_or_404(user_id)
    _, error = FriendService.send_request(current_user.id, target.id)
    if error:
        flash(error, "danger")
    else:
        flash(f"Wysłano zaproszenie do {target.name}.", "success")
    return redirect(request.referrer or url_for("friends.index"))


@friends_bp.route("/friends/accept/<int:friendship_id>", methods=["POST"])
@login_required
def accept_request(friendship_id):
    ok, error = FriendService.respond_to_request(friendship_id, current_user.id, accept=True)
    flash("Zaproszenie zaakceptowane." if ok else (error or "Błąd."), "success" if ok else "danger")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/decline/<int:friendship_id>", methods=["POST"])
@login_required
def decline_request(friendship_id):
    ok, error = FriendService.respond_to_request(friendship_id, current_user.id, accept=False)
    flash("Zaproszenie odrzucone." if ok else (error or "Błąd."), "info" if ok else "danger")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/remove/<int:friendship_id>", methods=["POST"])
@login_required
def remove_friend(friendship_id):
    ok = FriendService.remove_friend(friendship_id, current_user.id)
    flash("Usunięto znajomego." if ok else "Nie udało się usunąć.", "info" if ok else "danger")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/access/grant/<int:viewer_id>", methods=["POST"])
@login_required
def grant_access(viewer_id):
    ok, error = FriendService.grant_access(current_user.id, viewer_id)
    if ok:
        flash("Nadano dostęp do Twojego planu.", "success")
    else:
        flash(error, "danger")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/access/revoke/<int:viewer_id>", methods=["POST"])
@login_required
def revoke_access(viewer_id):
    FriendService.revoke_access(current_user.id, viewer_id)
    flash("Odebrano dostęp do Twojego planu.", "info")
    return redirect(url_for("friends.index"))
