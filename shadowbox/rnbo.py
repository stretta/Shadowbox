"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

#!/usr/bin/env python3

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

    if not isinstance(params_root, dict):
        return results

    for name, node in params_root.items():
        if not isinstance(node, dict):
            continue

        access = node.get("ACCESS", None)
        if access not in (2, 3):
            continue

        info = extract_range_info(node)

        results.append(
            {
                "name": name,
                "path": node.get("FULL_PATH"),
                "value": node.get("VALUE"),
                "type": node.get("TYPE", ""),
                "min": info["min"],
                "max": info["max"],
                "vals": info["vals"],
            }
        )

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
