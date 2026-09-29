# 远程部署脚本使用说明

## 概述

本工具包含以下组件：

1. **`remote_deploy.sh`** - 服务器端部署脚本，通过 frp 隧道远程部署到设备
2. **`device_install.sh`** - 设备端安装脚本，设备通过 curl 下载执行，安装 frpc 客户端
3. **`device_uninstall.sh`** - 设备端卸载脚本，设备通过 curl 下载执行，卸载 frpc 客户端
4. **`frp_monitor.py`** - 设备监控页面，实时查看在线设备和端口号

## 服务器端部署脚本 (remote_deploy.sh)

用于通过 frp 隧道远程部署/更新设备端服务。

### 安装位置

- 脚本: `/opt/remote_deploy/remote_deploy.sh`
- 文件: `/opt/remote_deploy/files/`
- 快捷命令: `/usr/local/bin/remote-deploy`

### 使用方法

```bash
# 自动分配端口部署
remote-deploy

# 指定设备端口
remote-deploy --device-id 7010

# 跳过 frpc 部署（仅更新插件和配置）
remote-deploy --device-id 7010 --skip-frpc

# 查看设备信息
remote-deploy --list
```

## 设备端安装脚本 (device_install.sh)

用于在设备上安装 frpc 客户端，使其连接到 frps 服务器。

### 使用方法

在设备上执行以下命令一键安装：

```bash
curl -fsSL http://111.198.61.41:8090/device_install.sh | bash
```

或下载后执行：

```bash
curl -fsSL http://111.198.61.41:8090/device_install.sh -o device_install.sh
bash device_install.sh
```

### 安装内容

- `/opt/frp/frpc` - frp 客户端二进制
- `/etc/frp/frpc.ini` - frp 客户端配置
- `/etc/systemd/system/frpc.service` - systemd 服务

### 配置说明

编辑 `/opt/remote_deploy/device_install.sh` 顶部的配置区域：

```bash
# frps 服务器配置
FRPS_SERVER="111.198.61.41"
FRPS_PORT="7080"
FRPS_TOKEN="60d8a83c544e6168db"

# 设备端口配置
DEVICE_SSH_PORT="7010"
DEVICE_WEB_PORT="7011"

# 本地服务端口
LOCAL_SSH_PORT="12222"
LOCAL_WEB_PORT="18080"

# frpc 版本
FRPC_VERSION="0.51.3"
FRPC_ARCH="arm64"  # arm64 / amd64
```

## 设备端卸载脚本 (device_uninstall.sh)

用于在设备上卸载 frpc 客户端，断开 frp 隧道连接。**默认自动确认，无需交互**。

### 使用方法

在设备上执行以下命令一键卸载（默认自动确认）：

```bash
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash
```

或下载后执行：

```bash
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh -o device_uninstall.sh
bash device_uninstall.sh
```

如需手动确认提示，使用 `--confirm` 参数：

```bash
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash -s -- --confirm
```

### 卸载内容

- 停止并禁用 frpc 服务
- 删除 frpc 二进制 (`/opt/frp/frpc`)
- 删除 frpc 配置 (`/etc/frp/frpc.ini`)
- 删除 frpc 日志 (`/var/log/frp/`)
- 删除 systemd 服务文件

### 安全说明

卸载后设备将：
- 断开 frp 隧道连接
- 外部无法再通过端口访问设备
- 防止设备被劫持产生网络安全风险

## 设备监控页面 (frp_monitor.py)

实时查看在线设备和端口号，方便远程调试。

### 访问地址

- **监控页面**: `http://111.198.61.41:8091`
- **API 接口**: `http://111.198.61.41:8091/api/devices`

### 功能特性

- 实时显示在线设备列表
- 显示设备 SSH 端口和 Web 端口
- **SSH 命令按钮**: 点击后自动复制命令到剪贴板，并弹出模态框显示完整命令，提示用户在终端粘贴执行
- **Web 地址按钮**: 点击后直接打开新窗口跳转到设备配置页面
- 每 30 秒自动刷新
- 支持手动刷新

### 服务管理

```bash
# 查看服务状态
systemctl status frp-monitor.service

# 重启服务
systemctl restart frp-monitor.service

# 查看日志
journalctl -u frp-monitor.service -f
```

## 部署流程

### 新设备部署流程

1. **设备端**：执行 `device_install.sh` 安装 frpc
   ```bash
   curl -fsSL http://111.198.61.41:8090/device_install.sh | bash
   ```

2. **服务器端**：使用 `remote_deploy.sh` 部署插件和配置
   ```bash
   remote-deploy --device-id 7010 --skip-frpc
   ```

3. **监控页面**：访问 `http://111.198.61.41:8091` 查看设备状态

4. **设备卸载**（调试完成后）：
   ```bash
   curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash
   ```

### 老设备升级流程

1. **服务器端**：使用 `remote_deploy.sh` 更新设备和 frpc
   ```bash
   remote-deploy --device-id 7010
   ```

2. **监控页面**：访问 `http://111.198.61.41:8091` 确认设备在线

## HTTP 文件服务

服务器提供 HTTP 文件服务（端口 8090），用于设备下载脚本和 frpc 二进制：

- 安装脚本: `http://111.198.61.41:8090/device_install.sh`
- 卸载脚本: `http://111.198.61.41:8090/device_uninstall.sh`
- frpc 二进制: `http://111.198.61.41:8090/frpc`

服务管理：
```bash
systemctl status http-server.service
systemctl restart http-server.service
```

## 端口分配说明

| 端口范围 | 用途 |
|----------|------|
| 7080/7081 | frps 服务端主端口 |
| 7580/7581 | frps Dashboard |
| 7010-7999 | 设备端口（自动分配，每次 +2） |
| 8090 | HTTP 文件服务 |
| 8091 | 设备监控页面 |

示例分配：
- 设备 1: SSH=7010, Web=7011
- 设备 2: SSH=7012, Web=7013
- 设备 3: SSH=7014, Web=7015

## 外部访问

部署完成后，通过以下地址访问设备：

```bash
# SSH
ssh -p 7010 root@111.198.61.41

# 配置网页
http://111.198.61.41:7011
```

## 故障排查

### SSH 连接失败

```bash
# 检查 frp 隧道状态
systemctl status frpc.service

# 查看 frpc 日志
journalctl -u frpc.service -n 50 --no-pager

# 测试隧道
ssh -p 7010 root@111.198.61.41
```

### 服务未启动

```bash
# 检查服务状态
systemctl status config-web.service
systemctl status frpc.service

# 查看日志
journalctl -u config-web.service -n 50 --no-pager
journalctl -u frpc.service -n 50 --no-pager

# 重启服务
systemctl restart config-web.service
systemctl restart frpc.service
```

### 文件部署失败

```bash
# 检查文件是否存在
ls -la /opt/remote_deploy/files/

# 检查权限
chmod +x /opt/remote_deploy/remote_deploy.sh
```

### HTTP 文件服务问题

```bash
# 检查服务状态
systemctl status http-server.service

# 检查防火墙
iptables -L INPUT -n | grep 8090

# 重启服务
systemctl restart http-server.service
```

### 监控页面问题

```bash
# 检查服务状态
systemctl status frp-monitor.service

# 检查防火墙
iptables -L INPUT -n | grep 8091

# 查看日志
journalctl -u frp-monitor.service -f

# 重启服务
systemctl restart frp-monitor.service
```

## 注意事项

1. **SSH 隧道依赖**: 部署脚本通过 frp 隧道 SSH 连接到设备，确保 frpc 正常运行
2. **frpc 重启**: 部署 frpc 时会重启服务，导致 SSH 连接短暂断开，脚本会自动重连验证
3. **配置文件备份**: scan_config.json 部署前会自动备份
4. **权限**: 脚本需要 root 权限执行 systemctl 命令
5. **防火墙**: 确保 8090 和 8091 端口对外开放
6. **安全**: 调试完成后请及时卸载 frpc，防止设备被劫持

## 快速命令参考

```bash
# 设备端安装 frpc
curl -fsSL http://111.198.61.41:8090/device_install.sh | bash

# 设备端卸载 frpc（默认自动确认）
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash

# 设备端卸载 frpc（手动确认）
curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash -s -- --confirm

# 部署到设备 1 (端口 7010)
remote-deploy --device-id 7010

# 只部署文件，不重启 frpc
remote-deploy --device-id 7010 --skip-frpc

# 查看设备信息
remote-deploy --list

# 查看帮助
remote-deploy --help

# 访问监控页面
http://111.198.61.41:8091
```
