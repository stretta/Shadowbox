#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STEP16_COUNT = 16
STEP16_MAX_MASK = (1 << STEP16_COUNT) - 1


@dataclass(frozen=True)
class Step16Cell:
    index: int
    active: bool
    focused: bool
    playing: bool


def is_step16_param(param: dict | None) -> bool:
    if not isinstance(param, dict):
        return False
    metadata = param.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("editor", "")).strip().lower() == "step16"


def normalize_mask(value: Any) -> int:
    if isinstance(value, list):
        value = value[0] if value else 0
    try:
        return int(value) & STEP16_MAX_MASK
    except Exception:
        return 0


def step_is_active(mask: int, step: int) -> bool:
    if step < 0 or step >= STEP16_COUNT:
        return False
    return bool((normalize_mask(mask) >> step) & 1)


def toggle_step(mask: int, step: int) -> int:
    if step < 0 or step >= STEP16_COUNT:
        return normalize_mask(mask)
    return normalize_mask(mask) ^ (1 << step)


def clamp_playhead(value: Any) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    try:
        playhead = int(value)
    except Exception:
        return None
    if playhead < 0 or playhead >= STEP16_COUNT:
        return None
    return playhead


def move_focus(current: int, delta: int) -> int:
    current = int(current) % STEP16_COUNT
    return (current + delta) % STEP16_COUNT


def build_cells(mask: int, focus_step: int, playhead: int | None) -> list[Step16Cell]:
    normalized_mask = normalize_mask(mask)
    focus_step = int(focus_step) % STEP16_COUNT
    playhead = clamp_playhead(playhead)
    return [
        Step16Cell(
            index=step,
            active=step_is_active(normalized_mask, step),
            focused=step == focus_step,
            playing=playhead == step,
        )
        for step in range(STEP16_COUNT)
    ]
