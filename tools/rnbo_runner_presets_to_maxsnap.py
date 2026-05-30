#!/usr/bin/env python3
"""
Convert RNBO Runner instance presets into Max rnbo~ .maxsnap files.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


OSCQUERY_URL = "http://127.0.0.1:5678"
OSC_PORT = 1234
MAXSNAP_HEADER = {
    "filetype": "C74Snapshot",
    "version": 2,
    "minorversion": 0,
    "type": "rnbo",
    "subtype": "",
    "embed": 0,
}


def safe_get(node: Any, path: list[Any], default: Any = None) -> Any:
    cur = node
    try:
        for part in path:
            cur = cur[part]
        return cur
    except Exception:
        return default


def pad_osc_bytes(data: bytes) -> bytes:
    return data + (b"\0" * ((4 - len(data) % 4) % 4))


def osc_string(value: str) -> bytes:
    return pad_osc_bytes(value.encode("utf-8") + b"\0")


def osc_message(path: str, value: Any) -> bytes:
    if isinstance(value, str):
        return osc_string(path) + osc_string(",s") + osc_string(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return osc_string(path) + osc_string(",i") + struct.pack(">i", value)
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return osc_string(path) + osc_string(",f") + struct.pack(">f", float(value))
    if value is None:
        return osc_string(path) + osc_string(",N")
    raise TypeError(f"unsupported OSC value type: {type(value).__name__}")


def send_osc_udp(host: str, port: int, path: str, value: Any) -> None:
    packet = osc_message(path, value)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, (host, port))


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


class RunnerTransport:
    def __init__(self, oscquery_url: str, osc_host: str, osc_port: int, ssh_host: str | None = None):
        self.oscquery_url = oscquery_url
        self.osc_host = osc_host
        self.osc_port = osc_port
        self.ssh_host = ssh_host

    def fetch_tree(self) -> dict[str, Any]:
        if self.ssh_host:
            command = f"curl -sS {shell_quote(self.oscquery_url)}"
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", self.ssh_host, command],
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout)

        with urllib.request.urlopen(self.oscquery_url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def send_value(self, path: str, value: Any) -> None:
        if self.ssh_host:
            payload = json.dumps({"host": self.osc_host, "port": self.osc_port, "path": path, "value": value})
            remote = (
                "python3 -c "
                + shell_quote(
                    "import json,socket,struct,sys;"
                    "p=json.loads(sys.stdin.read());"
                    "\n"
                    "def pad(b): return b + (b'\\0' * ((4 - len(b) % 4) % 4))\n"
                    "def s(v): return pad(v.encode('utf-8') + b'\\0')\n"
                    "v=p['value']\n"
                    "if isinstance(v, str): packet=s(p['path'])+s(',s')+s(v)\n"
                    "elif isinstance(v, int) and not isinstance(v, bool): packet=s(p['path'])+s(',i')+struct.pack('>i', v)\n"
                    "elif isinstance(v, (int, float)) and not isinstance(v, bool): packet=s(p['path'])+s(',f')+struct.pack('>f', float(v))\n"
                    "elif v is None: packet=s(p['path'])+s(',N')\n"
                    "else: raise SystemExit('unsupported OSC value')\n"
                    "sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.sendto(packet, (p['host'], int(p['port']))); sock.close()\n"
                )
            )
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", self.ssh_host, remote],
                input=payload,
                check=True,
                text=True,
                capture_output=True,
            )
            return

        send_osc_udp(self.osc_host, self.osc_port, path, value)


def find_instance(tree: dict[str, Any], instance_name: str) -> tuple[str, dict[str, Any]]:
    instances = safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS"], {})
    if not isinstance(instances, dict):
        raise ValueError("OSCQuery tree does not contain /rnbo/inst")

    matches: list[tuple[str, dict[str, Any]]] = []
    for instance_id, node in instances.items():
        if not str(instance_id).isdigit() or not isinstance(node, dict):
            continue
        name = safe_get(node, ["CONTENTS", "name", "VALUE"], "")
        jack_name = safe_get(node, ["CONTENTS", "jack", "CONTENTS", "name", "VALUE"], "")
        if instance_name in {str(name), str(jack_name), str(instance_id)}:
            matches.append((str(instance_id), node))

    if not matches:
        raise ValueError(f"no RNBO instance matched {instance_name!r}")
    if len(matches) > 1:
        ids = ", ".join(instance_id for instance_id, _ in matches)
        raise ValueError(f"instance name {instance_name!r} matched multiple instances: {ids}")
    return matches[0]


def range_vals(node: dict[str, Any]) -> list[Any]:
    ranges = node.get("RANGE")
    if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], dict):
        return []
    vals = ranges[0].get("VALS")
    return vals if isinstance(vals, list) else []


def param_value_for_snapshot(node: dict[str, Any]) -> Any:
    value = node.get("VALUE")
    vals = range_vals(node)
    if isinstance(value, str) and vals:
        try:
            return float(vals.index(value))
        except ValueError:
            return value
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return value


def collect_params(params_root: dict[str, Any]) -> dict[tuple[str, ...], Any]:
    collected: dict[tuple[str, ...], Any] = {}

    def walk(node: Any, parts: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        contents = node.get("CONTENTS")
        index_node = contents.get("index") if isinstance(contents, dict) else None
        if "TYPE" in node and "VALUE" in node and isinstance(index_node, dict):
            collected[parts] = param_value_for_snapshot(node)
            return
        if isinstance(contents, dict):
            for name, child in contents.items():
                if name in {"index", "display_name", "normalized", "meta"}:
                    continue
                walk(child, parts + (str(name),))

    walk(params_root, ())
    return collected


def snapshot_param_paths(snapshot: dict[str, Any]) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()

    def walk(node: Any, parts: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        if "value" in node and len(node) == 1:
            paths.add(parts)
            return
        sps = node.get("__sps")
        if isinstance(sps, dict):
            for name, child in sps.items():
                if isinstance(child, list):
                    continue
                walk(child, parts + (str(name),))
        for name, child in node.items():
            if name in {"__sps", "__presetid"}:
                continue
            walk(child, parts + (str(name),))

    walk(snapshot, ())
    return paths


def insert_snapshot_value(snapshot: dict[str, Any], parts: tuple[str, ...], value: Any) -> None:
    if not parts:
        return
    if len(parts) == 1:
        snapshot[parts[0]] = {"value": value}
        return

    sps = snapshot.setdefault("__sps", {})
    if not isinstance(sps, dict):
        snapshot["__sps"] = sps = {}
    cur = sps
    for part in parts[:-1]:
        child = cur.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            cur[part] = child
        cur = child
    cur[parts[-1]] = {"value": value}


def special_snapshot_values(template_snapshot: dict[str, Any], origin: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "__sps" in template_snapshot:
        out["__sps"] = copy.deepcopy(template_snapshot["__sps"])
    out["__presetid"] = template_snapshot.get("__presetid", origin)
    return out


def build_maxsnap(template: dict[str, Any], origin: str, preset_name: str, params: dict[tuple[str, ...], Any]) -> dict[str, Any]:
    template_snapshot = template.get("snapshot", {})
    if isinstance(template_snapshot, dict):
        snapshot = copy.deepcopy(template_snapshot)
    else:
        snapshot = special_snapshot_values({}, origin)
    snapshot["__presetid"] = snapshot.get("__presetid", origin)
    for parts, value in params.items():
        insert_snapshot_value(snapshot, parts, value)

    wrapper = dict(MAXSNAP_HEADER)
    wrapper.update(
        {
            "name": preset_name,
            "origin": origin,
            "snapshot": snapshot,
        }
    )
    return wrapper


def maxsnap_filename(name: str) -> str:
    safe = re.sub(r"[:/\\\\]+", "_", name).strip()
    return f"{safe or 'preset'}.maxsnap"


def load_and_wait(transport: RunnerTransport, load_path: str, loaded_path: str, preset_name: str, instance_name: str, timeout: float) -> dict[str, Any]:
    transport.send_value(load_path, preset_name)
    deadline = time.monotonic() + timeout
    latest = transport.fetch_tree()
    while time.monotonic() < deadline:
        latest = transport.fetch_tree()
        instance_id, instance = find_instance(latest, instance_name)
        loaded = safe_get(instance, ["CONTENTS", "presets", "CONTENTS", "loaded", "VALUE"], "")
        if loaded == preset_name:
            return latest
        time.sleep(0.15)
    raise TimeoutError(f"preset {preset_name!r} did not report loaded at {loaded_path!r}")


def convert_runner_presets(args: argparse.Namespace) -> int:
    template_path = Path(args.template).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    template = json.loads(template_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)

    transport = RunnerTransport(
        oscquery_url=args.oscquery_url,
        osc_host=args.osc_host,
        osc_port=args.osc_port,
        ssh_host=args.ssh_host,
    )

    tree = transport.fetch_tree()
    instance_id, instance = find_instance(tree, args.instance)
    origin = str(safe_get(instance, ["CONTENTS", "name", "VALUE"], args.instance) or args.instance)
    presets_root = safe_get(instance, ["CONTENTS", "presets", "CONTENTS"], {})
    entries = safe_get(presets_root, ["entries", "VALUE"], [])
    load_path = str(safe_get(presets_root, ["load", "FULL_PATH"], "") or "")
    loaded_path = str(safe_get(presets_root, ["loaded", "FULL_PATH"], "") or "")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"instance {origin!r} has no preset entries")
    if not load_path:
        raise ValueError(f"instance {origin!r} has no preset load path")

    template_paths = snapshot_param_paths(template.get("snapshot", {}))
    written: list[Path] = []
    seen_runner_paths: set[tuple[str, ...]] = set()
    for preset_name in entries:
        if not isinstance(preset_name, str) or not preset_name:
            continue
        loaded_tree = load_and_wait(transport, load_path, loaded_path, preset_name, args.instance, args.timeout)
        _, loaded_instance = find_instance(loaded_tree, args.instance)
        params_root = safe_get(loaded_instance, ["CONTENTS", "params"], {})
        params = collect_params(params_root)
        seen_runner_paths.update(params)
        maxsnap = build_maxsnap(template, origin, preset_name, params)
        output_path = output_dir / maxsnap_filename(preset_name)
        output_path.write_text(json.dumps(maxsnap, indent=4) + "\n")
        written.append(output_path)
        print(f"wrote {output_path}")

    extra = sorted("/".join(path) for path in seen_runner_paths - template_paths)
    missing = sorted("/".join(path) for path in template_paths - seen_runner_paths)
    print(f"converted {len(written)} presets from {origin} instance {instance_id}")
    if extra:
        print("runner params not present in template:")
        for name in extra:
            print(f"  + {name}")
    if missing:
        print("template params not present in runner:")
        for name in missing:
            print(f"  - {name}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True, help="RNBO instance name, JACK name, or instance id")
    parser.add_argument("--template", required=True, help="reference rnbo~ .maxsnap file")
    parser.add_argument("--output-dir", required=True, help="directory for generated .maxsnap files")
    parser.add_argument("--oscquery-url", default=OSCQUERY_URL, help="OSCQuery root URL")
    parser.add_argument("--osc-host", default="127.0.0.1", help="OSC UDP host")
    parser.add_argument("--osc-port", type=int, default=OSC_PORT, help="OSC UDP port")
    parser.add_argument("--ssh-host", help="fetch/send through ssh, e.g. pi@pt5.local")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for each preset load")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return convert_runner_presets(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
