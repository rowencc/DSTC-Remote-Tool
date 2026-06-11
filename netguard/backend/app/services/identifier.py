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
