from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.models.notification import Notification
from backend.models.user import User

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), 404
    if current_user.role != "CUSTOMER":
        return jsonify({"message": "Admins can view notifications only inside the selected customer profile."}), 403

    notifications = Notification.query.filter_by(
        user_id=user_id,
        channel="IN_APP",
    ).order_by(Notification.created_at.desc()).all()

    return jsonify({
        "notifications": [{
            "notification_id": n.notification_id,
            "channel": n.channel,
            "message": n.message,
            "status": n.status,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "transaction_id": n.transaction_id,
            "case_id": n.case_id,
            "user_id": n.user_id,
            "customer_name": n.user.name if n.user else None,
            "phone_number": n.user.phone if n.user else None,
        } for n in notifications]
    }), 200
