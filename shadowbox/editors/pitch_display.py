#!/usr/bin/env python3

from __future__ import annotations

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
