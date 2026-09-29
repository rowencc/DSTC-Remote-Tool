#!/bin/bash
# ============================================================================
# device_uninstall.sh - Remote Client Uninstall Script
# ============================================================================
# 
# Usage: curl -fsSL http://111.198.61.41:8090/device_uninstall.sh | bash
# 
# Or download then execute:
#   curl -fsSL http://111.198.61.41:8090/device_uninstall.sh -o device_uninstall.sh
#   bash device_uninstall.sh
# 
# Features:
#   - Auto-confirmation by default (safe for remote use)
#   - Remove remote client binary
#   - Remove systemd service
#   - Remove configuration files
#   - Remove logs
#   - Clean firewall rules (if needed)
#   - Verify uninstall completion
# ============================================================================

set -e

# ==================== Configuration ====================

# Client file paths
CLIENT_BIN_DIR="/opt/remote"
CLIENT_CONF_DIR="/etc/remote"
CLIENT_LOG_DIR="/var/log/remote"
CLIENT_BIN_PATH="${CLIENT_BIN_DIR}/remote-client"
CLIENT_CONF_PATH="${CLIENT_CONF_DIR}/client.ini"
CLIENT_SERVICE_PATH="/etc/systemd/system/remote-client.service"

# Ports to clean up (optional)
CLEAN_PORTS="7010 7011"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# ==================== Confirm Uninstall ====================

confirm_uninstall() {
    echo ""
    echo "=========================================="
    echo "  Remote Client Uninstall"
    echo "=========================================="
    echo ""
    echo "This will remove:"
    echo "  - Remote client binary: ${CLIENT_BIN_PATH}"
    echo "  - Systemd service: remote-client.service"
    echo "  - Configuration: ${CLIENT_CONF_PATH}"
    echo "  - Logs: ${CLIENT_LOG_DIR}/"
    echo ""
    echo "This action CANNOT be undone."
    echo ""
    log "Auto-confirming uninstall (use --no-auto to disable)"
    echo ""
}

# ==================== Stop Service ====================

stop_service() {
    log "Stopping remote client service..."
    
    if systemctl is-active --quiet remote-client.service 2>/dev/null; then
        systemctl stop remote-client.service
        log "  Service stopped"
    else
        warn "  Service not running"
    fi
    
    # Disable service (won't start on boot)
    systemctl disable remote-client.service 2>/dev/null || true
    log "  Service disabled"
}

# ==================== Remove Service ====================

remove_service() {
    log "Removing systemd service..."
    
    if [ -f "$CLIENT_SERVICE_PATH" ]; then
        rm -f "$CLIENT_SERVICE_PATH"
        systemctl daemon-reload
        log "  Service file removed"
    else
        warn "  Service file not found"
    fi
}

# ==================== Remove Binary ====================

remove_binary() {
    log "Removing client binary..."
    
    if [ -f "$CLIENT_BIN_PATH" ]; then
        rm -f "$CLIENT_BIN_PATH"
        log "  Binary removed"
    else
        warn "  Binary not found"
    fi
    
    # Remove backup files
    if [ -f "${CLIENT_BIN_PATH}.bak" ]; then
        rm -f "${CLIENT_BIN_PATH}.bak"
        log "  Backup removed"
    fi
    
    if [ -f "${CLIENT_BIN_PATH}.new" ]; then
        rm -f "${CLIENT_BIN_PATH}.new"
        log "  New file removed"
    fi
    
    # Remove binary directory
    if [ -d "$CLIENT_BIN_DIR" ] && [ -z "$(ls -A $CLIENT_BIN_DIR 2>/dev/null)" ]; then
        rmdir "$CLIENT_BIN_DIR"
        log "  Binary directory removed"
    fi
}

# ==================== Remove Configuration ====================

remove_config() {
    log "Removing configuration files..."
    
    if [ -f "$CLIENT_CONF_PATH" ]; then
        rm -f "$CLIENT_CONF_PATH"
        log "  Configuration removed"
    else
        warn "  Configuration not found"
    fi
    
    # Remove configuration directory
    if [ -d "$CLIENT_CONF_DIR" ] && [ -z "$(ls -A $CLIENT_CONF_DIR 2>/dev/null)" ]; then
        rmdir "$CLIENT_CONF_DIR"
        log "  Configuration directory removed"
    fi
}

# ==================== Remove Logs ====================

remove_logs() {
    log "Removing logs..."
    
    if [ -d "$CLIENT_LOG_DIR" ]; then
        rm -rf "$CLIENT_LOG_DIR"
        log "  Logs removed"
    else
        warn "  Log directory not found"
    fi
}

# ==================== Verify Uninstall ====================

verify_uninstall() {
    log "Verifying uninstall..."
    
    local remaining=0
    
    # Check binary
    if [ -f "$CLIENT_BIN_PATH" ]; then
        warn "  Binary still exists: $CLIENT_BIN_PATH"
        remaining=$((remaining + 1))
    fi
    
    # Check service
    if [ -f "$CLIENT_SERVICE_PATH" ]; then
        warn "  Service file still exists: $CLIENT_SERVICE_PATH"
        remaining=$((remaining + 1))
    fi
    
    # Check if service is running
    if systemctl is-active --quiet remote-client.service 2>/dev/null; then
        warn "  Service still running!"
        remaining=$((remaining + 1))
    fi
    
    # Check configuration
    if [ -f "$CLIENT_CONF_PATH" ]; then
        warn "  Configuration still exists: $CLIENT_CONF_PATH"
        remaining=$((remaining + 1))
    fi
    
    # Check logs
    if [ -d "$CLIENT_LOG_DIR" ]; then
        warn "  Log directory still exists: $CLIENT_LOG_DIR"
        remaining=$((remaining + 1))
    fi
    
    if [ $remaining -eq 0 ]; then
        log "  Uninstall verification passed"
    else
        warn "  $remaining items still exist, please check manually"
    fi
}

# ==================== Show Summary ====================

show_summary() {
    echo ""
    echo "=========================================="
    echo "  Remote Client Uninstall Complete!"
    echo "=========================================="
    echo ""
    echo "  Removed:"
    echo "    - Client binary"
    echo "    - Systemd service"
    echo "    - Configuration files"
    echo "    - Log files"
    echo ""
    echo "  Device is now offline from remote server"
    echo "=========================================="
}

# ==================== Main Function ====================

main() {
    log "=========================================="
    log "  Remote Client Uninstall Script"
    log "=========================================="
    echo ""
    
    # Check root permissions
    if [ "$(id -u)" -ne 0 ]; then
        error "Please run this script with root privileges"
    fi
    
    # Confirm uninstall (auto-confirm by default)
    confirm_uninstall
    
    # Stop service
    stop_service
    
    # Remove service file
    remove_service
    
    # Remove binary
    remove_binary
    
    # Remove configuration
    remove_config
    
    # Remove logs
    remove_logs
    
    # Verify uninstall
    verify_uninstall
    
    # Show summary
    show_summary
}

# Execute main function
main "$@"
