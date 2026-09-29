#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DsFlexProbe 路由器配置页（config_web.py）
================================================================

【作用】
  浏览器里填写目标路由 -> 分步验证「采集 + 上报」-> 全部成功才写入 scan_config.json。
  失败会标出卡在哪一步及处理建议；支持删除/清空已保存目标。

【本机开发/本地运行】
  本地工作副本: client-tools/config_web.py
  依赖: Python3 标准库；验证上报时需能 import 到 dsprobe（硬件端已具备）
  临时前台跑（改 SCAN_CONFIG / PLUGINS_DIR 避免动系统配置）:
    cd client-tools
    SCAN_CONFIG=./scan_config.json \
    PLUGINS_DIR=./plugins \
    CONFIG_WEB_PORT=18080 \
    python3 config_web.py
  浏览器打开: http://127.0.0.1:18080
  注意: 本地无 plugins/ 目录时品牌下拉为空；插件需从硬件拷回或部署到 PLUGINS_DIR。

【硬件端路径（探针，cherryba-m1）】
  设备 IP/SSH:  192.168.200.100:12222  user=root  （旧 IP 192.168.101.83 已弃用）
  脚本部署:     /root/main/tools/config_web.py
  插件目录:     /root/main/plugins/{brand}.py
                品牌文件名 = 品牌下拉值，如 rgw.py / h3c.py / xiaomi.py / xiaoyi.py
  采集配置:     /root/scan_config.json
                历史备份: /root/scan_config.json.bak.*
  调度入口:     /root/main/main.py
  调度状态:     /root/main/state/last_run.json
  日志:         /root/logs/cron.log（cron 每次覆盖写）
                /root/logs/{target_id}/...  /root/logs/report/...
  采集 crontab: */3 * * * * /usr/bin/python3 /root/main/main.py > /root/logs/cron.log 2>&1
  配置页服务:   systemd 单元 /etc/systemd/system/config-web.service
                监听 0.0.0.0:18080   URL: http://192.168.200.100:18080

【环境变量】（均有默认值）
  CONFIG_WEB_HOST   默认 0.0.0.0
  CONFIG_WEB_PORT   默认 18080
  SCAN_CONFIG       默认 /root/scan_config.json
  PLUGINS_DIR       默认 <config_web.py 上级>/plugins  → 硬件上即 /root/main/plugins

【硬件端部署命令】
  # 1) 推送本文件
  export SSHPASS='dongshengniubi666'
  sshpass -e scp -O -P 12222 -o StrictHostKeyChecking=no \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    pw/config_web.py root@192.168.200.100:/root/main/tools/config_web.py

  # 2) 推送插件（按需，brand -> 文件名）
  sshpass -e scp -O -P 12222 ... client-tools/plugins/rgw_plugin.py root@192.168.200.100:/root/main/plugins/rgw.py
  sshpass -e scp -O -P 12222 ... client-tools/plugins/h3c_plugin.py root@192.168.200.100:/root/main/plugins/h3c.py

  # 3) 首次安装并启用配置页服务
  sshpass -e ssh -p 12222 ... root@192.168.200.100 <<'EOF'
  cat > /etc/systemd/system/config-web.service <<'UNIT'
  [Unit]
  Description=DsFlexProbe config web
  After=network.target

  [Service]
  WorkingDirectory=/root/main
  Environment=CONFIG_WEB_HOST=0.0.0.0
  Environment=CONFIG_WEB_PORT=18080
  Environment=SCAN_CONFIG=/root/scan_config.json
  Environment=PLUGINS_DIR=/root/main/plugins
  Environment=PYTHONUNBUFFERED=1
  ExecStart=/usr/bin/python3 /root/main/tools/config_web.py
  Restart=always
  RestartSec=3

  [Install]
  WantedBy=multi-user.target
  UNIT
  systemctl daemon-reload
  systemctl enable --now config-web.service
  systemctl restart config-web.service
  systemctl is-active config-web.service
  curl -sS http://127.0.0.1:18080/healthz
  EOF

  # 4) 改代码后重启
  sshpass -e ssh -p 12222 ... root@192.168.200.100 \
    'python3 -m py_compile /root/main/tools/config_web.py && systemctl restart config-web.service'

【页面使用】
  1. 品牌选 rgw/h3c/...；host 填路由 IP 或完整 URL；填用户名密码
  2. 可选: 端口、DHCP 客户端页 device_path、采集间隔、HTTPS
  3. 目标 ID / model 自动生成，无需手填
  4. 「验证并保存」= 采集成功且上报 200 才写配置；「仅验证不保存」只测
  5. 已保存目标可单条删除或「清空历史」

【HTTP API】
  GET  /                     配置页 HTML
  GET  /api/state            品牌列表 + 已保存目标（密码掩码 ******）
  GET  /healthz              健康检查
  POST /api/diagnose         验证/保存   body: JSON 含 save(bool)
  POST /api/targets/delete   删除一条     body: {"id":"..."}
  POST /api/targets/clear    清空全部     body: {}

【流程】
  参数校验 -> 加载插件 -> 采集路由器 -> 组装上报体 -> HTTP 上报 -> 写入配置
  全绿才保存；cron 默认每 3 分钟跑 /root/main/main.py，按各 target.interval_sec 调度。

【回滚/备份】
  本地一键拉取: ./pull_device.sh
  配置备份在设备: /root/scan_config.json.bak.*
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAIN_DIR = Path(__file__).resolve().parent.parent
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

HOST = os.environ.get("CONFIG_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("CONFIG_WEB_PORT", "18080"))
SCAN_CONFIG = Path(os.environ.get("SCAN_CONFIG", "/root/scan_config.json"))
PLUGINS_DIR = Path(os.environ.get("PLUGINS_DIR", str(MAIN_DIR / "plugins")))
DEFAULT_REPORT_URL = "http://zt.bjdskj.com/api/api/v1/data/receiveAc"

_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------

def load_scan_config() -> Dict[str, Any]:
    if not SCAN_CONFIG.exists():
        raise FileNotFoundError(f"配置不存在: {SCAN_CONFIG}")
    with open(SCAN_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def save_scan_config(cfg: Dict[str, Any]) -> None:
    with _write_lock:
        SCAN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = SCAN_CONFIG.with_name(SCAN_CONFIG.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, SCAN_CONFIG)


def list_brands() -> List[str]:
    if not PLUGINS_DIR.exists():
        return []
    return sorted(
        p.stem
        for p in PLUGINS_DIR.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


def public_config() -> Dict[str, Any]:
    cfg = load_scan_config()
    targets = []
    for t in cfg.get("targets", []):
        ep = t.get("endpoint") or {}
        targets.append({
            "id": t.get("id"),
            "brand": t.get("brand"),
            "model": t.get("model"),
            "type": t.get("type"),
            "interval_sec": t.get("interval_sec"),
            "collect": t.get("collect"),
            "firmware": t.get("firmware"),
            "endpoint": {
                "host": ep.get("host"),
                "username": ep.get("username"),
                "password": "******" if ep.get("password") else "",
                "https": bool(ep.get("https")),
                "port": ep.get("port"),
                "base_path": ep.get("base_path") or "",
                "device_path": ep.get("device_path") or "",
            },
        })
    report = cfg.get("report") or {}
    http = report.get("http") or {}
    return {
        "brands": list_brands(),
        "targets": targets,
        "report": {
            "channel": report.get("channel"),
            "url": http.get("url"),
            "method": http.get("method", "POST"),
        },
        "defaults": cfg.get("defaults") or {},
        "config_path": str(SCAN_CONFIG),
    }


# ---------------------------------------------------------------------------
# 输入规范化：host / 路径 自适应
# ---------------------------------------------------------------------------

_DEFAULT_DEVICE_PATH = "/dhcpd_client_list.asp"


def normalize_endpoint_inputs(
    host_raw: Any,
    port_raw: Any = None,
    https_raw: Any = None,
    device_path_raw: Any = None,
) -> Dict[str, Any]:
    """
    把用户可能粘贴的完整地址规范成 endpoint 片段。

    host 兼容:
      192.168.100.1
      192.168.100.1:8080
      http(s)://192.168.100.1
      http(s)://192.168.100.1:8080/admin/
      http://192.168.100.1/dhcpd_client_list.asp   -> 路径可喂给 device_path

    device_path 兼容:
      /dhcpd_client_list.asp
      dhcpd_client_list.asp
      http://192.168.100.1/dhcpd_client_list.asp
      http://192.168.100.1:8080/admin/dhcpd_client_list.asp?x=1
    """
    host = (host_raw or "").strip()
    path_hint = ""
    https = False
    if isinstance(https_raw, bool):
        https = https_raw
    elif https_raw not in (None, "", False, 0, "0", "false", "False"):
        https = True

    # 从 host 里剥 scheme / path / port（scheme 优先于复选框）
    scheme_forced = None
    if "://" in host:
        scheme, rest = host.split("://", 1)
        scheme_forced = scheme.lower()
        if scheme_forced == "https":
            https = True
        elif scheme_forced == "http":
            https = False
        host = rest
    # 去掉 fragment/query 对 host 的污染
    for sep in ("#", "?"):
        if sep in host:
            host = host.split(sep, 1)[0]
    host = host.rstrip("/")

    # host 中可能含 path（用户整段复制 URL）
    if "/" in host:
        host, path_hint = host.split("/", 1)
        path_hint = "/" + path_hint

    # host:port
    port = None
    if port_raw not in (None, ""):
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = None
    if ":" in host and not host.startswith("["):
        h, p = host.rsplit(":", 1)
        if p.isdigit():
            if port is None:
                port = int(p)
            host = h

    host = host.strip().strip("/")
    # 去掉可能残留的 username@ 前缀
    if "@" in host:
        host = host.rsplit("@", 1)[-1]

    # device_path
    device_path = (device_path_raw or "").strip() or (path_hint if _looks_like_page(path_hint) else "")
    device_path = normalize_path(device_path) or _DEFAULT_DEVICE_PATH

    # base_path: host 里带的目录前缀（且不是具体页面文件）
    base_path = ""
    if path_hint and not _looks_like_page(path_hint):
        base_path = normalize_path(path_hint)  # e.g. /admin
        if base_path == "/":
            base_path = ""

    endpoint: Dict[str, Any] = {
        "host": host,
        "https": https,
        "device_path": device_path,
        "base_path": base_path,
    }
    if port is not None:
        endpoint["port"] = port
    return endpoint


def _looks_like_page(path: str) -> bool:
    if not path:
        return False
    p = path.split("?", 1)[0].split("#", 1)[0].lower()
    return bool(re.search(r"\.(asp|aspx|php|html?|cgi|do|jsp)(/|$)", p)) or bool(
        re.search(r"dhcp|client|station|host|wlan|wifi|online|connected", p, re.I)
        and re.search(r"\.[a-z0-9]{1,5}$", p)
    )


def normalize_path(raw: str) -> str:
    """统一成以 / 开头的 path；接受完整 URL。"""
    s = (raw or "").strip()
    if not s:
        return ""
    if "://" in s:
        # 完整 URL -> 取 path（+ 可选保留 query 丢掉）
        try:
            from urllib.parse import urlparse
            u = urlparse(s)
            s = u.path or "/"
            if u.query:
                s = f"{s}?{u.query}"
        except Exception:
            # 粗暴截取
            s = "/" + s.split("://", 1)[1].split("/", 1)[1] if "/" in s.split("://", 1)[1] else "/"
    s = s.split("#", 1)[0]
    if not s.startswith("/"):
        s = "/" + s
    # 去掉多余重复斜杠（保留 query 内）
    path, sep, query = s.partition("?")
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path + (sep + query if sep else "")


def normalize_id_from_host(brand: str, host: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z]+", "-", host or "")[-20:].strip("-") or "router"
    return f"{brand}-{safe}"


# ---------------------------------------------------------------------------
# 插件加载与验证
# ---------------------------------------------------------------------------

def load_probe_fn(brand: str, model: str):
    if model:
        specific = PLUGINS_DIR / f"{brand}_{model}.py"
        path = specific if specific.exists() else (PLUGINS_DIR / f"{brand}.py")
    else:
        path = PLUGINS_DIR / f"{brand}.py"
    if not path.exists():
        available = list_brands()
        raise FileNotFoundError(
            f"找不到插件 {brand}.py（可用: {', '.join(available) or '无'}），"
            f"请将插件放到 {PLUGINS_DIR}/"
        )

    import importlib.util

    module_name = f"diag_plugin_{brand}_{model or 'x'}_{int(time.time() * 1000)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载插件: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "probe"):
        raise RuntimeError(f"插件缺少 probe() 函数: {path}")
    return module.probe, path.name


def count_devices(plugin_data: Any) -> Tuple[int, List[str]]:
    if not isinstance(plugin_data, dict):
        return 0, []
    inner = plugin_data.get("data")
    if not isinstance(inner, dict):
        macs = [k for k, v in plugin_data.items() if isinstance(v, dict) and ":" in str(k)]
        return len(macs), macs[:5]
    macs = [k for k, v in inner.items() if isinstance(v, dict) and ":" in str(k)]
    return len(macs), macs[:5]


def build_report_payload(probe_result: Dict[str, Any]) -> Dict[str, Any]:
    """从插件 probe 返回值提取 {MAC: 设备dict} 上报表。"""
    plugin_data = probe_result.get("data", {})
    if not isinstance(plugin_data, dict) or not plugin_data:
        return {}
    # 1) data.device_list 为 dict
    raw_list = plugin_data.get("device_list")
    if isinstance(raw_list, dict) and raw_list:
        return raw_list
    # 2) data.data 为 dict（部分插件再嵌一层）
    inner = plugin_data.get("data")
    if isinstance(inner, dict) and inner:
        return {k: v for k, v in inner.items() if not str(k).startswith("_")}
    # 3) data 本身就是 MAC -> 设备dict
    mac_like = [k for k, v in plugin_data.items() if isinstance(v, dict) and ":" in str(k)]
    if mac_like:
        return {k: v for k, v in plugin_data.items() if not str(k).startswith("_")}
    # 4) data.device_list 为 list[dict]（含 MAC地址 字段）
    if isinstance(raw_list, list) and raw_list:
        out: Dict[str, Any] = {}
        for i, item in enumerate(raw_list):
            if not isinstance(item, dict):
                continue
            mac = item.get("MAC地址") or item.get("MAC") or item.get("mac") or ""
            if not mac:
                continue
            out[str(mac)] = item
        if out:
            return out
    return {}


def _report_url() -> str:
    try:
        cfg = load_scan_config()
        return ((cfg.get("report") or {}).get("http") or {}).get("url") or ""
    except Exception:
        return DEFAULT_REPORT_URL


def _do_report(url: str, wrapper: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        from dsprobe.reporting import HttpReporter
        cfg = load_scan_config()
        http_cfg = dict(((cfg.get("report") or {}).get("http") or {}))
        http_cfg.setdefault("url", url)
        reporter = HttpReporter(http_cfg)
        ok = reporter.report_single(wrapper)
        meta = getattr(reporter, "last_report_meta", {}) or {}
        resp = meta.get("response") or {}
        status = resp.get("status_code")
        excerpt = (resp.get("response_excerpt") or "")[:160]
        err = meta.get("error")
        if ok:
            return True, f"HTTP {status}, {excerpt}"
        return False, f"HTTP {status}, error={err or excerpt or '上报失败'}"
    except Exception as e:
        try:
            import requests
            body = build_report_payload(wrapper.get("data") or {})
            r = requests.post(
                url, json=body, timeout=15,
                headers={"Content-Type": "application/json"},
            )
            text = (r.text or "")[:160]
            if r.status_code == 200:
                return True, f"HTTP 200, {text}"
            return False, f"HTTP {r.status_code}, {text}"
        except Exception as e2:
            return False, f"上报异常: {e2}（HttpReporter: {e}）"


def _map_probe_error(err: str, host: str, username: str) -> str:
    e = err or ""
    if "已有5个用户" in e:
        return "路由器并发登录已达上限，稍等片刻重试；避免多处同时登录管理界面"
    if "ABCDEFGH" in e and "登录" in e:
        return "sessionid 为失败标记，检查账号密码；并确认未超出 5 并发登录限制"
    if "timed out" in e.lower() or "Connection" in e or "Name or service" in e:
        return f"无法连接 {host}：检查本机与路由器网络、host/IP 是否正确"
    if "登录失败" in e:
        return f"登录失败：检查用户名「{username}」与密码；部分路由需先打开登录页/带 Referer"
    if "401" in e or "403" in e:
        return "鉴权被拒绝：检查账号密码或是否需要验证码"
    if "timeout" in e.lower():
        return "请求超时：增大 timeout_sec 或检查路由器负载"
    return "根据错误检查网络、账号密码、插件是否匹配该型号界面"


def _upsert_target(new_target: Dict[str, Any]) -> int:
    cfg = load_scan_config()
    targets = cfg.get("targets") or []
    replaced = False
    for i, t in enumerate(targets):
        if t.get("id") == new_target["id"]:
            targets[i] = new_target
            replaced = True
            break
    if not replaced:
        targets.append(new_target)
    cfg["targets"] = targets
    cfg["_last_modified"] = time.time()
    save_scan_config(cfg)
    return len(targets)


def _delete_target(target_id: str) -> Tuple[bool, str]:
    tid = (target_id or "").strip()
    if not tid:
        return False, "id 为空"
    cfg = load_scan_config()
    targets = cfg.get("targets") or []
    before = len(targets)
    cfg["targets"] = [t for t in targets if str(t.get("id") or "") != tid]
    if len(cfg["targets"]) == before:
        return False, f"未找到目标 id={tid}"
    cfg["_last_modified"] = time.time()
    save_scan_config(cfg)
    return True, f"已删除 {tid}，剩余 {len(cfg['targets'])} 条"


def _clear_targets() -> Tuple[bool, str]:
    cfg = load_scan_config()
    n = len(cfg.get("targets") or [])
    cfg["targets"] = []
    cfg["_last_modified"] = time.time()
    save_scan_config(cfg)
    return True, f"已清空 {n} 条目标"


def _fail(steps: List[Dict], name: str, detail: str, hint: str = "") -> Dict[str, Any]:
    steps.append({"name": name, "ok": False, "detail": detail, "hint": hint})
    return _result(steps, False)


def _result(
    steps: List[Dict],
    ok: bool,
    device_count: int = 0,
    sample: Optional[List[str]] = None,
    report_status: Optional[int] = None,
    saved: bool = False,
    device_path: str = "",
) -> Dict[str, Any]:
    failed = next((s for s in steps if not s.get("ok")), None)
    return {
        "ok": ok,
        "steps": steps,
        "device_count": device_count,
        "sample_macs": sample or [],
        "report_status": report_status,
        "saved": saved,
        "device_path": device_path or "",
        "error": None if ok else (failed or {}).get("detail", "验证失败"),
        "hint": None if ok else (failed or {}).get("hint"),
    }


def diagnose(payload: Dict[str, Any]) -> Dict[str, Any]:
    """分步验证；payload['save']=False 时全部通过也不写盘。"""
    do_save = payload.get("save", True) is not False
    steps: List[Dict[str, Any]] = []

    target_id = (payload.get("id") or "").strip()
    brand = (payload.get("brand") or "").strip()
    model = (payload.get("model") or "").strip() or "universal"
    username = (payload.get("username") or "admin").strip()
    password = payload.get("password") or ""
    try:
        interval = int(payload.get("interval_sec") or 60)
    except (TypeError, ValueError):
        return _fail(steps, "参数校验", f"interval_sec 非法: {payload.get('interval_sec')}", "请输入整数秒，如 60")

    host_raw = payload.get("host")
    ep_norm = normalize_endpoint_inputs(
        host_raw,
        port_raw=payload.get("port"),
        https_raw=payload.get("https"),
        device_path_raw=payload.get("device_path"),
    )
    host = ep_norm.get("host") or ""
    username = username or "admin"

    collect = payload.get("collect") or ["device_list"]
    if isinstance(collect, str):
        collect = [c.strip() for c in collect.split(",") if c.strip()]
    collect = list(collect)
    if "device_list" not in collect:
        collect.insert(0, "device_list")

    if not target_id:
        target_id = normalize_id_from_host(brand, host)
    if not brand:
        return _fail(steps, "参数校验", "请选择品牌 brand", "品牌决定加载哪个插件文件")
    if not host:
        return _fail(steps, "参数校验", "请填写路由器地址 host",
                     "支持 IP/域名，也可粘贴 http://192.168.1.1 或完整管理页 URL")
    if not password:
        return _fail(steps, "参数校验", "请填写密码 password", "路由器管理密码必填")

    norm_note = f"host 规范为 {host}"
    if ep_norm.get("port"):
        norm_note += f":{ep_norm['port']}"
    if ep_norm.get("base_path"):
        norm_note += f" base={ep_norm['base_path']}"
    if (payload.get("host") or "").strip() not in (host, f"http://{host}", f"https://{host}"):
        norm_note += f"（原始: {(payload.get('host') or '').strip()[:80]}）"
    steps.append({
        "name": "参数校验",
        "ok": True,
        "detail": (
            f"id={target_id}, brand={brand}, model={model}, {norm_note}, "
            f"device_path={ep_norm.get('device_path')}, interval={interval}s, collect={collect}"
        ),
    })

    try:
        probe_fn, plugin_file = load_probe_fn(brand, model)
        steps.append({"name": "加载插件", "ok": True, "detail": f"plugins/{plugin_file}"})
    except Exception as e:
        steps.append({
            "name": "加载插件", "ok": False, "detail": str(e),
            "hint": f"确认 {PLUGINS_DIR}/{brand}.py 存在且含 probe()",
        })
        return _result(steps, False)

    endpoint: Dict[str, Any] = {
        "host": host,
        "username": username,
        "password": password,
        "device_path": ep_norm.get("device_path") or _DEFAULT_DEVICE_PATH,
        "base_path": ep_norm.get("base_path") or "",
    }
    if ep_norm.get("https"):
        endpoint["https"] = True
    if ep_norm.get("port") is not None:
        endpoint["port"] = int(ep_norm["port"])

    target = {
        "id": target_id,
        "brand": brand,
        "model": model,
        "type": f"{brand}.{model}",
        "collect": collect,
        "endpoint": endpoint,
        "interval_sec": interval,
    }
    defaults = {"retries": 2, "timeout_sec": 30}

    t0 = time.time()
    try:
        probe_result = probe_fn(target, endpoint, collect, defaults)
    except Exception as e:
        steps.append({
            "name": "采集路由器", "ok": False, "detail": f"插件异常: {e}",
            "hint": "检查网络是否可达、账号密码、路由器是否限制并发登录",
        })
        return _result(steps, False)
    elapsed = int((time.time() - t0) * 1000)

    # 插件可能自动探测到实际 device_path
    if isinstance(probe_result, dict):
        data = probe_result.get("data") or {}
        if isinstance(data, dict) and data.get("_device_path"):
            endpoint["device_path"] = data["_device_path"]
            steps.append({
                "name": "设备列表路径",
                "ok": True,
                "detail": f"实际使用 {data['_device_path']}",
            })

    if not isinstance(probe_result, dict) or not probe_result.get("success"):
        err = (probe_result or {}).get("error") if isinstance(probe_result, dict) else str(probe_result)
        err = err or "未知错误"
        tried = endpoint.get("device_path", _DEFAULT_DEVICE_PATH)
        hint = _map_probe_error(err, host, username)
        if "设备列表" in str(err) or "dhcp" in str(err).lower() or "未找到" in str(err):
            hint = (
                f"当前 device_path={tried} 打不开或解析失败。"
                f"请在管理界面打开「DHCP客户端/客户列表」，把地址栏或 iframe 的 URL 填到「设备列表路径」"
            )
        steps.append({
            "name": "采集路由器", "ok": False, "detail": f"{err}（{elapsed}ms）",
            "hint": hint,
        })
        return _result(steps, False, device_path=endpoint.get("device_path"))

    device_count, sample = count_devices(probe_result.get("data"))
    if device_count <= 0:
        keys = list((probe_result.get("data") or {}).keys())[:6]
        steps.append({
            "name": "采集路由器", "ok": False,
            "detail": f"登录成功但未解析到设备（{elapsed}ms），data keys={keys}",
            "hint": f"检查 device_path={endpoint.get('device_path')} 是否为含 MAC 列表的页面",
        })
        return _result(steps, False, device_path=endpoint.get("device_path"))

    steps.append({
        "name": "采集路由器", "ok": True,
        "detail": (
            f"成功，设备 {device_count} 台，样例 MAC: {', '.join(sample)}（{elapsed}ms），"
            f"path={endpoint.get('device_path')}"
        ),
    })

    report_body = build_report_payload(probe_result)
    if not report_body:
        steps.append({
            "name": "组装上报数据", "ok": False,
            "detail": "设备表为空或格式不符（需 MAC -> 设备字典）",
            "hint": "插件 data 应为 {MAC: {字段...}}，或 data.data 为该结构",
        })
        return _result(steps, False, device_count=device_count, sample=sample,
                       device_path=endpoint.get("device_path", ""))

    non_mac = [k for k in report_body.keys() if ":" not in str(k)]
    steps.append({
        "name": "组装上报数据", "ok": not non_mac,
        "detail": f"记录 {len(report_body)} 条, sample_keys={list(report_body.keys())[:5]}"
                  + (f", 非MAC键={non_mac}" if non_mac else ""),
        "hint": None if not non_mac else "上报体 key 必须是 MAC，辅助数据请用 _ 前缀",
    })
    if non_mac:
        return _result(steps, False, device_count=device_count, sample=sample,
                       device_path=endpoint.get("device_path", ""))

    report_url = _report_url()
    if not report_url:
        steps.append({
            "name": "上报服务端", "ok": False,
            "detail": "scan_config 未配置 report.http.url",
            "hint": "检查 report.http.url",
        })
        return _result(steps, False, device_count=device_count, sample=sample,
                       device_path=endpoint.get("device_path", ""))

    report_ok, report_detail = _do_report(report_url, {
        "target_id": target_id,
        "timestamp": int(time.time()),
        "success": True,
        "data": probe_result,
    })
    steps.append({
        "name": "上报服务端", "ok": report_ok, "detail": report_detail,
        "hint": None if report_ok else "检查外网/URL/服务端是否可达",
    })
    if not report_ok:
        return _result(steps, False, device_count=device_count, sample=sample,
                       device_path=endpoint.get("device_path", ""))

    if not do_save:
        steps.append({"name": "保存配置", "ok": True, "detail": "仅验证模式，未写入配置"})
        return _result(steps, True, device_count=device_count, sample=sample,
                       report_status=200, saved=False, device_path=endpoint.get("device_path", ""))

    try:
        saved = _upsert_target({
            "id": target_id,
            "brand": brand,
            "model": model,
            "type": f"{brand}.{model}",
            "firmware": payload.get("firmware") or "unknown",
            "interval_sec": interval,
            "collect": collect,
            "endpoint": endpoint,
        })
        steps.append({
            "name": "保存配置", "ok": True,
            "detail": f"已写入 {SCAN_CONFIG}（targets 共 {saved} 条），cron 将按 interval 自动采集",
        })
    except Exception as e:
        steps.append({
            "name": "保存配置", "ok": False, "detail": f"写入失败: {e}",
            "hint": "检查文件权限",
        })
        return _result(steps, False, device_count=device_count, sample=sample)

    return _result(steps, True, device_count=device_count, sample=sample,
                   report_status=200, saved=True, device_path=endpoint.get("device_path", ""))


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DsFlexProbe 路由器配置</title>
<style>
:root{--bg:#0f1419;--card:#1a2332;--line:#2d3a4d;--text:#e7ecf3;--muted:#8b9bb4;--ok:#3dd68c;--bad:#ff6b6b;--acc:#4c8dff;--warn:#f0b429}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.5}
.wrap{max-width:960px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.35rem;margin:0 0 4px;font-weight:650}
.sub{color:var(--muted);font-size:.9rem;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:16px}
label{display:block;font-size:.85rem;color:var(--muted);margin:12px 0 6px}
input,select{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:#0d1218;color:var(--text);font-size:.95rem;outline:none}
input:focus,select:focus{border-color:var(--acc)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.chk{display:flex;align-items:center;gap:8px;margin-top:22px;color:var(--muted);font-size:.9rem}
.chk input{width:auto}
.btns{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap}
button{border:0;border-radius:8px;padding:11px 18px;font-size:.95rem;cursor:pointer;font-weight:600}
.btn-p{background:var(--acc);color:#fff}
.btn-p:disabled,.btn-g:disabled{opacity:.5;cursor:not-allowed}
.btn-g{background:transparent;color:var(--muted);border:1px solid var(--line)}
.banner{padding:12px 14px;border-radius:8px;margin:14px 0;display:none;font-size:.92rem}
.banner.ok{display:block;background:rgba(61,214,140,.12);border:1px solid rgba(61,214,140,.45);color:var(--ok)}
.banner.bad{display:block;background:rgba(255,107,107,.1);border:1px solid rgba(255,107,107,.4);color:var(--bad)}
.steps{list-style:none;padding:0;margin:12px 0 0}
.steps li{display:flex;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;margin-bottom:8px;background:#121a24}
.steps li.ok{border-color:rgba(61,214,140,.35)}
.steps li.bad{border-color:rgba(255,107,107,.45)}
.dot{width:10px;height:10px;border-radius:50%;margin-top:6px;flex:0 0 10px;background:var(--muted)}
.steps li.ok .dot{background:var(--ok)}
.steps li.bad .dot{background:var(--bad)}
.s-name{font-weight:600;font-size:.9rem}
.s-detail{color:var(--muted);font-size:.85rem;word-break:break-all}
.s-hint{color:var(--warn);font-size:.85rem;margin-top:4px}
h2{font-size:1rem;margin:0 0 8px;color:var(--text)}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:500}
.muted{color:var(--muted)}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.75rem;background:#243044;color:var(--muted)}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #fff3;border-top-color:#fff;border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
@media(max-width:640px){.row,.row3{grid-template-columns:1fr !important}.chk{margin-top:8px}}
.btn-del{background:transparent !important;color:var(--bad) !important;border:1px solid rgba(255,107,107,.4) !important}
.btn-del:hover{background:rgba(255,107,107,.12) !important}
</style>
</head>
<body>
<div class="wrap">
  <h1>DsFlexProbe 路由器配置</h1>
  <div class="sub">端口 18080 · 填写参数后点「验证并保存」：采集成功且上报成功才会写入配置</div>

  <div class="card">
    <h2>目标路由器</h2>
    <div class="row3">
      <div>
        <label>品牌 brand（对应 plugins/xxx.py）</label>
        <select id="brand"></select>
      </div>
      <div>
        <label>采集间隔 interval_sec（秒）</label>
        <input id="interval" type="number" value="60" min="30"/>
      </div>
      <div class="chk">
        <input type="checkbox" id="https"/><span>使用 HTTPS（http/https URL 自动识别）</span>
      </div>
    </div>
    <div class="row" style="grid-template-columns:2fr 1fr 1fr">
      <div>
        <label>路由器地址 host *（IP / 域名 / 完整 URL 均可）</label>
        <input id="host" placeholder="192.168.100.1 或 http://192.168.100.1/admin"/>
      </div>
      <div>
        <label>用户名 username</label>
        <input id="username" value="admin"/>
      </div>
      <div>
        <label>密码 password *</label>
        <input id="password" type="password" placeholder="管理密码"/>
      </div>
    </div>
    <div class="row">
      <div>
        <label>端口 port（可空；URL 带端口会自动识别）</label>
        <input id="port" placeholder="留空"/>
      </div>
      <div>
        <label>设备列表路径 device_path（DHCP 客户端页，可空）</label>
        <input id="device_path" placeholder="/dhcpd_client_list.asp 或完整 URL"/>
      </div>
    </div>
    <p class="muted" style="margin:8px 0 0;font-size:.82rem">目标 ID / 型号 model 自动生成，无需填写</p>

    <div class="btns">
      <button class="btn-p" id="btnRun" onclick="runDiag(true)">验证并保存</button>
      <button class="btn-g" id="btnTest" onclick="runDiag(false)">仅验证不保存</button>
      <button class="btn-g" id="btnRefresh" onclick="loadState()">刷新列表</button>
      <button class="btn-g" id="btnClear" onclick="clearTargets()" style="border-color:rgba(255,107,107,.45);color:var(--bad)">清空历史</button>
    </div>

    <div id="banner" class="banner"></div>
    <ul id="steps" class="steps"></ul>
  </div>

  <div class="card">
    <h2>已保存目标 <span class="tag" id="reportTag"></span></h2>
    <div style="overflow:auto">
      <table>
        <thead><tr><th>ID</th><th>品牌</th><th>地址</th><th>设备路径</th><th>账号</th><th>间隔</th><th></th></tr></thead>
        <tbody id="tbody"><tr><td colspan="7" class="muted">加载中…</td></tr></tbody>
      </table>
    </div>
    <p class="muted" style="margin:12px 0 0;font-size:.85rem" id="cfgPath"></p>
  </div>

  <div class="card">
    <h2>说明</h2>
    <ol class="muted" style="font-size:.88rem;padding-left:1.2em;margin:0">
      <li>host 可填 IP，也可粘贴 <code>http://192.168.1.1</code> 或带路径的完整管理地址，提交时自动拆出 host/port/https</li>
      <li>设备列表路径默认 <code>/dhcpd_client_list.asp</code>；陌生路由请在管理页打开 DHCP 客户端列表，粘贴该页 URL</li>
      <li>验证步骤：参数 → 插件 → 采集 → 组装上报体 → HTTP 上报 → 写入配置</li>
      <li>全部成功才保存；失败会标出卡在哪一步及处理建议</li>
      <li>保存后由 cron（默认每 3 分钟）按 interval 自动采集上报</li>
    </ol>
  </div>
</div>
<script>
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function loadState(){
  try{
    const r = await fetch('/api/state');
    const d = await r.json();
    if(d.error){ showBanner(false, d.error); return; }
    const sel = document.getElementById('brand');
    const prevBrand = sel.value;
    const brands = d.brands||[];
    sel.innerHTML = brands.map(b=>{
      const on = (b===prevBrand) ? ' selected' : '';
      return `<option value="${esc(b)}"${on}>${esc(b)}</option>`;
    }).join('') || '<option value="">无插件</option>';
    if(prevBrand && brands.includes(prevBrand)) sel.value = prevBrand;
    document.getElementById('reportTag').textContent = (d.report&&d.report.url)||'无上报地址';
    document.getElementById('cfgPath').textContent = '配置文件: ' + (d.config_path||'');
    const tb = document.getElementById('tbody');
    if(!d.targets||!d.targets.length){ tb.innerHTML='<tr><td colspan="7" class="muted">暂无目标</td></tr>'; return; }
    tb.innerHTML = d.targets.map(t=>`<tr>
      <td>${esc(t.id||'')}</td><td>${esc(t.brand||'')}</td>
      <td>${esc((t.endpoint&&t.endpoint.host)||'')}</td>
      <td>${esc((t.endpoint&&(t.endpoint.device_path||''))||'')}</td>
      <td>${esc((t.endpoint&&t.endpoint.username)||'')}</td>
      <td>${t.interval_sec||''}s</td>
      <td><button class="btn-g btn-del" data-id="${esc(t.id||'')}" onclick="delTarget('${esc(t.id||'')}')" style="padding:4px 10px;font-size:.8rem">删除</button></td></tr>`).join('');
  }catch(e){ showBanner(false, '加载状态失败: '+e); }
}
async function apiPost(path, payload){
  const r = await fetch(path, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload||{})
  });
  return await r.json();
}
async function delTarget(id){
  if(!id) return;
  if(!confirm('删除目标 '+id+' ？')) return;
  try{
    const d = await apiPost('/api/targets/delete', {id});
    showBanner(!!d.ok, d.message||d.error||'');
    loadState();
  }catch(e){ showBanner(false, '删除失败: '+e); }
}
async function clearTargets(){
  if(!confirm('清空全部已保存目标？此操作不可恢复。')) return;
  try{
    const d = await apiPost('/api/targets/clear', {});
    showBanner(!!d.ok, d.message||d.error||'');
    loadState();
  }catch(e){ showBanner(false, '清空失败: '+e); }
}
async function runDiag(save){
  const btn = document.getElementById(save?'btnRun':'btnTest');
  const other = document.getElementById(save?'btnTest':'btnRun');
  const label = save?'验证并保存':'仅验证不保存';
  btn.disabled = true; other.disabled = true;
  btn.innerHTML = '<span class="spin"></span>验证中…';
  document.getElementById('banner').className='banner';
  document.getElementById('steps').innerHTML='';
  const payload = {
    id: '',
    brand: document.getElementById('brand').value,
    model: 'universal',
    host: document.getElementById('host').value.trim(),
    device_path: document.getElementById('device_path').value.trim(),
    username: document.getElementById('username').value.trim()||'admin',
    password: document.getElementById('password').value,
    port: document.getElementById('port').value.trim(),
    https: document.getElementById('https').checked,
    interval_sec: parseInt(document.getElementById('interval').value||'60',10),
    collect: ['device_list'],
    save: !!save
  };
  try{
    const r = await fetch('/api/diagnose', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    render(d, save);
    if(d.ok) loadState();
  }catch(e){
    showBanner(false, '请求失败: '+e);
  }finally{
    btn.disabled=false; other.disabled=false;
    btn.textContent = label;
  }
}
function showBanner(ok, msg){
  const b = document.getElementById('banner');
  b.className = 'banner ' + (ok?'ok':'bad');
  b.textContent = msg;
}
function render(d, save){
  const ul = document.getElementById('steps');
  ul.innerHTML = (d.steps||[]).map(s=>`
    <li class="${s.ok?'ok':'bad'}">
      <span class="dot"></span>
      <div>
        <div class="s-name">${esc(s.name)} ${s.ok?'✓':'✗'}</div>
        <div class="s-detail">${esc(s.detail||'')}</div>
        ${s.hint?`<div class="s-hint">建议: ${esc(s.hint)}</div>`:''}
      </div>
    </li>`).join('');
  if(d.ok){
    const n = d.device_count||0;
    const p = d.device_path?('，路径 '+d.device_path):'';
    showBanner(true, `成功！采集到 ${n} 台设备并完成上报${p}` + (d.saved&&save?'，配置已保存，将按间隔自动运行':'（未保存）'));
  }else{
    showBanner(false, '失败: ' + (d.error||'验证未通过') + (d.hint? '　→ '+d.hint : '') + '　请修改后重试');
  }
}
loadState();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "DsFlexConfig/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            try:
                self._json(200, public_config())
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        if path == "/healthz":
            self._json(200, {"ok": True, "port": PORT})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/api/diagnose", "/api/targets/delete", "/api/targets/clear"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            self._json(400, {"error": f"请求体解析失败: {e}"})
            return
        try:
            if path == "/api/targets/delete":
                ok, msg = _delete_target(str(payload.get("id") or ""))
                self._json(200, {"ok": ok, "message" if ok else "error": msg})
                return
            if path == "/api/targets/clear":
                ok, msg = _clear_targets()
                self._json(200, {"ok": ok, "message": msg})
                return
            result = diagnose(payload)
            self._json(200, result)
        except Exception as e:
            traceback.print_exc()
            self._json(500, {
                "ok": False,
                "error": str(e),
                "steps": [{"name": "服务异常", "ok": False, "detail": str(e)}],
            })


def main() -> None:
    if not SCAN_CONFIG.exists():
        print(f"WARN: {SCAN_CONFIG} 不存在", file=sys.stderr)
    print(f"Config web: http://{HOST}:{PORT}  plugins={list_brands()}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
