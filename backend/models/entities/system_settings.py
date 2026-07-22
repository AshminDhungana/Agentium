from sqlalchemy import Column, String, Text, DateTime, func
from .base import Base

class SystemSetting(Base):
    """
    Global system settings persisted in the database.
    Used for budget limits, engine configurations, etc.
    """
    __tablename__ = 'system_settings'
    
    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<SystemSetting(key='{self.key}', value='{self.value}')>"
