from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.audit_log import AuditLog
from backend.models.card import Card
from backend.models.fraud_alert import FraudAlert
from backend.models.fraud_case import FraudCase
from backend.models.notification import Notification
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.services.sms_service import deliver_sms_notification
from backend.services.transaction_ledger import apply_transaction_to_account, transaction_direction

alerts_bp = Blueprint("alerts", __name__, url_prefix="/api/alerts")


@alerts_bp.route("", methods=["GET"])
@jwt_required()
def list_alerts():
    user_id = int(get_jwt_identity())
    current_user = db.session.get(User, user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), 404
    if current_user.role not in {"CUSTOMER", "BANK_ADMIN"}:
        return jsonify({"message": "This role cannot access fraud alerts."}), 403

    if current_user.role == "CUSTOMER":
        alerts = FraudAlert.query.filter_by(user_id=user_id).order_by(FraudAlert.created_at.desc()).all()
    else:
        alerts = FraudAlert.query.order_by(FraudAlert.created_at.desc()).all()

    return jsonify({
        "alerts": [{
            "alert_id": a.alert_id,
            "transaction_id": a.transaction_id,
            "card_id": a.transaction.card_id if a.transaction else None,
            "risk_level": a.risk_level,
            "status": a.status,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "user_id": a.user_id,
            "customer_name": a.user.name if a.user else None,
            "merchant": a.transaction.merchant if a.transaction else None,
            "amount": a.transaction.amount if a.transaction else None,
            "direction": transaction_direction(a.transaction.transaction_type) if a.transaction else None,
            "transaction_time": a.transaction.transaction_time.isoformat() if a.transaction and a.transaction.transaction_time else None,
        } for a in alerts]
    }), 200


@alerts_bp.route("/<int:alert_id>/respond", methods=["POST"])
@jwt_required()
def respond_to_alert(alert_id):
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user or current_user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can respond to fraud alerts."}), 403
    data = request.get_json(silent=True) or {}
    response = str(data.get("response") or "").upper()

    alert = FraudAlert.query.filter_by(alert_id=alert_id, user_id=user_id).first()
    if not alert:
        return jsonify({"message": "Fraud alert not found."}), 404

    transaction = Transaction.query.get(alert.transaction_id)
    if not transaction:
        return jsonify({"message": "Transaction not found."}), 404
    if alert.status != "OPEN" or transaction.status != "PENDING":
        return jsonify({"message": "This alert has already been resolved."}), 409
    card = Card.query.get(transaction.card_id)
    sms_notification = None
    if response == "YES":
        ledger_error = apply_transaction_to_account(transaction)
        if ledger_error:
            return jsonify({"message": ledger_error}), 409
        alert.status = "RESOLVED"
        alert.resolved_at = db.func.now()
        transaction.status = "AUTHORIZED"
        transaction.prediction = "LEGITIMATE"
        db.session.add(AuditLog(
            user_id=user_id,
            actor_type="CUSTOMER",
            actor_id=user_id,
            action="CUSTOMER_CONFIRMED_TRANSACTION",
            object_type="transaction",
            object_id=transaction.transaction_id,
            details="Customer confirmed transaction as legitimate.",
        ))
    elif response == "NO":
        alert.status = "RESOLVED"
        alert.resolved_at = db.func.now()
        transaction.status = "FRAUD_REPORTED"
        if card:
            card.status = "HOLD"
        case = FraudCase(
            user_id=user_id,
            card_id=transaction.card_id,
            transaction_id=transaction.transaction_id,
            assigned_officer_id=None,
            case_status="OPEN",
            customer_response="NO",
        )
        db.session.add(case)
        db.session.flush()

        db.session.add(Notification(
            user_id=user_id,
            transaction_id=transaction.transaction_id,
            case_id=case.case_id,
            channel="IN_APP",
            message="Your fraud report has been received. Your card is on temporary hold and a fraud case is being investigated.",
            status="SENT",
        ))
        sms_notification = Notification(
            user_id=user_id,
            transaction_id=transaction.transaction_id,
            case_id=case.case_id,
            channel="SMS",
            message=f"VELORA BANK: Your fraud report has been received for ₹{transaction.amount:,.2f}. Your card is temporarily on hold while we investigate.",
            status="QUEUED",
        )
        db.session.add(sms_notification)

        db.session.add(AuditLog(
            user_id=user_id,
            actor_type="CUSTOMER",
            actor_id=user_id,
            action="CUSTOMER_REPORTED_FRAUD",
            object_type="case",
            object_id=case.case_id,
            details="Customer reported transaction as unauthorized.",
        ))
    else:
        return jsonify({"message": "response must be YES or NO."}), 400

    db.session.commit()
    if sms_notification:
        deliver_sms_notification(sms_notification, current_user.phone)
        db.session.commit()
    return jsonify({
        "message": "Fraud alert response recorded successfully.",
        "alert_status": alert.status,
        "transaction_status": transaction.status,
        "card_status": card.status if card else None,
    }), 200


@alerts_bp.route("/transactions/<int:transaction_id>/respond", methods=["POST"])
@jwt_required()
def respond_to_transaction(transaction_id):
    user_id = int(get_jwt_identity())
    current_user = db.session.get(User, user_id)
    if not current_user or current_user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can confirm or report transactions."}), 403

    data = request.get_json(silent=True) or {}
    response = str(data.get("response") or "").upper()
    if response not in {"YES", "NO"}:
        return jsonify({"message": "response must be YES or NO."}), 400

    transaction = Transaction.query.filter_by(transaction_id=transaction_id, user_id=user_id).first()
    if not transaction:
        return jsonify({"message": "Transaction not found for this customer."}), 404
    if transaction.status not in {"AUTHORIZED", "PENDING"}:
        return jsonify({"message": "This transaction can no longer be reviewed."}), 409

    open_case = FraudCase.query.filter(
        FraudCase.transaction_id == transaction_id,
        FraudCase.case_status.in_({"OPEN", "INVESTIGATING"}),
    ).first()
    if open_case:
        return jsonify({"message": "A fraud case is already open for this transaction."}), 409

    card = Card.query.get(transaction.card_id)
    sms_notification = None
    case = None
    if response == "YES":
        previous_confirmation = AuditLog.query.filter_by(
            user_id=user_id,
            action="CUSTOMER_CONFIRMED_TRANSACTION",
            object_type="transaction",
            object_id=transaction_id,
        ).first()
        if previous_confirmation:
            return jsonify({"message": "You have already confirmed this transaction."}), 409

        if transaction.status == "PENDING":
            alert = FraudAlert.query.filter_by(
                transaction_id=transaction_id,
                user_id=user_id,
                status="OPEN",
            ).first()
            if not alert:
                return jsonify({"message": "No open fraud alert was found for this pending transaction."}), 409
            ledger_error = apply_transaction_to_account(transaction)
            if ledger_error:
                return jsonify({"message": ledger_error}), 409
            alert.status = "RESOLVED"
            alert.resolved_at = db.func.now()
            transaction.status = "AUTHORIZED"
            transaction.prediction = "LEGITIMATE"

        db.session.add(AuditLog(
            user_id=user_id,
            actor_type="CUSTOMER",
            actor_id=user_id,
            action="CUSTOMER_CONFIRMED_TRANSACTION",
            object_type="transaction",
            object_id=transaction_id,
            details="Customer confirmed transaction as legitimate.",
        ))
    else:
        was_pending = transaction.status == "PENDING"
        if was_pending:
            alert = FraudAlert.query.filter_by(
                transaction_id=transaction_id,
                user_id=user_id,
                status="OPEN",
            ).first()
            if alert:
                alert.status = "RESOLVED"
                alert.resolved_at = db.func.now()
            transaction.status = "FRAUD_REPORTED"

        if card:
            card.status = "HOLD"
        case = FraudCase(
            user_id=user_id,
            card_id=transaction.card_id,
            transaction_id=transaction_id,
            assigned_officer_id=None,
            case_status="OPEN",
            customer_response="NO",
        )
        db.session.add(case)
        db.session.flush()

        db.session.add(Notification(
            user_id=user_id,
            transaction_id=transaction_id,
            case_id=case.case_id,
            channel="IN_APP",
            message="Your fraud report has been received. Your card is on temporary hold and a fraud case is being investigated.",
            status="SENT",
        ))
        sms_notification = Notification(
            user_id=user_id,
            transaction_id=transaction_id,
            case_id=case.case_id,
            channel="SMS",
            message=f"VELORA BANK: Your fraud report has been received for ₹{transaction.amount:,.2f}. Your card is temporarily on hold while we investigate.",
            status="QUEUED",
        )
        db.session.add(sms_notification)
        db.session.add(AuditLog(
            user_id=user_id,
            actor_type="CUSTOMER",
            actor_id=user_id,
            action="CUSTOMER_REPORTED_FRAUD",
            object_type="case",
            object_id=case.case_id,
            details="Customer reported a transaction as unauthorized from the notification center.",
        ))

    db.session.commit()
    if sms_notification:
        deliver_sms_notification(sms_notification, current_user.phone)
        db.session.commit()
    return jsonify({
        "message": "Transaction response recorded successfully.",
        "transaction_status": transaction.status,
        "card_status": card.status if card else None,
        "case_id": case.case_id if case else None,
    }), 200
