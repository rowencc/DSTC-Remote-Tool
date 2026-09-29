#!/bin/bash
# ============================================================================
# device_install.sh - Remote Client Install Script
# ============================================================================
# 
# Usage: curl -fsSL http://111.198.61.41:8090/device_install.sh | bash
# 
# Or download then execute:
#   curl -fsSL http://111.198.61.41:8090/device_install.sh -o device_install.sh
#   bash device_install.sh
# 
# Features:
#   - Install remote client binary
#   - Configure systemd service
#   - Auto-start and connect to remote server
# ============================================================================

set -e

# ==================== Configuration ====================

# Remote server configuration
REMOTE_SERVER="111.198.61.41"
REMOTE_PORT="7080"
REMOTE_TOKEN="60d8a83c544e6168db"

# Device port configuration (SSH tunnel port)
DEVICE_SSH_PORT="7010"
DEVICE_WEB_PORT="7011"

# Local service ports
LOCAL_SSH_PORT="12222"
LOCAL_WEB_PORT="18080"

# Client file paths
CLIENT_BIN_DIR="/opt/remote"
CLIENT_CONF_DIR="/etc/remote"
CLIENT_LOG_DIR="/var/log/remote"
CLIENT_BIN_PATH="${CLIENT_BIN_DIR}/remote-client"
CLIENT_CONF_PATH="${CLIENT_CONF_DIR}/client.ini"
CLIENT_SERVICE_PATH="/etc/systemd/system/remote-client.service"

# Client version
CLIENT_VERSION="0.51.3"
CLIENT_ARCH="arm64"  # arm64 / amd64

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ==================== Helper Functions ====================

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
    log "Checking dependencies..."
    
    local missing=()
    for cmd in curl wget scp bash; do
        if ! command -v $cmd &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    
    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing dependencies: ${missing[*]}"
    fi
    
    log "Dependencies check passed"
}

# ==================== Download Client ====================

download_client() {
    log "Downloading client v${CLIENT_VERSION} (${CLIENT_ARCH})..."
    
    # Create directories
    mkdir -p "$CLIENT_BIN_DIR" "$CLIENT_CONF_DIR" "$CLIENT_LOG_DIR"
    
    # Check if already exists
    if [ -f "$CLIENT_BIN_PATH" ]; then
        local existing_version
        existing_version=$("$CLIENT_BIN_PATH" -v 2>/dev/null || echo "unknown")
        if echo "$existing_version" | grep -q "$CLIENT_VERSION"; then
            log "  Client already exists (v${CLIENT_VERSION}), skipping download"
            return 0
        fi
        warn "  Existing client version mismatch, will overwrite"
    fi
    
    # Download client from server
    local download_url="http://${REMOTE_SERVER}:8090/remote-client"
    
    log "  Downloading from server: ${download_url}"
    
    if ! curl -fsSL "${download_url}" -o "${CLIENT_BIN_PATH}.new" 2>/dev/null; then
        warn "  Server download failed, trying GitHub..."
        
        local github_url="https://github.com/fatedier/frp/releases/download/v${CLIENT_VERSION}/frp_${CLIENT_VERSION}_linux_${CLIENT_ARCH}.tar.gz"
        local tmp_file=$(mktemp)
        
        if ! curl -fsSL "${github_url}" -o "${tmp_file}" 2>/dev/null; then
            error "Download failed, please download manually to ${CLIENT_BIN_PATH}"
        fi
        
        # Extract
        local tmp_dir=$(mktemp -d)
        tar -xzf "${tmp_file}" -C "${tmp_dir}"
        cp "${tmp_dir}/frp_${CLIENT_VERSION}_linux_${CLIENT_ARCH}/frpc" "${CLIENT_BIN_PATH}.new"
        rm -rf "${tmp_file}" "${tmp_dir}"
    fi
    
    # Replace binary
    if [ -f "$CLIENT_BIN_PATH" ]; then
        systemctl stop remote-client.service 2>/dev/null || true
        sleep 1
    fi
    
    mv "${CLIENT_BIN_PATH}.new" "$CLIENT_BIN_PATH"
    chmod +x "$CLIENT_BIN_PATH"
    
    log "  Client download complete: $(ls -lh "$CLIENT_BIN_PATH" | awk '{print $5}')"
}

# ==================== Create Configuration ====================

create_config() {
    log "Creating client configuration..."
    
    cat > "$CLIENT_CONF_PATH" << EOF
[common]
server_addr = ${REMOTE_SERVER}
server_port = ${REMOTE_PORT}
login_fail_exit = true
token = ${REMOTE_TOKEN}
log_to = ${CLIENT_LOG_DIR}/client.log
log_level = debug
log_max_days = 7

[ssh-device]
type = tcp
local_ip = 127.0.0.1
local_port = ${LOCAL_SSH_PORT}
remote_port = ${DEVICE_SSH_PORT}

[web-device]
type = tcp
local_ip = 127.0.0.1
local_port = ${LOCAL_WEB_PORT}
remote_port = ${DEVICE_WEB_PORT}
EOF
    
    log "  Configuration created: $CLIENT_CONF_PATH"
}

# ==================== Create Service ====================

create_service() {
    log "Creating systemd service..."
    
    cat > "$CLIENT_SERVICE_PATH" << EOF
[Unit]
Description=Remote Client Service
After=network.target

[Service]
Type=simple
ExecStart=${CLIENT_BIN_PATH} -c ${CLIENT_CONF_PATH}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    log "  Service created: $CLIENT_SERVICE_PATH"
}

# ==================== Start Service ====================

start_service() {
    log "Starting client service..."
    
    # Enable and start service
    systemctl enable remote-client.service
    systemctl start remote-client.service
    
    # Wait for service to start
    sleep 3
    
    # Check status
    if systemctl is-active --quiet remote-client.service; then
        log "  Client service started"
    else
        warn "  Client service failed to start, check logs: journalctl -u remote-client.service -n 50"
        return 1
    fi
}

# ==================== Verify Connection ====================

verify_connection() {
    log "Verifying server connection..."
    
    sleep 5
    
    # Check systemd logs
    if journalctl -u remote-client.service -n 100 --no-pager 2>/dev/null | grep -q "login to server success"; then
        log "  Connection successful!"
    else
        warn "  Waiting for connection..."
        sleep 5
        if journalctl -u remote-client.service -n 100 --no-pager 2>/dev/null | grep -q "login to server success"; then
            log "  Connection successful!"
        else
            warn "  Connection may have failed, check logs: journalctl -u remote-client.service -n 50 --no-pager"
            return 1
        fi
    fi
}

# ==================== Show Summary ====================

show_summary() {
    echo ""
    echo "=========================================="
    echo "  Remote Client Installation Complete!"
    echo "=========================================="
    echo ""
    echo "  Server: ${REMOTE_SERVER}:${REMOTE_PORT}"
    echo "  SSH Port: ${DEVICE_SSH_PORT}"
    echo "  Web Port: ${DEVICE_WEB_PORT}"
    echo ""
    echo "  Access:"
    echo "    SSH: ssh -p ${DEVICE_SSH_PORT} root@${REMOTE_SERVER}"
    echo "    Web: http://${REMOTE_SERVER}:${DEVICE_WEB_PORT}"
    echo ""
    echo "  Service status: systemctl status remote-client.service"
    echo "  View logs: journalctl -u remote-client.service -f"
    echo "=========================================="
}

# ==================== Main Function ====================

main() {
    log "=========================================="
    log "  Remote Client Installation Script"
    log "=========================================="
    echo ""
    
    # Check root permissions
    if [ "$(id -u)" -ne 0 ]; then
        error "Please run this script with root privileges"
    fi
    
    # Check dependencies
    check_dependencies
    
    # Download client
    download_client
    
    # Create configuration
    create_config
    
    # Create service
    create_service
    
    # Start service
    start_service
    
    # Verify connection
    verify_connection
    
    # Show summary
    show_summary
}

# Execute main function
main "$@"
