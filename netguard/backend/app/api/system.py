from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.device import Device
from app.models.alert import Alert

router = APIRouter()

@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    device_count = db.query(Device).count()
    alert_count = db.query(Alert).filter(Alert.acknowledged == False).count()
    risk_devices = db.query(Device).filter(
        Device.risk_level.in_(["HIGH", "CRITICAL"])
    ).count()
    return {
        "device_count": device_count,
        "unacknowledged_alerts": alert_count,
        "risk_devices": risk_devices
    }

@router.get("/health")
def health_check():
    return {"status": "healthy"}
