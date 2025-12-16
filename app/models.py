from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class EnvelopeTracking(db.Model):
    """Model to track envelopes and their callback information"""
    __tablename__ = 'envelope_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    envelope_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    callback_url = db.Column(db.String(2048), nullable=False)
    requester_host = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='sent')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    signed_at = db.Column(db.DateTime, nullable=True)
    notified_at = db.Column(db.DateTime, nullable=True)
    notification_status = db.Column(db.String(50), nullable=True)
    
    def __repr__(self):
        return f'<EnvelopeTracking {self.envelope_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'envelope_id': self.envelope_id,
            'callback_url': self.callback_url,
            'requester_host': self.requester_host,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'signed_at': self.signed_at.isoformat() if self.signed_at else None,
            'notified_at': self.notified_at.isoformat() if self.notified_at else None,
            'notification_status': self.notification_status
        }
