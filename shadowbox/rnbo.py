#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from pythonosc.udp_client import SimpleUDPClient


RNBO_HOST = "127.0.0.1"
RNBO_PORT = 1234
OSCQUERY_URL = "http://127.0.0.1:5678"


@dataclass
class RNBOSnapshot:
    instances: list[dict]
    patchers: list[str]
    add_instance_path: str
    remove_instance_path: str
    system: dict


def safe_get(node: Any, path: list[Any], default: Any = None) -> Any:
    cur = node
    try:
        for part in path:
            cur = cur[part]
        return cur
        # pragma: no cover - defensive lookup helper
    except Exception:
        return default


def extract_range_info(node: dict) -> dict:
    out = {"min": None, "max": None, "vals": None}
    ranges = node.get("RANGE", None)
    if not isinstance(ranges, list) or not ranges:
        return out

    first = ranges[0]
    if not isinstance(first, dict):
        return out

    if "VALS" in first and isinstance(first["VALS"], list):
        out["vals"] = first["VALS"]
    if "MIN" in first:
        out["min"] = first["MIN"]
    if "MAX" in first:
        out["max"] = first["MAX"]
    return out


def extract_meta_info(node: dict) -> dict[str, Any]:
    contents = node.get("CONTENTS", {})
    if not isinstance(contents, dict):
        return {}

    metadata: dict[str, Any] = {}

    meta_node = contents.get("meta", {})
    if isinstance(meta_node, dict):
        raw_value = meta_node.get("VALUE", "")
        if isinstance(raw_value, str) and raw_value.strip():
            raw_value = raw_value.strip()
            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
                elif isinstance(parsed, list):
                    metadata["tags"] = [str(item).strip() for item in parsed if str(item).strip()]
                elif isinstance(parsed, str) and parsed.strip():
                    metadata["tags"] = [parsed.strip()]
            except Exception:
                metadata["tags"] = [raw_value]

    # RNBO exports may also publish UI hints as direct scalar children such as
    # `editor`, `display_name`, or `ui_role` rather than a JSON blob in `meta`.
    for child_name, child_node in contents.items():
        if child_name == "meta" or not isinstance(child_node, dict):
            continue
        if "VALUE" not in child_node:
            continue
        value = child_node.get("VALUE")
        if isinstance(value, (str, int, float, bool)):
            metadata[str(child_name)] = value

    return metadata


def should_keep_param(name: str, node: dict) -> bool:
    access = node.get("ACCESS", None)
    if access not in (2, 3):
        return False

    full_path = str(node.get("FULL_PATH", ""))
    if not full_path:
        return False

    lowered = str(name).lower()
    path_lowered = full_path.lower()

    reject_exact = {"meta", "normalized", "raw", "meter", "signal", "display_name", "index"}
    reject_suffixes = (
        "/meta",
        "/normalized",
        "/raw",
        "/meter",
        "/signal",
        "/display_name",
        "/index",
        "/out",
        "/in",
    )
    reject_contains = ("/meters/", "/meter/", "/signals/", "/signal/")

    if lowered in reject_exact:
        return False
    if any(lowered.endswith(suffix) for suffix in reject_suffixes):
        return False
    if any(path_lowered.endswith(suffix) for suffix in reject_suffixes):
        return False
    if any(token in path_lowered for token in reject_contains):
        return False

    value = node.get("VALUE", None)
    ptype = node.get("TYPE", "")
    ranges = node.get("RANGE", None)
    contents = node.get("CONTENTS", None)

    has_value = "VALUE" in node and value is not None
    has_type = isinstance(ptype, str) and ptype != ""
    has_range = isinstance(ranges, list) and len(ranges) > 0
    has_children = isinstance(contents, dict) and len(contents) > 0

    if has_children and not (has_value or has_type or has_range):
        return False
    if not (has_value or has_type or has_range):
        return False
    if value is None and not has_range and not has_type:
        return False
    return True


def _discover_instance_params(instance_root: dict) -> list[dict]:
    params_root = safe_get(instance_root, ["params", "CONTENTS"], {})
    results: list[dict] = []
    seen_paths: set[str] = set()

    def walk(nodes: dict, prefix: str = "") -> None:
        if not isinstance(nodes, dict):
            return

        for name, node in nodes.items():
            if not isinstance(node, dict):
                continue

            full_name = f"{prefix}/{name}" if prefix else name
            if should_keep_param(full_name, node):
                full_path = node.get("FULL_PATH")
                if isinstance(full_path, str) and full_path and full_path not in seen_paths:
                    info = extract_range_info(node)
                    results.append(
                        {
                            "name": full_name,
                            "path": full_path,
                            "value": node.get("VALUE"),
                            "type": node.get("TYPE", ""),
                            "min": info["min"],
                            "max": info["max"],
                            "vals": info["vals"],
                            "metadata": extract_meta_info(node),
                        }
                    )
                    seen_paths.add(full_path)

            child_nodes = node.get("CONTENTS")
            if isinstance(child_nodes, dict):
                walk(child_nodes, full_name)

    walk(params_root)
    results.sort(key=lambda item: str(item.get("name", "")).lower())
    return results


def _discover_instance_presets(instance_root: dict) -> list[dict]:
    presets_root = safe_get(instance_root, ["presets", "CONTENTS"], {})
    entries_node = safe_get(presets_root, ["entries"], {})
    load_node = safe_get(presets_root, ["load"], {})

    entries = entries_node.get("VALUE", [])
    load_path = load_node.get("FULL_PATH", "")

    if not isinstance(entries, list) or not isinstance(load_path, str) or not load_path:
        return []

    presets: list[dict] = []
    for entry in entries:
        if isinstance(entry, str) and entry:
            presets.append(
                {
                    "name": entry,
                    "path": load_path,
                    "value": entry,
                }
            )
    return presets


def _discover_instance_state(instance_root: dict) -> list[dict]:
    results: list[dict] = []
    seen_paths: set[str] = set()

    def walk(nodes: dict, prefix: str = "") -> None:
        if not isinstance(nodes, dict):
            return

        for name, node in nodes.items():
            if not isinstance(node, dict):
                continue

            full_name = f"{prefix}/{name}" if prefix else str(name)
            full_path = node.get("FULL_PATH")
            if isinstance(full_path, str) and full_path and full_path not in seen_paths and "VALUE" in node:
                info = extract_range_info(node)
                results.append(
                    {
                        "name": full_name,
                        "path": full_path,
                        "value": node.get("VALUE"),
                        "type": node.get("TYPE", ""),
                        "min": info["min"],
                        "max": info["max"],
                        "vals": info["vals"],
                        "metadata": extract_meta_info(node),
                    }
                )
                seen_paths.add(full_path)

            child_nodes = node.get("CONTENTS")
            if isinstance(child_nodes, dict):
                walk(child_nodes, full_name)

    state_roots = [
        ("", safe_get(instance_root, ["state", "CONTENTS"], {})),
        ("", safe_get(instance_root, ["messages", "CONTENTS", "out", "CONTENTS"], {})),
        ("", safe_get(instance_root, ["messages", "CONTENTS", "out", "CONTENTS", "state", "CONTENTS"], {})),
    ]
    for prefix, root in state_roots:
        walk(root, prefix)

    results.sort(key=lambda item: str(item.get("name", "")).lower())
    return results


def _routing_port(name: str, node: dict, targets: list[str]) -> dict:
    value = node.get("VALUE", [])
    if not isinstance(value, list):
        value = [value] if value not in ("", None) else []
    return {
        "name": name,
        "path": node.get("FULL_PATH", ""),
        "connections": value,
        "targets": list(targets),
    }


def _discover_routing_ports(connections_root: dict, direction: str, targets: list[str]) -> list[dict]:
    ports_root = safe_get(connections_root, [direction, "CONTENTS"], {})
    ports: list[dict] = []
    if not isinstance(ports_root, dict):
        return ports

    for name, node in sorted(ports_root.items(), key=lambda item: str(item[0]).lower()):
        if isinstance(node, dict):
            ports.append(_routing_port(str(name), node, targets))
    return ports


def _discover_instance_routing(instance_root: dict, system_ports: dict) -> dict:
    jack_root = safe_get(instance_root, ["jack", "CONTENTS"], {})
    connections_root = safe_get(jack_root, ["connections", "CONTENTS"], {})

    audio_sources = system_ports.get("audio_sources", [])
    audio_sinks = system_ports.get("audio_sinks", [])
    midi_sources = system_ports.get("midi_sources", [])
    midi_sinks = system_ports.get("midi_sinks", [])

    return {
        "audio": {
            "inputs": _discover_routing_ports(
                safe_get(connections_root, ["audio", "CONTENTS"], {}),
                "sinks",
                audio_sources,
            ),
            "outputs": _discover_routing_ports(
                safe_get(connections_root, ["audio", "CONTENTS"], {}),
                "sources",
                audio_sinks,
            ),
        },
        "midi": {
            "inputs": _discover_routing_ports(
                safe_get(connections_root, ["midi", "CONTENTS"], {}),
                "sinks",
                midi_sources,
            ),
            "outputs": _discover_routing_ports(
                safe_get(connections_root, ["midi", "CONTENTS"], {}),
                "sources",
                midi_sinks,
            ),
        },
    }


def _instance_label(instance_root: dict, instance_id: str) -> str:
    alias = safe_get(instance_root, ["config", "CONTENTS", "name_alias", "VALUE"], "")
    name = safe_get(instance_root, ["name", "VALUE"], "")
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    if isinstance(name, str) and name.strip():
        return name.strip()
    return f"instance {instance_id}"


def _system_ports(tree: dict) -> dict:
    return {
        "audio_sinks": safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "ports", "CONTENTS", "audio", "CONTENTS", "sinks", "VALUE"], []),
        "audio_sources": safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "ports", "CONTENTS", "audio", "CONTENTS", "sources", "VALUE"], []),
        "midi_sinks": safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "ports", "CONTENTS", "midi", "CONTENTS", "sinks", "VALUE"], []),
        "midi_sources": safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "ports", "CONTENTS", "midi", "CONTENTS", "sources", "VALUE"], []),
    }


def discover_instances(tree: dict) -> list[dict]:
    inst_root = safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS"], {})
    system_ports = _system_ports(tree)
    instances: list[dict] = []

    if not isinstance(inst_root, dict):
        return instances

    for instance_id, instance_node in sorted(inst_root.items(), key=lambda item: str(item[0])):
        if not str(instance_id).isdigit():
            continue
        if not isinstance(instance_node, dict):
            continue

        contents = instance_node.get("CONTENTS", {})
        if not isinstance(contents, dict):
            continue

        instances.append(
            {
                "id": str(instance_id),
                "label": _instance_label(contents, str(instance_id)),
                "name": safe_get(contents, ["name", "VALUE"], ""),
                "params": _discover_instance_params(contents),
                "state": _discover_instance_state(contents),
                "presets": _discover_instance_presets(contents),
                "routing": _discover_instance_routing(contents, system_ports),
            }
        )

    return instances


def discover_patchers(tree: dict) -> list[str]:
    patchers_root = safe_get(tree, ["CONTENTS", "rnbo", "CONTENTS", "patchers", "CONTENTS"], {})
    if not isinstance(patchers_root, dict):
        return []
    return sorted([str(name) for name in patchers_root.keys()], key=str.lower)


def discover_add_instance_path(tree: dict) -> str:
    value = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS", "control", "CONTENTS", "load", "FULL_PATH"],
        "",
    )
    return str(value) if value is not None else ""


def discover_remove_instance_path(tree: dict) -> str:
    value = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS", "control", "CONTENTS", "unload", "FULL_PATH"],
        "",
    )
    return str(value) if value is not None else ""


def discover_system(tree: dict) -> dict:
    card_node = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "card"],
        {},
    )
    card_info = extract_range_info(card_node)
    period_frames_node = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "period_frames"],
        {},
    )
    period_frames_info = extract_range_info(period_frames_node)
    sample_rate_node = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "sample_rate"],
        {},
    )
    sample_rate_info = extract_range_info(sample_rate_node)

    cpu_load = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "cpu_load", "VALUE"],
        None,
    )
    xruns = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "info", "CONTENTS", "xrun_count", "VALUE"],
        None,
    )
    sample_rate = sample_rate_node.get("VALUE", None)
    period_frames = period_frames_node.get("VALUE", None)
    runner_version = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "info", "CONTENTS", "runner_version", "VALUE"],
        "",
    )
    jack_restart_path = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "restart", "FULL_PATH"],
        "",
    )

    return {
        "audio": {
            "card_path": card_node.get("FULL_PATH", "/rnbo/jack/config/card"),
            "current_card": card_node.get("VALUE", ""),
            "card_options": card_info["vals"] or [],
            "input_targets": _system_ports(tree).get("audio_sources", []),
            "output_targets": _system_ports(tree).get("audio_sinks", []),
            "sample_rate_path": sample_rate_node.get("FULL_PATH", "/rnbo/jack/config/sample_rate"),
            "sample_rate": sample_rate,
            "sample_rate_options": sample_rate_info["vals"] or [],
            "sample_rate_min": sample_rate_info["min"],
            "sample_rate_max": sample_rate_info["max"],
            "period_frames_path": period_frames_node.get("FULL_PATH", "/rnbo/jack/config/period_frames"),
            "period_frames": period_frames,
            "period_frames_options": period_frames_info["vals"] or [],
        },
        "status": {
            "cpu_load": cpu_load,
            "xruns": xruns,
            "runner_version": runner_version,
        },
        "maint": {
            "jack_restart_path": str(jack_restart_path) if jack_restart_path is not None else "",
        },
    }


class RNBOClient:
    def __init__(
        self,
        host: str = RNBO_HOST,
        port: int = RNBO_PORT,
        oscquery_url: str = OSCQUERY_URL,
    ):
        self.host = host
        self.port = port
        self.oscquery_url = oscquery_url
        self.client = SimpleUDPClient(self.host, self.port)

    def send_value(self, path: str, value: Any) -> None:
        print("send:", path, value)
        self.client.send_message(path, value)

    def send_trigger(self, path: str) -> None:
        print("trigger:", path)
        self.client.send_message(path, [])

    def set_param(self, path: str, value: Any) -> None:
        self.send_value(path, value)

    def set_audio_device(self, device_name: str, path: Optional[str] = None) -> None:
        if path is None:
            snapshot = self.discover()
            path = snapshot.system.get("audio", {}).get("card_path", "/rnbo/jack/config/card")
        self.send_value(path, device_name)

    def restart_jack(self, path: str) -> None:
        if not path:
            return
        self.send_trigger(path)

    def fetch_tree(self) -> dict:
        with urllib.request.urlopen(self.oscquery_url, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover(self) -> RNBOSnapshot:
        try:
            tree = self.fetch_tree()
            return RNBOSnapshot(
                instances=discover_instances(tree),
                patchers=discover_patchers(tree),
                add_instance_path=discover_add_instance_path(tree),
                remove_instance_path=discover_remove_instance_path(tree),
                system=discover_system(tree),
            )
        except Exception as e:
            print("OSCQuery discovery failed:", e)
            return RNBOSnapshot(
                instances=[],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={
                    "audio": {
                        "card_path": "/rnbo/jack/config/card",
                        "current_card": "",
                        "card_options": [],
                        "input_targets": [],
                        "output_targets": [],
                        "sample_rate_path": "/rnbo/jack/config/sample_rate",
                        "sample_rate": None,
                        "sample_rate_options": [],
                        "sample_rate_min": None,
                        "sample_rate_max": None,
                        "period_frames_path": "/rnbo/jack/config/period_frames",
                        "period_frames": None,
                        "period_frames_options": [],
                    },
                    "status": {
                        "cpu_load": None,
                        "xruns": None,
                        "runner_version": "",
                    },
                    "maint": {
                        "jack_restart_path": "",
                    },
                },
            )
