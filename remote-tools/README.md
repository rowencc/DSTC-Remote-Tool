# DSTC-Remote-Tool

大正通设备远程运维工具集：基于 frp 内网穿透，实现 500+ 设备规模的远程维护、脚本下发、一键安装/卸载、状态监控。

- **服务端**：公网服务器 `111.198.61.41`（frps v0.71.0, Docker, host network mode）
- **客户端**：探针设备（Cherry Hi3516CV600, ARM64），运行 frpc + 采集插件
- **数据流**：设备 → frpc → frps → 外部运维方；脚本下发 → HTTP 8090 → 设备

---

## 目录结构

```
remote-tools/
├── README.md                          本文件
├── server-deploy/                     服务端部署脚本（在 frps 服务器上运行）
│   ├── remote_deploy.sh               一键部署/升级设备（通过 frp 隧道）
│   └── files/                         frpc 二进制下载缓存（remote-client，不入库）
│       └── .gitkeep
├── client-deploy/                     客户端部署脚本（在探针设备上 curl|bash 执行）
│   ├── device_install.sh              一键安装 frpc 客户端
│   └── device_uninstall.sh            一键卸载 frpc 客户端
├── client-tools/                      客户端工具（部署到探针设备上运行）
│   ├── config_web.py                  采集配置 Web UI（端口 18080）
│   ├── plugins/                       采集插件（按品牌）
│   │   ├── rgw_plugin.py              4G CPE 采集（Mongoose + xml_action.cgi）
│   │   └── h3c_plugin.py              H3C GR/ICG 系列路由器采集
│   └── scan_config.json               采集目标配置
└── other/                             其他工具
    ├── http_server.py                 服务端 HTTP 文件服务（端口 8090，下发 frpc/脚本）
    ├── frp_monitor.py                 服务端监控页面（端口 8091，设备状态）
    ├── deploy_device.py               开发机 → 探针：本地 SSH 一键部署（macOS/Win）
    └── pull_device.sh                 开发机 ← 探针：拉取最新脚本/配置到本地
```

---

## 快速命令

```bash
# 设备端一键安装 frpc（在探针设备上执行）
curl -fsSL http://111.198.61.41:8090/device_install.sh | bash

# 设备端一键卸载 frpc（默认自动确认，加 --confirm 手动确认）
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash

# 服务端一键部署设备（在 frps 服务器上执行）
remote-deploy                            # 自动分配端口
remote-deploy --device-id 7010           # 指定端口
remote-deploy --device-id 7010 --skip-frpc  # 只更新插件/配置，不重启 frpc
remote-deploy --list                     # 列出已用/可用端口

# 开发机本地部署到探针（macOS）
cd other
python3 deploy_device.py                 # 交互式弹窗输入 IP
python3 deploy_device.py --ip 192.168.200.100

# 开发机从探针拉取（macOS）
cd other
./pull_device.sh                         # 默认 192.168.200.100:12222

# 访问监控页面
http://111.198.61.41:8091
```

---

## 部署流程

### 新设备首次部署

```
探针设备                              frps 服务器 (111.198.61.41)
   |                                         |
   | curl /device_install.sh | bash          |
   +---------------------------------------->| [1] 安装 frpc
   |  (frpc 建立反向隧道)                    |
   |                                         | [2] remote-deploy --device-id 7010
   |  <----- scp 插件/配置/frpc.ini --------+
   |                                         |
   |  [3] 访问 http://111.198.61.41:7011 打开配置页
   |  [4] 访问 http://111.198.61.41:7010 SSH 调试
   |
   | 卸载：curl /device_uninstall.sh | bash
```

### 老设备升级

```bash
# 服务器上执行
remote-deploy --device-id 7010

# 访问监控页确认在线
http://111.198.61.41:8091
```

---

## 服务端脚本

### `server-deploy/remote_deploy.sh`

通过 frp 隧道 SSH 到设备，下发插件、配置、systemd 服务、frpc 客户端。

**在 frps 服务器上部署：**

```bash
# 部署到 /opt/remote_deploy/
sudo mkdir -p /opt/remote_deploy
sudo cp -r /path/to/remote-tools/server-deploy/. /opt/remote_deploy/
sudo cp -r /path/to/remote-tools/client-deploy/ /opt/remote_deploy/
sudo cp -r /path/to/remote-tools/client-tools/ /opt/remote_deploy/

# 下载 frpc 二进制到 files/（一次性）
cd /opt/remote_deploy/server-deploy/files
wget https://github.com/fatedier/frp/releases/download/v0.51.3/frp_0.51.3_linux_arm64.tar.gz
tar xzf frp_0.51.3_linux_arm64.tar.gz
mv frp_0.51.3_linux_arm64/frpc remote-client
chmod +x remote-client

# 快捷命令
sudo ln -sf /opt/remote_deploy/server-deploy/remote_deploy.sh /usr/local/bin/remote-deploy
```

**参数：**

| 参数 | 说明 |
|------|------|
| `--device-id N` | 指定设备 SSH 端口（默认 7010） |
| `--skip-frpc` | 跳过 frpc 客户端下发（仅更新插件/配置） |
| `--list` | 列出已用端口和下一个可用端口 |
| `--no-auto-port` | 关闭端口自动分配，手动输入 |

**部署内容（设备端）：**

| 远端路径 | 来源 | 说明 |
|---------|------|------|
| `/root/main/plugins/rgw.py` | `client-tools/plugins/rgw_plugin.py` | 4G CPE 采集插件 |
| `/root/main/plugins/h3c.py` | `client-tools/plugins/h3c_plugin.py` | H3C 路由器采集插件 |
| `/root/main/tools/config_web.py` | `client-tools/config_web.py` | 配置 Web UI |
| `/root/scan_config.json` | `client-tools/scan_config.json` | 采集配置（部署前自动备份） |
| `/etc/systemd/system/config-web.service` | 脚本内嵌 | 配置页 systemd 服务 |
| `/opt/remote/remote-client` | `server-deploy/files/remote-client` | frpc 二进制 |
| `/etc/remote/client.ini` | 脚本内嵌（动态端口） | frpc 配置 |
| `/etc/systemd/system/remote-client.service` | 脚本内嵌 | frpc systemd 服务 |

---

## 客户端部署脚本

### `client-deploy/device_install.sh`

在探针设备上 `curl | bash` 一键安装 frpc 客户端，使其连接到 frps 服务器。

```bash
# 一键安装
curl -fsSL http://111.198.61.41:8090/device_install.sh | bash

# 或下载后执行
curl -fsSL http://111.198.61.41:8090/device_install.sh -o device_install.sh
bash device_install.sh
```

**关键配置**（脚本顶部）：

```bash
FRPS_SERVER="111.198.61.41"
FRPS_PORT="7080"
FRPS_TOKEN="60d8a83c544e6168db"
DEVICE_SSH_PORT="7010"      # 分配的 SSH 端口
DEVICE_WEB_PORT="7011"      # 分配的 Web 端口
LOCAL_SSH_PORT="12222"      # 设备本地 SSH
LOCAL_WEB_PORT="18080"      # 设备本地配置页
CLIENT_VERSION="0.51.3"
CLIENT_ARCH="arm64"
```

**安装内容：**

- `/opt/remote/remote-client` — frpc 二进制
- `/etc/remote/client.ini` — frpc 配置
- `/etc/systemd/system/remote-client.service` — systemd 服务

### `client-deploy/device_uninstall.sh`

**默认自动确认，无需交互**（因为 `curl | bash` 无法通过管道交互）。加 `--confirm` 可手动确认。

```bash
# 一键卸载（默认自动确认）
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash

# 手动确认模式
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash -s -- --confirm
```

**卸载内容：**

- 停止并禁用 frpc 服务
- 删除 `/opt/remote/remote-client`、`/etc/remote/client.ini`、`/var/log/remote/`
- 删除 systemd 服务文件

---

## 客户端工具

### `client-tools/config_web.py`

采集配置 Web UI。浏览器填写目标路由 → 分步验证「采集 + 上报」→ 全部成功才写入 `scan_config.json`。

**在探针设备上运行：**

- 部署路径：`/root/main/tools/config_web.py`
- systemd 服务：`config-web.service`
- 本地端口：`18080`
- 通过 frp 隧道暴露：`http://111.198.61.41:7011`

**本地开发运行：**

```bash
cd client-tools
SCAN_CONFIG=./scan_config.json \
PLUGINS_DIR=./plugins \
CONFIG_WEB_PORT=18080 \
python3 config_web.py
```

### `client-tools/plugins/`

采集插件按品牌命名：`{brand}.py`。品牌下拉值即为文件名。

| 插件 | 品牌 | 说明 |
|-----|------|------|
| `rgw_plugin.py` | `rgw` | 4G CPE / MIFI（AR5510 等，Mongoose + xml_action.cgi） |
| `h3c_plugin.py` | `h3c` | H3C GR/ICG 系列路由器（GR2200 等，Playwright codegen 录制） |

部署到设备：`/root/main/plugins/{brand}.py`

### `client-tools/scan_config.json`

采集目标配置。`deploy_device.py` 和 `remote_deploy.sh` 部署前会自动备份为 `scan_config.json.bak.<ts>`。

---

## 其他工具

### `other/http_server.py`

服务端 HTTP 文件服务，端口 `8090`。设备通过此服务下载 frpc 二进制和安装/卸载脚本。

**部署在 frps 服务器上：**

```bash
sudo cp other/http_server.py /opt/remote_deploy/
# systemd unit: http-server.service
# 端口：8090（iptables 必须放行）
```

**路径映射：**

| URL | 实际文件 |
|-----|---------|
| `/frpc` | `/opt/remote_deploy/server-deploy/files/remote-client` |
| `/remote-client` | `/opt/remote_deploy/server-deploy/files/remote-client` |
| `/device_install.sh` | `/opt/remote_deploy/client-deploy/device_install.sh` |
| `/device_uninstall.sh` | `/opt/remote_deploy/client-deploy/device_uninstall.sh` |

### `other/frp_monitor.py`

设备监控页面，端口 `8091`。调用 frps API v2 (`/api/v2/clients` + `/api/v2/proxies`)，实时显示在线设备、SSH/Web 端口、SSH 命令复制、Web 直达按钮。30 秒自动刷新。

**部署在 frps 服务器上：**

```bash
sudo cp other/frp_monitor.py /opt/remote_deploy/
# systemd unit: frp-monitor.service
# 端口：8091（iptables 必须放行）
# frps API auth: master:Rowen@3328
```

访问地址：`http://111.198.61.41:8091`

### `other/deploy_device.py`

开发机 → 探针设备的本地部署工具（macOS/Windows）。**不走 frp**，直接 SSH 到探针内网 IP（如 `192.168.200.100:12222`）下发插件/配置页/systemd 服务。

```bash
cd other
python3 deploy_device.py                         # 交互式弹窗输入 IP
python3 deploy_device.py --ip 192.168.200.100    # 命令行指定
python3 deploy_device.py --skip-config           # 跳过 scan_config.json
python3 deploy_device.py --ui native|tk|terminal # 强制 UI 后端
```

### `other/pull_device.sh`

开发机 ← 探针设备的只读拉取工具。整包备份到 `other/device_backup_<时间戳>/`，同时覆盖 `client-tools/` 下的本地工作副本。

```bash
cd other
./pull_device.sh                                  # 默认 192.168.200.100:12222
./pull_device.sh 192.168.200.100 12222            # 指定 IP/端口
SSHPASS='newpassword' ./pull_device.sh            # 覆盖 SSH 密码
```

---

## 端口分配

| 端口 | 用途 | 备注 |
|-----|------|------|
| 7080 | frps 主端口（TCP） | 保留 |
| 7081 | frps 主端口（备用） | 保留 |
| 7580 | frps Dashboard | 保留 |
| 7010–7999 | 设备端口 | 每设备 +2：SSH=7010, Web=7011 |
| 8090 | HTTP 文件服务 | 设备下载脚本/二进制 |
| 8091 | 设备监控页面 | 运维查看 |

**示例分配：**

| 设备 | SSH | Web |
|-----|-----|-----|
| 1 | 7010 | 7011 |
| 2 | 7012 | 7013 |
| 3 | 7014 | 7015 |

---

## 外部访问

部署完成后，通过以下地址访问设备：

```bash
# SSH（通过 frp 隧道）
ssh -p 7010 root@111.198.61.41

# 配置页（通过 frp 隧道）
http://111.198.61.41:7011
```

---

## 故障排查

### SSH 连接失败

```bash
# 设备上检查 frpc 状态
systemctl status remote-client.service
journalctl -u remote-client.service -n 50 --no-pager

# 测试隧道
ssh -p 7010 root@111.198.61.41
```

### 服务未启动（配置页 18080）

```bash
systemctl status config-web.service
journalctl -u config-web.service -n 50 --no-pager
systemctl restart config-web.service
```

### HTTP 文件服务问题

```bash
systemctl status http-server.service
iptables -L INPUT -n | grep 8090
systemctl restart http-server.service
```

### 监控页面问题

```bash
systemctl status frp-monitor.service
iptables -L INPUT -n | grep 8091
journalctl -u frp-monitor.service -f
systemctl restart frp-monitor.service
```

### 文件部署失败

```bash
# 服务端检查文件
ls -la /opt/remote_deploy/server-deploy/files/
ls -la /opt/remote_deploy/client-tools/

# 检查脚本权限
chmod +x /opt/remote_deploy/server-deploy/remote_deploy.sh
```

---

## 注意事项

1. **SSH 隧道依赖**：`remote_deploy.sh` 通过 frp 隧道 SSH 到设备，确保 frpc 正常运行。
2. **frpc 重启**：下发 frpc 时会重启服务，SSH 连接短暂断开，脚本自动重连验证。
3. **配置备份**：`scan_config.json` 部署前自动备份为 `.bak.<ts>`。
4. **权限**：脚本需要 root 权限执行 `systemctl`。
5. **防火墙**：确保 `7080, 7580, 8090, 8091, 7010-7999` 端口对外开放（iptables 默认 DROP）。
6. **安全**：调试完成后请及时卸载 frpc，防止设备被劫持。
7. **frps API**：`frp_monitor.py` 使用 frps v0.71+ 的 `/api/v2/clients` + `/api/v2/proxies` 端点。Basic auth：`master:Rowen@3328`。
