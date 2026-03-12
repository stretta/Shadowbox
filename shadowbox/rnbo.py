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

FALLBACK_PATCHES = ["chord", "moveparam"]


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class RNBOSnapshot:
    patches: list[str]
    current_patch: str
    params: list[dict]
    system: dict


# ============================================================
# LOW-LEVEL HELPERS
# ============================================================

def safe_get(node: Any, path: list[Any], default: Any = None) -> Any:
    cur = node
    try:
        for p in path:
            cur = cur[p]
        return cur
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


def should_keep_param(name: str, node: dict) -> bool:
    access = node.get("ACCESS", None)
    if access not in (2, 3):
        return False

    full_path = str(node.get("FULL_PATH", ""))
    if not full_path:
        return False

    lowered = str(name).lower()
    path_lowered = full_path.lower()

    # Keep nested user params like plate/mix, reverb/decay, osc1/detune.
    # Only reject clearly helper/internal variants.
    reject_exact = {
        "normalized",
        "raw",
        "meter",
        "signal",
    }

    reject_suffixes = (
        "/normalized",
        "/raw",
        "/meter",
        "/signal",
        "/out",
        "/in",
    )

    reject_contains = (
        "/meters/",
        "/meter/",
        "/signals/",
        "/signal/",
    )

    if lowered in reject_exact:
        return False

    if any(lowered.endswith(suffix) for suffix in reject_suffixes):
        return False

    if any(path_lowered.endswith(suffix) for suffix in reject_suffixes):
        return False

    if any(token in path_lowered for token in reject_contains):
        return False

    return True


# ============================================================
# DISCOVERY PARSERS
# ============================================================

def discover_patchers(tree: dict) -> list[str]:
    patchers = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "patchers", "CONTENTS"],
        {},
    )

    if isinstance(patchers, dict) and patchers:
        return sorted(patchers.keys(), key=str.lower)

    return FALLBACK_PATCHES[:]


def discover_current_patch(tree: dict) -> str:
    return safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS", "0", "CONTENTS", "name", "VALUE"],
        "",
    )


def discover_params(tree: dict) -> list[dict]:
    params_root = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS", "0", "CONTENTS", "params", "CONTENTS"],
        {},
    )

    results: list[dict] = []
    seen_paths: set[str] = set()

    def should_keep_editable_param(full_name: str, node: dict) -> bool:
        access = node.get("ACCESS")
        if access not in (2, 3):
            return False

        full_path = node.get("FULL_PATH")
        if not isinstance(full_path, str) or not full_path:
            return False

        lowered_name = str(full_name).lower()
        lowered_path = full_path.lower()

        reject_exact = {
            "meta",
            "normalized",
            "raw",
            "meter",
            "signal",
        }

        reject_suffixes = (
            "/meta",
            "/normalized",
            "/raw",
            "/meter",
            "/signal",
            "/out",
            "/in",
        )

        reject_contains = (
            "/meters/",
            "/signals/",
        )

        if lowered_name in reject_exact:
            return False

        if any(lowered_name.endswith(s) for s in reject_suffixes):
            return False

        if any(lowered_path.endswith(s) for s in reject_suffixes):
            return False

        if any(token in lowered_path for token in reject_contains):
            return False

        value = node.get("VALUE", None)
        ptype = node.get("TYPE", "")
        ranges = node.get("RANGE", None)
        contents = node.get("CONTENTS", None)

        has_value = "VALUE" in node and value is not None
        has_type = isinstance(ptype, str) and ptype != ""
        has_range = isinstance(ranges, list) and len(ranges) > 0
        has_children = isinstance(contents, dict) and len(contents) > 0

        # Skip pure container/group nodes.
        if has_children and not (has_value or has_type or has_range):
            return False

        # Must look like a real parameter.
        if not (has_value or has_type or has_range):
            return False

        # Ignore obvious command-like null nodes.
        if value is None and not has_range and not has_type:
            return False

        return True

    def walk_params(nodes: dict, prefix: str = "") -> None:
        if not isinstance(nodes, dict):
            return

        for name, node in nodes.items():
            if not isinstance(node, dict):
                continue

            full_name = f"{prefix}/{name}" if prefix else name

            if should_keep_editable_param(full_name, node):
                full_path = node.get("FULL_PATH")
                if full_path not in seen_paths:
                    seen_paths.add(full_path)

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
                        }
                    )

            child_nodes = node.get("CONTENTS")
            if isinstance(child_nodes, dict):
                walk_params(child_nodes, full_name)

    walk_params(params_root)
    results.sort(key=lambda x: x["name"].lower())
    return results

def discover_system(tree: dict) -> dict:
    card_node = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "card"],
        {},
    )
    card_info = extract_range_info(card_node)

    auto_start_node = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "inst", "CONTENTS", "config", "CONTENTS", "auto_start_last"],
        {},
    )

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
    sample_rate = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "sample_rate", "VALUE"],
        None,
    )
    period_frames = safe_get(
        tree,
        ["CONTENTS", "rnbo", "CONTENTS", "jack", "CONTENTS", "config", "CONTENTS", "period_frames", "VALUE"],
        None,
    )

    return {
        "audio": {
            "card_path": card_node.get("FULL_PATH", "/rnbo/jack/config/card"),
            "current_card": card_node.get("VALUE", ""),
            "card_options": card_info["vals"] or [],
            "sample_rate": sample_rate,
            "period_frames": period_frames,
        },
        "startup": {
            "auto_start_path": auto_start_node.get("FULL_PATH", "/rnbo/inst/config/auto_start_last"),
            "auto_start_last": auto_start_node.get("VALUE", False),
        },
        "status": {
            "cpu_load": cpu_load,
            "xruns": xruns,
        },
        "maint": {
            "jack_restart_path": "/rnbo/jack/restart",
        },
    }


# ============================================================
# RNBO CLIENT
# ============================================================

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

    # ----------------------------
    # OSC send helpers
    # ----------------------------

    def send_value(self, path: str, value: Any) -> None:
        print("send:", path, value)
        self.client.send_message(path, value)

    def send_trigger(self, path: str) -> None:
        print("trigger:", path)
        self.client.send_message(path, [])

    # ----------------------------
    # high-level commands
    # ----------------------------

    def load_patch(self, patch_name: str) -> None:
        print("load patch:", patch_name)
        self.client.send_message("/rnbo/inst/control/load", [0, patch_name])

    def set_param(self, path: str, value: Any) -> None:
        self.send_value(path, value)

    def set_audio_device(self, device_name: str, path: Optional[str] = None) -> None:
        if path is None:
            snapshot = self.discover()
            path = snapshot.system.get("audio", {}).get("card_path", "/rnbo/jack/config/card")
        self.send_value(path, device_name)

    def restart_jack(self, path: str = "/rnbo/jack/restart") -> None:
        self.send_trigger(path)

    def set_auto_start_last(self, enabled: bool, path: Optional[str] = None) -> None:
        if path is None:
            snapshot = self.discover()
            path = snapshot.system.get("startup", {}).get("auto_start_path", "/rnbo/inst/config/auto_start_last")
        self.send_value(path, enabled)

    # ----------------------------
    # OSCQuery fetch / parse
    # ----------------------------

    def fetch_tree(self) -> dict:
        with urllib.request.urlopen(self.oscquery_url, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover(self) -> RNBOSnapshot:
        try:
            tree = self.fetch_tree()
            return RNBOSnapshot(
                patches=discover_patchers(tree),
                current_patch=discover_current_patch(tree),
                params=discover_params(tree),
                system=discover_system(tree),
            )
        except Exception as e:
            print("OSCQuery discovery failed:", e)
            return RNBOSnapshot(
                patches=FALLBACK_PATCHES[:],
                current_patch="",
                params=[],
                system={
                    "audio": {
                        "card_path": "/rnbo/jack/config/card",
                        "current_card": "",
                        "card_options": [],
                        "sample_rate": None,
                        "period_frames": None,
                    },
                    "startup": {
                        "auto_start_path": "/rnbo/inst/config/auto_start_last",
                        "auto_start_last": False,
                    },
                    "status": {
                        "cpu_load": None,
                        "xruns": None,
                    },
                    "maint": {
                        "jack_restart_path": "/rnbo/jack/restart",
                    },
                },
            )