from typing import Dict, Optional
from app.services.vendor_lookup import VendorLookup

KNOWN_CAMERA_VENDORS = [
    "HIKVISION", "DAHUA", "UNIVIEW", "TIANDY", "KEDACOM",
    "HONEYWELL", "AXIS", "BOSCH", "SONY", "SAMSUNG",
    "AVIGILON", "MILESTONE", "VIVOTEK", "DINVOTEK", "CP PLUS",
    "EZVIV", "REOLINK", "AMCREST", "WANSVIEW", "ZOSI",
    "FUNGLUE", "YI", "XIAOMI", "TP-LINK", "TUYA",
]

KNOWN_ROUTER_VENDORS = [
    "TP-LINK", "D-LINK", "NETGEAR", "UBIQUITI", "ASUSTEK",
    "CISCO", "LINKSYS", "HUAWEI", "ZTE", "TENDA",
    "MERCURY", "FAST", "RUIJIE", "H3C", "TOTOLINK",
    "PHICOMM", "EDIMAX", "ENGENIUS", "MIKROTIK", "ARUBA",
]

KNOWN_IOT_VENDORS = [
    "XIAOMI", "HUAWEI", "BROADLINK", "YEELIGHT", "Aqara",
    "SONY", "PHILIPS", "TUYA", "SONOFF", "MAGICHOME",
]

KNOWN_PHONE_VENDORS = [
    "APPLE", "SAMSUNG", "HUAWEI", "XIAOMI", "OPPO",
    "VIVO", "ONEPLUS", "REALME", "HONOR", "GOOGLE",
    "MOTOROLA", "NOKIA", "SONY", "LG", "ZTE",
]

KNOWN_COMPUTER_VENDORS = [
    "APPLE", "DELL", "HP", "LENOVO", "ASUSTEK",
    "ACER", "MSI", "RAZER", "SAMSUNG", "MICROSOFT",
]

KNOWN_CAMERA_KEYWORDS = [
    "camera", "webcam", "ip camera", "nvr", "dvr", "cctv",
    "surveillance", "hikvision", "dahua", "uniview",
]

KNOWN_ROUTER_KEYWORDS = [
    "router", "gateway", "access point", "ap", "wifi",
    "wireless", "modem", "switch",
]

KNOWN_IOT_KEYWORDS = [
    "iot", "smart", "sensor", "thermostat", "bulb", "plug",
    "switch", "camera", "speaker", "hub", "gateway",
]

KNOWN_PHONE_KEYWORDS = [
    "phone", "mobile", "android", "ios", "iphone", "galaxy",
    "pixel", "redmi", "oppo", "vivo",
]

KNOWN_COMPUTER_KEYWORDS = [
    "windows", "linux", "macos", "mac os", "desktop", "laptop",
    "ubuntu", "debian", "centos", "fedora", "microsoft",
]


class DeviceIdentifier:
    def __init__(self):
        self.vendor_lookup = VendorLookup()

    def identify_device(self, scan_result: Dict) -> Dict:
        mac_address = scan_result.get("mac_address", "")
        hostname = scan_result.get("hostname", "")
        vendor = scan_result.get("vendor") or self.vendor_lookup.lookup(mac_address)
        device_type = self._determine_device_type(scan_result, vendor, hostname)
        device_model = self._determine_device_model(vendor, hostname)
        confidence = self._calculate_confidence(scan_result, vendor, hostname)
        risk_level = self._assess_risk(scan_result, vendor, device_type)

        return {
            **scan_result,
            "vendor": vendor,
            "device_type": device_type,
            "device_model": device_model,
            "confidence": confidence,
            "risk_level": risk_level
        }

    def _determine_device_type(self, scan_result: Dict, vendor: Optional[str], hostname: str) -> str:
        os_matches = scan_result.get("os_matches", [])
        hostname_lower = hostname.lower()

        for match in os_matches:
            name = match.get("name", "").lower()
            if any(kw in name for kw in KNOWN_CAMERA_KEYWORDS):
                return "camera"
            if any(kw in name for kw in KNOWN_ROUTER_KEYWORDS):
                return "router"
            if any(kw in name for kw in KNOWN_PHONE_KEYWORDS):
                return "phone"
            if any(kw in name for kw in KNOWN_COMPUTER_KEYWORDS):
                return "computer"
            if any(kw in name for kw in KNOWN_IOT_KEYWORDS):
                return "iot"

        if vendor:
            vu = vendor.upper()
            if any(k in vu for k in ["HIKVISION", "DAHUA", "UNIVIEW", "TIANDY", "KEDACOM", "AXIS", "BOSCH", "VIVOTEK", "CP PLUS", "REOLINK", "AMCREST"]):
                return "camera"
            if any(k in vu for k in ["H3C", "TP-LINK", "D-LINK", "NETGEAR", "UBIQUITI", "CISCO", "LINKSYS", "ZTE", "TENDA", "RUIJIE", "MERCURY"]):
                return "network"
            if any(k in vu for k in ["APPLE", "SAMSUNG", "HUAWEI", "XIAOMI", "OPPO", "VIVO", "ONEPLUS", "HONOR", "GOOGLE", "MOTOROLA"]):
                return "phone"
            if any(k in vu for k in ["DELL", "HP", "LENOVO", "ASUSTEK", "ACER", "MSI", "MICROSOFT"]):
                return "computer"
            if any(k in vu for k in ["INTEL", "AZUREWAVE", "FN-LINK", "FN-LINK"]):
                return "wireless"
            if any(k in vu for k in ["HUALAI", "HIGH-FLYING", "BILIAN", "AI-LINK"]):
                return "network"
            if any(k in vu for k in ["BROADLINK", "YEELIGHT", "AQARA", "SONOFF", "TUYA"]):
                return "iot"
            if "CLOUD NETWORK" in vu:
                return "network"

        if any(kw in hostname_lower for kw in ["camera", "ipc", "nvr", "dvr", "cam"]):
            return "camera"
        if any(kw in hostname_lower for kw in ["router", "ap", "wifi", "gateway"]):
            return "router"

        return "unknown"

    def _determine_device_model(self, vendor: Optional[str], hostname: str) -> str:
        if not vendor:
            return ""
        if not hostname:
            return vendor
        return f"{vendor} ({hostname})"

    def _calculate_confidence(self, scan_result: Dict, vendor: Optional[str], hostname: str) -> float:
        score = 0.0
        if vendor:
            score += 0.3
        if hostname:
            score += 0.3
        os_matches = scan_result.get("os_matches", [])
        if os_matches:
            score += 0.3
        if scan_result.get("vendor"):
            score += 0.1
        return min(score, 1.0)

    def _assess_risk(self, scan_result: Dict, vendor: Optional[str], device_type: str) -> str:
        if device_type == "camera":
            return "HIGH"
        if vendor and vendor.upper() in [v.upper() for v in KNOWN_CAMERA_VENDORS]:
            return "HIGH"
        if device_type == "unknown":
            return "MEDIUM"
        return "LOW"
