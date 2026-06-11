# NetGuard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a network device identification and monitoring system that detects unknown devices via MAC addresses, identifies device types, and alerts on suspicious devices like hidden cameras.

**Architecture:** Python backend (FastAPI) + Vue3 frontend with MySQL storage. Uses nmap/scapy for network scanning, multi-dimensional fingerprinting for device identification, and multi-channel alerting.

**Tech Stack:** Python 3.10+, FastAPI, MySQL 8.0, nmap, scapy, Vue3, ECharts, Redis

---

## File Structure

```
netguard/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── device.py
│   │   │   ├── alert.py
│   │   │   └── scan_record.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── scanner.py
│   │   │   ├── identifier.py
│   │   │   └── alerter.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── devices.py
│   │       ├── alerts.py
│   │       └── system.py
│   ├── data/
│   │   └── oui.json
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_scanner.py
│   │   ├── test_identifier.py
│   │   ├── test_alerter.py
│   │   └── test_integration.py
│   ├── requirements.txt
│   ├── config.yaml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── index.js
│   │   ├── views/
│   │   │   ├── Home.vue
│   │   │   ├── Devices.vue
│   │   │   └── Alerts.vue
│   │   ├── router/
│   │   │   └── index.js
│   │   ├── App.vue
│   │   └── main.js
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
└── docs/
```

---

## Task 1: Project Setup and Backend Foundation

**Files:**
- Create: `netguard/backend/requirements.txt`
- Create: `netguard/backend/config.yaml`
- Create: `netguard/backend/app/__init__.py`
- Create: `netguard/backend/app/config.py`
- Create: `netguard/backend/app/database.py`
- Create: `netguard/backend/app/main.py`
- Create: `netguard/backend/app/models/__init__.py`
- Create: `netguard/backend/app/services/__init__.py`
- Create: `netguard/backend/app/api/__init__.py`

- [ ] **Step 1: Create project directories**

```bash
cd /Users/rowen/IdeaProjects/mimoProject
mkdir -p netguard/backend/app/{models,services,api}
mkdir -p netguard/backend/data
mkdir -p netguard/backend/tests
mkdir -p netguard/frontend/src/{api,views,router}
```

- [ ] **Step 2: Create requirements.txt**

```
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
pymysql==1.1.0
python-nmap==0.7.1
scapy==2.5.0
redis==5.0.1
pyyaml==6.0.1
python-multipart==0.0.6
aiofiles==23.2.1
websockets==12.0
apscheduler==3.10.4
requests==2.31.0
```

- [ ] **Step 3: Create config.yaml**

```yaml
app:
  name: NetGuard
  version: 1.0.0
  debug: true

database:
  host: localhost
  port: 3306
  user: root
  password: root
  database: netguard

scanner:
  networks:
    - 192.168.1.0/24
  interval: 300
  timeout: 30

alerter:
  email:
    enabled: false
    smtp_server: smtp.gmail.com
    smtp_port: 587
    username: ""
    password: ""
  wechat:
    enabled: false
    webhook_url: ""
  dingtalk:
    enabled: false
    webhook_url: ""
```

- [ ] **Step 4: Create config.py**

```python
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

config = load_config()
```

- [ ] **Step 5: Create database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import config

db_config = config["database"]
DATABASE_URL = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Create main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import config
from app.api import devices, alerts, system

app = FastAPI(
    title=config["app"]["name"],
    version=config["app"]["version"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(system.router, prefix="/api/system", tags=["system"])

@app.get("/")
def root():
    return {"message": "NetGuard API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 7: Create __init__.py files**

```bash
touch netguard/backend/app/__init__.py
touch netguard/backend/app/models/__init__.py
touch netguard/backend/app/services/__init__.py
touch netguard/backend/app/api/__init__.py
touch netguard/backend/tests/__init__.py
```

- [ ] **Step 8: Commit**

```bash
cd netguard
git init
git add backend/
git commit -m "feat: initialize backend project structure"
```

---

## Task 2: Database Models

**Files:**
- Create: `netguard/backend/app/models/device.py`
- Create: `netguard/backend/app/models/alert.py`
- Create: `netguard/backend/app/models/scan_record.py`

- [ ] **Step 1: Create device.py**

```python
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
```

- [ ] **Step 2: Create alert.py**

```python
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
```

- [ ] **Step 3: Create scan_record.py**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add database models"
```

---

## Task 3: Network Scanner Service

**Files:**
- Create: `netguard/backend/app/services/scanner.py`

- [ ] **Step 1: Create scanner.py**

```python
import nmap
from scapy.all import ARP, Ether, srp
from typing import List, Dict, Optional
from app.config import config

class NetworkScanner:
    def __init__(self):
        self.nm = nmap.PortScanner()
        self.config = config["scanner"]

    def scan_network(self, network: Optional[str] = None) -> List[Dict]:
        if not network:
            network = self.config["networks"][0]

        self.nm.scan(hosts=network, arguments="-sn")

        devices = []
        for host in self.nm.all_hosts():
            device = {
                "ip_address": host,
                "mac_address": self.nm[host]["addresses"].get("mac", ""),
                "hostname": self.nm[host]["hostname"],
                "vendor": self.nm[host]["vendor"].get("mac", "")
            }
            devices.append(device)
        return devices

    def deep_scan(self, ip: str) -> Dict:
        self.nm.scan(hosts=ip, arguments="-O -sV --version-intensity 5")

        if ip not in self.nm.all_hosts():
            return {}

        host_data = self.nm[ip]
        return {
            "ip_address": ip,
            "mac_address": host_data["addresses"].get("mac", ""),
            "os_matches": host_data.get("osmatch", []),
            "ports": host_data.get("tcp", {}),
            "vendor": host_data["vendor"].get("mac", "")
        }

    def arp_scan(self, network: Optional[str] = None) -> List[Dict]:
        if not network:
            network = self.config["networks"][0]

        arp = ARP(pdst=network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        result = srp(ether/arp, timeout=3, verbose=False)[0]

        devices = []
        for sent, received in result:
            devices.append({
                "ip_address": received.psrc,
                "mac_address": received.hwsrc
            })
        return devices
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/scanner.py
git commit -m "feat: add network scanner service"
```

---

## Task 4: Device Identification Service

**Files:**
- Create: `netguard/backend/app/services/vendor_lookup.py`
- Create: `netguard/backend/app/services/identifier.py`

- [ ] **Step 1: Create vendor_lookup.py**

```python
import json
from pathlib import Path
from typing import Optional

class VendorLookup:
    def __init__(self):
        self.oui_db = self._load_oui_db()

    def _load_oui_db(self) -> dict:
        oui_path = Path(__file__).parent.parent.parent / "data" / "oui.json"
        if oui_path.exists():
            with open(oui_path, "r") as f:
                return json.load(f)
        return {}

    def lookup(self, mac_address: str) -> Optional[str]:
        mac_prefix = mac_address.upper().replace(":", "").replace("-", "")[:6]
        return self.oui_db.get(mac_prefix)

    def add_vendor(self, mac_prefix: str, vendor: str):
        self.oui_db[mac_prefix.upper()] = vendor
```

- [ ] **Step 2: Create identifier.py**

```python
from typing import Dict, Optional
from app.services.vendor_lookup import VendorLookup
from app.services.scanner import NetworkScanner

class DeviceIdentifier:
    def __init__(self):
        self.vendor_lookup = VendorLookup()
        self.scanner = NetworkScanner()

        self.known_risk_vendors = [
            "HIKVISION", "DAHUA", "UNIVIEW",
            "XIAOMI", "TP-LINK", "HUAWEI"
        ]

        self.device_type_rules = {
            "camera": ["camera", "webcam", "ip camera", "nvr", "dvr"],
            "router": ["router", "gateway", "access point"],
            "switch": ["switch", "bridge"],
            "phone": ["phone", "mobile", "android", "ios"],
            "computer": ["windows", "linux", "macos", "desktop", "laptop"],
            "iot": ["iot", "smart", "sensor", "thermostat"]
        }

    def identify_device(self, scan_result: Dict) -> Dict:
        mac_address = scan_result.get("mac_address", "")
        vendor = scan_result.get("vendor") or self.vendor_lookup.lookup(mac_address)
        device_type = self._determine_device_type(scan_result, vendor)
        risk_level = self._assess_risk(scan_result, vendor, device_type)

        return {
            **scan_result,
            "vendor": vendor,
            "device_type": device_type,
            "risk_level": risk_level
        }

    def _determine_device_type(self, scan_result: Dict, vendor: Optional[str]) -> str:
        os_matches = scan_result.get("os_matches", [])
        for match in os_matches:
            name = match.get("name", "").lower()
            for device_type, keywords in self.device_type_rules.items():
                for keyword in keywords:
                    if keyword in name:
                        return device_type
        return "unknown"

    def _assess_risk(self, scan_result: Dict, vendor: Optional[str], device_type: str) -> str:
        if device_type in ["camera", "nvr", "dvr"]:
            return "HIGH"
        if vendor and vendor.upper() in self.known_risk_vendors:
            return "MEDIUM"
        if device_type == "unknown":
            return "MEDIUM"
        return "LOW"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/vendor_lookup.py backend/app/services/identifier.py
git commit -m "feat: add device identification service"
```

---

## Task 5: Alert Service

**Files:**
- Create: `netguard/backend/app/services/alerter.py`

- [ ] **Step 1: Create alerter.py**

```python
import smtplib
import requests
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime
from app.config import config
from app.database import SessionLocal
from app.models.alert import Alert

class AlertService:
    def __init__(self):
        self.config = config["alerter"]

    def create_alert(self, device_id: int, alert_type: str, severity: str, message: str) -> Alert:
        db = SessionLocal()
        try:
            alert = Alert(
                device_id=device_id,
                alert_type=alert_type,
                severity=severity,
                message=message
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            self._send_notifications(alert)
            return alert
        finally:
            db.close()

    def _send_notifications(self, alert: Alert):
        if self.config["email"]["enabled"]:
            self._send_email(alert)
        if self.config["wechat"]["enabled"]:
            self._send_wechat(alert)
        if self.config["dingtalk"]["enabled"]:
            self._send_dingtalk(alert)

    def _send_email(self, alert: Alert):
        email_config = self.config["email"]
        msg = MIMEText(f"NetGuard Alert: {alert.message}")
        msg["Subject"] = f"[NetGuard] {alert.severity}: {alert.alert_type}"
        msg["From"] = email_config["username"]
        msg["To"] = email_config["username"]
        try:
            with smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"]) as server:
                server.starttls()
                server.login(email_config["username"], email_config["password"])
                server.send_message(msg)
        except Exception as e:
            print(f"Email alert failed: {e}")

    def _send_wechat(self, alert: Alert):
        wechat_config = self.config["wechat"]
        payload = {
            "msgtype": "text",
            "text": {"content": f"NetGuard Alert: {alert.severity}\n{alert.message}"}
        }
        try:
            requests.post(wechat_config["webhook_url"], json=payload, timeout=10)
        except Exception as e:
            print(f"WeChat alert failed: {e}")

    def _send_dingtalk(self, alert: Alert):
        dingtalk_config = self.config["dingtalk"]
        payload = {
            "msgtype": "text",
            "text": {"content": f"NetGuard Alert: {alert.severity}\n{alert.message}"}
        }
        try:
            requests.post(dingtalk_config["webhook_url"], json=payload, timeout=10)
        except Exception as e:
            print(f"DingTalk alert failed: {e}")

    def acknowledge_alert(self, alert_id: int, user: str) -> bool:
        db = SessionLocal()
        try:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.acknowledged = True
                alert.acknowledged_by = user
                alert.acknowledged_at = datetime.now()
                db.commit()
                return True
            return False
        finally:
            db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/alerter.py
git commit -m "feat: add alert service with multi-channel notifications"
```

---

## Task 6: API Endpoints

**Files:**
- Create: `netguard/backend/app/api/devices.py`
- Create: `netguard/backend/app/api/alerts.py`
- Create: `netguard/backend/app/api/system.py`

- [ ] **Step 1: Create devices.py**

```python
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
```

- [ ] **Step 2: Create alerts.py**

```python
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
```

- [ ] **Step 3: Create system.py**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/
git commit -m "feat: add API endpoints for devices, alerts, and system"
```

---

## Task 7: Vue3 Frontend Setup

**Files:**
- Create: `netguard/frontend/package.json`
- Create: `netguard/frontend/vite.config.js`
- Create: `netguard/frontend/src/main.js`
- Create: `netguard/frontend/src/App.vue`
- Create: `netguard/frontend/src/api/index.js`
- Create: `netguard/frontend/src/router/index.js`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "netguard-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.3.4",
    "vue-router": "^4.2.5",
    "axios": "^1.6.0",
    "echarts": "^5.4.3",
    "element-plus": "^2.4.3"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.5.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 2: Create vite.config.js**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

- [ ] **Step 3: Create main.js**

```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

- [ ] **Step 4: Create App.vue**

```vue
<template>
  <el-container>
    <el-aside width="200px">
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/">
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <span>Devices</span>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <span>Alerts</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script>
export default {
  name: 'App'
}
</script>
```

- [ ] **Step 5: Create api/index.js**

```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: '/api'
})

export default api
```

- [ ] **Step 6: Create router/index.js**

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Devices from '../views/Devices.vue'
import Alerts from '../views/Alerts.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/devices', component: Devices },
  { path: '/alerts', component: Alerts }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: initialize Vue3 frontend"
```

---

## Task 8: Frontend Pages

**Files:**
- Create: `netguard/frontend/src/views/Home.vue`
- Create: `netguard/frontend/src/views/Devices.vue`
- Create: `netguard/frontend/src/views/Alerts.vue`

- [ ] **Step 1: Create Home.vue**

```vue
<template>
  <div>
    <h1>NetGuard Dashboard</h1>
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>Total Devices</template>
          <div class="stat-number">{{ stats.device_count }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Unacknowledged Alerts</template>
          <div class="stat-number warning">{{ stats.unacknowledged_alerts }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Risk Devices</template>
          <div class="stat-number danger">{{ stats.risk_devices }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      stats: {
        device_count: 0,
        unacknowledged_alerts: 0,
        risk_devices: 0
      }
    }
  },
  mounted() {
    this.loadStats()
  },
  methods: {
    async loadStats() {
      const res = await api.get('/system/stats')
      this.stats = res.data
    }
  }
}
</script>

<style scoped>
.stat-number {
  font-size: 48px;
  font-weight: bold;
  text-align: center;
}
.warning { color: #e6a23c; }
.danger { color: #f56c6c; }
</style>
```

- [ ] **Step 2: Create Devices.vue**

```vue
<template>
  <div>
    <el-button type="primary" @click="scanNetwork" :loading="scanning">
      Scan Network
    </el-button>
    <el-table :data="devices" style="width: 100%">
      <el-table-column prop="mac_address" label="MAC Address" />
      <el-table-column prop="vendor" label="Vendor" />
      <el-table-column prop="device_type" label="Type" />
      <el-table-column prop="ip_address" label="IP Address" />
      <el-table-column prop="risk_level" label="Risk">
        <template #default="{ row }">
          <el-tag :type="getRiskType(row.risk_level)">
            {{ row.risk_level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_seen" label="Last Seen" />
    </el-table>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      devices: [],
      scanning: false
    }
  },
  mounted() {
    this.loadDevices()
  },
  methods: {
    async loadDevices() {
      const res = await api.get('/devices/')
      this.devices = res.data
    },
    async scanNetwork() {
      this.scanning = true
      try {
        await api.post('/devices/scan')
        await this.loadDevices()
      } finally {
        this.scanning = false
      }
    },
    getRiskType(risk) {
      const types = {
        'LOW': 'success',
        'MEDIUM': 'warning',
        'HIGH': 'danger',
        'CRITICAL': 'danger'
      }
      return types[risk] || 'info'
    }
  }
}
</script>
```

- [ ] **Step 3: Create Alerts.vue**

```vue
<template>
  <div>
    <el-table :data="alerts" style="width: 100%">
      <el-table-column prop="severity" label="Severity">
        <template #default="{ row }">
          <el-tag :type="getSeverityType(row.severity)">
            {{ row.severity }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="alert_type" label="Type" />
      <el-table-column prop="message" label="Message" />
      <el-table-column prop="created_at" label="Time" />
      <el-table-column label="Actions">
        <template #default="{ row }">
          <el-button
            v-if="!row.acknowledged"
            size="small"
            @click="acknowledgeAlert(row.id)"
          >
            Acknowledge
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      alerts: []
    }
  },
  mounted() {
    this.loadAlerts()
  },
  methods: {
    async loadAlerts() {
      const res = await api.get('/alerts/')
      this.alerts = res.data
    },
    async acknowledgeAlert(id) {
      await api.put(`/alerts/${id}/ack`)
      await this.loadAlerts()
    },
    getSeverityType(severity) {
      const types = {
        'INFO': 'info',
        'WARNING': 'warning',
        'CRITICAL': 'danger'
      }
      return types[severity] || 'info'
    }
  }
}
</script>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add frontend pages for dashboard, devices, alerts"
```

---

## Task 9: Docker Deployment

**Files:**
- Create: `netguard/docker-compose.yml`
- Create: `netguard/backend/Dockerfile`
- Create: `netguard/frontend/Dockerfile`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: netguard
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=mysql+pymysql://root:root@db:3306/netguard
      - REDIS_URL=redis://redis:6379

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  mysql_data:
```

- [ ] **Step 2: Create backend/Dockerfile**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y nmap && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Create frontend/Dockerfile**

```dockerfile
FROM node:18-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile
git commit -m "feat: add Docker deployment configuration"
```

---

## Task 10: Integration Testing

**Files:**
- Create: `netguard/backend/tests/test_integration.py`

- [ ] **Step 1: Create test_integration.py**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/test_integration.py
git commit -m "feat: add integration tests"
```

---

## Execution Approach

This plan has 10 tasks with the following dependencies:

- **Tasks 1-2**: Foundation (sequential)
- **Tasks 3-5**: Services (can be parallelized after Task 2)
- **Tasks 6-8**: API and Frontend (can be parallelized after services)
- **Tasks 9-10**: Deployment and Testing (final integration)
