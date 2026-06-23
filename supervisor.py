import json
import logging
import os
import platform
import shutil
import socket
import ssl
import time
import uuid

SUPERVISOR_HOST = os.getenv("SUPERVISOR_HOST", "10.62.206.206")
SUPERVISOR_PORT = int(os.getenv("SUPERVISOR_PORT", "8000"))

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")


def _get_system_metrics():
    cpu_logical = os.cpu_count() or 1
    cpu_physical = max(1, cpu_logical // 2)

    mem_total_mb = 16384
    mem_avail_mb = 8192
    mem_percent = 50.0
    mem_used_mb = 8192

    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            mem_total_mb = mem.ullTotalPhys // (1024 * 1024)
            mem_avail_mb = mem.ullAvailPhys // (1024 * 1024)
            mem_percent = mem.dwMemoryLoad
            mem_used_mb = mem_total_mb - mem_avail_mb
    except Exception:
        pass

    cpu_percent = 50.0
    load_1m = 1.0
    load_5m = 1.0
    uptime_seconds = 3600
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        uptime_ms = ctypes.c_ulonglong(0)
        kernel32.GetTickCount64(ctypes.byref(uptime_ms))
        uptime_seconds = uptime_ms.value // 1000
    except Exception:
        pass

    disk_total_gb = 100.0
    disk_free_gb = 50.0
    disk_percent_used = 50.0
    try:
        du = shutil.disk_usage(".")
        disk_total_gb = du.total / (1024 ** 3)
        disk_free_gb = du.free / (1024 ** 3)
        disk_percent_used = (du.total - du.free) / du.total * 100
    except Exception:
        pass

    return {
        "uptime_seconds": uptime_seconds,
        "load_average_1m": round(load_1m, 2),
        "load_average_5m": round(load_5m, 2),
        "cpu": {
            "usage_percent": round(cpu_percent, 2),
            "count_logical": cpu_logical,
            "count_physical": cpu_physical,
        },
        "memory": {
            "total_mb": mem_total_mb,
            "available_mb": mem_avail_mb,
            "percent_used": round(mem_percent, 2),
            "memory_used": mem_used_mb,
        },
        "disk": {
            "total_gb": round(disk_total_gb, 1),
            "free_gb": round(disk_free_gb, 1),
            "percent_used": round(disk_percent_used, 1),
        },
    }


def _resolve_peer_id(address, neighbors_map):
    for mid, naddr in neighbors_map.items():
        if naddr == address:
            return mid
    return address


def build_report(server_uuid, hostname, task_queue, workers,
                 borrowed_workers, lent_workers, neighbors,
                 capacity, release_threshold,
                 tasks_completed, tasks_failed, tasks_running,
                 task_timestamps):
    total_registered = len(workers)
    workers_alive = total_registered
    workers_home = total_registered - len(borrowed_workers)
    workers_idle = max(0, total_registered - tasks_running)
    workers_available_capacity = workers_idle

    borrowed_list = []
    for wid, addr in lent_workers.items():
        pid = _resolve_peer_id(addr, neighbors)
        borrowed_list.append({"direction": "out", "peer_uuid": pid})
    for wid, addr in borrowed_workers.items():
        pid = _resolve_peer_id(addr, neighbors)
        borrowed_list.append({"direction": "in", "peer_uuid": pid})

    tasks_pending = task_queue.qsize()
    oldest_task_age = 0
    if tasks_pending > 0 and task_timestamps:
        now = time.time()
        ages = [now - ts for ts in task_timestamps.values()]
        oldest_task_age = int(max(ages)) if ages else 0

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    neighbors_list = [
        {"server_uuid": mid, "status": "available", "last_heartbeat": ts}
        for mid in neighbors
    ]

    return {
        "server_uuid": server_uuid,
        "hostname": hostname,
        "role": "master",
        "task": "performance_report",
        "timestamp": ts,
        "message_id": str(uuid.uuid4()),
        "payload_version": "sprint4-monitor",
        "performance": {
            "system": _get_system_metrics(),
            "farm_state": {
                "workers": {
                    "total_registered": total_registered,
                    "workers_utilization": tasks_running,
                    "workers_alive": workers_alive,
                    "workers_idle": workers_idle,
                    "workers_borrowed": len(lent_workers),
                    "workers_received": len(borrowed_workers),
                    "workers_failed": 0,
                    "workers_home": workers_home,
                    "workers_available_capacity": workers_available_capacity,
                    "borrowed_workers": borrowed_list,
                },
                "tasks": {
                    "tasks_pending": tasks_pending,
                    "tasks_running": tasks_running,
                    "tasks_completed": tasks_completed,
                    "tasks_failed": tasks_failed,
                    "oldest_task_age_s": oldest_task_age,
                },
            },
            "config_thresholds": {
                "max_task": capacity,
                "warn_cpu_percent": 85,
                "warn_memory_percent": 85,
                "release_task": release_threshold,
            },
            "neighbors": neighbors_list,
        },
    }


def send_report(server_uuid, hostname, task_queue, workers,
                borrowed_workers, lent_workers, neighbors,
                capacity, release_threshold,
                tasks_completed, tasks_failed, tasks_running,
                task_timestamps, supervisor_host, supervisor_port,
                dashboard_url=None):
    try:
        payload = build_report(
            server_uuid, hostname, task_queue, workers,
            borrowed_workers, lent_workers, neighbors,
            capacity, release_threshold,
            tasks_completed, tasks_failed, tasks_running,
            task_timestamps,
        )

        data = json.dumps(payload).encode("utf-8")

        sock = socket.create_connection(
            (supervisor_host, supervisor_port),
            timeout=10
        )

        try:
            sock.sendall(data)

            logging.info(
                "supervisor report sent uuid=%s pending=%d running=%d completed=%d lent=%d borrowed=%d",
                server_uuid,
                task_queue.qsize(),
                tasks_running,
                tasks_completed,
                len(lent_workers),
                len(borrowed_workers),
            )

            # tentativa de resposta (opcional)
            try:
                response = sock.recv(4096)
                if response:
                    logging.info("supervisor response: %s", response)
            except socket.timeout:
                pass

        finally:
            sock.close()

        # ===== DASHBOARD =====
        url = dashboard_url or DASHBOARD_URL
        if url:
            try:
                host_port = url.replace("http://", "").replace("https://", "").split("/")[0]
                dhost, dport = host_port.split(":") if ":" in host_port else (host_port, "80")

                dsock = socket.create_connection((dhost, int(dport)), timeout=5)

                header = (
                    f"POST /api/report HTTP/1.1\r\n"
                    f"Host: {dhost}:{dport}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(data)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()

                dsock.sendall(header + data)
                dsock.recv(1024)
                dsock.close()

                logging.info("dashboard report sent to %s", url)

            except Exception as dex:
                logging.warning("dashboard report failed: %s", dex)

    except Exception as exc:
        logging.warning("supervisor report failed: %s", exc)
