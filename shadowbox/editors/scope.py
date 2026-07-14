#!/usr/bin/env python3

from __future__ import annotations

import math
import re
from collections import deque
from typing import Any


SCOPE_EDITOR_NAMES = {"scope", "scope_display", "time_domain_scope"}
SCOPE_DEFAULT_STATE = "scope"
SCOPE_MAX_SAMPLES = 1024


class ScopeSampleBuffer(deque):
    """Bounded sample history with a cheap render-cache revision."""

    def __init__(self, values=(), *, maxlen: int = SCOPE_MAX_SAMPLES):
        super().__init__(values, maxlen=maxlen)
        self.revision = 0

    def extend_samples(self, values) -> None:
        super().extend(values)
        self.revision += 1

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self)[index]
        return super().__getitem__(index)

    def __eq__(self, other) -> bool:
        if isinstance(other, (list, tuple)):
            return list(self) == list(other)
        return super().__eq__(other)


def normalize_editor_name(value: Any) -> str:
    text = str(value or "").strip().strip("\"'")
    text = re.sub(r"[\s-]+", "_", text.lower())
    return text


def is_scope_param(param: dict | None) -> bool:
    if not isinstance(param, dict):
        return False
    metadata = param.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    return normalize_editor_name(metadata.get("editor", "")) in SCOPE_EDITOR_NAMES


def scope_state_key(param: dict | None) -> str:
    metadata = param.get("metadata", {}) if isinstance(param, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    value = metadata.get("scope_state", SCOPE_DEFAULT_STATE)
    return str(value).strip() or SCOPE_DEFAULT_STATE


def normalize_scope_samples(value: Any) -> list[float]:
    if value is None or value == "":
        return []
    if isinstance(value, bool):
        return []
    values = value if isinstance(value, (list, tuple)) else [value]

    samples: list[float] = []
    for item in values:
        if isinstance(item, bool):
            continue
        try:
            numeric = float(item)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        samples.append(max(-1.0, min(1.0, numeric)))
    return samples


def append_scope_samples(existing, value: Any, max_samples: int = SCOPE_MAX_SAMPLES) -> ScopeSampleBuffer:
    samples = normalize_scope_samples(value)
    if isinstance(existing, ScopeSampleBuffer) and existing.maxlen == max_samples:
        buffer = existing
    else:
        buffer = ScopeSampleBuffer(list(existing)[-max_samples:], maxlen=max_samples)
    if samples:
        buffer.extend_samples(samples)
    return buffer


def scope_time_seconds(sample_count: int, sample_rate: Any) -> float | None:
    try:
        rate = float(sample_rate)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rate) or rate <= 0:
        return None
    return max(0, int(sample_count)) / rate
