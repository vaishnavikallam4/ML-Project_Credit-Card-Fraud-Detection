from datetime import datetime

from backend.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=True)
    case_id = db.Column(db.Integer, db.ForeignKey("fraud_cases.case_id"), nullable=True)
    channel = db.Column(db.String(20), default="IN_APP", nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="QUEUED", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))
    transaction = db.relationship("Transaction", backref=db.backref("notifications", lazy=True))
    fraud_case = db.relationship("FraudCase", backref=db.backref("notifications", lazy=True))
