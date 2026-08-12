#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

from shadowbox.surfaces.base import ResolvedSurface


REQUIRED_STATE = (
    "current_stage",
    "playback_debug",
    "midi_debug",
    "shadowscore_ack",
)

ACK_LABELS = {
    90: "COMMITTED",
    91: "REJECTED",
    92: "READY",
    93: "ACTIVE",
}

_NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


def _leaf_name(item: dict) -> str:
    name = str(item.get("name", "") or "").strip().strip("/")
    return name.rsplit("/", 1)[-1].lower()


def resolve_shadowscore_client_bindings(instance: dict) -> ResolvedSurface | None:
    matches: dict[str, list[dict]] = {key: [] for key in REQUIRED_STATE}
    for item in instance.get("state", []):
        key = _leaf_name(item)
        if key in matches:
            matches[key].append(item)
    if any(len(matches[key]) != 1 for key in REQUIRED_STATE):
        return None
    return ResolvedSurface(
        str(instance.get("id", "")),
        state={key: matches[key][0] for key in REQUIRED_STATE},
    )


def numeric_list(value: Any) -> list[float] | None:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        value = [value]
    result: list[float] = []
    for item in value:
        if isinstance(item, bool):
            return None
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            return None
    return result


def parse_current_stage(value: Any) -> int | None:
    values = numeric_list(value)
    if not values:
        return None
    stage = values[0]
    if not stage.is_integer() or stage < 0:
        return None
    return int(stage)


def parse_playback_debug(value: Any) -> dict | None:
    values = numeric_list(value)
    if values is None or len(values) < 3:
        return None
    opcode, stage_value, count_value = values[:3]
    if int(opcode) != 30 or opcode != int(opcode):
        return None
    if stage_value < 0 or not stage_value.is_integer():
        return None
    if count_value < 0 or not count_value.is_integer():
        return None
    note_count = int(count_value)
    expected = 3 + note_count * 3
    if len(values) != expected:
        return None
    notes = []
    for index in range(note_count):
        pitch, duration, velocity = values[3 + index * 3 : 6 + index * 3]
        if not all(number.is_integer() for number in (pitch, duration, velocity)):
            return None
        if not (0 <= pitch <= 127 and duration >= 0 and 0 <= velocity <= 127):
            return None
        notes.append({"pitch": int(pitch), "duration": int(duration), "velocity": int(velocity)})
    return {"stage": int(stage_value), "note_count": note_count, "notes": notes}


def parse_midi_debug(value: Any) -> dict | None:
    values = numeric_list(value)
    if values is None or len(values) != 3:
        return None
    pitch_value, velocity_value, duration_ms = values
    if not pitch_value.is_integer() or not velocity_value.is_integer():
        return None
    pitch = int(pitch_value)
    velocity = int(velocity_value)
    if not (0 <= pitch <= 127 and 0 <= velocity <= 127 and duration_ms >= 0):
        return None
    return {"pitch": pitch, "velocity": velocity, "duration_ms": duration_ms}


def ack_opcode(value: Any) -> int | None:
    values = numeric_list(value)
    if not values:
        return None
    ints = [int(number) for number in values if number.is_integer()]
    if len(ints) != len(values):
        return None
    if len(ints) > 1 and ints[0] == 90 and ints[1] in {91, 92, 93}:
        return ints[1]
    return ints[0] if ints[0] in ACK_LABELS else None


def ack_label(value: Any) -> str:
    opcode = ack_opcode(value)
    return ACK_LABELS.get(opcode, "WAITING")


def midi_note_label(pitch: int) -> str:
    value = max(0, min(127, int(pitch)))
    return f"{_NOTE_NAMES[value % 12]}{value // 12 - 1}"
