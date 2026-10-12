from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required

from backend.extensions import db, limiter
from backend.models.user import User


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def normalize_phone(phone_value):
    if phone_value is None:
        return ""
    digits = "".join(ch for ch in str(phone_value).strip() if ch.isdigit() or ch in {"+"})
    return digits.strip()


def phone_matches(candidate_phone, stored_phone):
    return normalize_phone(candidate_phone) and normalize_phone(stored_phone) == normalize_phone(candidate_phone)


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("3 per hour")
def register():
    if not current_app.config.get("PUBLIC_REGISTRATION_ENABLED", False):
        return jsonify({"message": "Customer registration is disabled. Contact the bank to provision an account."}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = normalize_phone(data.get("phone", ""))
    password = str(data.get("password", ""))
    address = str(data.get("address", "")).strip()
    if not name or not email or not password:
        return jsonify({"message": "Name, email and password are required."}), 400

    if len(password) < 8:
        return jsonify({"message": "Password must contain at least 8 characters."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "An account with this email already exists."}), 409

    if phone and any(normalize_phone(existing.phone) == phone for existing in User.query.all()):
        return jsonify({"message": "An account with this phone number already exists."}), 409

    user = User(
        name=name,
        email=email,
        phone=phone or None,
        role="CUSTOMER",
        address=address or None,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "Registration successful.",
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
        },
    }), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def login():
    data = request.get_json(silent=True) or {}
    email_value = str(data.get("email") or "").strip().lower()
    phone_value = normalize_phone(data.get("phone") or "")
    login_value = email_value or phone_value
    password = str(data.get("password", ""))

    if not login_value or not password:
        return jsonify({"message": "Email or phone number and password are required."}), 400

    user = User.query.filter_by(email=login_value).first()
    if not user:
        user = next((candidate for candidate in User.query.all() if normalize_phone(candidate.phone) == login_value), None)
    if not user or not user.check_password(password):
        return jsonify({"message": "Invalid email/phone or password."}), 401
    if user.role not in {"CUSTOMER", "BANK_ADMIN"}:
        return jsonify({"message": "This role is no longer enabled. Please contact the bank admin."}), 403

    token = create_access_token(identity=str(user.user_id), additional_claims={"role": user.role})

    return jsonify({
        "message": "Login successful.",
        "access_token": token,
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
        },
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found."}), 404

    return jsonify({
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "address": user.address,
        }
    }), 200
