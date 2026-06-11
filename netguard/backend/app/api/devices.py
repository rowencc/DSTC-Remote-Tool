from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional
from app.database import get_db
from app.models.device import Device
from app.services.scanner import NetworkScanner
from app.services.identifier import DeviceIdentifier

router = APIRouter()
scanner = NetworkScanner()
identifier = DeviceIdentifier()

@router.get("/", response_model=List[dict])
def get_devices(
    skip: int = 0,
    limit: int = 100,
    risk_level: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Device)
    if risk_level:
        query = query.filter(Device.risk_level == risk_level)
    devices = query.offset(skip).limit(limit).all()
    return [
        {
            "id": d.id,
            "mac_address": d.mac_address,
            "vendor": d.vendor,
            "device_type": d.device_type,
            "ip_address": d.ip_address,
            "risk_level": d.risk_level,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None
        }
        for d in devices
    ]

@router.get("/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        "id": device.id,
        "mac_address": device.mac_address,
        "vendor": device.vendor,
        "device_type": device.device_type,
        "os_info": device.os_info,
        "ip_address": device.ip_address,
        "hostname": device.hostname,
        "first_seen": device.first_seen.isoformat() if device.first_seen else None,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "risk_level": device.risk_level,
        "is_authorized": device.is_authorized,
        "notes": device.notes
    }

@router.post("/scan")
def trigger_scan(network: Optional[str] = None, db: Session = Depends(get_db)):
    devices = scanner.scan_network(network)
    new_count = 0
    for dev_data in devices:
        existing = db.query(Device).filter(
            Device.mac_address == dev_data["mac_address"]
        ).first()
        identified = identifier.identify_device(dev_data)
        if existing:
            existing.last_seen = func.now()
            existing.ip_address = dev_data["ip_address"]
        else:
            new_device = Device(
                mac_address=dev_data["mac_address"],
                mac_prefix=dev_data["mac_address"][:8],
                vendor=identified.get("vendor"),
                device_type=identified.get("device_type"),
                ip_address=dev_data["ip_address"],
                hostname=dev_data.get("hostname"),
                risk_level=identified.get("risk_level")
            )
            db.add(new_device)
            new_count += 1
    db.commit()
    return {"device_count": len(devices), "new_device_count": new_count}

@router.put("/{device_id}")
def update_device(
    device_id: int,
    is_authorized: Optional[bool] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if is_authorized is not None:
        device.is_authorized = is_authorized
    if notes is not None:
        device.notes = notes
    db.commit()
    return {"message": "Device updated"}
