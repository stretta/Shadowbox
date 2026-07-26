#!/usr/bin/env python3

from __future__ import annotations


CLOCK_PARAM_NAMES = ("Clock", "Swing", "ClockInterval", "SwingAmt")
CLOCK_PARAM_KEYS = {name: name.lower() for name in CLOCK_PARAM_NAMES}


def clock_param_leaf(name: object) -> str | None:
    parts = [part for part in str(name).split("/") if part]
    if len(parts) == 1 and parts[0] in CLOCK_PARAM_KEYS:
        return parts[0]
    if len(parts) == 2 and parts[0] == "Clock" and parts[1] in CLOCK_PARAM_KEYS:
        return parts[1]
    return None


def resolve_clock_bindings(params: object) -> dict[str, dict] | None:
    if not isinstance(params, list):
        return None

    bindings: dict[str, dict] = {}
    for param in params:
        if not isinstance(param, dict):
            continue
        leaf = clock_param_leaf(param.get("name", ""))
        if leaf is None:
            continue
        key = CLOCK_PARAM_KEYS[leaf]
        if key in bindings:
            return None
        bindings[key] = param

    required = set(CLOCK_PARAM_KEYS.values())
    return bindings if required.issubset(bindings) else None
