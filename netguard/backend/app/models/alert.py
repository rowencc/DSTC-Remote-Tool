from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    alert_type = Column(String(50), nullable=False)
    severity = Column(Enum('INFO', 'WARNING', 'CRITICAL'), nullable=False)
    message = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=func.now())
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(100))