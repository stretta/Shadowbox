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

REJECT_LABELS = {
    1: "STALE TRANSACTION",
    2: "NOTE COUNT",
    3: "ROW RANGE",
    4: "PROTOCOL",
    5: "ROW ORDER",
    6: "CHECKSUM",
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
    parsed = parse_shadowscore_ack(value)
    return parsed.get("opcode") if parsed else None


def parse_shadowscore_ack(value: Any) -> dict | None:
    values = numeric_list(value)
    if not values:
        return None
    ints = [int(number) for number in values if number.is_integer()]
    if len(ints) != len(values):
        return None
    offset = 1 if len(ints) > 1 and ints[0] == 90 and ints[1] in {1, 20, 90, 91, 92, 93} else 0
    opcode = ints[offset]
    fields = ints[offset + 1 :]
    if opcode not in {1, 20, 90, 91, 92, 93} or not fields:
        return None
    result = {"opcode": opcode, "transaction_id": fields[0]}
    if opcode == 1 and len(fields) >= 4:
        result.update({"phase": "receiving", "received": 0, "expected": fields[1], "pattern_length": fields[2], "stages_per_beat": fields[3]})
    elif opcode == 20 and len(fields) >= 4:
        result.update({"phase": "receiving", "note_index": fields[1], "received": fields[2], "ok": fields[3] == 1})
    elif opcode == 91 and len(fields) >= 4:
        result.update({"phase": "rejected", "reason": fields[1], "reason_label": REJECT_LABELS.get(fields[1], "UNKNOWN"), "received": fields[2], "ok": False})
    elif opcode in {90, 92} and len(fields) >= 3:
        result.update({"phase": "committed" if opcode == 90 else "ready", "received": fields[1], "expected": fields[1], "ok": fields[-1] == 1})
        if len(fields) >= 4:
            result["pattern_length"] = fields[2]
    elif opcode == 93 and len(fields) >= 4:
        result.update({"phase": "active", "pattern_length": fields[1], "stage": fields[2], "ok": fields[3] == 1})
    else:
        return None
    return result


def ack_label(value: Any) -> str:
    opcode = ack_opcode(value)
    return ACK_LABELS.get(opcode, "WAITING")


def transfer_status_label(status: dict | None) -> str:
    if not status:
        return "WAITING"
    phase = status.get("phase")
    received = status.get("received")
    expected = status.get("expected")
    progress = f"{received}/{expected}" if received is not None and expected is not None else str(received) if received is not None else ""
    if phase == "receiving":
        return f"RECEIVING {progress}".rstrip()
    if phase == "rejected":
        return f"REJECTED {status.get('reason_label', 'UNKNOWN')} {progress}".rstrip()
    if phase == "ready":
        return f"READY {progress}".rstrip()
    if phase == "committed":
        return f"COMMITTED {progress}".rstrip()
    if phase == "active":
        return "ACTIVE"
    return "WAITING"


def midi_note_label(pitch: int) -> str:
    value = max(0, min(127, int(pitch)))
    return f"{_NOTE_NAMES[value % 12]}{value // 12 - 1}"
