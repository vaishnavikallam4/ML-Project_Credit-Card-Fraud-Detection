from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from secrets import token_hex

from backend.extensions import db
from backend.models.audit_log import AuditLog
from backend.models.card import Card
from backend.models.fraud_case import FraudCase
from backend.models.investigation_note import InvestigationNote
from backend.models.notification import Notification
from backend.models.police_report import PoliceReport
from backend.models.transaction import Transaction
from backend.models.user import User
from backend.services.sms_service import deliver_sms_notification
from backend.services.transaction_ledger import apply_transaction_to_account

cases_bp = Blueprint("cases", __name__, url_prefix="/api/cases")


@cases_bp.route("", methods=["GET"])
@jwt_required()
def list_cases():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404

    if user.role == "BANK_ADMIN":
        cases = FraudCase.query.order_by(FraudCase.created_at.desc()).all()
    elif user.role == "CUSTOMER":
        cases = FraudCase.query.filter_by(user_id=user_id).order_by(FraudCase.created_at.desc()).all()
    else:
        return jsonify({"message": "This role cannot access fraud cases."}), 403
    return jsonify({
        "cases": [{
            "case_id": c.case_id,
            "user_id": c.user_id,
            "card_id": c.card_id,
            "transaction_id": c.transaction_id,
            "case_status": c.case_status,
            "customer_response": c.customer_response,
            "assigned_officer_id": c.assigned_officer_id,
            "resolution_decision": c.resolution_decision,
            "customer_name": c.user.name if c.user else None,
            "customer_email": c.user.email if c.user else None,
            "transaction": {
                "transaction_id": c.transaction.transaction_id,
                "merchant": c.transaction.merchant,
                "amount": c.transaction.amount,
                "risk_level": c.transaction.risk_level,
                "status": c.transaction.status,
            } if c.transaction else None,
            "police_report": {
                "reference_number": c.police_report.reference_number,
                "police_station": c.police_report.police_station,
                "status": c.police_report.status,
            } if c.police_report else None,
        } for c in cases]
    }), 200


@cases_bp.route("/<int:case_id>", methods=["GET"])
@jwt_required()
def get_case(case_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user or user.role != "BANK_ADMIN":
        return jsonify({"message": "Unauthorized."}), 403

    case = FraudCase.query.get(case_id)
    if not case:
        return jsonify({"message": "Fraud case not found."}), 404

    transaction = Transaction.query.get(case.transaction_id)
    return jsonify({
        "case": {
            "case_id": case.case_id,
            "case_status": case.case_status,
            "customer_response": case.customer_response,
            "resolution_decision": case.resolution_decision,
            "transaction": {
                "transaction_id": transaction.transaction_id,
                "merchant": transaction.merchant,
                "location": transaction.location,
                "amount": transaction.amount,
                "transaction_type": transaction.transaction_type,
                "fraud_probability": transaction.fraud_probability,
                "risk_level": transaction.risk_level,
                "prediction": transaction.prediction,
            } if transaction else None,
        }
    }), 200


@cases_bp.route("/<int:case_id>/note", methods=["POST"])
@jwt_required()
def add_note(case_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user or user.role != "BANK_ADMIN":
        return jsonify({"message": "Only bank admins can add investigation notes."}), 403

    data = request.get_json(silent=True) or {}
    note_text = str(data.get("note_text") or "").strip()
    if not note_text:
        return jsonify({"message": "note_text is required."}), 400

    case = FraudCase.query.get(case_id)
    if not case:
        return jsonify({"message": "Fraud case not found."}), 404

    note = InvestigationNote(case_id=case.case_id, officer_id=user_id, note_text=note_text)
    case.case_status = "INVESTIGATING"
    case.assigned_officer_id = user_id
    case.updated_at = db.func.now()
    db.session.add(note)
    db.session.add(AuditLog(
        user_id=user_id,
        actor_type="BANK_ADMIN",
        actor_id=user_id,
        action="INVESTIGATION_NOTE_ADDED",
        object_type="case",
        object_id=case.case_id,
        details=note_text,
    ))
    db.session.commit()

    return jsonify({"message": "Investigation note added.", "note_id": note.note_id}), 201


@cases_bp.route("/<int:case_id>/resolve", methods=["POST"])
@jwt_required()
def resolve_case(case_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user or user.role != "BANK_ADMIN":
        return jsonify({"message": "Unauthorized."}), 403

    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision") or "").upper()
    if decision not in {"FRAUD", "FALSE_ALARM"}:
        return jsonify({"message": "decision must be FRAUD or FALSE_ALARM."}), 400

    case = FraudCase.query.get(case_id)
    if not case:
        return jsonify({"message": "Fraud case not found."}), 404
    if case.case_status not in {"OPEN", "INVESTIGATING"}:
        return jsonify({"message": "This case has already been resolved."}), 409

    transaction = Transaction.query.get(case.transaction_id)
    card = Card.query.get(case.card_id)
    if decision == "FRAUD":
        case.case_status = "CONFIRMED_FRAUD"
        case.resolution_decision = "FRAUD"
        if transaction:
            transaction.status = "FRAUDULENT"
        if card:
            card.status = "BLOCKED"
        msg = "Your card has been blocked due to confirmed fraudulent activity."
    else:
        if transaction and transaction.status != "AUTHORIZED":
            ledger_error = apply_transaction_to_account(transaction)
            if ledger_error:
                return jsonify({"message": ledger_error}), 409
        case.case_status = "FALSE_ALARM"
        case.resolution_decision = "FALSE_ALARM"
        if transaction:
            transaction.status = "AUTHORIZED"
        if card and card.status == "HOLD":
            card.status = "ACTIVE"
        msg = "The reported transaction was classified as a false alarm. Your card is active again."

    case.updated_at = db.func.now()
    sms_notification = Notification(
        user_id=case.user_id,
        transaction_id=case.transaction_id,
        case_id=case.case_id,
        channel="SMS",
        message=f"VELORA BANK: {msg}",
        status="QUEUED",
    )
    db.session.add(Notification(
        user_id=case.user_id,
        transaction_id=case.transaction_id,
        case_id=case.case_id,
        channel="IN_APP",
        message=msg,
        status="SENT",
    ))
    db.session.add(sms_notification)
    db.session.add(AuditLog(
        user_id=case.user_id,
        actor_type="BANK_ADMIN",
        actor_id=user_id,
        action="CASE_RESOLVED",
        object_type="case",
        object_id=case.case_id,
        details=f"Case resolved as {decision}.",
    ))
    db.session.commit()
    deliver_sms_notification(sms_notification, case.user.phone if case.user else None)
    db.session.commit()

    return jsonify({
        "message": "Case resolved successfully.",
        "case_status": case.case_status,
        "decision": decision,
        "card_status": card.status if card else None,
        "phone_alert_status": sms_notification.status,
    }), 200


@cases_bp.route("/<int:case_id>/police-report", methods=["POST"])
@jwt_required()
def file_police_report(case_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user or user.role != "BANK_ADMIN":
        return jsonify({"message": "Only a bank admin can file a police report."}), 403

    case = FraudCase.query.get(case_id)
    if not case:
        return jsonify({"message": "Fraud case not found."}), 404
    if case.resolution_decision != "FRAUD":
        return jsonify({"message": "Confirm the case as fraud before filing a police report."}), 409
    if case.police_report:
        return jsonify({"message": "A police report is already recorded for this case."}), 409

    data = request.get_json(silent=True) or {}
    police_station = str(data.get("police_station") or "").strip()
    if not police_station:
        return jsonify({"message": "police_station is required."}), 400
    if len(police_station) > 200:
        return jsonify({"message": "police_station must be 200 characters or fewer."}), 400

    transaction = Transaction.query.get(case.transaction_id)
    summary = (
        f"Customer reported unauthorized activity at {transaction.merchant or 'unknown merchant'} "
        f"for amount {transaction.amount:.2f}."
        if transaction else "Customer reported unauthorized card activity."
    )
    report = PoliceReport(
        case_id=case.case_id,
        filed_by=user_id,
        reference_number=f"VEL-{datetime.utcnow():%Y%m%d}-{token_hex(4).upper()}",
        police_station=police_station,
        summary=summary,
    )
    db.session.add(report)
    db.session.add(AuditLog(
        user_id=case.user_id,
        actor_type="BANK_ADMIN",
        actor_id=user_id,
        action="POLICE_REPORT_RECORDED",
        object_type="case",
        object_id=case.case_id,
        details=f"Police report {report.reference_number} recorded for {police_station}.",
    ))
    db.session.add(Notification(
        user_id=case.user_id,
        transaction_id=case.transaction_id,
        case_id=case.case_id,
        channel="IN_APP",
        message=f"Your confirmed fraud case was recorded for police follow-up. Reference: {report.reference_number}.",
        status="SENT",
    ))
    sms_notification = Notification(
        user_id=case.user_id,
        transaction_id=case.transaction_id,
        case_id=case.case_id,
        channel="SMS",
        message=f"VELORA BANK: Your confirmed fraud case was recorded for police follow-up. Reference: {report.reference_number}.",
        status="QUEUED",
    )
    db.session.add(sms_notification)
    db.session.commit()
    deliver_sms_notification(sms_notification, case.user.phone if case.user else None)
    db.session.commit()

    return jsonify({
        "message": "Police report recorded in the simulation.",
        "report": {
            "police_report_id": report.police_report_id,
            "reference_number": report.reference_number,
            "police_station": report.police_station,
            "status": report.status,
        },
        "phone_alert_status": sms_notification.status,
    }), 201
