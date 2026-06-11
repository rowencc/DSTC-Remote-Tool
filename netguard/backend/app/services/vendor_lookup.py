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
