from datetime import datetime

from backend.extensions import db


class InvestigationNote(db.Model):
    __tablename__ = "investigation_notes"

    note_id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("fraud_cases.case_id"), nullable=False)
    officer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    note_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    officer = db.relationship("User", backref=db.backref("investigation_notes", lazy=True))
