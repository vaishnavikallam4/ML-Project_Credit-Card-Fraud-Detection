from datetime import datetime

from backend.extensions import db


class Account(db.Model):
    __tablename__ = "accounts"

    account_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    account_number = db.Column(db.String(30), unique=True, nullable=False)
    account_type = db.Column(db.String(50), default="Savings", nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)
    status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("accounts", lazy=True))
