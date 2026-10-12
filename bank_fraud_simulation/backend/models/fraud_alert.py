from datetime import datetime

from backend.extensions import db


class FraudAlert(db.Model):
    __tablename__ = "fraud_alerts"

    alert_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=False)
    risk_level = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(30), default="OPEN", nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("fraud_alerts", lazy=True))
    transaction = db.relationship("Transaction", backref=db.backref("fraud_alert", uselist=False))
