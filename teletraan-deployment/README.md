<div align="center">

```
╔══════════════════════════════════════════════════════╗
║   ████████╗███████╗██╗     ███████╗████████╗██████╗  ║
║      ██╔══╝██╔════╝██║     ██╔════╝╚══██╔══╝██╔══██╗ ║
║      ██║   █████╗  ██║     █████╗     ██║   ██████╔╝ ║
║      ██║   ██╔══╝  ██║     ██╔══╝     ██║   ██╔══██╗ ║
║      ██║   ███████╗███████╗███████╗   ██║   ██║  ██║ ║
║      ╚═╝   ╚══════╝╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝ ║
║          TRAAN  I  —  AUTOBOT COMMAND NETWORK        ║
╚══════════════════════════════════════════════════════╝
```

**A Transformers G1-themed homelab dashboard**  
Monitor nodes · Track Docker containers · Watch your network · Manage storage pools

[![License: MIT](https://img.shields.io/badge/License-MIT-cyan.svg)](LICENSE)
[![TrueNAS SCALE](https://img.shields.io/badge/TrueNAS-SCALE-blue)](https://www.truenas.com/truenas-scale/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-yellow)](https://python.org)

</div>

---

## Features

- **Multi-node monitoring** — CPU (per-thread), GPU/iGPU, NPU, RAM with ZFS ARC breakdown, drives with temps
- **Network watchdog** — alerts when a machine drops its Ethernet connection
- **Docker management** — view, start/stop containers across all nodes with quick-launch shortcuts
- **ZFS/TrueNAS storage** — auto-imports pool names, health, used/usable capacity in GiB/TiB
- **Multi-user auth** — per-user favorite sites, admin-controlled Docker visibility per user
- **HA failover** — backup node takes over serving the dashboard if TrueNAS goes down
- **No nginx required** — served by Python's built-in `http.server`
- **Pure HTML/JS** — single file dashboard, no build step, no npm, no framework

---

## Screenshots

> *Coming soon — contributions welcome*

---

## Quick Start

### 1. TrueNAS SCALE

Create a dataset for the dashboard files:
```
Storage → Add Dataset → Name: teletraan
```

Upload the files:
```bash
scp teletraan-dashboard.html truenas_admin@<truenas-ip>:/tmp/index.html
scp agent.py truenas_admin@<truenas-ip>:/tmp/agent.py
ssh truenas_admin@<truenas-ip>
sudo mv /tmp/index.html /mnt/<pool>/teletraan/index.html
sudo mv /tmp/agent.py /mnt/<pool>/teletraan/agent.py
```

Deploy via **Apps → Custom App → Install via YAML** — paste `truenas-app.yaml` with your pool path updated.

Dashboard available at: `http://<truenas-ip>:7070`

### 2. Each Ubuntu/Debian node

```bash
sudo bash deploy-agent.sh        # default port 7071
sudo bash deploy-agent.sh 7072   # if 7071 is already taken
```

### 3. Add nodes in the dashboard

Login with `admin / autobot`, click **+** in the sidebar, enter IP and agent port.  
Leave the name blank to auto-detect the OEM machine name.

---

## File Reference

| File | Purpose |
|---|---|
| `teletraan-dashboard.html` | Dashboard UI — rename to `index.html` on the host |
| `agent.py` | Node agent — exposes system stats as JSON on port 7071 |
| `truenas-app.yaml` | TrueNAS SCALE custom app definition |
| `deploy-agent.sh` | One-command agent installer for Ubuntu/Debian |
| `ha-failover.sh` | HA watcher — backup node serves dashboard if primary dies |
| `teletraan-ha.service` | Systemd unit for the HA watcher |

---

## Port Reference

| Service | Default Port | Configurable |
|---|---|---|
| Dashboard UI | 7070 | Yes — edit YAML |
| Node Agent | 7071 | Yes — `deploy-agent.sh <port>` |

Chosen specifically to avoid conflicts with common homelab ports (8080, 8443, 9000, 9443).

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `autobot` | Admin |

**Change these immediately in Admin → User Management after first login.**

---

## HA Failover (no keepalived needed)

On any backup Ubuntu machine:
```bash
sudo cp ha-failover.sh /opt/teletraan/
sudo cp teletraan-dashboard.html /opt/teletraan/index.html
# Edit teletraan-ha.service — set your TrueNAS IP
sudo cp teletraan-ha.service /etc/systemd/system/
sudo systemctl enable --now teletraan-ha
```

The watcher polls TrueNAS every 5 seconds. After 3 consecutive failures it starts serving the dashboard itself on port 7070. Steps down automatically when TrueNAS recovers.

---

## Updating from GitHub

On TrueNAS after cloning the repo:
```bash
cd /mnt/<pool>/teletraan
git pull
sudo docker restart teletraan-agent
```

---

## Contributing

Pull requests welcome. If you find a bug or want a feature, open an issue.

---

## License

MIT — do whatever you want with it.

---

<div align="center">
<sub>Built for the Autobot Command Network. Till all are one.</sub>
</div>
