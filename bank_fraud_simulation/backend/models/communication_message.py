from datetime import datetime

from backend.extensions import db


class CommunicationMessage(db.Model):
    __tablename__ = "communication_messages"

    message_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False,
        index=True,
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    case_id = db.Column(db.Integer, db.ForeignKey("fraud_cases.case_id"), nullable=True)
    card_id = db.Column(db.Integer, db.ForeignKey("cards.card_id"), nullable=True)
    requested_card_action = db.Column(db.String(20), nullable=False, default="NONE")
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer = db.relationship("User", foreign_keys=[customer_id])
    sender = db.relationship("User", foreign_keys=[sender_id])
    case = db.relationship("FraudCase")
    card = db.relationship("Card")
