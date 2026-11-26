"""DeskBuddy PC Agent.

Run this script on your laptop/PC when `deskbuddy_backend` is deployed on the
cloud (e.g., Railway). It collects local foreground window activity, system
metrics (CPU/RAM/GPU), and music status, then continuously pushes them to the
cloud backend so your wireless DeskBuddy companion reflects your PC in real-time.
"""

import argparse
import ctypes
import os
import platform
import sys
import time
from typing import Any, Dict, Tuple

try:
    import psutil
except ImportError:
    print("psutil required: pip install psutil")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("requests required: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Windows user32 helpers
# ---------------------------------------------------------------------------
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


def _windows_user32():
    if platform.system() != "Windows":
        return None
    try:
        return ctypes.windll.user32
    except Exception:
        return None


def get_idle_seconds() -> float:
    user32 = _windows_user32()
    if user32 is None:
        return 0.0
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        tick_count = user32.GetTickCount() & 0xFFFFFFFF
        elapsed = (tick_count - info.dwTime) & 0xFFFFFFFF
        return max(0.0, elapsed / 1000.0)
    except Exception:
        return 0.0


def get_foreground_window() -> Tuple[str, str, int]:
    user32 = _windows_user32()
    if user32 is None:
        return "", "", 0
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", "", 0
        length = int(user32.GetWindowTextLengthW(hwnd))
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = int(pid.value)
        app_name = ""
        if pid_val:
            try:
                app_name = psutil.Process(pid_val).name()
            except Exception:
                app_name = ""
        return app_name, title_buffer.value, pid_val
    except Exception:
        return "", "", 0


def collect_metrics() -> Dict[str, Any]:
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        return {
            "cpu_percent": cpu,
            "memory_percent": mem,
            "gpu_percent": 0.0,
            "cpu_temp_c": -1,
        }
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="DeskBuddy Cloud PC Agent")
    parser.add_argument(
        "--url",
        default=os.getenv(
            "BACKEND_URL",
            "https://industrial-inspection-maintenance-x-desk-buddy-n-production.up.railway.app",
        ),
        help="Backend base URL",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("AGENT_TOKEN", ""),
        help="Shared agent token (optional)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Push interval in seconds",
    )
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/api/v1/companion/pc-state"
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["x-agent-token"] = args.token

    print("=" * 60)
    print("  DeskBuddy Cloud PC Agent")
    print(f"  Target: {endpoint}")
    print("  Streaming PC activity to cloud...")
    print("=" * 60)

    # Initial cpu call to prime psutil
    psutil.cpu_percent(interval=None)

    consecutive_errors = 0
    while True:
        try:
            app, title, pid = get_foreground_window()
            idle = get_idle_seconds()
            metrics = collect_metrics()

            payload = {
                "app": app,
                "window": title,
                "pid": pid,
                "idle_seconds": round(idle, 1),
                "audio_active": False,
                "metrics": metrics,
            }

            resp = requests.post(endpoint, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                consecutive_errors = 0
                print(
                    f"\r[OK] App: {app[:20]:<20} | Idle: {idle:>5.1f}s | CPU: {metrics.get('cpu_percent', 0):>4.1f}%",
                    end="",
                    flush=True,
                )
            else:
                consecutive_errors += 1
                if consecutive_errors % 5 == 1:
                    print(f"\n[WARN] Server returned HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors % 5 == 1:
                print(f"\n[ERR] Push failed: {exc}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
