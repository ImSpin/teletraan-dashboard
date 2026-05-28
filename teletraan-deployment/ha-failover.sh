#!/usr/bin/env bash
# ============================================================
# TELETRAAN I — HA Failover Script (no keepalived needed)
# 
# Run this on each BACKUP Ubuntu node (not TrueNAS).
# It watches the primary host (TrueNAS) and if it goes down,
# starts serving the dashboard from THIS machine on port 7070.
# When TrueNAS comes back, it gracefully steps down.
#
# Usage: sudo bash ha-failover.sh <primary-ip> [backup-port]
# Example: sudo bash ha-failover.sh 192.168.1.20 7070
#
# To run permanently:
#   sudo cp ha-failover.sh /opt/teletraan/
#   sudo systemctl enable teletraan-ha  (created by this script)
# ============================================================

set -e
PRIMARY_IP="${1:?Usage: sudo bash ha-failover.sh <primary-ip> [port]}"
DASHBOARD_PORT="${2:-7070}"
DASHBOARD_FILE="/opt/teletraan/index.html"
CHECK_INTERVAL=5      # seconds between health checks
FAIL_THRESHOLD=3      # consecutive failures before taking over
RECOVER_THRESHOLD=3   # consecutive successes before stepping down

fail_count=0
recover_count=0
is_serving=false
server_pid=""

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [TELETRAAN-HA] $*"; }

check_primary() {
  curl -sf --max-time 3 "http://$PRIMARY_IP:$DASHBOARD_PORT/" > /dev/null 2>&1
}

start_serving() {
  if [[ "$is_serving" == false ]]; then
    log "PRIMARY DOWN — Taking over dashboard on port $DASHBOARD_PORT"
    if [[ ! -f "$DASHBOARD_FILE" ]]; then
      log "ERROR: $DASHBOARD_FILE not found. Copy the dashboard file there first."
      return 1
    fi
    cd "$(dirname "$DASHBOARD_FILE")"
    python3 -m http.server "$DASHBOARD_PORT" --bind 0.0.0.0 &
    server_pid=$!
    is_serving=true
    log "Now serving dashboard (PID $server_pid)"
    # Open firewall if ufw is active
    if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
      ufw allow "$DASHBOARD_PORT/tcp" comment "Teletraan HA" >/dev/null 2>&1 || true
    fi
  fi
}

stop_serving() {
  if [[ "$is_serving" == true ]] && [[ -n "$server_pid" ]]; then
    log "PRIMARY RECOVERED — Stepping down (killing PID $server_pid)"
    kill "$server_pid" 2>/dev/null || true
    is_serving=false
    server_pid=""
  fi
}

cleanup() {
  log "Shutting down HA watcher"
  stop_serving
  exit 0
}
trap cleanup SIGTERM SIGINT

log "HA Watcher started. Watching $PRIMARY_IP:$DASHBOARD_PORT every ${CHECK_INTERVAL}s"
log "Failover threshold: $FAIL_THRESHOLD failures / Recovery: $RECOVER_THRESHOLD successes"

while true; do
  if check_primary; then
    fail_count=0
    if [[ "$is_serving" == true ]]; then
      recover_count=$((recover_count + 1))
      log "Primary responding ($recover_count/$RECOVER_THRESHOLD to step down)"
      if [[ $recover_count -ge $RECOVER_THRESHOLD ]]; then
        stop_serving
        recover_count=0
      fi
    fi
  else
    recover_count=0
    fail_count=$((fail_count + 1))
    log "Primary unreachable ($fail_count/$FAIL_THRESHOLD to take over)"
    if [[ $fail_count -ge $FAIL_THRESHOLD ]]; then
      start_serving
    fi
  fi
  sleep "$CHECK_INTERVAL"
done
