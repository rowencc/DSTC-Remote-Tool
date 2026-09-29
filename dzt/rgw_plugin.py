#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4G Wireless Router CPE (Mongoose + xml_action.cgi) 探测插件
品牌: rgw
型号: 通用 (AR5510 等 4G CPE / mifi)
固件: >=1.0

管理页为 SPA 点击切换，真数据接口在 JS 中:
- 登录: GET /login.cgi 取 Digest challenge，再带 query + Authorization
- 设备列表: GET /xml_action.cgi?method=get&module=duster&file=device_management_all
- 菜单映射: xml/ui_mifi.xml 中 mConnected_Devices -> device_management_all
"""

import hashlib
import random
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote

import requests

_DEFAULT_XML_FILE = "device_management_all"
_XML_FILES = (
    "device_management_all",
    "device_management",
    "lan",
)


def format_conn_time(raw: Any) -> str:
    """连接时长统一为 MM:SS 或 HH:MM:SS（0 小时不显示）。

    兼容示例:
      0 hours,33 mins, 57 secs  -> 33:57
      1 hours,33 mins, 57 secs  -> 01:33:57
      0 小时 33 分 57 秒 / 1小时33分57秒
      33:57 / 01:33:57 / 57s / 1d 2h 3m 4s
      "" -> ""
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # 已是 HH:MM:SS 或 MM:SS
    m = re.fullmatch(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})", s)
    if m:
        h = int(m.group(1) or 0)
        mi, sec = int(m.group(2)), int(m.group(3))
        return _fmt_dhms(h, mi, sec)

    h = mi = sec = day = 0
    # 中文
    for pat, setter in (
        (r"(\d+)\s*天", "d"), (r"(\d+)\s*日", "d"),
        (r"(\d+)\s*(?:hours?|hour|hrs?|h|小时|时)", "h"),
        (r"(\d+)\s*(?:mins?|minutes?|m|分|分钟)", "m"),
        (r"(\d+)\s*(?:secs?|seconds?|s|秒)", "s"),
    ):
        pass
    dm = re.search(r"(\d+)\s*(?:days?|day|d|天|日)", s, re.I)
    hm = re.search(r"(\d+)\s*(?:hours?|hour|hrs?|hr|h|小时|时)", s, re.I)
    mm = re.search(r"(\d+)\s*(?:mins?|minutes?|min|m|分|分钟)", s, re.I)
    sm = re.search(r"(\d+)\s*(?:secs?|seconds?|sec|s|秒)", s, re.I)
    if hm or mm or sm or dm:
        day = int(dm.group(1)) if dm else 0
        h = int(hm.group(1)) if hm else 0
        mi = int(mm.group(1)) if mm else 0
        sec = int(sm.group(1)) if sm else 0
        h += day * 24
        # 无任何单位但有冒号以外的纯数字+单位混合已覆盖；若只有天没有 h/m/s 单位误匹配
        if not (hm or mm or sm) and dm:
            return _fmt_dhms(h, 0, 0)
        return _fmt_dhms(h, mi, sec)

    # 紧凑英文: 0h33m57s / 1h33m57s
    m = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", s, re.I)
    if m and any(m.groups()):
        day = int(m.group(1) or 0)
        h = int(m.group(2) or 0) + day * 24
        mi = int(m.group(3) or 0)
        sec = int(m.group(4) or 0)
        return _fmt_dhms(h, mi, sec)

    # 纯秒数
    if re.fullmatch(r"\d+", s):
        total = int(s)
        return _fmt_dhms(total // 3600, (total % 3600) // 60, total % 60)

    return s


def _fmt_dhms(h: int, mi: int, sec: int) -> str:
    if h <= 0 and mi <= 0 and sec <= 0 and (h, mi, sec) != (0, 0, 0):
        return ""
    if h > 0:
        return f"{h:02d}:{mi:02d}:{sec:02d}"
    return f"{mi:02d}:{sec:02d}"


def probe(target: Dict[str, Any], endpoint: Dict[str, Any],
          collect: List[str], defaults: Dict[str, Any]) -> Dict[str, Any]:
    adapter = RGWAdapter(
        timeout=int(defaults.get("timeout_sec", defaults.get("timeout", 30)) or 30),
        retries=int(defaults.get("retries", 2) or 2),
    )
    try:
        return adapter.probe(target, endpoint, collect, defaults)
    except Exception as e:
        return {"success": False, "error": f"探测异常: {e}", "data": {}}


class RGWAdapter:
    def __init__(self, timeout: int = 30, retries: int = 2):
        self.timeout = timeout
        self.max_retries = retries
        self.base_url = ""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Expires": "-1",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        })
        self.ssid = ""
        self.mac = ""
        self.current_device_mac = ""
        self.base_path = ""
        self.device_path = _DEFAULT_XML_FILE
        self._realm = ""
        self._nonce = ""
        self._qop = "auth"
        self._username = ""
        self._password = ""
        self._nc = 1
        self.get_mac_sysfs()

    def probe(self, target: Dict[str, Any], endpoint: Dict[str, Any],
              collect: List[str], defaults: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._build_base_url(endpoint)
            self._apply_paths(endpoint, target)
            username = endpoint.get("username", "admin")
            password = endpoint["password"]

            login_err = self._authenticate(username, password)
            if login_err:
                return {"success": False, "error": login_err, "data": {}}

            result_data: Dict[str, Any] = {}
            for item in collect:
                if item == "device_list":
                    devices, used_file = self._get_device_list_with_fallback()
                    if isinstance(devices, dict) and devices.get("success") is False:
                        return {"success": False, "error": devices.get("error"), "data": {}}
                    result_data.update(devices)
                    result_data["_device_path"] = f"/xml_action.cgi?file={used_file}"
                    self.device_path = used_file
                elif item == "system_info":
                    info = self._get_system_info()
                    if info.get("success") is False:
                        return {"success": False, "error": info.get("error"), "data": {}}
                    result_data.update(info)
                elif item in ("arp_table", "dhcp_static"):
                    result_data[f"_{item}"] = []
            return {"success": True, "error": None, "data": result_data}
        except Exception as e:
            return {"success": False, "error": f"探测异常: {e}", "data": {}}
        finally:
            try:
                self._logout()
            except Exception:
                pass
            self.session.close()

    def _build_base_url(self, endpoint: Dict[str, Any]) -> None:
        raw = str(endpoint.get("host") or "").strip()
        if not raw:
            raise ValueError("endpoint.host 为空")
        https = bool(endpoint.get("https"))
        host = raw
        if "://" in host:
            scheme, host = host.split("://", 1)
            if scheme.lower() == "https":
                https = True
            elif scheme.lower() == "http":
                https = False
        for sep in ("#", "?"):
            if sep in host:
                host = host.split(sep, 1)[0]
        host = host.rstrip("/")
        path_from_host = ""
        if "/" in host:
            host, path_from_host = host.split("/", 1)
            path_from_host = "/" + path_from_host

        port = endpoint.get("port")
        if ":" in host and not host.startswith("["):
            h, p = host.rsplit(":", 1)
            if p.isdigit():
                if port in (None, ""):
                    port = int(p)
                host = h
        port_i = None
        if port not in (None, ""):
            try:
                port_i = int(port)
            except (TypeError, ValueError):
                port_i = None

        protocol = "https" if https else "http"
        if port_i and not ((protocol == "http" and port_i == 80) or (protocol == "https" and port_i == 443)):
            self.base_url = f"{protocol}://{host}:{port_i}"
        else:
            self.base_url = f"{protocol}://{host}"
        self._host_path_hint = path_from_host

    def _apply_paths(self, endpoint: Dict[str, Any], target: Optional[Dict[str, Any]] = None) -> None:
        target = target or {}
        ep_base = str(endpoint.get("base_path") or target.get("base_path") or "").strip()
        if not ep_base and getattr(self, "_host_path_hint", ""):
            hint = self._host_path_hint.split("?", 1)[0]
            if hint and not re.search(r"\.(asp|aspx|php|html?|cgi|do|jsp)$", hint, re.I):
                ep_base = hint
        self.base_path = self._norm_path(ep_base)
        if self.base_path == "/":
            self.base_path = ""

        raw_dp = str(
            endpoint.get("device_path")
            or target.get("device_path")
            or ""
        ).strip()
        file_name = self._xml_file_from_device_path(raw_dp) or _DEFAULT_XML_FILE
        self.device_path = file_name

    @staticmethod
    def _xml_file_from_device_path(raw_dp: str) -> str:
        if not raw_dp:
            return ""
        s = raw_dp.split("?", 1)[0]
        # 完整 URL 或 /xml_action.cgi 路径
        if "xml_action" in s or s.endswith(".cgi") or s.endswith(".asp") or s.endswith(".xml"):
            # 从 query 抽 file=
            if "file=" in raw_dp:
                return raw_dp.split("file=", 1)[1].split("&", 1)[0].split("#", 1)[0]
            base = s.rstrip("/").rsplit("/", 1)[-1]
            # /dhcpd_client_list.asp 等 H3C 路径在本插件不适用，用默认
            if base in ("device_management_all", "device_management", "lan"):
                return base
            return ""
        # 用户直接填 device_management_all
        if re.fullmatch(r"[A-Za-z0-9_]+", raw_dp):
            return raw_dp
        return ""

    @staticmethod
    def _norm_path(p: str) -> str:
        s = (p or "").strip()
        if not s:
            return ""
        s = s.split("#", 1)[0]
        path, _, query = s.partition("?")
        if not path.startswith("/"):
            path = "/" + path
        path = re.sub(r"/{2,}", "/", path)
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path + (f"?{query}" if query else "")

    @staticmethod
    def _md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_challenge(header: str) -> Optional[Dict[str, str]]:
        if not header or not header.lower().startswith("digest"):
            return None
        realm_m = re.search(r'realm="([^"]*)"', header, re.I)
        nonce_m = re.search(r'nonce="([^"]*)"', header, re.I)
        qop_m = re.search(r'qop="([^"]*)"', header, re.I)
        if not realm_m or not nonce_m:
            return None
        return {
            "realm": realm_m.group(1),
            "nonce": nonce_m.group(1),
            "qop": (qop_m.group(1) if qop_m else "auth"),
        }

    def _digest_header(self, uri: str, method: str = "GET") -> str:
        self._nc += 1
        nc = f"{self._nc:08d}"
        cnonce = self._md5(f"{int(time.time() * 1000)}{random.randint(0, 100000)}")[:16]
        ha1 = self._md5(f"{self._username}:{self._realm}:{self._password}")
        ha2 = self._md5(f"{method}:{uri}")
        response = self._md5(f"{ha1}:{self._nonce}:{nc}:{cnonce}:{self._qop}:{ha2}")
        return (
            f'Digest username="{self._username}", realm="{self._realm}", '
            f'nonce="{self._nonce}", uri="{uri}", response="{response}", '
            f'qop={self._qop}, nc={nc}, cnonce="{cnonce}"'
        )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(1)
                return self.session.request(method, url, **kwargs)
            except requests.exceptions.RequestException as e:
                last_exc = e
                print(f"  请求失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
        raise last_exc

    def _authenticate(self, username: str, password: str) -> Optional[str]:
        """Digest 登录（对齐前端 utils.js doLogin）"""
        login_url = f"{self.base_url}/login.cgi"
        try:
            resp = self._request("GET", login_url)
        except Exception as e:
            return f"无法连接登录页 {login_url}: {e}"

        challenge = self._parse_challenge(
            resp.headers.get("WWW-Authenticate") or resp.headers.get("www-authenticate") or ""
        )
        if not challenge:
            # 个别固件把 challenge 放在 body / 另一资源
            try:
                resp2 = self._request(
                    "GET",
                    f"{self.base_url}/xml_action.cgi",
                    params={"method": "get", "module": "duster", "file": "status1"},
                )
                challenge = self._parse_challenge(
                    resp2.headers.get("WWW-Authenticate") or resp2.headers.get("www-authenticate") or ""
                )
            except Exception:
                challenge = None
        if not challenge:
            return f"未获取到 Digest challenge（login.cgi HTTP {resp.status_code}）"

        self._realm = challenge["realm"]
        self._nonce = challenge["nonce"]
        self._qop = challenge["qop"] or "auth"
        self._username = username
        self._password = password
        self._nc = 1

        # 前端: HA2 = GET /cgi/protected.cgi，query 带 response；Authorization 用 /cgi/xml_action.cgi
        nc = f"{self._nc:08d}"
        cnonce = self._md5(f"{int(time.time() * 1000)}{random.randint(0, 100000)}")[:16]
        ha1 = self._md5(f"{username}:{self._realm}:{password}")
        ha2_prot = self._md5("GET:/cgi/protected.cgi")
        login_response = self._md5(f"{ha1}:{self._nonce}:{nc}:{cnonce}:{self._qop}:{ha2_prot}")
        query = urlencode({
            "Action": "Digest",
            "username": username,
            "realm": self._realm,
            "nonce": self._nonce,
            "response": login_response,
            "qop": self._qop,
            "cnonce": cnonce,
            "temp": "asr",
        })
        auth_header = self._digest_header("/cgi/xml_action.cgi")
        try:
            r = self._request(
                "GET",
                f"{login_url}?{query}",
                headers={"Authorization": auth_header},
            )
        except Exception as e:
            return f"登录请求失败: {e}"

        body = (r.text or "")
        if "200 OK" in body or r.status_code == 200:
            # body 含 200 OK 即前端 login_done 成功；status 200 也可能仅是 challenge 复发
            if "200 OK" in body:
                print("登录成功 (login.cgi Digest)")
                return None
        # 再试标准 Digest 对 login.cgi 本身
        try:
            std_auth = self._digest_header("/login.cgi")
            r2 = self._request("GET", login_url, headers={"Authorization": std_auth})
            if "200 OK" in (r2.text or ""):
                print("登录成功 (login.cgi std Digest)")
                return None
        except Exception:
            pass

        # 若 login 歧义，直接用 xml_action 探测；UNAUTHORIZED 才算失败
        try:
            probe = self._xml_get("status1")
            if "UNAUTHORIZED" in probe:
                return f"登录失败（password 错误或会话未建立），realm={self._realm}"
            print("登录成功 (xml_action 可访问)")
            return None
        except Exception as e:
            return f"登录失败: {e}"

    def _xml_get(self, file_name: str) -> str:
        url = f"{self.base_url}/xml_action.cgi"
        params = {"method": "get", "module": "duster", "file": file_name}
        auth = self._digest_header("/cgi/xml_action.cgi")
        resp = self._request("GET", url, params=params, headers={"Authorization": auth})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} file={file_name}")
        return resp.text or ""

    def _logout(self) -> None:
        try:
            self._request(
                "GET",
                f"{self.base_url}/xml_action.cgi",
                params={"Action": "logout"},
                headers={"Authorization": self._digest_header("/cgi/xml_action.cgi")},
            )
        except Exception as e:
            print(f"登出失败(忽略): {e}")

    def _get_device_list(self, file_name: str) -> Dict[str, Any]:
        print(f"正在获取已连接设备... file={file_name}")
        xml_text = self._xml_get(file_name)
        if "UNAUTHORIZED" in xml_text and "<Item" not in xml_text:
            return {"success": False, "error": "设备列表未授权 (UNAUTHORIZED)"}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            return {"success": False, "error": f"XML 解析失败 ({file_name}): {e}"}

        items = root.findall(".//Item")
        if not items:
            # 空列表也可能是成功
            if root.find(".//device_management") is not None or root.find("RGW") is not None:
                return {}
            return {"success": False, "error": f"未找到设备 Item ({file_name})"}

        devices: Dict[str, Any] = {}
        index = 0
        for item in items:
            mac = self._normalize_mac(_text(item, "mac"))
            if not mac:
                continue
            name = _text(item, "name")
            try:
                name = bytes(name, "utf-8").decode("utf-8", "ignore")
            except Exception:
                pass
            # 前端对 name 做 decodeURIComponent
            if "%" in name:
                try:
                    from urllib.parse import unquote
                    name = unquote(name)
                except Exception:
                    pass
            ip = _text(item, "ip_address") or _text(item, "ip")
            conn_time = format_conn_time(_text(item, "conn_time"))
            conn_type = _text(item, "conn_type")
            blocked = _text(item, "blocked")
            connected = _text(item, "connected")
            devices[mac] = {
                "MAC地址": mac,
                "主机名": name,
                "IP地址": ip,
                "连接时间": conn_time,
                "序号": index,
                "连接SSID": self.ssid,
                "ap的id": "",
                "AP的MAC地址": self.mac,
                "VLAN": "",
                "信号强度": "",
                "信道": "",
                "频宽": "",
                "发送速率": "",
                "接收速率": "",
                "数据量": "",
                "厂商": "",
                "备注": f"conn={conn_type};blocked={blocked};connected={connected}",
                "网关的MAC地址": self.mac,
                "系统": "",
                "设备mac": self.current_device_mac,
                "端口": "",
                "其他": "",
            }
            index += 1
        return devices

    def _get_device_list_with_fallback(self) -> Tuple[Dict[str, Any], str]:
        candidates: List[str] = []
        primary = self.device_path or _DEFAULT_XML_FILE
        candidates.append(primary)
        for p in _XML_FILES:
            if p not in candidates:
                candidates.append(p)
        # 配置里若粘了 H3C 的 asp 路径，忽略之
        last_err = ""
        for name in candidates:
            if name.endswith(".asp") or name.endswith(".html") or "/" in name:
                continue
            try:
                result = self._get_device_list(name)
            except Exception as e:
                last_err = str(e)
                continue
            if not isinstance(result, dict):
                continue
            if result.get("success") is False:
                last_err = str(result.get("error") or "")
                continue
            if name != primary:
                print(f"设备列表 file 回退成功: {name}")
            return result, name
        return {
            "success": False,
            "error": last_err or f"无法获取设备列表（已试 {len(candidates)} 个 file）",
        }, primary

    def _get_system_info(self) -> Dict[str, Any]:
        print("正在获取系统信息...")
        info: Dict[str, Any] = {}
        try:
            # 首页 HTML title
            r = self._request("GET", f"{self.base_url}/")
            m = re.search(r"<title>([^<]+)</title>", r.text or "", re.I)
            if m:
                info["设备标题"] = m.group(1).strip()
        except Exception as e:
            print(f"获取首页失败(忽略): {e}")
        try:
            status_xml = self._xml_get("status1")
            root = ET.fromstring(status_xml)
            for tag in ("ssid", "SSID", "ssid2g", "ssid5g"):
                v = _text(root, tag)
                if v:
                    self.ssid = v
                    break
            for tag in ("mac", "lan_mac", "wan_mac", "macAddress", "mac_address"):
                v = _text(root, tag)
                if v and re.fullmatch(r"[0-9A-Fa-f:]{12,17}", v):
                    self.mac = self._normalize_mac(v)
                    break
        except Exception as e:
            print(f"获取 status1 失败(忽略): {e}")
        try:
            lan_xml = self._xml_get("lan")
            root = ET.fromstring(lan_xml)
            for tag in ("mac", "lan_mac", "ssid"):
                v = _text(root, tag)
                if v and not self.mac and re.search(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", v):
                    self.mac = self._normalize_mac(v)
                if v and not self.ssid and tag == "ssid":
                    self.ssid = v
        except Exception as e:
            print(f"获取 lan 失败(忽略): {e}")

        info["base_url"] = self.base_url
        info["xml_file"] = self.device_path
        return {"_system_info": info}

    def get_mac_sysfs(self, interface: str = "eth0") -> None:
        try:
            with open(f"/sys/class/net/{interface}/address", "r") as f:
                self.current_device_mac = self._normalize_mac(f.read().strip())
        except (FileNotFoundError, IOError, OSError):
            for iface in ("en0", "eth0"):
                try:
                    with open(f"/sys/class/net/{iface}/address", "r") as f:
                        self.current_device_mac = self._normalize_mac(f.read().strip())
                        return
                except (FileNotFoundError, IOError, OSError):
                    continue

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        if not mac:
            return ""
        mac_clean = re.sub(r"[^0-9a-fA-F]", "", mac)
        if len(mac_clean) != 12:
            return mac
        return ":".join(mac_clean[i:i + 2].upper() for i in range(0, 12, 2))


def _text(node: ET.Element, tag: str) -> str:
    el = node.find(tag)
    if el is None:
        # 忽略命名空间
        for child in node:
            if child.tag.split("}")[-1] == tag:
                return (child.text or "").strip()
        return ""
    return (el.text or "").strip()
