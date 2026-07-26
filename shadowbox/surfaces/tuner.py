#!/usr/bin/env python3

from __future__ import annotations

from shadowbox.editors.pitch_display import cents_state_key, is_pitch_display_param, pitch_state_key
from shadowbox.surfaces.base import ResolvedSurface


def _find_state(instance: dict, key: str) -> dict | None:
    normalized = str(key).strip().lower().lstrip("/")
    for item in instance.get("state", []):
        name = str(item.get("name", "")).strip().lower().lstrip("/")
        path = str(item.get("path", "")).strip().lower()
        if name == normalized or path.endswith(f"/{normalized}"):
            return item
    return None


def resolve_tuner_bindings(instance: dict) -> ResolvedSurface | None:
    anchors = [param for param in instance.get("params", []) if is_pitch_display_param(param)]
    anchor = anchors[0] if len(anchors) == 1 else None
    pitch = _find_state(instance, pitch_state_key(anchor)) if anchor else None
    cents = _find_state(instance, cents_state_key(anchor)) if anchor else None
    if pitch is None:
        pitch = _find_state(instance, "pitch") or _find_state(instance, "pitch_name")
    if cents is None:
        cents = _find_state(instance, "cents") or _find_state(instance, "pitch_cents")
    if pitch is None or cents is None:
        return None
    params = {"anchor": anchor} if anchor else {}
    return ResolvedSurface(
        str(instance.get("id", "")),
        params=params,
        state={"pitch": pitch, "cents": cents},
    )
