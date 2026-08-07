#!/usr/bin/env python3
"""Perform the fixed, installer-authorized Shadowbox system power action."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable


SYSTEMCTL = "/usr/bin/systemctl"


def reboot_system(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    result = run([SYSTEMCTL, "reboot"], check=False)
    return int(result.returncode)


def main(argv: list[str]) -> int:
    if argv[1:] != ["reboot"]:
        print("Usage: system_power.py reboot", file=sys.stderr)
        return 2
    try:
        return reboot_system()
    except OSError as exc:
        print(f"could not reboot: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
