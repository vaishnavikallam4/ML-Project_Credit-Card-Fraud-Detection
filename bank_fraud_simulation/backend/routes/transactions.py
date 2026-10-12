from datetime import datetime
import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.account import Account
from backend.models.audit_log import AuditLog
from backend.models.card import Card
from backend.models.fraud_alert import FraudAlert
from backend.models.fraud_case import FraudCase
from backend.models.notification import Notification
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.services.behavior_analyzer import analyze_behavior
from backend.services.ml_service import predict_fraud
from backend.services.risk_engine import calculate_overall_risk
from backend.services.sms_service import deliver_sms_notification
from backend.services.transaction_ledger import apply_transaction_to_account, transaction_direction

transactions_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


@transactions_bp.route("", methods=["POST"])
@jwt_required()
def create_transaction():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), 404
    if current_user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can submit transactions."}), 403

    card_id = data.get("card_id")
    amount = data.get("amount")
    merchant = str(data.get("merchant") or "").strip() or "Unknown Merchant"
    location = str(data.get("location") or "").strip() or "Unknown Location"
    transaction_type = str(data.get("transaction_type") or "online_purchase").strip() or "online_purchase"

    if card_id is None or amount is None:
        return jsonify({"message": "card_id and amount are required."}), 400

    try:
        card_id = int(card_id)
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"message": "card_id must be an integer and amount must be a number."}), 400

    if not math.isfinite(amount) or amount <= 0:
        return jsonify({"message": "Amount must be a finite number greater than zero."}), 400

    card = Card.query.filter_by(card_id=card_id, user_id=user_id).first()
    if not card:
        return jsonify({"message": "Card not found for this user."}), 404

    if card.status != "ACTIVE":
        return jsonify({"message": f"This card is {card.status.lower()} and cannot be used."}), 403
    account = card.account
    if not account or account.user_id != user_id:
        return jsonify({"message": "This card is not linked to an active customer account."}), 409
    if account.status != "ACTIVE":
        return jsonify({"message": f"This account is {account.status.lower()} and cannot be used."}), 403
    if transaction_direction(transaction_type) == "DEBIT" and account.balance < amount:
        return jsonify({"message": "The account has insufficient funds for this transaction."}), 409

    transaction_time = datetime.utcnow()
    merchant_category = "luxury" if "luxury" in merchant.lower() else "general"
    country = "Dubai" if "dubai" in location.lower() else "IN"
    ml_payload = {
        "amount": amount,
        "transaction_hour": transaction_time.hour,
        "is_weekend": 1 if transaction_time.weekday() >= 5 else 0,
        "merchant_category": merchant_category,
        "transaction_type": transaction_type.lower(),
        "country": country,
        "is_international": 1 if country != "IN" else 0,
        "customer_avg_amount": max(5000.0, amount * 0.35),
        "recent_txn_count": 1,
        "device_risk": 0.1,
    }

    ml_result = predict_fraud(ml_payload)
    behavior_result = analyze_behavior(user_id, amount, transaction_time)
    risk_result = calculate_overall_risk(ml_result["fraud_probability"], behavior_result["behavior_score"], amount)

    transaction = Transaction(
        user_id=user_id,
        card_id=card_id,
        account_id=card.account_id,
        merchant=merchant,
        location=location,
        amount=amount,
        transaction_type=transaction_type,
        transaction_time=transaction_time,
        status="AUTHORIZED" if risk_result["risk_level"] == "LOW" else "PENDING",
        fraud_probability=ml_result["fraud_probability"],
        prediction=ml_result["prediction"],
        behavior_score=behavior_result["behavior_score"],
        risk_level=risk_result["risk_level"],
    )

    db.session.add(transaction)
    db.session.flush()
    if transaction.status == "AUTHORIZED":
        ledger_error = apply_transaction_to_account(transaction)
        if ledger_error:
            db.session.rollback()
            return jsonify({"message": ledger_error}), 409

    alert = None
    if risk_result["risk_level"] in {"MEDIUM", "HIGH"}:
        alert = FraudAlert(
            user_id=user_id,
            transaction_id=transaction.transaction_id,
            risk_level=risk_result["risk_level"],
            status="OPEN",
            message=f"Suspicious transaction detected for {merchant} at {location}.",
        )
        db.session.add(alert)

    direction = transaction_direction(transaction_type)
    movement = "credited to" if direction == "CREDIT" else "debited from"
    notification = Notification(
        user_id=user_id,
        transaction_id=transaction.transaction_id,
        channel="IN_APP",
        message=f"₹{amount:,.2f} {movement} your account via card ending {card.last_four} at {merchant}.",
        status="SENT",
    )
    db.session.add(notification)

    sms_message = Notification(
        user_id=user_id,
        transaction_id=transaction.transaction_id,
        channel="SMS",
        message=f"VELORA BANK: ₹{amount:,.2f} {movement} your account via card ending {card.last_four} at {merchant} in {location}.",
        status="QUEUED",
    )
    db.session.add(sms_message)

    db.session.add(AuditLog(
        user_id=user_id,
        actor_type="CUSTOMER",
        actor_id=user_id,
        action="TRANSACTION_CREATED",
        object_type="transaction",
        object_id=transaction.transaction_id,
        details=f"Transaction processed for {merchant} amount {amount}.",
    ))

    db.session.commit()
    customer = User.query.get(user_id)
    deliver_sms_notification(sms_message, customer.phone if customer else None)
    db.session.commit()

    response = {
        "message": (
            "Transaction processed successfully."
            if sms_message.status in {"ACCEPTED", "SIMULATED"}
            else "Transaction processed, but the SMS alert was not sent."
        ),
        "transaction": {
            "transaction_id": transaction.transaction_id,
            "merchant": transaction.merchant,
            "location": transaction.location,
            "amount": transaction.amount,
            "transaction_type": transaction.transaction_type,
            "direction": transaction_direction(transaction.transaction_type),
            "risk_level": transaction.risk_level,
            "prediction": transaction.prediction,
            "fraud_probability": round(float(ml_result["fraud_probability"]), 4),
            "behavior_score": behavior_result["behavior_score"],
            "signals": behavior_result["signals"],
        },
        "fraud_alert_created": bool(alert),
        "sms_message": {
            "phone_number": customer.phone if customer else None,
            "message": sms_message.message,
            "status": sms_message.status,
            "delivery_note": (
                "Accepted by MSG91; delivery to the handset is not confirmed."
                if sms_message.status == "ACCEPTED"
                else "Simulation only; no SMS was sent."
                if sms_message.status == "SIMULATED"
                else "Not sent. Check the phone number and MSG91 configuration."
            ),
        },
    }
    return jsonify(response), 201


@transactions_bp.route("", methods=["GET"])
@jwt_required()
def list_transactions():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"message": "User not found."}), 404
    if current_user.role not in {"CUSTOMER", "BANK_ADMIN"}:
        return jsonify({"message": "This role cannot access transactions."}), 403

    if current_user.role == "CUSTOMER":
        transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.transaction_time.desc()).all()
        reported_transaction_ids = {
            case.transaction_id
            for case in FraudCase.query.filter_by(user_id=user_id).all()
        }
        confirmed_transaction_ids = {
            audit.object_id
            for audit in AuditLog.query.filter_by(
                user_id=user_id,
                action="CUSTOMER_CONFIRMED_TRANSACTION",
                object_type="transaction",
            ).all()
            if audit.object_id is not None
        }
    else:
        transactions = Transaction.query.order_by(Transaction.transaction_time.desc()).all()
        reported_transaction_ids = set()
        confirmed_transaction_ids = set()

    return jsonify({
        "transactions": [{
            "transaction_id": tx.transaction_id,
            "card_id": tx.card_id,
            "merchant": tx.merchant,
            "location": tx.location,
            "amount": tx.amount,
            "transaction_type": tx.transaction_type,
            "direction": transaction_direction(tx.transaction_type),
            "status": tx.status,
            "prediction": tx.prediction,
            "fraud_probability": tx.fraud_probability,
            "risk_level": tx.risk_level,
            "behavior_score": tx.behavior_score,
            "transaction_time": tx.transaction_time.isoformat() if tx.transaction_time else None,
            "user_id": tx.user_id,
            "customer_name": tx.user.name if tx.user else None,
            "customer_email": tx.user.email if tx.user else None,
            "customer_review_status": (
                "REPORTED" if tx.transaction_id in reported_transaction_ids
                else "CONFIRMED" if tx.transaction_id in confirmed_transaction_ids
                else None
            ),
        } for tx in transactions]
    }), 200
