from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.alert import Alert
from app.services.alerter import AlertService

router = APIRouter()
alerter = AlertService()

@router.get("/", response_model=List[dict])
def get_alerts(
    skip: int = 0,
    limit: int = 100,
    acknowledged: Optional[bool] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if acknowledged is not None:
        query = query.filter(Alert.acknowledged == acknowledged)
    if severity:
        query = query.filter(Alert.severity == severity)
    alerts = query.order_by(Alert.created_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": a.id,
            "device_id": a.device_id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "acknowledged": a.acknowledged
        }
        for a in alerts
    ]

@router.get("/stats")
def get_alert_stats(db: Session = Depends(get_db)):
    total = db.query(Alert).count()
    unacknowledged = db.query(Alert).filter(Alert.acknowledged == False).count()
    critical = db.query(Alert).filter(Alert.severity == "CRITICAL").count()
    return {"total": total, "unacknowledged": unacknowledged, "critical": critical}

@router.put("/{alert_id}/ack")
def acknowledge_alert(alert_id: int, user: str = "admin"):
    success = alerter.acknowledge_alert(alert_id, user)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert acknowledged"}
