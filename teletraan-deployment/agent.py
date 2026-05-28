#!/usr/bin/env python3
"""
TELETRAAN I — Node Agent
Runs on each machine. Exposes system stats as JSON on port 7071.
Deploy with: docker compose up -d teletraan-agent
Or bare-metal: pip install psutil flask flask-cors py-cpuinfo && python agent.py
"""

import os, json, platform, socket, subprocess, time
from flask import Flask, jsonify
from flask_cors import CORS

try:
    import psutil
except ImportError:
    os.system("pip install psutil flask flask-cors py-cpuinfo -q")
    import psutil

app = Flask(__name__)
CORS(app)

AGENT_PORT = int(os.environ.get("AGENT_PORT", 7071))
HOST_PROC   = os.environ.get("HOST_PROC", "/proc")

# ── Helpers ────────────────────────────────────────────────────────────────

def safe(fn, default=None):
    try: return fn()
    except Exception: return default

def get_hostname():
    """Try to get OEM machine name, fall back to hostname."""
    name = socket.gethostname()
    # Linux: try DMI product name (works on most OEM laptops/desktops)
    for path in ["/sys/class/dmi/id/product_name", "/host/sys/class/dmi/id/product_name"]:
        try:
            v = open(path).read().strip()
            if v and v.lower() not in ("", "to be filled by o.e.m.", "system product name",
                                        "none", "default string", "not specified"):
                return {"hostname": name, "oem_name": v}
        except Exception:
            pass
    return {"hostname": name, "oem_name": None}

def get_cpu():
    freq = safe(lambda: psutil.cpu_freq())
    return {
        "percent": psutil.cpu_percent(interval=0.5),
        "per_cpu": psutil.cpu_percent(interval=0.5, percpu=True),
        "freq_current": round(freq.current / 1000, 2) if freq else None,
        "freq_max":     round(freq.max / 1000, 2)     if freq else None,
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical":  psutil.cpu_count(logical=True),
        "model": platform.processor() or "Unknown",
        "arch": platform.machine(),
    }

def get_cpu_temp():
    temps = {}
    try:
        all_temps = psutil.sensors_temperatures()
        for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
            if key in all_temps:
                readings = all_temps[key]
                temps["cpu"] = round(readings[0].current, 1)
                temps["cores"] = [round(r.current, 1) for r in readings]
                break
        if not temps:
            for k, v in all_temps.items():
                if v:
                    temps["cpu"] = round(v[0].current, 1)
                    break
    except Exception:
        pass
    return temps

def get_gpu():
    result = {"present": False, "igpu": False, "name": "Unknown", "temp": None, "load": None, "vram_used": None, "vram_total": None}
    # Try NVIDIA
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        result.update({
            "present": True, "igpu": False,
            "name": pynvml.nvmlDeviceGetName(h),
            "temp": pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU),
            "load": pynvml.nvmlDeviceGetUtilizationRates(h).gpu,
            "vram_used":  pynvml.nvmlDeviceGetMemoryInfo(h).used  // (1024*1024),
            "vram_total": pynvml.nvmlDeviceGetMemoryInfo(h).total // (1024*1024),
        })
        return result
    except Exception: pass
    # Try AMD via sysfs
    try:
        gpu_temp_path = "/sys/class/drm/card0/device/hwmon/hwmon0/temp1_input"
        if os.path.exists(gpu_temp_path):
            temp = int(open(gpu_temp_path).read().strip()) / 1000
            name_path = "/sys/class/drm/card0/device/hwmon/hwmon0/name"
            name = open(name_path).read().strip() if os.path.exists(name_path) else "AMD iGPU"
            result.update({"present": True, "igpu": True, "name": name, "temp": round(temp, 1)})
            return result
    except Exception: pass
    # Intel iGPU via sensors
    try:
        all_temps = psutil.sensors_temperatures()
        for key in ("iwlwifi_1", "pch_cannonlake", "acpitz"):
            if key in all_temps:
                result.update({"present": True, "igpu": True, "name": "Intel iGPU", "temp": round(all_temps[key][0].current, 1)})
                return result
    except Exception: pass
    return result

def get_npu():
    """Detect NPU — AMD XDNA, Intel NPU, etc."""
    result = {"present": False, "name": None, "load": None, "tops": None}
    # AMD XDNA (Ryzen AI)
    try:
        out = subprocess.check_output(["lspci"], text=True, timeout=3)
        if "signal processing" in out.lower() or "xdna" in out.lower():
            result.update({"present": True, "name": "AMD XDNA NPU", "tops": 38})
    except Exception: pass
    # Intel VPU
    try:
        out = subprocess.check_output(["lspci"], text=True, timeout=3)
        if "vpu" in out.lower() or "meteor lake" in out.lower():
            result.update({"present": True, "name": "Intel VPU NPU", "tops": 11})
    except Exception: pass
    return result

def get_ram():
    v = psutil.virtual_memory()
    s = psutil.swap_memory()
    # Try to get ZFS ARC size from /proc/spl/kstat/zfs/arcstats
    arc_gib = 0
    try:
        with open('/proc/spl/kstat/zfs/arcstats') as f:
            for line in f:
                if line.startswith('size '):
                    arc_bytes = int(line.split()[2])
                    arc_gib = round(arc_bytes / (1024**3), 2)
                    break
    except Exception:
        pass
    return {
        "total":     round(v.total / (1024**3), 1),
        "used":      round(v.used  / (1024**3), 1),
        "available": round(v.available / (1024**3), 1),
        "percent":   v.percent,
        "cached":    round(getattr(v, "cached", 0) / (1024**3), 1),
        "arc_gib":   arc_gib,
        "swap_total": round(s.total / (1024**3), 1),
        "swap_used":  round(s.used  / (1024**3), 1),
        "swap_percent": s.percent,
    }

def get_drives():
    drives = []
    partitions = safe(psutil.disk_partitions, [])
    seen_devices = set()
    for p in partitions:
        if p.device in seen_devices: continue
        if any(x in p.fstype for x in ("squash", "overlay", "tmpfs", "devtmpfs")): continue
        seen_devices.add(p.device)
        usage = safe(lambda: psutil.disk_usage(p.mountpoint))
        if not usage: continue
        drive = {
            "device": p.device,
            "mountpoint": p.mountpoint,
            "fstype": p.fstype,
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb":  round(usage.used  / (1024**3), 1),
            "percent":  usage.percent,
            "model": get_drive_model(p.device),
            "temp":  get_drive_temp(p.device),
            "health": get_drive_health(p.device),
            "is_nvme": "nvme" in p.device.lower(),
            "rpm": get_drive_rpm(p.device),
        }
        drives.append(drive)
    return drives

def get_drive_model(device):
    base = os.path.basename(device).rstrip("0123456789")
    for path in [f"/sys/block/{base}/device/model", f"/host/sys/block/{base}/device/model"]:
        try: return open(path).read().strip()
        except: pass
    return "Unknown"

def get_drive_temp(device):
    try:
        base = os.path.basename(device).rstrip("0123456789")
        out = subprocess.check_output(
            ["smartctl", "-A", f"/dev/{base}"], text=True, timeout=5, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Temperature_Celsius" in line or "Temperature" in line:
                parts = line.split()
                return int(parts[-1]) if parts else None
    except Exception: pass
    return None

def get_drive_health(device):
    try:
        base = os.path.basename(device).rstrip("0123456789")
        out = subprocess.check_output(
            ["smartctl", "-H", f"/dev/{base}"], text=True, timeout=5, stderr=subprocess.DEVNULL)
        if "PASSED" in out or "OK" in out: return "OK"
        if "FAILED" in out: return "FAIL"
    except Exception: pass
    return "N/A"

def get_drive_rpm(device):
    try:
        base = os.path.basename(device).rstrip("0123456789")
        out = subprocess.check_output(
            ["smartctl", "-A", f"/dev/{base}"], text=True, timeout=5, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Rotation_Rate" in line:
                parts = line.split()
                for p in reversed(parts):
                    try: return int(p)
                    except: pass
    except Exception: pass
    return 0  # 0 = SSD/NVMe

def get_network():
    counters = psutil.net_io_counters(pernic=True)
    ifaces = {}
    for iface, stats in counters.items():
        if iface == "lo": continue
        ifaces[iface] = {
            "bytes_sent": stats.bytes_sent,
            "bytes_recv": stats.bytes_recv,
        }
    return ifaces

def get_processes():
    procs = []
    for p in sorted(psutil.process_iter(["pid","name","cpu_percent","memory_percent"]),
                    key=lambda x: -(x.info["cpu_percent"] or 0))[:10]:
        procs.append({
            "pid": p.info["pid"],
            "name": p.info["name"],
            "cpu": round(p.info["cpu_percent"] or 0, 1),
            "mem": round(p.info["memory_percent"] or 0, 1),
        })
    return procs

def get_zfs_pools():
    """Get ZFS pool info via zpool command."""
    pools = []
    try:
        out = subprocess.check_output(
            ["zpool", "list", "-H", "-p", "-o", "name,size,alloc,free,capacity,health"],
            text=True, timeout=5)
        for line in out.strip().splitlines():
            parts = line.split('\t')
            if len(parts) < 6: continue
            name, size_b, alloc_b, free_b, cap, health = parts
            try:
                size_gib  = round(int(size_b)  / (1024**3), 2)
                alloc_gib = round(int(alloc_b) / (1024**3), 2)
                free_gib  = round(int(free_b)  / (1024**3), 2)
                pct = round(int(alloc_b) / int(size_b) * 100, 1) if int(size_b) > 0 else 0
            except Exception:
                size_gib = alloc_gib = free_gib = pct = 0
            # Get vdev topology
            vdev_type = "ZFS"
            try:
                vstatus = subprocess.check_output(
                    ["zpool", "status", name], text=True, timeout=5)
                for vl in vstatus.splitlines():
                    vl = vl.strip().lower()
                    if 'raidz2' in vl: vdev_type = 'RAIDZ2'; break
                    if 'raidz1' in vl or 'raidz ' in vl: vdev_type = 'RAIDZ1'; break
                    if 'mirror' in vl: vdev_type = 'Mirror'; break
                    if 'stripe' in vl: vdev_type = 'Stripe'; break
            except Exception:
                pass
            pools.append({
                "name": name, "type": "zfs",
                "size_gib": size_gib, "alloc_gib": alloc_gib,
                "free_gib": free_gib, "percent": pct,
                "health": health.strip(), "vdev": vdev_type,
            })
    except Exception:
        pass
    return pools


    try:
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--format",
             '{"name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}"}'],
            text=True, timeout=5)
        containers = []
        for line in out.strip().splitlines():
            try: containers.append(json.loads(line))
            except: pass
        return containers
    except Exception:
        return []

# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/stats")
def stats():
    return jsonify({
        "identity": get_hostname(),
        "cpu":      get_cpu(),
        "cpu_temp": get_cpu_temp(),
        "gpu":      get_gpu(),
        "npu":      get_npu(),
        "ram":      get_ram(),
        "drives":   get_drives(),
        "network":  get_network(),
        "processes": get_processes(),
        "uptime":   int(time.time() - psutil.boot_time()),
        "os": {
            "system":  platform.system(),
            "release": platform.release(),
            "version": platform.version()[:60],
        },
        "zfs_pools": get_zfs_pools(),
        "timestamp": int(time.time()),
    })

@app.route("/docker")
def docker():
    return jsonify({"containers": get_docker_containers()})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "hostname": socket.gethostname()})

@app.route("/")
def index():
    return jsonify({"service": "teletraan-agent", "version": "2.0"})

if __name__ == "__main__":
    print(f"[TELETRAAN AGENT] Starting on port {AGENT_PORT}")
    app.run(host="0.0.0.0", port=AGENT_PORT, threaded=True)
