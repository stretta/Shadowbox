#!/usr/bin/env python3

from __future__ import annotations

from shadowbox.editors.scope import is_scope_param, scope_state_key
from shadowbox.surfaces.base import ResolvedSurface


def _find_state(instance: dict, key: str) -> dict | None:
    normalized = str(key).strip().lower().lstrip("/")
    for item in instance.get("state", []):
        name = str(item.get("name", "")).strip().lower().lstrip("/")
        path = str(item.get("path", "")).strip().lower()
        if name == normalized or path.endswith(f"/{normalized}"):
            return item
    return None


def resolve_time_domain_scope_bindings(instance: dict) -> ResolvedSurface | None:
    anchors = [param for param in instance.get("params", []) if is_scope_param(param)]
    if len(anchors) != 1:
        return None
    anchor = anchors[0]
    samples = _find_state(instance, scope_state_key(anchor))
    if samples is None:
        return None
    return ResolvedSurface(
        str(instance.get("id", "")),
        params={"sample_rate": anchor},
        state={"samples": samples},
    )
