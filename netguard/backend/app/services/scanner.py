import subprocess
import socket
import nmap
from typing import List, Dict, Optional
from app.config import config
from app.services.vendor_lookup import VendorLookup


class NetworkScanner:
    def __init__(self):
        self.nm = nmap.PortScanner()
        self.config = config["scanner"]
        self.vendor_lookup = VendorLookup()

    def scan_network(self, network: Optional[str] = None) -> List[Dict]:
        arp_devices = self._arp_table()
        devices = []
        for d in arp_devices:
            hostname = self._reverse_dns(d["ip_address"])
            vendor = self.vendor_lookup.lookup(d["mac_address"])
            devices.append({
                "ip_address": d["ip_address"],
                "mac_address": d["mac_address"],
                "hostname": hostname,
                "vendor": vendor
            })
        return devices

    def _arp_table(self) -> List[Dict]:
        devices = []
        seen = set()
        try:
            for iface in ["en0", "en1"]:
                try:
                    output = subprocess.check_output(
                        ["arp", "-a", "-i", iface],
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=5
                    )
                    for line in output.splitlines():
                        parts = line.split()
                        if len(parts) >= 4:
                            ip = parts[1].strip("()")
                            mac = parts[3]
                            if mac in ("(incomplete)", "ff:ff:ff:ff:ff:ff"):
                                continue
                            mac_upper = mac.upper()
                            if ip not in seen and mac_upper not in seen:
                                seen.add(ip)
                                devices.append({
                                    "ip_address": ip,
                                    "mac_address": mac_upper,
                                })
                except Exception:
                    continue
        except Exception:
            pass
        return devices

    def _reverse_dns(self, ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except Exception:
            return ""

    def deep_scan(self, ip: str) -> Dict:
        self.nm.scan(hosts=ip, arguments="-sV --open --host-timeout 10s")
        if ip not in self.nm.all_hosts():
            return {}
        host_data = self.nm[ip]
        open_ports = {}
        if "tcp" in host_data:
            for port, info in host_data["tcp"].items():
                open_ports[port] = info.get("name", "") + "/" + info.get("product", "")
        return {
            "ip_address": ip,
            "mac_address": host_data.get("addresses", {}).get("mac", ""),
            "os_matches": host_data.get("osmatch", []),
            "open_ports": open_ports,
            "vendor": host_data.get("vendor", {}).get("mac", "")
        }

    def quick_port_scan(self, ip: str) -> Dict:
        self.nm.scan(hosts=ip, arguments="-F --host-timeout 5s")
        if ip not in self.nm.all_hosts():
            return {}
        host_data = self.nm[ip]
        open_ports = {}
        if "tcp" in host_data:
            for port, info in host_data["tcp"].items():
                open_ports[port] = info.get("name", "")
        return {
            "open_ports": open_ports,
            "vendor": host_data.get("vendor", {}).get("mac", "")
        }
