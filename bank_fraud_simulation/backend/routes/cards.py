from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.extensions import db
from backend.models.account import Account
from backend.models.card import Card
from backend.models.user import User

cards_bp = Blueprint("cards", __name__, url_prefix="/api/cards")


@cards_bp.route("", methods=["POST"])
@jwt_required()
def create_card():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role != "CUSTOMER":
        return jsonify({"message": "Only customers can create cards from this portal."}), 403

    card_type = str(data.get("card_type") or "").strip()
    last_four = str(data.get("last_four") or "").strip()
    expiry_month = str(data.get("expiry_month") or "").strip()
    expiry_year = str(data.get("expiry_year") or "").strip()
    account_id = data.get("account_id")

    if not card_type or not last_four or not expiry_month or not expiry_year:
        return jsonify({"message": "card_type, last_four, expiry_month and expiry_year are required."}), 400
    if account_id is None:
        return jsonify({"message": "account_id is required to link a card to an account."}), 400

    if len(last_four) != 4 or not last_four.isdigit():
        return jsonify({"message": "last_four must contain exactly four digits."}), 400
    try:
        account_id = int(account_id)
    except (TypeError, ValueError):
        return jsonify({"message": "account_id must be an integer."}), 400
    if not Account.query.filter_by(account_id=account_id, user_id=user_id).first():
        return jsonify({"message": "Account not found for this customer."}), 404

    card = Card(
        user_id=user_id,
        account_id=account_id,
        card_type=card_type,
        last_four=last_four,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        status="ACTIVE",
    )

    db.session.add(card)
    db.session.commit()

    return jsonify({
        "message": "Card created successfully.",
        "card": {
            "card_id": card.card_id,
            "card_type": card.card_type,
            "last_four": card.last_four,
            "expiry_month": card.expiry_month,
            "expiry_year": card.expiry_year,
            "status": card.status,
        },
    }), 201


@cards_bp.route("", methods=["GET"])
@jwt_required()
def list_cards():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404
    if user.role not in {"CUSTOMER", "BANK_ADMIN"}:
        return jsonify({"message": "This role cannot access cards."}), 403

    if user.role == "CUSTOMER":
        cards = Card.query.filter_by(user_id=user_id).all()
    else:
        cards = Card.query.order_by(Card.card_id.desc()).all()

    return jsonify({
        "cards": [{
            "card_id": c.card_id,
            "card_type": c.card_type,
            "last_four": c.last_four,
            "expiry_month": c.expiry_month,
            "expiry_year": c.expiry_year,
            "status": c.status,
            "account_id": c.account_id,
            "user_id": c.user_id,
            "customer_name": c.user.name if c.user else None,
        } for c in cards]
    }), 200
