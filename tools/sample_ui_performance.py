#!/usr/bin/env python3
"""Sample Shadowbox CPU/load/temperature and recent network-helper activity."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path


def _read_cpu_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
    return int(fields[13]) + int(fields[14])


def _temperature() -> str:
    try:
        return f"{int(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000:.1f}C"
    except (OSError, ValueError):
        return "-"


def _helper_count(since: str) -> int:
    try:
        result = subprocess.run(
            ["journalctl", "-u", "shadowbox.service", "--since", since, "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return sum(line.count("wifi_network.sh") + line.count("nmcli") for line in result.stdout.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, help="Shadowbox process id (defaults to systemctl MainPID)")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    pid = args.pid
    if not pid:
        result = subprocess.run(
            ["systemctl", "show", "shadowbox.service", "--property", "MainPID", "--value"],
            capture_output=True,
            text=True,
            check=False,
        )
        pid = int(result.stdout.strip() or "0")
    if pid <= 0:
        parser.error("shadowbox.service is not running; pass --pid")

    ticks_per_second = os.sysconf("SC_CLK_TCK")
    started = time.monotonic()
    previous_at = started
    previous_ticks = _read_cpu_ticks(pid)
    samples: list[float] = []
    print("elapsed cpu_percent load1 temperature")
    while time.monotonic() - started < args.seconds:
        time.sleep(max(0.1, args.interval))
        now = time.monotonic()
        ticks = _read_cpu_ticks(pid)
        cpu = ((ticks - previous_ticks) / ticks_per_second) / (now - previous_at) * 100.0
        samples.append(cpu)
        print(f"{now - started:7.1f} {cpu:10.1f} {os.getloadavg()[0]:5.2f} {_temperature()}")
        previous_at, previous_ticks = now, ticks
    helper_count = _helper_count(f"-{max(1, int(args.seconds) + 5)} seconds")
    print(f"summary avg_cpu={sum(samples) / len(samples):.1f}% max_cpu={max(samples):.1f}% network_helpers={helper_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
