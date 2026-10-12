from datetime import datetime

from backend.extensions import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("cards.card_id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.account_id"), nullable=True)
    merchant = db.Column(db.String(150), nullable=True)
    location = db.Column(db.String(150), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(30), default="PENDING", nullable=False)
    transaction_time = db.Column(db.DateTime, default=datetime.utcnow)
    fraud_probability = db.Column(db.Float, nullable=True)
    risk_level = db.Column(db.String(20), nullable=True)
    prediction = db.Column(db.String(30), nullable=True)
    behavior_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("transactions", lazy=True))
    card = db.relationship("Card", backref=db.backref("transactions", lazy=True))
    account = db.relationship("Account", backref=db.backref("transactions", lazy=True))
