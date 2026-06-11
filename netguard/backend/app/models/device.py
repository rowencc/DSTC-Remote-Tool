from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum
from sqlalchemy.sql import func
from app.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac_address = Column(String(17), unique=True, nullable=False, index=True)
    mac_prefix = Column(String(8), nullable=False, index=True)
    vendor = Column(String(100))
    device_type = Column(String(50))
    os_info = Column(String(100))
    ip_address = Column(String(15))
    hostname = Column(String(100))
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())
    risk_level = Column(Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'), default='LOW')
    is_authorized = Column(Boolean, default=False)
    notes = Column(String(500))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())