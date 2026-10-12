from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.account import Account
from backend.models.card import Card
from backend.models.audit_log import AuditLog
from backend.models.fraud_alert import FraudAlert
from backend.models.fraud_case import FraudCase
from backend.models.notification import Notification
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.services.sms_service import deliver_sms_notification
from backend.services.transaction_ledger import transaction_direction

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _require_admin():
    current_user = User.query.get(int(get_jwt_identity()))
    if not current_user or current_user.role != "BANK_ADMIN":
        return None, (jsonify({"message": "Only bank admins can perform this action."}), 403)
    return current_user, None


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_customer_directory():
    current_user, error_response = _require_admin()
    if error_response:
        return error_response

    customers = User.query.filter_by(role="CUSTOMER").order_by(User.created_at.desc()).all()
    payload = [{
            "user_id": customer.user_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
        } for customer in customers]

    return jsonify({"users": payload}), 200


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@jwt_required()
def get_customer_profile(user_id):
    current_user, error_response = _require_admin()
    if error_response:
        return error_response

    customer = User.query.get(user_id)
    if not customer or customer.role != "CUSTOMER":
        return jsonify({"message": "Customer not found."}), 404

    accounts = Account.query.filter_by(user_id=user_id).order_by(Account.created_at.desc()).all()
    cards = Card.query.filter_by(user_id=user_id).order_by(Card.created_at.desc()).all()
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.transaction_time.desc()).all()
    alerts = FraudAlert.query.filter_by(user_id=user_id).order_by(FraudAlert.created_at.desc()).all()
    cases = FraudCase.query.filter_by(user_id=user_id).order_by(FraudCase.created_at.desc()).all()
    sms_messages = Notification.query.filter_by(
        user_id=user_id,
        channel="SMS",
    ).order_by(Notification.created_at.desc()).all()

    return jsonify({
        "user": {
            "user_id": customer.user_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
            "role": customer.role,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
        },
        "accounts": [{
            "account_id": acc.account_id,
            "account_number": acc.account_number,
            "account_type": acc.account_type,
            "balance": acc.balance,
            "status": acc.status,
        } for acc in accounts],
        "cards": [{
            "card_id": card.card_id,
            "card_type": card.card_type,
            "last_four": card.last_four,
            "expiry_month": card.expiry_month,
            "expiry_year": card.expiry_year,
            "status": card.status,
            "account_id": card.account_id,
        } for card in cards],
        "transactions": [{
            "transaction_id": tx.transaction_id,
            "merchant": tx.merchant,
            "location": tx.location,
            "amount": tx.amount,
            "transaction_type": tx.transaction_type,
            "direction": transaction_direction(tx.transaction_type),
            "status": tx.status,
            "risk_level": tx.risk_level,
            "fraud_probability": tx.fraud_probability,
            "prediction": tx.prediction,
            "transaction_time": tx.transaction_time.isoformat() if tx.transaction_time else None,
        } for tx in transactions],
        "alerts": [{
            "alert_id": alert.alert_id,
            "message": alert.message,
            "risk_level": alert.risk_level,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        } for alert in alerts],
        "cases": [{
            "case_id": case.case_id,
            "case_status": case.case_status,
            "customer_response": case.customer_response,
            "resolution_decision": case.resolution_decision,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "police_report": {
                "reference_number": case.police_report.reference_number,
                "police_station": case.police_report.police_station,
                "status": case.police_report.status,
                "created_at": case.police_report.created_at.isoformat() if case.police_report.created_at else None,
            } if case.police_report else None,
        } for case in cases],
        "sms_messages": [{
            "notification_id": item.notification_id,
            "message": item.message,
            "status": item.status,
            "phone_number": customer.phone,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        } for item in sms_messages],
    }), 200


@admin_bp.route("/cards/<int:card_id>/status", methods=["PATCH"])
@jwt_required()
def update_card_status(card_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    card = Card.query.get(card_id)
    if not card:
        return jsonify({"message": "Card not found."}), 404

    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").upper()
    if status not in {"ACTIVE", "HOLD", "BLOCKED"}:
        return jsonify({"message": "status must be ACTIVE, HOLD, or BLOCKED."}), 400

    previous_status = card.status
    card.status = status
    db.session.add(AuditLog(
        user_id=card.user_id,
        actor_type="BANK_ADMIN",
        actor_id=admin.user_id,
        action="CARD_STATUS_CHANGED",
        object_type="card",
        object_id=card.card_id,
        details=f"Card ending {card.last_four} status changed from {previous_status} to {status}.",
    ))
    message = f"Your {card.card_type} card ending {card.last_four} status was changed to {status.lower()} by the bank."
    db.session.add(Notification(
        user_id=card.user_id,
        channel="IN_APP",
        message=message,
        status="SENT",
    ))
    sms_notification = Notification(
        user_id=card.user_id,
        channel="SMS",
        message=f"VELORA BANK: {message}",
        status="QUEUED",
    )
    db.session.add(sms_notification)
    db.session.commit()
    deliver_sms_notification(sms_notification, card.user.phone if card.user else None)
    db.session.commit()

    return jsonify({
        "message": "Card status updated.",
        "card_id": card.card_id,
        "status": card.status,
        "phone_number": card.user.phone if card.user else None,
        "phone_alert_status": sms_notification.status,
    }), 200
