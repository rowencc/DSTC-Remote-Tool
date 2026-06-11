from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class ScanRecord(Base):
    __tablename__ = "scan_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_type = Column(String(20), nullable=False)
    target_network = Column(String(18), nullable=False)
    device_count = Column(Integer, default=0)
    new_device_count = Column(Integer, default=0)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)