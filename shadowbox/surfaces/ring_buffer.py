#!/usr/bin/env python3

from __future__ import annotations

import math
from typing import Any

from shadowbox.surfaces.base import ResolvedSurface


OVERVIEW_COLUMNS = 800
OVERVIEW_VALUES_PER_CHUNK = 50
OVERVIEW_COLUMNS_PER_CHUNK = OVERVIEW_VALUES_PER_CHUNK // 2
OVERVIEW_CHUNK_COUNT = OVERVIEW_COLUMNS // OVERVIEW_COLUMNS_PER_CHUNK
OVERVIEW_MESSAGE_LENGTH = OVERVIEW_VALUES_PER_CHUNK + 1
BUFFER_DURATION_SECONDS = 10.0
RING_PARAM_KEYS = ("rate", "position", "grain_duration", "transpose", "record_toggle")


def _normalized_name(value: object) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum())


def _unique_named_item(items: object, name: str) -> dict | None:
    if not isinstance(items, list):
        return None
    normalized = _normalized_name(name)
    matches = [
        item
        for item in items
        if isinstance(item, dict) and _normalized_name(item.get("name", "")) == normalized
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_ring_buffer_bindings(instance: dict) -> ResolvedSurface | None:
    trigger = _unique_named_item(instance.get("inputs"), "itriggeroverview")
    sync_request = _unique_named_item(instance.get("inputs"), "getrecordsync")
    chunks = _unique_named_item(instance.get("state"), "overviewchunks")
    record_sync = _unique_named_item(instance.get("state"), "recordsync")
    params = {
        "rate": _unique_named_item(instance.get("params"), "Rate"),
        "position": _unique_named_item(instance.get("params"), "Position"),
        "grain_duration": _unique_named_item(instance.get("params"), "GrainDuration"),
        "transpose": _unique_named_item(instance.get("params"), "Transpose"),
        "record_toggle": _unique_named_item(instance.get("params"), "RecordToggle"),
    }
    if trigger is None or sync_request is None or chunks is None or record_sync is None or any(
        param is None for param in params.values()
    ):
        return None
    return ResolvedSurface(
        instance_id=str(instance.get("id", "")),
        params={key: param for key, param in params.items() if param is not None},
        state={"overview_chunks": chunks, "record_sync": record_sync},
        inputs={"request_overview": trigger, "request_record_sync": sync_request},
    )


def normalize_record_sync(value: Any) -> float | None:
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return None
        value = value[0]
    if isinstance(value, bool):
        return None
    try:
        phase = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(phase) or phase < 0.0 or phase > 1.0:
        return None
    return phase


def projected_record_sync(
    phase: float | None,
    *,
    recording: bool,
    elapsed_seconds: float,
    duration_seconds: float = BUFFER_DURATION_SECONDS,
) -> float | None:
    if phase is None:
        return None
    if not recording or duration_seconds <= 0:
        return phase
    return (phase + max(0.0, float(elapsed_seconds)) / duration_seconds) % 1.0


def rotate_overview_columns(
    columns: list[tuple[float, float] | None],
    phase: float | None,
) -> list[tuple[float, float] | None]:
    if not columns or phase is None:
        return list(columns)
    # record~ sync identifies the column currently being written.  Starting
    # there puts the preceding, newly completed column at the right edge, so
    # advancing sync makes the waveform move left underneath that edge.
    write_index = int(max(0.0, min(1.0, float(phase))) * len(columns)) % len(columns)
    return list(columns[write_index:]) + list(columns[:write_index])


def empty_overview_columns() -> list[tuple[float, float] | None]:
    return [None] * OVERVIEW_COLUMNS


def normalize_overview_chunk(value: Any) -> tuple[int, list[tuple[float, float]]] | None:
    if not isinstance(value, (list, tuple)) or len(value) != OVERVIEW_MESSAGE_LENGTH:
        return None
    try:
        raw_index = float(value[0])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(raw_index) or raw_index != int(raw_index):
        return None
    chunk_index = int(raw_index)
    if chunk_index < 1 or chunk_index > OVERVIEW_CHUNK_COUNT:
        return None

    samples: list[float] = []
    for item in value[1:]:
        if isinstance(item, bool):
            return None
        try:
            sample = float(item)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(sample):
            return None
        samples.append(max(-1.0, min(1.0, sample)))

    pairs: list[tuple[float, float]] = []
    for minimum, maximum in zip(samples[0::2], samples[1::2]):
        if minimum > maximum:
            return None
        pairs.append((minimum, maximum))
    return chunk_index, pairs


def apply_overview_chunk(
    columns: list[tuple[float, float] | None],
    received: set[int],
    value: Any,
) -> bool:
    parsed = normalize_overview_chunk(value)
    if parsed is None or len(columns) != OVERVIEW_COLUMNS:
        return False
    chunk_index, pairs = parsed
    start = (chunk_index - 1) * OVERVIEW_COLUMNS_PER_CHUNK
    columns[start : start + OVERVIEW_COLUMNS_PER_CHUNK] = pairs
    received.add(chunk_index)
    return True


def overview_columns_for_width(
    columns: list[tuple[float, float] | None],
    width: int,
) -> list[tuple[float, float] | None]:
    width = max(0, int(width))
    if width <= 0 or not columns:
        return []
    result: list[tuple[float, float] | None] = []
    count = len(columns)
    for pixel in range(width):
        start = (pixel * count) // width
        end = max(start + 1, ((pixel + 1) * count + width - 1) // width)
        known = [pair for pair in columns[start:min(count, end)] if pair is not None]
        if known:
            result.append((min(pair[0] for pair in known), max(pair[1] for pair in known)))
        else:
            result.append(None)
    return result
