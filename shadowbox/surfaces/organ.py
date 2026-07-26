#!/usr/bin/env python3

from __future__ import annotations

import re

from shadowbox.surfaces.base import ResolvedSurface


FOOTAGES = ("16", "5_1_3", "8", "4", "2_2_3", "2", "1_3_5", "1_1_3", "1")
FOOTAGE_COLORS = ("brown", "brown", "white", "white", "black", "white", "black", "black", "white")


def _normalized_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _footage_for_param(param: dict) -> str | None:
    name = str(param.get("name", ""))
    normalized = _normalized_name(name.rsplit("/", 1)[-1])
    aliases = {
        "bass": "16",
        "quint": "5_1_3",
        "neutral": "8",
        "octave": "4",
        "nazard": "2_2_3",
        "blockflute": "2",
        "tierce": "1_3_5",
        "larigot": "1_1_3",
        "sifflute": "1",
        "drawbar16": "16",
        "drawbar513": "5_1_3",
        "drawbar8": "8",
        "drawbar4": "4",
        "drawbar223": "2_2_3",
        "drawbar2": "2",
        "drawbar135": "1_3_5",
        "drawbar113": "1_1_3",
        "drawbar1": "1",
    }
    return aliases.get(normalized)


def resolve_organ_bindings(instance: dict) -> ResolvedSurface | None:
    matches: dict[str, list[dict]] = {footage: [] for footage in FOOTAGES}
    for param in instance.get("params", []):
        footage = _footage_for_param(param)
        if footage:
            matches[footage].append(param)

    if any(len(matches[footage]) != 1 for footage in FOOTAGES):
        return None
    bindings = {footage: matches[footage][0] for footage in FOOTAGES}
    contracts = {(param.get("min"), param.get("max")) for param in bindings.values()}
    if contracts not in ({(-96, 0)}, {(0, 8)}):
        return None
    return ResolvedSurface(str(instance.get("id", "")), params=bindings)
