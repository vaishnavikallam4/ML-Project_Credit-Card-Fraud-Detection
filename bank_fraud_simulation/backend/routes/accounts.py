import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.account import Account
from backend.models.user import User

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


@accounts_bp.route("", methods=["POST"])
@jwt_required()
def create_account():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can create accounts from this portal."}), 403

    account_number = str(data.get("account_number") or "").strip()
    account_type = str(data.get("account_type") or "Savings").strip()
    try:
        balance = float(data.get("balance", 0.0))
    except (TypeError, ValueError):
        return jsonify({"message": "balance must be a finite non-negative number."}), 400

    if not account_number:
        return jsonify({"message": "account_number is required."}), 400
    if len(account_number) > 30:
        return jsonify({"message": "account_number must be 30 characters or fewer."}), 400
    if len(account_type) > 50:
        return jsonify({"message": "account_type must be 50 characters or fewer."}), 400
    if not math.isfinite(balance) or balance < 0:
        return jsonify({"message": "balance must be a finite non-negative number."}), 400

    if Account.query.filter_by(account_number=account_number).first():
        return jsonify({"message": "Account number already exists."}), 409

    account = Account(
        user_id=user_id,
        account_number=account_number,
        account_type=account_type or "Savings",
        balance=balance,
        status="ACTIVE",
    )

    db.session.add(account)
    db.session.commit()

    return jsonify({
        "message": "Account created successfully.",
        "account": {
            "account_id": account.account_id,
            "account_number": account.account_number,
            "account_type": account.account_type,
            "balance": account.balance,
            "status": account.status,
        },
    }), 201


@accounts_bp.route("", methods=["GET"])
@jwt_required()
def list_accounts():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role not in {"CUSTOMER", "BANK_ADMIN"}:
        return jsonify({"message": "This role cannot access accounts."}), 403

    if user.role == "CUSTOMER":
        accounts = Account.query.filter_by(user_id=user_id).all()
    else:
        accounts = Account.query.order_by(Account.created_at.desc()).all()

    return jsonify({
        "accounts": [{
            "account_id": a.account_id,
            "account_number": a.account_number,
            "account_type": a.account_type,
            "balance": a.balance,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "user_id": a.user_id,
            "customer_name": a.user.name if a.user else None,
            "customer_email": a.user.email if a.user else None,
        } for a in accounts]
    }), 200
