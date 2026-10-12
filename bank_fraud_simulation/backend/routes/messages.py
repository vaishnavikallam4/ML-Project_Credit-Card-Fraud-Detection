from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.audit_log import AuditLog
from backend.models.card import Card
from backend.models.communication_message import CommunicationMessage
from backend.models.fraud_case import FraudCase
from backend.models.user import User


messages_bp = Blueprint("messages", __name__, url_prefix="/api/messages")
ALLOWED_CARD_ACTIONS = {"NONE", "HOLD", "BLOCKED"}


def _message_payload(item):
    return {
        "message_id": item.message_id,
        "customer_id": item.customer_id,
        "sender_id": item.sender_id,
        "sender_name": item.sender.name if item.sender else "Bank",
        "sender_role": item.sender.role if item.sender else "BANK_ADMIN",
        "case_id": item.case_id,
        "card_id": item.card_id,
        "card_last_four": item.card.last_four if item.card else None,
        "requested_card_action": item.requested_card_action,
        "message": item.message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _load_customer_messages(customer_id):
    return CommunicationMessage.query.filter_by(customer_id=customer_id) \
        .order_by(CommunicationMessage.created_at.asc(), CommunicationMessage.message_id.asc()).all()


def _save_message(customer, sender, data):
    message_text = str(data.get("message") or "").strip()
    if not message_text:
        return None, (jsonify({"message": "message is required."}), 400)
    if len(message_text) > 2000:
        return None, (jsonify({"message": "message must be 2000 characters or fewer."}), 400)

    action = str(data.get("requested_card_action") or "NONE").upper()
    if action not in ALLOWED_CARD_ACTIONS:
        return None, (jsonify({"message": "requested_card_action must be NONE, HOLD, or BLOCKED."}), 400)

    card_id = data.get("card_id")
    if action == "NONE":
        card_id = None
    elif card_id is None:
        return None, (jsonify({"message": "Choose a card when requesting a hold or block."}), 400)
    else:
        try:
            card_id = int(card_id)
        except (TypeError, ValueError):
            return None, (jsonify({"message": "card_id must be an integer."}), 400)
        card = Card.query.filter_by(card_id=card_id, user_id=customer.user_id).first()
        if not card:
            return None, (jsonify({"message": "Card not found for this customer."}), 404)

    case_id = data.get("case_id")
    if case_id is not None:
        try:
            case_id = int(case_id)
        except (TypeError, ValueError):
            return None, (jsonify({"message": "case_id must be an integer."}), 400)
        if not FraudCase.query.filter_by(case_id=case_id, user_id=customer.user_id).first():
            return None, (jsonify({"message": "Fraud case not found for this customer."}), 404)

    item = CommunicationMessage(
        customer_id=customer.user_id,
        sender_id=sender.user_id,
        case_id=case_id,
        card_id=card_id,
        requested_card_action=action,
        message=message_text,
    )
    db.session.add(item)
    db.session.add(AuditLog(
        user_id=customer.user_id,
        actor_type=sender.role,
        actor_id=sender.user_id,
        action="CUSTOMER_ADMIN_MESSAGE_SENT",
        object_type="communication_message",
        details=f"Message sent in customer conversation; requested card action: {action}.",
    ))
    db.session.commit()
    return item, None


@messages_bp.route("", methods=["GET"])
@jwt_required()
def list_customer_messages():
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can read messages from this endpoint."}), 403

    return jsonify({
        "messages": [_message_payload(item) for item in _load_customer_messages(user.user_id)],
    }), 200


@messages_bp.route("", methods=["POST"])
@jwt_required()
def send_customer_message():
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can start a customer conversation."}), 403

    item, error = _save_message(user, user, request.get_json(silent=True) or {})
    if error:
        return error
    return jsonify({"message": "Message sent to the bank.", "item": _message_payload(item)}), 201


@messages_bp.route("/customers/<int:customer_id>", methods=["GET"])
@jwt_required()
def list_admin_customer_messages(customer_id):
    admin = _current_user()
    if not admin or admin.role != "BANK_ADMIN":
        return jsonify({"message": "Only bank admins can access customer conversations."}), 403
    customer = User.query.filter_by(user_id=customer_id, role="CUSTOMER").first()
    if not customer:
        return jsonify({"message": "Customer not found."}), 404

    return jsonify({
        "messages": [_message_payload(item) for item in _load_customer_messages(customer_id)],
    }), 200


@messages_bp.route("/customers/<int:customer_id>", methods=["POST"])
@jwt_required()
def reply_to_customer(customer_id):
    admin = _current_user()
    if not admin or admin.role != "BANK_ADMIN":
        return jsonify({"message": "Only bank admins can reply to customer conversations."}), 403
    customer = User.query.filter_by(user_id=customer_id, role="CUSTOMER").first()
    if not customer:
        return jsonify({"message": "Customer not found."}), 404

    item, error = _save_message(customer, admin, request.get_json(silent=True) or {})
    if error:
        return error
    return jsonify({"message": "Reply sent to the customer.", "item": _message_payload(item)}), 201
