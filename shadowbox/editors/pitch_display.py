#!/usr/bin/env python3

from __future__ import annotations

import math
from typing import Any


def is_pitch_display_param(param: dict | None) -> bool:
    if not isinstance(param, dict):
        return False
    metadata = param.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("editor", "")).strip().lower() == "pitch_display"


def _state_key(metadata: dict[str, Any], name: str, default: str) -> str:
    value = metadata.get(name, default)
    return str(value).strip() or default


def pitch_state_key(param: dict | None) -> str:
    metadata = param.get("metadata", {}) if isinstance(param, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return _state_key(metadata, "pitch_state", "pitch_name")


def cents_state_key(param: dict | None) -> str:
    metadata = param.get("metadata", {}) if isinstance(param, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return _state_key(metadata, "cents_state", "pitch_cents")


def normalize_pitch_to_midi_note(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple)) and len(value) == 1:
        return normalize_pitch_to_midi_note(value[0])
    if value in (None, "", "-"):
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return int(round(numeric_value))
