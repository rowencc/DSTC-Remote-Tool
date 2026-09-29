#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H3C ICG/GR 系列路由器探测插件
品牌: h3c
型号: 通用 (GR2200 等)
固件: >=1.0

基于 Playwright codegen 录制的路由适配:
- 登录: POST /userLogin.asp (form, GB2312)
- 设备列表: GET /dhcpd_client_list.asp (JS Array, MAC;IP;主机名;接口)
- ARP 表: GET /arp_tmp.asp
- DHCP 静态: GET /dhcp_staticlist.asp
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

# 常见 DHCP/在线客户端列表路径（配置未命中时按序探测）
_COMMON_DEVICE_PATHS = (
    '/dhcpd_client_list.asp',
    '/dhcp_client_list.asp',
    '/dhcpd_client.asp',
    '/dhcp_client.asp',
    '/client_list.asp',
    '/dhcp_list.asp',
    '/lan_dhcp_client.asp',
    '/dhcpd_leases.asp',
    '/status_dhcp.asp',
    '/dhcp.asp',
    '/lan/dhcp_client_list.asp',
    '/web/dhcpd_client_list.asp',
    '/cgi-bin/dhcp_client_list.cgi',
    '/cgi-bin/status_dhcp.cgi',
    '/admin/status_dhcp.asp',
    '/admin/dhcp_client_list.asp',
)


def probe(target: Dict[str, Any], endpoint: Dict[str, Any],
          collect: List[str], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """插件探测入口函数"""
    adapter = H3CAdapter(
        timeout=defaults.get('timeout_sec', defaults.get('timeout', 30)),
        retries=defaults.get('retries', 2),
    )
    try:
        return adapter.probe(target, endpoint, collect, defaults)
    except Exception as e:
        return {"success": False, "error": f"探测异常: {e}", "data": {}}


class H3CAdapter:
    """H3C ICG 路由器适配器"""

    def __init__(self, timeout: int = 30, retries: int = 2):
        self.timeout = timeout
        self.max_retries = retries
        self.base_url = ""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        })
        self.ssid = ""
        self.mac = ""
        self.current_device_mac = ""
        self.base_path = ""
        self.device_path = '/dhcpd_client_list.asp'
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

            self.get_status_info()

            result_data: Dict[str, Any] = {}
            for item in collect:
                if item == "device_list":
                    devices, used_path = self._get_device_list_with_fallback()
                    if isinstance(devices, dict) and devices.get('success') is False:
                        return {"success": False, "error": devices.get('error'), "data": {}}
                    result_data.update(devices)
                    result_data['_device_path'] = used_path
                    self.device_path = used_path
                elif item == "arp_table":
                    arp = self._get_arp_table()
                    if arp.get('success') is False:
                        return {"success": False, "error": arp.get('error'), "data": {}}
                    result_data.update(arp)
                elif item == "dhcp_static":
                    st = self._get_dhcp_static()
                    if st.get('success') is False:
                        return {"success": False, "error": st.get('error'), "data": {}}
                    result_data.update(st)
                elif item == "system_info":
                    info = self._get_system_info()
                    if info.get('success') is False:
                        return {"success": False, "error": info.get('error'), "data": {}}
                    result_data.update(info)

            return {"success": True, "error": None, "data": result_data}

        except Exception as e:
            return {"success": False, "error": f"探测异常: {e}", "data": {}}
        finally:
            try:
                self._logout()
            except Exception:
                pass
            self.session.close()

    def _logout(self) -> None:
        """登出释放会话（路由器限制最多 5 个并发登录）"""
        if 'JSESSIONID' not in self.session.cookies:
            return
        try:
            self._request(
                'POST', self._resolve_url('/goform/aspForm'),
                data={'CMD': 'LOGOUT', 'GO': '4;login.htm'},
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': self._resolve_url('/home.asp'),
                },
            )
            print("已登出释放会话")
        except Exception as e:
            print(f"登出失败(忽略): {e}")

    def _build_base_url(self, endpoint: Dict[str, Any]) -> None:
        """规范化 host：支持 IP、host:port、http(s)://... 完整地址。"""
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
                https = bool(endpoint.get("https"))
        for sep in ("#", "?"):
            if sep in host:
                host = host.split(sep, 1)[0]
        host = host.rstrip("/")
        # 完整 URL 里可能带 path/base，这里只保留 authority 到 host/port
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
        if port not in (None, ""):
            try:
                port_i = int(port)
            except (TypeError, ValueError):
                port_i = None
        else:
            port_i = None

        protocol = "https" if https else "http"
        # 标准端口省略
        if port_i and not ((protocol == "http" and port_i == 80) or (protocol == "https" and port_i == 443)):
            self.base_url = f"{protocol}://{host}:{port_i}"
        else:
            self.base_url = f"{protocol}://{host}"
        # 供 _apply_paths 使用
        self._host_path_hint = path_from_host

    def _apply_paths(self, endpoint: Dict[str, Any], target: Optional[Dict[str, Any]] = None) -> None:
        """读取可配置 base_path / device_path，并做兼容归一。"""
        target = target or {}
        ep_base = str(endpoint.get("base_path") or target.get("base_path") or "").strip()
        if not ep_base and getattr(self, "_host_path_hint", ""):
            hint = self._host_path_hint.split("?", 1)[0]
            # 目录前缀才当 base；具体页面不当 base
            if hint and not re.search(r"\.(asp|aspx|php|html?|cgi|do|jsp)$", hint, re.I):
                ep_base = hint
        self.base_path = self._norm_path(ep_base)
        if self.base_path == "/":
            self.base_path = ""

        raw_dp = str(
            endpoint.get("device_path")
            or target.get("device_path")
            or endpoint.get("dhcp_path")
            or ""
        ).strip()
        # 若 device_path 是完整 URL，优先取其 path；host 应以 base 为准
        if "://" in raw_dp:
            try:
                from urllib.parse import urlparse
                u = urlparse(raw_dp)
                raw_dp = u.path or "/dhcpd_client_list.asp"
            except Exception:
                raw_dp = "/" + raw_dp.split("://", 1)[-1].split("/", 1)[-1]
        self.device_path = self._norm_path(raw_dp) or "/dhcpd_client_list.asp"

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

    def _resolve_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        p = path if path.startswith("/") else "/" + path
        return f"{self.base_url}{self.base_path}{p}"

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', self.timeout)
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
        """POST /userLogin.asp 表单登录（GB2312 编码）

        H3C GR2200 特殊点（录制 HAR 分析得出）:
        - 登录响应不发 Set-Cookie，而是返回 JS:
          var sessionid="<真实sid>"; var initid="ABCDEFGH";
          成功时 sessionid != initid，浏览器执行
          addCookie("JSESSIONID", sessionid, 0) 写 Cookie
        - 必须带 Origin/Referer，否则服务端不发真实 sessionid
        - 成功后需手动把 JSESSIONID 种进 requests.Session

        Returns:
            None=成功；否则错误说明（含路由 messages）
        """
        from urllib.parse import quote

        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/136.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                      'image/avif,image/webp,image/apng,*/*;q=0.8,'
                      'application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
        }

        # 1. 先 GET 登录页
        login_url = self._resolve_url('/userLogin.asp')
        try:
            self._request('GET', login_url, headers=base_headers)
        except Exception as e:
            return f"无法连接登录页 {login_url}: {e}"

        # 2. POST 登录
        body = (
            "save2Cookie=&vldcode="
            f"&account={quote(username, safe='')}"
            f"&password={quote(password, safe='')}"
            "&btnSubmit=+%B5%C7%C2%BC+"
        )
        post_headers = dict(base_headers)
        post_headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': f"{self.base_url}{self.base_path}" if self.base_path else self.base_url,
            'Referer': login_url,
        })
        try:
            resp = self._request(
                'POST', login_url,
                data=body, headers=post_headers,
            )
        except Exception as e:
            return f"登录请求失败: {e}"
        if resp.status_code != 200:
            return f"登录 HTTP {resp.status_code}"

        resp.encoding = 'gb2312'
        text = resp.text or ''

        # 3. 解析 sessionid
        import re as _re
        sid_m = _re.search(r'var\s+sessionid\s*=\s*"([^"]*)"', text)
        init_m = _re.search(r'var\s+initid\s*=\s*"([^"]*)"', text)
        msg_m = _re.search(r'var\s+messages\s*=\s*"([^"]*)"', text)

        sessionid = sid_m.group(1) if sid_m else ''
        initid = init_m.group(1) if init_m else ''
        messages = (msg_m.group(1) if msg_m else '').strip()

        if not sessionid or sessionid == initid or sessionid == 'ABCDEFGH':
            print(f"登录失败: sessionid={sessionid!r} initid={initid!r} messages={messages!r}")
            if messages:
                return f"登录失败: {messages}"
            return "登录失败（sessionid 无效）"

        # 4. 手动种 Cookie（模拟浏览器 addCookie）
        host = self.base_url.split('://', 1)[-1].split(':', 1)[0]
        self.session.cookies.set('JSESSIONID', sessionid, domain=host, path='/')
        print(f"登录成功, JSESSIONID={sessionid}")
        return None

    def _get_page(self, path: str) -> Optional[str]:
        url = self._resolve_url(path)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/136.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': f"{self.base_url}{self.base_path}/home.asp",
        }
        resp = self._request('GET', url, headers=headers)
        if resp.status_code != 200:
            print(f"GET {path} -> HTTP {resp.status_code}")
            return None
        # 设备页面固定 GB2312（Content-Type: text/html;charset=GB2312）
        resp.encoding = 'gb2312'
        return resp.text

    @staticmethod
    def _extract_js_array(html: str, var_name: str) -> List[str]:
        """从 HTML 中提取 var name=new Array('a','b',...); 的元素列表"""
        pattern = rf"var\s+{re.escape(var_name)}\s*=\s*new\s+Array\s*\((.*?)\);"
        m = re.search(pattern, html, re.S)
        if not m:
            return []
        return re.findall(r"'([^']*)'", m.group(1))

    def _get_device_list(self, path: Optional[str] = None) -> Dict[str, Any]:
        """解析 DHCP 客户端列表 -> 规范化设备字典"""
        use_path = path or self.device_path or '/dhcpd_client_list.asp'
        print(f"正在获取 DHCP 客户端列表... path={use_path}")
        html = self._get_page(use_path)
        if html is None:
            return {'success': False, 'error': f'无法获取设备列表页 {use_path}'}

        items = self._extract_js_array(html, 'dhcpd_client_list')
        if not items:
            # 兼容其它常见 JS 数组变量名
            for alt in (
                'dhcp_client_list', 'dhcpdclientlist', 'client_list',
                'dhcpLeaseList', 'host_list', 'lan_host_list',
            ):
                items = self._extract_js_array(html, alt)
                if items:
                    break
        if not items:
            # 空列表也算成功（仅当页面看起来像 DHCP 列表）
            if 'dhcpd_client_list' in html or re.search(r'dhcp.*client|client.*list', html, re.I):
                return {}
            return {'success': False, 'error': f'页面中未找到 dhcpd_client_list 数组 ({use_path})'}

        devices: Dict[str, Any] = {}
        for i, raw in enumerate(items):
            parts = [p.strip() for p in raw.split(';')]
            # 格式: MAC;IP;主机名;接口（无在线时长字段，对齐 xiaoyi 时取不到则留空）
            mac = self._normalize_mac(parts[0]) if parts else ''
            ip = parts[1] if len(parts) > 1 else ''
            hostname = parts[2] if len(parts) > 2 else ''
            iface = parts[3] if len(parts) > 3 else ''
            if not mac:
                continue
            devices[mac] = {
                'MAC地址': mac,
                '主机名': hostname,
                'IP地址': ip,
                '连接时间': '',
                '序号': i,
                '连接SSID': self.ssid,
                'ap的id': '',
                'AP的MAC地址': self.mac,
                'VLAN': '',
                '信号强度': '',
                '信道': '',
                '频宽': '',
                '发送速率': '',
                '接收速率': '',
                '数据量': '',
                '厂商': '',
                '备注': '',
            '网关的MAC地址': self.mac,
                '系统': '',
                '设备mac': self.current_device_mac,
                '端口': '',
                '其他': '',
            }
        return devices

    def _get_device_list_with_fallback(self) -> Tuple[Dict[str, Any], str]:
        """先取配置路径，失败再探测常见 DHCP 列表路径。

        Returns:
            (result, used_path)
        """
        candidates: List[str] = []
        primary = self.device_path or '/dhcpd_client_list.asp'
        candidates.append(primary)
        for p in _COMMON_DEVICE_PATHS:
            if p not in candidates:
                candidates.append(p)

        last_err = ''
        for path in candidates:
            result = self._get_device_list(path)
            # 成功（含空列表）或明确“数组缺失但页面像列表”时采用
            if not isinstance(result, dict):
                continue
            if result.get('success') is False:
                err = str(result.get('error') or '')
                # 加载失败继续试；数组缺失说明路径可能不对
                last_err = err
                if err.startswith('无法获取'):
                    continue
                if '未找到' in err or '数组' in err:
                    continue
                # 其它错误返回给上层
                return result, path
            # success
            if path != primary:
                print(f"设备列表路径回退成功: {path}")
            return result, path

        return {
            'success': False,
            'error': last_err or f'无法获取设备列表（已试 {len(candidates)} 个路径）',
        }, primary

    def _get_arp_table(self) -> Dict[str, Any]:
        """解析 ARP 表"""
        print("正在获取 ARP 表...")
        html = self._get_page('/arp_tmp.asp')
        if html is None:
            return {'success': False, 'error': '无法获取 arp_tmp.asp'}
        # ARP 页面可能是表格或 JS 数组，尽力解析
        entries = self._extract_js_array(html, 'arp_list') or \
                  self._extract_js_array(html, 'arp_tmp_list')
        rows = []
        if entries:
            for raw in entries:
                parts = [p.strip() for p in raw.split(';')]
                rows.append({
                    'IP地址': parts[0] if parts else '',
                    'MAC地址': self._normalize_mac(parts[1]) if len(parts) > 1 else '',
                    '接口': parts[2] if len(parts) > 2 else '',
                })
        else:
            # 表格解析兜底
            for m in re.finditer(
                r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I
            ):
                cells = re.findall(r'<td[^>]*>(.*?)</td>', m.group(1), re.S | re.I)
                cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if len(cells) >= 2 and re.search(r'\d+\.\d+\.\d+\.\d+', cells[0] or ''):
                    rows.append({
                        'IP地址': cells[0],
                        'MAC地址': self._normalize_mac(cells[1]) if len(cells) > 1 else '',
                        '接口': cells[2] if len(cells) > 2 else '',
                    })
        return {'arp_table': rows}

    def _get_dhcp_static(self) -> Dict[str, Any]:
        """解析 DHCP 静态绑定列表"""
        print("正在获取 DHCP 静态列表...")
        html = self._get_page('/dhcp_staticlist.asp')
        if html is None:
            return {'success': False, 'error': '无法获取 dhcp_staticlist.asp'}
        items = self._extract_js_array(html, 'dhcp_static_list')
        rows = []
        for raw in items:
            parts = [p.strip() for p in raw.split(';')]
            rows.append({
                'MAC地址': self._normalize_mac(parts[0]) if parts else '',
                'IP地址': parts[1] if len(parts) > 1 else '',
                '主机名': parts[2] if len(parts) > 2 else '',
            })
        return {'dhcp_static': rows}

    def get_status_info(self) -> None:
        """从首页提取 LAN MAC / SSID，供设备列表字段填充（对齐 xiaoyi）"""
        print("正在获取状态信息...")
        try:
            html = self._get_page('/home.asp')
            if not html:
                return
            # LAN MAC 常见于 home.asp 中的 MAC 地址文本
            m = re.search(
                r'(?:LAN\s*MAC|MAC\s*地址|macAddr|wanMac|lanMac)[^0-9A-Fa-f]{0,20}'
                r'([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})',
                html, re.I,
            )
            if m:
                self.mac = self._normalize_mac(m.group(1))
            # SSID 若页面可见
            s = re.search(r'(?:SSID|ssid)\s*[=:]\s*["\']?([^"\'<\s]+)', html, re.I)
            if s:
                self.ssid = s.group(1)
        except Exception as e:
            print(f"获取状态信息失败(忽略): {e}")

    def get_mac_sysfs(self, interface: str = 'eth0') -> None:
        """读取本机网卡 MAC（对齐 xiaoyi 的设备mac 字段来源）"""
        try:
            with open(f'/sys/class/net/{interface}/address', 'r') as f:
                self.current_device_mac = self._normalize_mac(f.read().strip())
        except (FileNotFoundError, IOError, OSError):
            # 非 Linux 或无 eth0 时尝试 en0（macOS 调试）
            for iface in ('en0', 'eth0'):
                try:
                    with open(f'/sys/class/net/{iface}/address', 'r') as f:
                        self.current_device_mac = self._normalize_mac(f.read().strip())
                        return
                except (FileNotFoundError, IOError, OSError):
                    continue

    def _get_system_info(self) -> Dict[str, Any]:
        """从首页提取基础系统信息"""
        print("正在获取系统信息...")
        html = self._get_page('/home.asp')
        if html is None:
            return {'success': False, 'error': '无法获取 home.asp'}
        info: Dict[str, Any] = {}
        # 设备型号常见于 title
        m = re.search(r'<title>([^<]+)</title>', html, re.I)
        if m:
            info['设备标题'] = m.group(1).strip()
        info['base_url'] = self.base_url
        # 前缀 _ : prepare_data 上报时会过滤，仅留在本地历史，不污染服务端原格式
        return {'_system_info': info}

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        if not mac:
            return ""
        mac_clean = re.sub(r'[^0-9a-fA-F]', '', mac)
        if len(mac_clean) != 12:
            return mac
        return ':'.join(mac_clean[i:i + 2].upper() for i in range(0, 12, 2))
