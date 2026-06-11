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
            "mac_prefix": d.mac_prefix,
            "vendor": d.vendor,
            "device_type": d.device_type,
            "device_model": getattr(d, 'device_model', '') or '',
            "ip_address": d.ip_address,
            "hostname": d.hostname,
            "risk_level": d.risk_level,
            "is_authorized": d.is_authorized,
            "first_seen": d.first_seen.isoformat() if d.first_seen else None,
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
    scanned = 0
    for dev_data in devices:
        mac = dev_data.get("mac_address", "")
        if not mac:
            continue
        scanned += 1
        existing = db.query(Device).filter(
            Device.mac_address == mac
        ).first()
        identified = identifier.identify_device(dev_data)
        if existing:
            existing.last_seen = func.now()
            existing.ip_address = dev_data["ip_address"]
            if dev_data.get("hostname"):
                existing.hostname = dev_data["hostname"]
            if identified.get("vendor"):
                existing.vendor = identified["vendor"]
        else:
            new_device = Device(
                mac_address=mac,
                mac_prefix=mac[:8],
                vendor=identified.get("vendor"),
                device_type=identified.get("device_type"),
                ip_address=dev_data["ip_address"],
                hostname=dev_data.get("hostname"),
                os_info=identified.get("device_model", ""),
                risk_level=identified.get("risk_level")
            )
            db.add(new_device)
            new_count += 1
    db.commit()
    return {"device_count": scanned, "new_device_count": new_count}

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


@router.post("/{device_id}/deep-scan")
def deep_scan_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    result = scanner.deep_scan(device.ip_address)
    if not result:
        return {"message": "Scan returned no results", "ip": device.ip_address}
    vendor = result.get("vendor") or device.vendor
    identified = identifier.identify_device({
        "ip_address": device.ip_address,
        "mac_address": device.mac_address,
        "hostname": device.hostname or "",
        "vendor": vendor,
        "os_matches": result.get("os_matches", []),
        "open_ports": result.get("open_ports", {})
    })
    if vendor:
        device.vendor = vendor
    if identified.get("device_type"):
        device.device_type = identified["device_type"]
    if identified.get("risk_level"):
        device.risk_level = identified["risk_level"]
    if identified.get("device_model"):
        device.os_info = identified["device_model"]
    db.commit()
    return {
        "ip": device.ip_address,
        "vendor": vendor,
        "device_type": device.device_type,
        "risk_level": device.risk_level,
        "open_ports": result.get("open_ports", {}),
        "os_matches": result.get("os_matches", [])
    }
