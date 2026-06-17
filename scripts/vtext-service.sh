#!/usr/bin/env bash
# vtext service management script
# Usage: vtext-service.sh <command>
# Commands: install, uninstall, start, stop, restart, status, logs, follow

set -euo pipefail

SERVICE_NAME="vtext"
PYTHON="/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3"
WORK_DIR="/mnt/data/projects/vtext"
SERVICE_FILE="${HOME}/.config/systemd/user/${SERVICE_NAME}.service"
SERVER_URL="http://127.0.0.1:8000"

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()     { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { err "$*"; exit 1; }

# ── helpers ───────────────────────────────────────────────────────────────────
require_service() {
    [[ -f "$SERVICE_FILE" ]] || die "Service not installed. Run: $0 install"
}

is_active() {
    systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null
}

# ── commands ──────────────────────────────────────────────────────────────────
cmd_install() {
    if [[ -f "$SERVICE_FILE" ]]; then
        warn "Service file already exists: ${SERVICE_FILE}"
        read -rp "Overwrite? [y/N] " ans
        [[ "${ans,,}" == "y" ]] || { info "Aborted."; exit 0; }
    fi

    mkdir -p "$(dirname "$SERVICE_FILE")"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=vtext transcription server
After=network.target

[Service]
Type=simple
WorkingDirectory=${WORK_DIR}
ExecStart=${PYTHON} -m vtext_server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable "${SERVICE_NAME}"
    loginctl enable-linger "$USER" 2>/dev/null || true
    ok "Service installed and enabled."
    info "Run '$0 start' to start it now."
}

cmd_uninstall() {
    require_service
    if is_active; then
        info "Stopping service..."
        systemctl --user stop "${SERVICE_NAME}"
    fi
    systemctl --user disable "${SERVICE_NAME}" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl --user daemon-reload
    ok "Service uninstalled."
}

cmd_start() {
    require_service
    if is_active; then
        warn "Service is already running."
    else
        systemctl --user start "${SERVICE_NAME}"
        ok "Service started."
    fi
}

cmd_stop() {
    require_service
    if is_active; then
        systemctl --user stop "${SERVICE_NAME}"
        ok "Service stopped."
    else
        warn "Service is not running."
    fi
}

cmd_restart() {
    require_service
    systemctl --user restart "${SERVICE_NAME}"
    ok "Service restarted."
}

cmd_status() {
    require_service
    echo -e "\n${BOLD}── systemd ──────────────────────────────────────────${NC}"
    systemctl --user status "${SERVICE_NAME}" --no-pager || true

    echo -e "\n${BOLD}── health API ───────────────────────────────────────${NC}"
    if command -v curl &>/dev/null; then
        response=$(curl -sf --max-time 3 "${SERVER_URL}/health" 2>/dev/null) || {
            warn "Server not reachable at ${SERVER_URL}"
            return
        }
        # Pretty-print if python3 available
        echo "$response" | ${PYTHON} -m json.tool 2>/dev/null || echo "$response"
    else
        warn "curl not found, skipping health check."
    fi
}

cmd_logs() {
    local lines="${1:-50}"
    require_service
    echo -e "${BOLD}── last ${lines} lines ───────────────────────────────${NC}"
    journalctl --user -u "${SERVICE_NAME}" -n "${lines}" --no-pager
}

cmd_follow() {
    require_service
    info "Following logs (Ctrl+C to exit)..."
    journalctl --user -u "${SERVICE_NAME}" -f
}

cmd_help() {
    echo -e "${BOLD}Usage:${NC} $(basename "$0") <command> [options]"
    echo ""
    echo -e "${BOLD}Commands:${NC}"
    printf "  %-12s %s\n" "install"   "Install and enable the systemd user service"
    printf "  %-12s %s\n" "uninstall" "Stop, disable and remove the service"
    printf "  %-12s %s\n" "start"     "Start the service"
    printf "  %-12s %s\n" "stop"      "Stop the service"
    printf "  %-12s %s\n" "restart"   "Restart the service"
    printf "  %-12s %s\n" "status"    "Show systemd status + live health API info"
    printf "  %-12s %s\n" "logs [N]"  "Show last N log lines (default: 50)"
    printf "  %-12s %s\n" "follow"    "Tail logs in real time"
}

# ── dispatch ──────────────────────────────────────────────────────────────────
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    status)    cmd_status ;;
    logs)      cmd_logs "${1:-50}" ;;
    follow)    cmd_follow ;;
    help|--help|-h) cmd_help ;;
    *) err "Unknown command: ${COMMAND}"; cmd_help; exit 1 ;;
esac
