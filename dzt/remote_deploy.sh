#!/bin/bash
# ============================================================================
# remote_deploy.sh - Remote One-Click Deploy Script (placed on frps server)
# ============================================================================
# 
# Purpose:
#   Deploy/update all device services via frp tunnel (plugins, config web, remote client)
#   For device upgrades and daily maintenance
#
# Deployment Content:
#   Device:
#     /root/main/plugins/rgw.py          - 4G CPE collection plugin
#     /root/main/plugins/h3c.py          - H3C router collection plugin
#     /root/main/tools/config_web.py     - Config web service
#     /root/scan_config.json             - Collection config
#     /etc/systemd/system/config-web.service - Config web systemd service
#     /opt/remote/remote-client          - Remote client binary
#     /etc/remote/client.ini             - Remote client config
#     /etc/systemd/system/remote-client.service - Remote client systemd service
#
# Usage:
#   On frps server (111.198.61.41):
#     ./remote_deploy.sh                          # Auto-assign ports and deploy
#     ./remote_deploy.sh --device-id 7010         # Specify device SSH port
#     ./remote_deploy.sh --device-id 7010 --skip-frpc  # Skip remote client deploy
#     ./remote_deploy.sh --list                   # List used ports and available ports
#     ./remote_deploy.sh --no-auto-port           # Disable auto-port, manual input
#
# Dependencies:
#   sshpass, curl, wget, tar
#
# Configuration:
#   Modify the config section at the top of this script for different environments
# ============================================================================

set -e

# ==================== Configuration ====================

# frps server configuration
FRPS_SERVER="111.198.61.41"
FRPS_PORT="7080"
FRPS_TOKEN="60d8a83c544e6168db"
FRPS_DASHBOARD_PORT="7580"  # frps dashboard port

# Device port configuration
DEVICE_PORT_START=7010    # Device port start
DEVICE_PORT_END=7999      # Device port end
DEVICE_SSH_PORT_DEFAULT=7010  # Default device SSH tunnel port
DEVICE_SSH_USER="root"
DEVICE_SSH_PASS="dongshengniubi666"

# Reserved ports (not assigned to devices)
RESERVED_PORTS=(7080 7580)

# Remote client configuration
CLIENT_VERSION="0.51.3"
CLIENT_ARCH="arm64"  # arm64 / amd64
CLIENT_DOWNLOAD_URL="https://github.com/fatedier/frp/releases/download/v${CLIENT_VERSION}/frp_${CLIENT_VERSION}_linux_${CLIENT_ARCH}.tar.gz"

# File source directory (files/ subdirectory under script directory)
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
FILES_DIR="${SCRIPT_DIR}/files"

# Device paths
DEVICE_PLUGINS_DIR="/root/main/plugins"
DEVICE_TOOLS_DIR="/root/main/tools"
DEVICE_CONFIG_DIR="/root"
DEVICE_CLIENT_BIN_DIR="/opt/remote"
DEVICE_CLIENT_CONF_DIR="/etc/remote"
DEVICE_CLIENT_LOG_DIR="/var/log/remote"

# ==================== Color Output ====================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ==================== Check Dependencies ====================

check_dependencies() {
    local missing=()
    
    for cmd in sshpass ssh curl tar; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    
    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing dependencies: ${missing[*]}, please install first"
    fi
    
    log "Dependencies check passed"
}

# ==================== Auto Port Allocation ====================

# Find next available port pair (SSH: port, Web: port+1)
# Check from START_PORT, return SSH port number
# Note: Log output to stderr to avoid interfering with command substitution
find_next_port() {
    local start_port="$1"
    local max_port="${2:-$DEVICE_PORT_END}"
    
    # Log output to stderr
    echo "[INFO] Checking available ports (from $start_port)..." >&2
    
    # Get all listening ports at once (performance optimization)
    local listening_ports
    listening_ports=$(ss -tlnp 2>/dev/null | grep -oP ':\K[0-9]+' | sort -nu)
    
    # Use Python for fast port availability check (performance optimization)
    local result
    result=$(python3 -c "
import sys
start = $start_port
max_p = $max_port
reserved = [7080, 7081, 7580, 7581]
listening = set([int(p) for p in '''$listening_ports'''.strip().split() if p])

port = start
found = None
while port <= max_p:
    # Check if it's a reserved port
    is_reserved = any(port == r or port+1 == r for r in reserved)
    if is_reserved:
        print(f'[INFO]   Skipping reserved port: {port}/{port+1} (frps server)', file=sys.stderr)
        port += 2
        continue
    
    # Check if ports are available
    ssh_avail = port not in listening
    web_avail = port+1 not in listening
    
    if ssh_avail and web_avail:
        print(f'[INFO] Found available port: SSH={port}, Web={port+1}', file=sys.stderr)
        found = port
        break
    
    if not ssh_avail:
        print(f'[WARN]   Port {port} is already in use', file=sys.stderr)
    if not web_avail:
        print(f'[WARN]   Port {port+1} is already in use', file=sys.stderr)
    
    port += 2

if found:
    print(found)
else:
    print(f'[WARN] No available port found (range: {start}-{max_p})', file=sys.stderr)
    sys.exit(1)
" 2>&1)
    
    # Separate stderr and stdout
    echo "$result" | grep -E '^\[INFO\]|^\[WARN\]' >&2
    local port
    port=$(echo "$result" | grep -oP '^\d+$' | tail -1)
    
    echo "$port"
}

# List used device ports
list_used_ports() {
    log "Used device ports:"
    log "=========================================="
    
    # Get all listening ports at once (performance optimization)
    local listening_ports
    listening_ports=$(ss -tlnp 2>/dev/null | grep -oP ':\K[0-9]+' | sort -nu)
    
    # Use Python for fast port usage check (performance optimization)
    python3 -c "
import sys
start = 7010
end = 7999
reserved = [7080, 7081, 7580, 7581]
listening = set([int(p) for p in '''$listening_ports'''.strip().split() if p])

port = start
found = 0
while port <= end:
    # Check if it's a reserved port
    is_reserved = any(port == r or port+1 == r for r in reserved)
    if is_reserved:
        print(f'  Port {port}/{port+1}: [Reserved] frps server', file=sys.stdout)
        port += 2
        continue
    
    # Check if ports are in use
    ssh_used = port in listening
    web_used = port+1 in listening
    
    if ssh_used or web_used:
        if ssh_used and web_used:
            status = 'SSH+Web online'
        elif ssh_used:
            status = 'SSH only online'
        else:
            status = 'Web only online'
        print(f'  Port {port}/{port+1}: {status}', file=sys.stdout)
        found += 1
    
    port += 2

if found == 0:
    print('  No device ports in use', file=sys.stdout)
"
    
    log "=========================================="
    local next_port
    next_port=$(find_next_port $DEVICE_PORT_START 2>/dev/null)
    log "Next available port: $next_port (SSH) / $((next_port+1)) (Web)"
}

# ==================== Prepare Files ====================

prepare_files() {
    if [ ! -d "$FILES_DIR" ]; then
        error "File directory does not exist: $FILES_DIR"
    fi
    
    log "Checking local files..."
    
    local required_files=(
        "rgw_plugin.py"
        "h3c_plugin.py"
        "config_web.py"
        "scan_config.json"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$FILES_DIR/$file" ]; then
            warn "File not found: $FILES_DIR/$file (will skip)"
        fi
    done
    
    log "File check complete"
}

# ==================== SSH Connection ====================

ssh_cmd() {
    local device_port="$1"
    local command="$2"
    
    sshpass -e ssh \
        -p "$device_port" \
        -o StrictHostKeyChecking=no \
        -o PreferredAuthentications=password \
        -o PubkeyAuthentication=no \
        -o ConnectTimeout=10 \
        "${DEVICE_SSH_USER}@${FRPS_SERVER}" \
        "$command"
}

scp_cmd() {
    local device_port="$1"
    local local_file="$2"
    local remote_file="$3"
    
    sshpass -e scp \
        -O \
        -P "$device_port" \
        -o StrictHostKeyChecking=no \
        -o PreferredAuthentications=password \
        -o PubkeyAuthentication=no \
        "$local_file" \
        "${DEVICE_SSH_USER}@${FRPS_SERVER}:${remote_file}"
}

# ==================== Deploy Plugin Files ====================

deploy_plugins() {
    local device_port="$1"
    
    log "Deploying collection plugins to device..."
    
    # Create directories
    ssh_cmd "$device_port" "mkdir -p $DEVICE_PLUGINS_DIR $DEVICE_TOOLS_DIR"
    
    # Deploy rgw_plugin.py
    if [ -f "$FILES_DIR/rgw_plugin.py" ]; then
        log "  Deploying rgw_plugin.py..."
        scp_cmd "$device_port" "$FILES_DIR/rgw_plugin.py" "$DEVICE_PLUGINS_DIR/rgw.py"
    fi
    
    # Deploy h3c_plugin.py
    if [ -f "$FILES_DIR/h3c_plugin.py" ]; then
        log "  Deploying h3c_plugin.py..."
        scp_cmd "$device_port" "$FILES_DIR/h3c_plugin.py" "$DEVICE_PLUGINS_DIR/h3c.py"
    fi
    
    # Deploy config_web.py
    if [ -f "$FILES_DIR/config_web.py" ]; then
        log "  Deploying config_web.py..."
        scp_cmd "$device_port" "$FILES_DIR/config_web.py" "$DEVICE_TOOLS_DIR/config_web.py"
    fi
    
    # Deploy scan_config.json (backup first)
    if [ -f "$FILES_DIR/scan_config.json" ]; then
        log "  Deploying scan_config.json (backup first)..."
        ssh_cmd "$device_port" "test -f $DEVICE_CONFIG_DIR/scan_config.json && cp -a $DEVICE_CONFIG_DIR/scan_config.json $DEVICE_CONFIG_DIR/scan_config.json.bak.\$(date +%s) || true"
        scp_cmd "$device_port" "$FILES_DIR/scan_config.json" "$DEVICE_CONFIG_DIR/scan_config.json"
    fi
    
    log "Plugin deployment complete"
}

# ==================== Deploy systemd Services ====================

deploy_services() {
    local device_port="$1"
    
    log "Deploying systemd services..."
    
    # config-web.service
    log "  Creating config-web.service..."
    ssh_cmd "$device_port" "cat > /etc/systemd/system/config-web.service << 'EOF'
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
EOF"
    
    # remote-client.service
    log "  Creating remote-client.service..."
    ssh_cmd "$device_port" "cat > /etc/systemd/system/remote-client.service << 'EOF'
[Unit]
Description=Remote Client Service
After=network.target

[Service]
Type=simple
ExecStart=/opt/remote/remote-client -c /etc/remote/client.ini
Restart=always
RestartSec=3
LimitNOFILE=65535
User=root

[Install]
WantedBy=multi-user.target
EOF"
    
    # Reload systemd
    ssh_cmd "$device_port" "systemctl daemon-reload"
    
    # Enable services
    log "  Enabling services..."
    ssh_cmd "$device_port" "systemctl enable config-web.service remote-client.service"
    
    # Only restart config-web.service (remote-client restarted in deploy_client)
    log "  Restarting config-web.service..."
    ssh_cmd "$device_port" "systemctl restart config-web.service"
    
    sleep 2
    
    # Check service status
    local config_status
    config_status=$(ssh_cmd "$device_port" "systemctl is-active config-web.service" 2>/dev/null || echo "unknown")
    
    if [ "$config_status" = "active" ]; then
        log "  config-web.service: ${GREEN}active${NC}"
    else
        warn "  config-web.service: ${YELLOW}$config_status${NC}"
    fi
    
    log "Service deployment complete"
}

# ==================== Deploy Remote Client ====================

deploy_client() {
    local device_port="$1"
    
    log "Deploying remote client..."
    
    # Create directories
    ssh_cmd "$device_port" "mkdir -p $DEVICE_CLIENT_BIN_DIR $DEVICE_CLIENT_CONF_DIR $DEVICE_CLIENT_LOG_DIR"
    
    # Check for remote client binary
    if [ ! -f "$FILES_DIR/remote-client" ]; then
        warn "No remote-client binary locally, checking device..."
        
        # Check if device already has remote-client
        local existing_client
        existing_client=$(ssh_cmd "$device_port" "test -f $DEVICE_CLIENT_BIN_DIR/remote-client && echo exists || echo not_exists" 2>/dev/null || echo "error")
        
        if [ "$existing_client" = "exists" ]; then
            log "  Device already has remote-client, skipping download"
        else
            warn "  Device has no remote-client, please download manually to $FILES_DIR/remote-client"
            warn "  Download link: $CLIENT_DOWNLOAD_URL"
            return 1
        fi
    else
        log "  Uploading remote-client binary..."
        
        # Create temp file first to avoid Text file busy error
        scp_cmd "$device_port" "$FILES_DIR/remote-client" "$DEVICE_CLIENT_BIN_DIR/remote-client.new"
        ssh_cmd "$device_port" "chmod +x $DEVICE_CLIENT_BIN_DIR/remote-client.new"
        
        # Backup old remote-client (if exists)
        ssh_cmd "$device_port" "test -f $DEVICE_CLIENT_BIN_DIR/remote-client && cp $DEVICE_CLIENT_BIN_DIR/remote-client $DEVICE_CLIENT_BIN_DIR/remote-client.bak || true"
    fi
    
    # Deploy remote client config (with dynamic ports)
    log "  Deploying client.ini (ports: SSH=$device_port, Web=$((device_port+1)))..."
    ssh_cmd "$device_port" "cat > $DEVICE_CLIENT_CONF_DIR/client.ini << EOF
[common]
server_addr = ${FRPS_SERVER}
server_port = ${FRPS_PORT}
login_fail_exit = true
token = ${FRPS_TOKEN}
log_to = /var/log/remote/client.log
log_level = debug
log_max_days = 7

[ssh-device-001]
type = tcp
local_ip = 127.0.0.1
local_port = 12222
remote_port = ${device_port}

[web-device-001]
type = tcp
local_ip = 127.0.0.1
local_port = 18080
remote_port = $((device_port+1))
EOF"
    
    # Restart remote client (Note: this will disconnect current SSH)
    log "  Restarting remote-client (connection will drop)..."
    warn "  SSH connection will drop, please reconnect later to verify..."
    
    # Replace remote-client binary and restart service
    ssh_cmd "$device_port" "mv $DEVICE_CLIENT_BIN_DIR/remote-client.new $DEVICE_CLIENT_BIN_DIR/remote-client && nohup bash -c 'sleep 1 && systemctl restart remote-client.service' > /dev/null 2>&1 & disown"
    
    # Wait for remote-client to restart and re-establish tunnel
    log "  Waiting for tunnel to re-establish (approx 10 seconds)..."
    sleep 10
    
    # Try to reconnect and verify
    local retry=0
    local connected=false
    
    while [ $retry -lt 5 ]; do
        if ssh_cmd "$device_port" "systemctl is-active remote-client.service" &>/dev/null; then
            connected=true
            break
        fi
        sleep 3
        retry=$((retry + 1))
    done
    
    if [ "$connected" = true ]; then
        local client_status
        client_status=$(ssh_cmd "$device_port" "systemctl is-active remote-client.service" 2>/dev/null || echo "unknown")
        
        if [ "$client_status" = "active" ]; then
            log "  remote-client deployed: ${GREEN}active${NC}"
        else
            warn "  remote-client status: ${YELLOW}$client_status${NC}"
        fi
    else
        warn "  Cannot verify remote-client status (connection timeout)"
        warn "  Please check manually: ssh -p $device_port root@$FRPS_SERVER 'systemctl is-active remote-client.service'"
    fi
    
    log "Remote client deployment complete"
}

# ==================== Verify Deployment ====================

verify_deployment() {
    local device_port="$1"
    
    log "Verifying deployment..."
    
    # Check Python compilation
    local compile_result
    compile_result=$(ssh_cmd "$device_port" "python3 -m py_compile /root/main/tools/config_web.py /root/main/plugins/rgw.py /root/main/plugins/h3c.py 2>&1 && echo OK || echo FAIL" 2>/dev/null || echo "ERROR")
    
    if echo "$compile_result" | grep -q "OK"; then
        log "  Python compile: ${GREEN}OK${NC}"
    else
        warn "  Python compile: ${YELLOW}$compile_result${NC}"
    fi
    
    # Check config web page
    local health_result
    health_result=$(ssh_cmd "$device_port" "curl -s --max-time 3 http://127.0.0.1:18080/healthz" 2>/dev/null || echo "ERROR")
    
    if echo "$health_result" | grep -q "ok"; then
        log "  Config web: ${GREEN}OK${NC}"
    else
        warn "  Config web: ${YELLOW}$health_result${NC}"
    fi
    
    # Check remote client
    local client_status
    client_status=$(ssh_cmd "$device_port" "systemctl is-active remote-client.service" 2>/dev/null || echo "ERROR")
    
    if [ "$client_status" = "active" ]; then
        log "  remote-client: ${GREEN}active${NC}"
    else
        warn "  remote-client: ${YELLOW}$client_status${NC}"
    fi
    
    log "Verification complete"
}

# ==================== List Devices ====================

list_devices() {
    log "Device port mapping info"
    log "=========================================="
    log "Server: $FRPS_SERVER"
    log "frps port: $FRPS_PORT"
    log "=========================================="
    log ""
    log "Port allocation: Auto from 7010, +2 each time (SSH+Web)"
    log ""
    log "External access:"
    log "  SSH: ssh -p <port> root@$FRPS_SERVER"
    log "  Web: http://$FRPS_SERVER:<port+1>"
    log ""
    log "Examples:"
    log "  Device 1: SSH=7010, Web=7011"
    log "  Device 2: SSH=7012, Web=7013"
    log "  Device 3: SSH=7014, Web=7015"
    log "=========================================="
    
    # Try to check frps status
    log ""
    log "frps status check..."
    local frps_status
    frps_status=$(curl -s -o /dev/null -w "%{http_code}" -u "master:Rowen@3328" "http://127.0.0.1:7580/" 2>/dev/null || echo "ERROR")
    
    if [ "$frps_status" = "200" ] || [ "$frps_status" = "301" ] || [ "$frps_status" = "302" ]; then
        log "  frps dashboard: ${GREEN}OK${NC} (http://127.0.0.1:7580)"
    else
        warn "  frps dashboard: ${YELLOW}$frps_status${NC}"
    fi
}

# ==================== Main Function ====================

main() {
    local device_port=""
    local skip_client=false
    local list_only=false
    local auto_port=true  # Default: auto-assign ports
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --device-id)
                device_port="$2"
                auto_port=false
                shift 2
                ;;
            --skip-frpc)
                skip_client=true
                shift
                ;;
            --auto-port)
                auto_port=true
                shift
                ;;
            --no-auto-port)
                auto_port=false
                shift
                ;;
            --list)
                list_only=true
                shift
                ;;
            --help|-h)
                head -40 "$0" | tail -35
                exit 0
                ;;
            *)
                error "Unknown argument: $1 (use --help for usage)"
                ;;
        esac
    done
    
    # List devices
    if [ "$list_only" = true ]; then
        list_devices
        list_used_ports
        exit 0
    fi
    
    # Check dependencies
    check_dependencies
    
    # Set device port
    if [ -z "$device_port" ]; then
        if [ "$auto_port" = true ]; then
            log "Auto-assigning port..."
            device_port=$(find_next_port $DEVICE_SSH_PORT_DEFAULT)
            if [ -z "$device_port" ]; then
                error "No available port found"
            fi
            log "Assigned port: SSH=$device_port, Web=$((device_port+1))"
        else
            read -p "Enter device SSH tunnel port (default $DEVICE_SSH_PORT_DEFAULT): " device_port
            device_port="${device_port:-$DEVICE_SSH_PORT_DEFAULT}"
        fi
    fi
    
    export SSHPASS="$DEVICE_SSH_PASS"
    
    # Test connection
    log "Testing SSH connection (port $device_port)..."
    if ! ssh_cmd "$device_port" "hostname" &>/dev/null; then
        error "SSH connection failed (port $device_port), please check if frp tunnel is working"
    fi
    
    local hostname
    hostname=$(ssh_cmd "$device_port" "hostname" 2>/dev/null)
    log "Connected to device: $hostname"
    
    # Prepare files
    prepare_files
    
    # Deploy plugins
    deploy_plugins "$device_port"
    
    # Deploy services
    deploy_services "$device_port"
    
    # Deploy remote client (unless skipped)
    if [ "$skip_client" = false ]; then
        deploy_client "$device_port"
    else
        warn "Skipping remote client deployment"
    fi
    
    # Verify
    verify_deployment "$device_port"
    
    # Done
    echo ""
    log "=========================================="
    log "Deployment complete!"
    log "=========================================="
    log "Device SSH port: $device_port"
    log "External SSH: ssh -p $device_port root@${FRPS_SERVER}"
    log "Config web: http://${FRPS_SERVER}:$((device_port + 1))"
    log "=========================================="
}

# Execute main function
main "$@"
