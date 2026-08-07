#!/usr/bin/env python3
"""Read or update Shadowbox's persistent HDMI mirror setting."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path


SETTING = "SHADOWBOX_DSI_HDMI_MIRROR"
DEFAULT_CONFIG_PATH = Path("/etc/default/shadowbox")
TRUE_VALUES = {"1", "true", "yes", "on"}


def config_path() -> Path:
    # Tests can target a temporary file as an unprivileged user. The installed
    # sudo helper always uses the fixed system path, even if an environment
    # variable is supplied by its caller.
    test_path = os.environ.get("SHADOWBOX_HDMI_MIRROR_TEST_CONFIG", "").strip()
    if os.geteuid() != 0 and test_path:
        return Path(test_path)
    return DEFAULT_CONFIG_PATH


def read_enabled(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"could not read {path}: {exc}") from exc
    value = "0"
    for line in lines:
        if line.startswith(f"{SETTING}="):
            value = line.split("=", 1)[1].strip()
    return value.lower() in TRUE_VALUES


def write_enabled(path: Path, enabled: bool) -> None:
    try:
        source = path.read_text(encoding="utf-8").splitlines()
        source_stat = path.stat()
    except OSError as exc:
        raise RuntimeError(f"could not read {path}: {exc}") from exc

    replacement = f"{SETTING}={1 if enabled else 0}"
    output: list[str] = []
    replaced = False
    for line in source:
        if line.startswith(f"{SETTING}="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(replacement)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IMODE(source_stat.st_mode))
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"enable", "disable", "status"}:
        print("Usage: hdmi_mirror_config.py <enable|disable|status>", file=sys.stderr)
        return 2

    path = config_path()
    command = argv[1]
    try:
        if command == "status":
            print("ENABLED" if read_enabled(path) else "DISABLED")
            return 0
        enabled = command == "enable"
        write_enabled(path, enabled)
        print("ENABLED" if enabled else "DISABLED")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
