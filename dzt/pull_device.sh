#!/usr/bin/env bash
# =============================================================================
# pull_device.sh — 从探针硬件拉取最新脚本/配置到本地（只读同步）
# =============================================================================
#
# 【作用】
#   1. 整包备份到本地: pw/device_backup_<时间戳>/
#   2. 覆盖本地工作副本: rgw_plugin.py / h3c_plugin.py / config_web.py / scan_config.json
#   3. 生成 MANIFEST.txt（文件清单 + targets + 部署提示）
#
# 【依赖】
#   bash, sshpass, scp, python3, ssh
#   macOS: brew install sshpass  （或已有）
#
# 【用法】
#   cd ".../pw"
#   ./pull_device.sh                         # 默认 192.168.200.100:12222
#   ./pull_device.sh 192.168.200.100 12222   # 指定 IP/端口
#   SSHPASS='xxx' ./pull_device.sh           # 临时改 SSH 密码
#   ./pull_device.sh -h | --help             # 帮助
#
# 【硬件端默认连接】
#   Host: 192.168.200.100   Port: 12222   User: root
#   Password 环境变量: SSHPASS（脚本默认 dongshengniubi666，可被外部覆盖）
#   说明: 换路由后探针可能 DHCP 变更；旧地址 192.168.101.83 已不用。
#         若连不上，先在新网段扫 12222 端口确认当前 IP。
#
# 【硬件端会被拉取的路径】
#   /root/main/plugins/*.py              插件（rgw/h3c/xiaomi/xiaoyi...）
#   /root/main/tools/config_web.py       配置页
#   /root/scan_config.json               当前采集配置
#   /root/scan_config.json.bak.*         配置历史备份
#   /etc/systemd/system/config-web.service
#   /root/main/state/last_run.json       调度状态
#   crontab -l                           采集定时任务
#   systemctl cat config-web.service     服务单元内容
#
# 【本地输出】
#   pw/device_backup_<时间戳>/
#     plugins/   全部 *.py 插件
#     tools/     config_web.py
#     config/    scan_config.json + bak + crontab + systemd + last_run
#     MANIFEST.txt
#   同时覆盖本地工作副本（与设备 md5 一致时即最新）:
#     pw/rgw_plugin.py  pw/h3c_plugin.py  pw/config_web.py  pw/scan_config.json
#
# 【反向部署：本地改完推回硬件】
#   export SSHPASS='dongshengniubi666'
#   SSH='sshpass -e ssh -p 12222 -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no'
#   SCP='sshpass -e scp -O -P 12222 -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no'
#   HOST=root@192.168.200.100
#
#   # 配置页
#   $SCP pw/config_web.py $HOST:/root/main/tools/config_web.py
#   $SSH $HOST 'python3 -m py_compile /root/main/tools/config_web.py && systemctl restart config-web.service'
#
#   # 插件（文件名 = 品牌 brand）
#   $SCP pw/rgw_plugin.py $HOST:/root/main/plugins/rgw.py
#   $SCP pw/h3c_plugin.py $HOST:/root/main/plugins/h3c.py
#   # 插件即时生效（cron 下一轮会加载），无需重启 config-web
#
#   # 只推配置（一般用页面「验证并保存」写入，不建议手改硬推）
#   $SCP pw/scan_config.json $HOST:/root/scan_config.json
#
# 【相关服务（硬件端）】
#   config-web.service   配置页     端口 18080   enable/start/restart 见 config_web.py 头注释
#   crontab              采集调度   */3 * * * * /usr/bin/python3 /root/main/main.py > /root/logs/cron.log 2>&1
#   查看:
#     systemctl status config-web.service
#     systemctl cat config-web.service
#     crontab -l
#     curl -sS http://127.0.0.1:18080/healthz
#
# 【本脚本只读，不修改硬件任何文件。】
# =============================================================================

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,70p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

HOST="${1:-192.168.200.100}"
PORT="${2:-12222}"
SSHPASS="${SSHPASS:-dongshengniubi666}"
export SSHPASS

LOCAL="$(cd "$(dirname "$0")" && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
BK="$LOCAL/device_backup_$STAMP"
mkdir -p "$BK/plugins" "$BK/tools" "$BK/config"

SSH_OPTS=(-o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no)
SCP=(sshpass -e scp -O -P "$PORT" "${SSH_OPTS[@]}")
SSH=(sshpass -e ssh -p "$PORT" "${SSH_OPTS[@]}")

echo "Pull from ${HOST}:${PORT} -> $BK"

"${SSH[@]}" "root@$HOST" 'hostname; ls /root/main/plugins/*.py; systemctl is-active config-web.service'

"${SCP[@]}" "root@${HOST}:/root/main/plugins/*.py" "$BK/plugins/"
"${SCP[@]}" "root@${HOST}:/root/main/tools/config_web.py" "$BK/tools/"
"${SCP[@]}" "root@${HOST}:/root/scan_config.json" "$BK/config/"
"${SCP[@]}" "root@${HOST}:/etc/systemd/system/config-web.service" "$BK/config/" || true
"${SCP[@]}" "root@${HOST}:/root/main/state/last_run.json" "$BK/config/" || true

# scan_config 历史备份
while IFS= read -r f; do
  [ -n "$f" ] || continue
  "${SCP[@]}" "root@${HOST}:$f" "$BK/config/" || true
done < <("${SSH[@]}" "root@$HOST" 'ls /root/scan_config.json.bak.* 2>/dev/null' || true)

"${SSH[@]}" "root@$HOST" 'crontab -l' > "$BK/config/crontab.txt" || true
"${SSH[@]}" "root@$HOST" 'systemctl cat config-web.service' > "$BK/config/config-web.service.txt" || true

# 覆盖本地工作副本
"${SCP[@]}" "root@${HOST}:/root/main/plugins/rgw.py" "$LOCAL/rgw_plugin.py"
"${SCP[@]}" "root@${HOST}:/root/main/plugins/h3c.py" "$LOCAL/h3c_plugin.py"
"${SCP[@]}" "root@${HOST}:/root/main/tools/config_web.py" "$LOCAL/config_web.py"
"${SCP[@]}" "root@${HOST}:/root/scan_config.json" "$LOCAL/scan_config.json"

python3 - <<PY
from pathlib import Path
import json, datetime
bk = Path(r"$BK")
files = sorted(str(p.relative_to(bk)) for p in bk.rglob("*") if p.is_file())
cfg = json.loads((bk/"config/scan_config.json").read_text())
targets = cfg.get("targets") or []
lines = [
  f"Pulled from ${HOST}:${PORT} at {datetime.datetime.now():%F %T}",
  "",
  "Contents:",
  *files,
  "",
  f"scan_config targets ({len(targets)}):",
]
for t in targets:
    ep = t.get("endpoint") or {}
    lines.append(f"  - {t.get('id')} brand={t.get('brand')} host={ep.get('host')} path={ep.get('device_path')}")
lines += ["", "Local working copies:", "  rgw_plugin.py  h3c_plugin.py  config_web.py  scan_config.json"]
lines += ["", "Deploy back to device:", "  See header of pull_device.sh or config_web.py"]
(bk/"MANIFEST.txt").write_text("\n".join(lines) + "\n")
print("files:", len(files))
print("targets:", len(targets))
for t in targets:
    print(" ", t.get("id"), t.get("brand"), (t.get("endpoint") or {}).get("host"))
PY

echo "Done. Backup: $BK"
echo "Working copies updated under $LOCAL"
