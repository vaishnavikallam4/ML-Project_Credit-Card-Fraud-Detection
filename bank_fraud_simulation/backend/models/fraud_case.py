from datetime import datetime

from backend.extensions import db


class FraudCase(db.Model):
    __tablename__ = "fraud_cases"

    case_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("cards.card_id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.transaction_id"), nullable=False)
    assigned_officer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    case_status = db.Column(db.String(30), default="OPEN", nullable=False)
    customer_response = db.Column(db.String(20), nullable=True)
    resolution_decision = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.relationship("InvestigationNote", backref="fraud_case", lazy=True)
    police_report = db.relationship("PoliceReport", back_populates="fraud_case", uselist=False)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("fraud_cases", lazy=True))
    officer = db.relationship("User", foreign_keys=[assigned_officer_id], backref=db.backref("assigned_cases", lazy=True))
    card = db.relationship("Card", backref=db.backref("fraud_cases", lazy=True))
    transaction = db.relationship("Transaction", backref=db.backref("fraud_cases", lazy=True))
