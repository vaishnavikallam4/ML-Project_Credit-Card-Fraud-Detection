from datetime import datetime

from backend.extensions import db


class Card(db.Model):
    __tablename__ = "cards"

    card_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.account_id"), nullable=True)
    card_type = db.Column(db.String(50), nullable=False)
    last_four = db.Column(db.String(4), nullable=False)
    expiry_month = db.Column(db.String(2), nullable=False)
    expiry_year = db.Column(db.String(4), nullable=False)
    status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("cards", lazy=True))
    account = db.relationship("Account", backref=db.backref("cards", lazy=True))
