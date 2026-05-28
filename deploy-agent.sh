#!/usr/bin/env bash
# ============================================================
# TELETRAAN I — Agent Installer
# Run this on each Ubuntu/Debian node you want to monitor.
# Usage: sudo bash deploy-agent.sh [PORT]
#   PORT defaults to 7071. Change it if 7071 is taken.
#
# What it does:
#   1. Installs python3, pip, and smartmontools if missing
#   2. Installs Python deps (psutil, flask, flask-cors)
#   3. Drops agent.py into /opt/teletraan/
#   4. Creates a systemd service (teletraan-agent.service)
#   5. Enables it to start on boot and starts it now
# ============================================================

set -e
AGENT_PORT="${1:-7071}"
INSTALL_DIR="/opt/teletraan"
SERVICE_FILE="/etc/systemd/system/teletraan-agent.service"
AGENT_URL="http://teletraan.local:7070/agent.py"   # served from TrueNAS app
# Fallback: if you can't reach TrueNAS, the script embeds the agent inline below.

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   TELETRAAN I — NODE AGENT INSTALLER     ║"
echo "  ║   Port: $AGENT_PORT                              ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── 1. Check root ─────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run as root: sudo bash deploy-agent.sh"
  exit 1
fi

# ── 2. Install system dependencies ───────────────────────
echo "[1/5] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip smartmontools lm-sensors curl

# ── 3. Install Python packages ────────────────────────────
echo "[2/5] Installing Python packages..."
pip3 install -q psutil flask flask-cors py-cpuinfo 2>/dev/null || \
pip3 install --break-system-packages -q psutil flask flask-cors 2>/dev/null || true

# ── 4. Create install directory and drop agent ────────────
echo "[3/5] Installing agent to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Try to fetch from TrueNAS dashboard host first
if curl -sf --max-time 3 "$AGENT_URL" -o "$INSTALL_DIR/agent.py" 2>/dev/null; then
  echo "     Fetched agent.py from TrueNAS."
else
  echo "     TrueNAS unreachable — using bundled agent."
  # The bundled agent is written by the TrueNAS app setup.
  # If this script is run standalone, copy agent.py manually:
  if [[ -f "$(dirname "$0")/agent.py" ]]; then
    cp "$(dirname "$0")/agent.py" "$INSTALL_DIR/agent.py"
    echo "     Copied agent.py from local directory."
  else
    echo "ERROR: agent.py not found. Copy it to the same folder as this script."
    exit 1
  fi
fi

chmod +x "$INSTALL_DIR/agent.py"

# ── 5. Create systemd service ─────────────────────────────
echo "[4/5] Creating systemd service..."
cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=Teletraan I Node Agent
Documentation=https://github.com/your-repo/teletraan
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=AGENT_PORT=$AGENT_PORT
ExecStart=/usr/bin/python3 $INSTALL_DIR/agent.py
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=teletraan-agent

# Give it access to hardware sensors
AmbientCapabilities=CAP_SYS_RAWIO CAP_DAC_READ_SEARCH

[Install]
WantedBy=multi-user.target
SERVICE

# ── 6. Enable and start ───────────────────────────────────
echo "[5/5] Enabling and starting teletraan-agent..."
systemctl daemon-reload
systemctl enable teletraan-agent
systemctl restart teletraan-agent

sleep 2

# ── 7. Verify ─────────────────────────────────────────────
if systemctl is-active --quiet teletraan-agent; then
  echo ""
  echo "  ✓ Agent is running on port $AGENT_PORT"
  echo "  ✓ Auto-starts on boot"
  echo ""
  echo "  Test it: curl http://$(hostname -I | awk '{print $1}'):$AGENT_PORT/health"
  echo "  Add this node to Teletraan I dashboard:"
  echo "    IP:   $(hostname -I | awk '{print $1}')"
  echo "    Port: $AGENT_PORT"
  echo ""
else
  echo ""
  echo "  ✗ Agent failed to start. Check logs:"
  echo "    journalctl -u teletraan-agent -n 30"
  echo ""
  systemctl status teletraan-agent --no-pager || true
  exit 1
fi

# ── 8. Firewall ───────────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
  echo "  Opening port $AGENT_PORT in ufw..."
  ufw allow "$AGENT_PORT/tcp" comment "Teletraan Agent" >/dev/null
  echo "  ✓ Firewall rule added"
fi
