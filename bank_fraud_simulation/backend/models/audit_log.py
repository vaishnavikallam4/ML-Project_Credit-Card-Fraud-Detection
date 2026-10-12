from datetime import datetime

from backend.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    audit_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    actor_type = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(80), nullable=False)
    object_type = db.Column(db.String(50), nullable=True)
    object_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("audit_logs", lazy=True))
