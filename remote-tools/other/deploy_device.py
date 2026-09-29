#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_device.py — 一键部署到探针硬件（macOS / Windows）
================================================================

【作用】
  弹窗输入当前设备 IP（及端口/密码）后，自动将采集插件、配置页、
  scan_config、systemd 服务部署到设备并启动。

【部署内容】
  本地 client-tools/ 下:
    plugins/rgw_plugin.py -> /root/main/plugins/rgw.py      （4G CPE 采集）
    plugins/h3c_plugin.py -> /root/main/plugins/h3c.py      （H3C 采集）
    config_web.py         -> /root/main/tools/config_web.py （配置页）
    scan_config.json      -> /root/scan_config.json         （可选，先备份）
  远端写入:
    /etc/systemd/system/config-web.service
    systemctl daemon-reload && enable --now && restart config-web
    远端 py_compile 校验

【硬件路径说明】
  路径随部署网络变化，IP 由弹窗输入，不写死。
  默认端口 12222、用户 root；文件在设备上的固定逻辑路径不变:
    /root/main/plugins/  /root/main/tools/  /root/scan_config.json

【输入方式（--ui，自动回退）】
  macOS 默认: 系统弹窗 osascript -> 终端（双击 .command 用系统弹窗，避免 Tk 空白）
  其它平台:   tkinter -> 终端
  --ui native|tk|terminal 可强制；命令行 --ip 免交互

【用法】
  图形/弹窗（推荐）:
    python3 deploy_device.py
    macOS: 双击 deploy_device.command   （系统弹窗）
    Windows: 双击 deploy_device.bat     （tkinter 或终端）
    python3 deploy_device.py --ui terminal   # 强制终端输入

  命令行（免弹窗，CI/排障）:
    python3 deploy_device.py --ip 192.168.1.10 --port 12222 --user root --password 'xxx' --yes
    python3 deploy_device.py --ip 192.168.1.10 --skip-config   # 不推 scan_config
    python3 deploy_device.py --ip 192.168.1.10 --no-service    # 只推文件不装服务
    python3 deploy_device.py --help

【依赖】
  Python 3.8+ 标准库；tkinter 可选
  macOS 系统弹窗只需 osascript（系统自带）
  SSH 通道（任选其一，脚本自动探测）:
    1) paramiko（无则尝试 pip install --user paramiko）
    2) macOS/Linux: sshpass + OpenSSH scp/ssh
    3) Windows: plink（PuTTY）或 Git 自带 sshpass（Git Bash）

【部署成功后】
  配置页: http://<设备IP>:18080
  采集:   crontab 已存在时自动生效；否则见 config_web.py 头说明手动加:
    */3 * * * * /usr/bin/python3 /root/main/main.py > /root/logs/cron.log 2>&1
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

CLIENT_TOOLS_DIR = Path(__file__).resolve().parent.parent / "client-tools"
DEFAULT_PORT = 12222
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "dongshengniubi666"

# 本地文件 -> 远端路径
FILES: List[Tuple[str, str]] = [
    (str(CLIENT_TOOLS_DIR / "plugins" / "rgw_plugin.py"), "/root/main/plugins/rgw.py"),
    (str(CLIENT_TOOLS_DIR / "plugins" / "h3c_plugin.py"), "/root/main/plugins/h3c.py"),
    (str(CLIENT_TOOLS_DIR / "config_web.py"), "/root/main/tools/config_web.py"),
    (str(CLIENT_TOOLS_DIR / "scan_config.json"), "/root/scan_config.json"),
]

UNIT_NAME = "config-web.service"
UNIT_PATH = f"/etc/systemd/system/{UNIT_NAME}"
UNIT_BODY = """[Unit]
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
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# 传输后端
# ---------------------------------------------------------------------------

class SshBackend:
    """统一 put / run 接口。"""

    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.mode = ""
        self._paramiko = None
        self._detect()

    def _detect(self) -> None:
        # 1) paramiko（跨平台首选）
        try:
            import paramiko  # type: ignore
            self._paramiko = paramiko
            self.mode = "paramiko"
            return
        except ImportError:
            pass

        # 2) sshpass + openssh
        if have("sshpass") and have("ssh") and have("scp"):
            self.mode = "sshpass"
            return

        # 3) Windows plink
        if have("plink"):
            self.mode = "plink"
            return

        # 4) 尝试安装 paramiko
        log("未找到 SSH 客户端，尝试安装 paramiko ...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "paramiko"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            try:
                import paramiko  # type: ignore
                import importlib
                importlib.reload(paramiko)
                self._paramiko = paramiko
                self.mode = "paramiko"
                return
            except ImportError:
                pass

        die(
            "无法建立 SSH 通道。请任选其一:\n"
            "  - pip install paramiko\n"
            "  - macOS: brew install sshpass\n"
            "  - Windows: 安装 PuTTY(plink) 或 Git for Windows\n"
            f"  pip 输出: {r.stderr[-400:] if r.stderr else r.stdout[-400:]}"
        )

    def run(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        log(f"  $ {command}")
        if self.mode == "paramiko":
            return self._run_paramiko(command, timeout)
        if self.mode == "sshpass":
            env = os.environ.copy()
            env["SSHPASS"] = self.password
            cmd = [
                "sshpass", "-e", "ssh",
                "-p", str(self.port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "PreferredAuthentications=password",
                "-o", "PubkeyAuthentication=no",
                "-o", "ConnectTimeout=10",
                f"{self.user}@{self.host}",
                command,
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        if self.mode == "plink":
            cmd = [
                "plink", "-ssh", "-P", str(self.port),
                "-pw", self.password,
                "-batch",
                f"{self.user}@{self.host}",
                command,
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        die(f"unknown mode {self.mode}")
        return 1, "", "unknown"

    def put(self, local: Path, remote: str, timeout: int = 60) -> None:
        if not local.exists():
            die(f"本地文件不存在: {local}")
        log(f"  PUT {local.name} -> {remote}")
        if self.mode == "paramiko":
            self._put_paramiko(local, remote)
            return
        if self.mode == "sshpass":
            env = os.environ.copy()
            env["SSHPASS"] = self.password
            # 目标目录
            dir_remote = remote.rsplit("/", 1)[0]
            self.run(f"mkdir -p {dir_remote}")
            cmd = [
                "sshpass", "-e", "scp",
                "-O", "-P", str(self.port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "PreferredAuthentications=password",
                "-o", "PubkeyAuthentication=no",
                str(local),
                f"{self.user}@{self.host}:{remote}",
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
            if p.returncode != 0:
                die(f"scp 失败: {p.stderr}")
            return
        if self.mode == "plink":
            # pscp 通常随 PuTTY 安装
            if have("pscp"):
                cmd = [
                    "pscp", "-P", str(self.port), "-pw", self.password,
                    "-batch", str(local), f"{self.user}@{self.host}:{remote}",
                ]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if p.returncode != 0:
                    die(f"pscp 失败: {p.stderr}")
                return
            # 回退: 经 stdin base64
            import base64
            data = base64.b64encode(local.read_bytes()).decode("ascii")
            dir_remote = remote.rsplit("/", 1)[0]
            self.run(f"mkdir -p {dir_remote}")
            # 分块避免超长命令行
            self.run(f"rm -f {remote}.b64")
            for i in range(0, len(data), 40000):
                chunk = data[i:i + 40000]
                self.run(f"printf %s '{chunk}' >> {remote}.b64")
            rc, out, err = self.run(f"base64 -d {remote}.b64 > {remote} && rm -f {remote}.b64")
            if rc != 0:
                die(f"写入失败: {err or out}")
            return
        die(f"unknown mode {self.mode}")

    def _run_paramiko(self, command: str, timeout: int) -> Tuple[int, str, str]:
        assert self._paramiko is not None
        client = self._paramiko.SSHClient()
        client.set_missing_host_key_policy(self._paramiko.AutoAddPolicy())
        try:
            client.connect(
                self.host, port=self.port, username=self.user,
                password=self.password, timeout=10,
                allow_agent=False, look_for_keys=False,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            rc = stdout.channel.recv_exit_status()
            return rc, out, err
        finally:
            client.close()

    def _put_paramiko(self, local: Path, remote: str) -> None:
        assert self._paramiko is not None
        client = self._paramiko.SSHClient()
        client.set_missing_host_key_policy(self._paramiko.AutoAddPolicy())
        try:
            client.connect(
                self.host, port=self.port, username=self.user,
                password=self.password, timeout=10,
                allow_agent=False, look_for_keys=False,
            )
            sftp = client.open_sftp()
            try:
                dir_remote = remote.rsplit("/", 1)[0]
                try:
                    sftp.stat(dir_remote)
                except IOError:
                    # 递归创建
                    parts = dir_remote.strip("/").split("/")
                    cur = ""
                    for p in parts:
                        cur += "/" + p
                        try:
                            sftp.stat(cur)
                        except IOError:
                            sftp.mkdir(cur)
                sftp.put(str(local), remote)
            finally:
                sftp.close()
        finally:
            client.close()


# ---------------------------------------------------------------------------
# 部署
# ---------------------------------------------------------------------------

def deploy(ip: str, port: int, user: str, password: str,
           skip_config: bool = False, no_service: bool = False) -> None:
    backend = SshBackend(ip, port, user, password)
    log(f"SSH 后端: {backend.mode}  -> {user}@{ip}:{port}")

    # 连通性
    rc, out, err = backend.run("hostname && uname -a | head -1")
    if rc != 0:
        die(f"SSH 连接失败: {err or out}")
    log(f"设备: {out.strip()}")

    # 远端目录
    rc, _, err = backend.run(
        "mkdir -p /root/main/plugins /root/main/tools /root/main/state /root/logs"
    )
    if rc != 0:
        die(f"创建目录失败: {err}")

    # 备份已有 scan_config
    if not skip_config:
        backend.run(
            "test -f /root/scan_config.json && "
            "cp -a /root/scan_config.json /root/scan_config.json.bak.deploy_$(date +%s) || true"
        )

    # 逐个推送
    for local, remote in FILES:
        if skip_config and remote.endswith("scan_config.json"):
            log(f"  SKIP {remote}")
            continue
        local_path = Path(local)
        if not local_path.exists():
            if remote.endswith("scan_config.json"):
                log(f"  SKIP {remote}（本地不存在）")
                continue
            die(f"缺少本地文件: {local_path}")
        backend.put(local_path, remote)

    # 写 systemd unit（临时文件再 put）
    if not no_service:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".service", delete=False, encoding="utf-8"
        ) as f:
            f.write(UNIT_BODY)
            tmp = Path(f.name)
        try:
            backend.put(tmp, UNIT_PATH)
        finally:
            tmp.unlink(missing_ok=True)

    # 校验 + 服务
    log("远端校验 ...")
    rc, out, err = backend.run(
        "python3 -m py_compile /root/main/tools/config_web.py "
        "/root/main/plugins/rgw.py /root/main/plugins/h3c.py && echo COMPILE_OK"
    )
    if rc != 0 or "COMPILE_OK" not in out:
        die(f"远端编译失败:\n{out}\n{err}")
    log("COMPILE_OK")

    if not no_service:
        log("配置 systemd config-web.service ...")
        cmds = [
            "systemctl daemon-reload",
            "systemctl enable config-web.service",
            "systemctl restart config-web.service",
            "sleep 1",
            "systemctl is-active config-web.service",
            "curl -sS --max-time 3 http://127.0.0.1:18080/healthz || true",
            # 确保采集 cron 存在
            "(crontab -l 2>/dev/null | grep -q 'main/main.py' || "
            "(crontab -l 2>/dev/null; echo '"
            "*/3 * * * * /usr/bin/python3 /root/main/main.py > /root/logs/cron.log 2>&1"
            "') | crontab -)",
            "crontab -l | tail -3",
        ]
        script = " && ".join(f"({c})" for c in cmds)
        # 上面写法会吞输出，改为分步
        for c in cmds:
            rc, out, err = backend.run(c)
            if out.strip():
                log(f"  {out.strip()}")
            if rc != 0 and "is-active" not in c and "healthz" not in c and "crontab" not in c:
                # healthz/crontab 容错
                if "grep -q" in c:
                    pass
                else:
                    log(f"  warn rc={rc} {err.strip()[:200]}")

        rc, out, err = backend.run("systemctl is-active config-web.service")
        active = out.strip()
        log(f"config-web.service => {active}")
        if active != "active":
            rc, out, err = backend.run(
                "journalctl -u config-web.service -n 30 --no-pager || true"
            )
            log(out)
            die("config-web 未进入 active")

    log("")
    log("=" * 56)
    log("部署成功")
    log(f"  设备:     {ip}:{port}")
    log(f"  插件:     /root/main/plugins/rgw.py, h3c.py")
    log(f"  配置页:   /root/main/tools/config_web.py")
    if not skip_config:
        log(f"  配置:     /root/scan_config.json")
    log(f"  服务:     {UNIT_PATH}")
    log(f"  打开:     http://{ip}:18080")
    log("=" * 56)


# ---------------------------------------------------------------------------
# 输入：tkinter 弹窗 -> macOS osascript -> 终端交互（三级回退）
# ---------------------------------------------------------------------------

def _pack(ip: str, port: int, user: str, password: str,
          skip_config: bool, no_service: bool):
    return (ip, port, user, password, skip_config, no_service)


def ask_tkinter() -> Optional[tuple]:
    """有 tkinter 时用图形弹窗。返回 None=用户取消；抛 ImportError=无 tkinter。"""
    import tkinter as tk
    from tkinter import ttk, messagebox

    result: dict = {}
    root = tk.Tk()
    root.title("DsFlexProbe 一键部署")
    root.resizable(False, False)
    root.update_idletasks()
    w, h = 440, 340
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="部署到探针硬件", font=("", 12, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    fields = [
        ("设备 IP *", "ip", ""),
        ("SSH 端口", "port", str(DEFAULT_PORT)),
        ("用户名", "user", DEFAULT_USER),
        ("密码", "password", DEFAULT_PASSWORD),
    ]
    entries = {}
    for i, (label, key, default) in enumerate(fields, start=1):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 8))
        show = "*" if key == "password" else ""
        e = ttk.Entry(frm, width=36, show=show)
        e.insert(0, default)
        e.grid(row=i, column=1, sticky="ew", pady=4)
        entries[key] = e

    skip_cfg = tk.BooleanVar(value=False)
    no_svc = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        frm, text="跳过 scan_config.json（只推插件/配置页）", variable=skip_cfg
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Checkbutton(
        frm, text="只推文件，不安装/重启服务", variable=no_svc
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=2)

    ttk.Label(
        frm,
        text=f"默认端口 {DEFAULT_PORT}；设备路径 /root/main/... 随部署固定，IP 按当前网络填",
        foreground="#666",
        wraplength=400,
    ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def on_ok() -> None:
        ip = entries["ip"].get().strip()
        if not ip:
            messagebox.showerror("错误", "请填写设备 IP")
            return
        try:
            port = int(entries["port"].get().strip() or DEFAULT_PORT)
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字")
            return
        user = entries["user"].get().strip() or DEFAULT_USER
        password = entries["password"].get()
        if not password:
            messagebox.showerror("错误", "请填写 SSH 密码")
            return
        result["ok"] = True
        result["val"] = _pack(
            ip, port, user, password, bool(skip_cfg.get()), bool(no_svc.get())
        )
        root.destroy()

    def on_cancel() -> None:
        result["ok"] = False
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))
    ttk.Button(btns, text="取消", command=on_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(btns, text="开始部署", command=on_ok).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.bind("<Return>", lambda e: on_ok())
    entries["ip"].focus_set()
    root.mainloop()
    if not result.get("ok"):
        return None
    return result["val"]


def ask_osascript() -> Optional[tuple]:
    """macOS 原生弹窗（不依赖 tkinter）。取消返回 None。"""
    if platform.system() != "Darwin":
        raise RuntimeError("osascript only on macOS")
    if not have("osascript"):
        raise RuntimeError("osascript not found")

    script = f'''
set ipAddr to text returned of (display dialog "设备 IP *" default answer "" with title "DsFlexProbe 一键部署")
if ipAddr is "" then error "取消"
set sshPort to text returned of (display dialog "SSH 端口" default answer "{DEFAULT_PORT}" with title "DsFlexProbe 一键部署")
set sshUser to text returned of (display dialog "用户名" default answer "{DEFAULT_USER}" with title "DsFlexProbe 一键部署")
set sshPass to text returned of (display dialog "密码" default answer "{DEFAULT_PASSWORD}" with title "DsFlexProbe 一键部署" with hidden answer)
set c1 to button returned of (display dialog "部署选项" buttons {{"取消", "跳过配置+服务", "只跳过配置", "完整部署"}} default button "完整部署" with title "DsFlexProbe 一键部署")
set skipCfg to false
set noSvc to false
if c1 is "取消" then error "取消"
if c1 is "跳过配置+服务" then
    set skipCfg to true
    set noSvc to true
else if c1 is "只跳过配置" then
    set skipCfg to true
end if
return ipAddr & "\t" & sshPort & "\t" & sshUser & "\t" & sshPass & "\t" & (skipCfg as text) & "\t" & (noSvc as text)
'''
    p = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        if "用户被取消" in err or "user canceled" in err.lower() or "取消" in err:
            return None
        raise RuntimeError(err or "osascript failed")
    line = (p.stdout or "").strip()
    parts = line.split("\t")
    if len(parts) < 6:
        raise RuntimeError(f"osascript 输出异常: {line!r}")
    ip, port_s, user, password, skip_s, nos_s = parts[:6]
    if not ip.strip():
        return None
    try:
        port = int(port_s.strip() or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    return _pack(
        ip.strip(), port, user.strip() or DEFAULT_USER, password,
        skip_s.lower() in ("true", "1", "yes"),
        nos_s.lower() in ("true", "1", "yes"),
    )


def ask_terminal() -> Optional[tuple]:
    """终端交互输入（.command/.bat 双击必有 TTY）。"""
    print("-" * 56)
    print("DsFlexProbe 一键部署 — 终端输入")
    print(f"默认端口 {DEFAULT_PORT}，用户 {DEFAULT_USER}；直接回车用默认值")
    print("-" * 56)
    try:
        ip = input("设备 IP *: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not ip:
        print("IP 不能为空")
        return None
    try:
        port_s = input(f"SSH 端口 [{DEFAULT_PORT}]: ").strip()
        user = input(f"用户名 [{DEFAULT_USER}]: ").strip()
        password = input(f"密码 [{DEFAULT_PASSWORD}]: ").strip()
        skip_s = input("跳过 scan_config.json? [y/N]: ").strip().lower()
        no_s = input("只推文件、不装服务? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    try:
        port = int(port_s or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    return _pack(
        ip, port, user or DEFAULT_USER, password or DEFAULT_PASSWORD,
        skip_s in ("y", "yes"),
        no_s in ("y", "yes"),
    )


def ask_any(prefer: str = "auto") -> Optional[tuple]:
    """弹窗优先；失败自动回退。None=用户取消。

    prefer:
      auto     - macOS 优先系统弹窗（osascript），其它平台 tkinter
      native   - 只用 osascript（macOS）
      tk       - 强制 tkinter
      terminal - 强制终端
    """
    order: list[str]
    if prefer == "terminal":
        order = ["terminal"]
    elif prefer == "native":
        order = ["osascript", "terminal"]
    elif prefer == "tk":
        order = ["tkinter", "osascript", "terminal"]
    elif platform.system() == "Darwin":
        # macOS 双击：系统弹窗最稳；Tk 在部分 Python 上空白
        order = ["osascript", "tkinter", "terminal"]
    else:
        order = ["tkinter", "terminal"]

    tk_fail = False
    for step in order:
        if step == "tkinter":
            if tk_fail:
                continue
            try:
                return ask_tkinter()
            except ImportError as e:
                tk_fail = True
                log(f"tkinter 不可用（{e}）")
            except Exception as e:
                tk_fail = True
                log(f"tkinter 弹窗失败（{e}）")
            continue
        if step == "osascript":
            try:
                val = ask_osascript()
                log("已使用系统弹窗 (osascript)")
                return val
            except Exception as e:
                log(f"osascript 不可用（{e}）")
            continue
        if step == "terminal":
            if sys.stdin is not None and sys.stdin.isatty():
                log("回退到终端输入 ...")
                return ask_terminal()
            log("无 TTY，无法终端输入")
            continue

    die(
        "无法获取输入：图形弹窗不可用，且非交互终端。\n"
        "  可选:\n"
        "  - 终端运行: python3 deploy_device.py --ui terminal\n"
        "  - 命令行:   python3 deploy_device.py --ip <设备IP> --yes"
    )
    return None


def main() -> None:
    p = argparse.ArgumentParser(
        description="一键部署采集插件/配置页/服务到探针硬件（macOS/Windows）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--ip", help="设备 IP（不传则弹窗/终端输入）")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD, help="SSH 密码")
    p.add_argument("--skip-config", action="store_true", help="不推送 scan_config.json")
    p.add_argument("--no-service", action="store_true", help="不安装/重启 systemd 服务")
    p.add_argument("--yes", action="store_true", help="跳过部署前确认")
    p.add_argument(
        "--ui",
        choices=("auto", "native", "tk", "terminal"),
        default="auto",
        help="输入界面: auto=系统弹窗优先, native=osascript, tk=tkinter, terminal=终端",
    )
    args = p.parse_args()

    log(f"平台: {platform.system()} {platform.machine()}  Python {platform.python_version()}  exe={sys.executable}")

    ip, port, user, password, skip_config, no_service = (
        args.ip, args.port, args.user, args.password,
        args.skip_config, args.no_service,
    )
    from_gui = False

    if not args.ip:
        gui = ask_any(prefer=args.ui)
        if gui is None:
            log("已取消")
            sys.exit(0)
        ip, port, user, password, skip_config, no_service = gui
        from_gui = True

    if not from_gui and not args.yes:
        log(f"将部署到 {user}@{ip}:{port}  skip_config={skip_config} no_service={no_service}")
        try:
            ans = input("确认继续? [y/N] ").strip().lower()
        except EOFError:
            ans = "y"
        if ans not in ("y", "yes"):
            log("已取消")
            sys.exit(0)

    if not ip:
        die("未提供设备 IP")

    try:
        deploy(ip, port, user, password, skip_config=skip_config, no_service=no_service)
    except SystemExit:
        raise
    except Exception as e:
        die(f"部署异常: {e}")


if __name__ == "__main__":
    main()
