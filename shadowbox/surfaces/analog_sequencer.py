#!/usr/bin/env python3

from __future__ import annotations

import re

from shadowbox.surfaces.base import ResolvedSurface


_STAGE_RE = re.compile(r"^0?([1-9]|1[0-6])Stage(Value|Step)$", re.IGNORECASE)


def resolve_analog_sequencer_bindings(instance: dict) -> ResolvedSurface | None:
    params: dict[str, dict] = {}
    for param in instance.get("params", []):
        name = str(param.get("name", ""))
        match = _STAGE_RE.fullmatch(name)
        if match:
            stage = int(match.group(1))
            role = "value" if match.group(2).lower() == "value" else "enabled"
            key = f"stage_{stage:02d}_{role}"
            if key in params:
                return None
            params[key] = param
        elif name in {
            "Scale",
            "ZeroVolts",
            "Swing",
            "Portamento",
            "Mode",
            "ClockInterval",
            "GateTime",
            "MaxCnt",
            "SwingAmt",
            "ClockRate",
            "Clock",
        }:
            params[name.lower()] = param

    required = {
        *(f"stage_{stage:02d}_value" for stage in range(1, 17)),
        *(f"stage_{stage:02d}_enabled" for stage in range(1, 17)),
        "maxcnt",
        "clock",
    }
    if not required.issubset(params):
        return None

    playheads = [
        item
        for item in instance.get("state", [])
        if str(item.get("name", "")).strip().lower().lstrip("/") == "current_stage"
        or str(item.get("path", "")).strip().lower().endswith("/current_stage")
    ]
    if len(playheads) != 1:
        return None
    return ResolvedSurface(
        str(instance.get("id", "")),
        params=params,
        state={"playhead": playheads[0]},
    )
