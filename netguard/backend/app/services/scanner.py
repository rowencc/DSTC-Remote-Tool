import subprocess
import nmap
from typing import List, Dict, Optional
from app.config import config


class NetworkScanner:
    def __init__(self):
        self.nm = nmap.PortScanner()
        self.config = config["scanner"]

    def scan_network(self, network: Optional[str] = None) -> List[Dict]:
        if not network:
            network = self.config["networks"][0]

        devices = self._arp_scan_native(network)
        if not devices:
            devices = self._nmap_scan(network)
        return devices

    def _arp_scan_native(self, network: str) -> List[Dict]:
        try:
            output = subprocess.check_output(
                ["arp", "-a", "-i", "en0"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10
            )
            devices = []
            seen = set()
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[1].strip("()")
                    mac = parts[3]
                    if mac == "(incomplete)" or mac == "ff:ff:ff:ff:ff:ff":
                        continue
                    if ip not in seen and mac not in seen:
                        seen.add(ip)
                        devices.append({
                            "ip_address": ip,
                            "mac_address": mac.upper(),
                            "hostname": "",
                            "vendor": ""
                        })
            return devices
        except Exception:
            return []

    def _nmap_scan(self, network: str) -> List[Dict]:
        self.nm.scan(hosts=network, arguments="-sn --host-timeout 10s")
        devices = []
        for host in self.nm.all_hosts():
            host_data = self.nm[host]
            mac = host_data.get("addresses", {}).get("mac", "")
            if not mac:
                continue
            devices.append({
                "ip_address": host,
                "mac_address": mac.upper(),
                "hostname": host_data.get("hostnames", [{}])[0].get("name", "") if host_data.get("hostnames") else "",
                "vendor": host_data.get("vendor", {}).get("mac", "")
            })
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
