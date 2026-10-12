from datetime import datetime

from backend.extensions import db


class PoliceReport(db.Model):
    __tablename__ = "police_reports"

    police_report_id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("fraud_cases.case_id"), unique=True, nullable=False)
    filed_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    reference_number = db.Column(db.String(40), unique=True, nullable=False)
    police_station = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(30), default="SIMULATED_FILED", nullable=False)
    summary = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    fraud_case = db.relationship("FraudCase", back_populates="police_report")
    admin = db.relationship("User", backref=db.backref("filed_police_reports", lazy=True))
