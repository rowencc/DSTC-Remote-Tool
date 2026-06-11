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