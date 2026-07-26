#!/usr/bin/env python3

from __future__ import annotations

from shadowbox.surfaces.base import ResolvedSurface


FIELD_SPECS = (
    ("steps", "Steps", "Steps"),
    ("steps_secondary", "StepsSecondary", "Secondary Steps"),
    ("primary_rotation", "PrimaryRotation", "Primary Rotation"),
    ("secondary_rotation", "SecondaryRotation", "Secondary Rotation"),
    ("octave", "Oct", "Octave"),
    ("velocity", "Velocity", "Velocity"),
    ("duration", "Duration", "Duration"),
)

FIELD_KEYS = tuple(spec[0] for spec in FIELD_SPECS)
FIELD_LABELS = {key: label for key, _name, label in FIELD_SPECS}
FIELD_SHORT_LABELS = {
    "steps": "Stp",
    "steps_secondary": "Stp2",
    "primary_rotation": "Rot",
    "secondary_rotation": "Rot2",
    "octave": "Oct",
    "velocity": "Vel",
    "duration": "Dur",
}
SIGNED_FIELD_KEYS = frozenset({"primary_rotation", "secondary_rotation", "octave"})


def _normalized_name(value: object) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum())


def _items_by_name(items: object) -> dict[str, dict]:
    if not isinstance(items, list):
        return {}
    return {
        _normalized_name(item.get("name", "")): item
        for item in items
        if isinstance(item, dict) and item.get("name")
    }


def format_list_value(value: object) -> str:
    values = value if isinstance(value, list) else [value]
    formatted = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, bool):
            formatted.append("1" if item else "0")
        elif isinstance(item, float) and item.is_integer():
            formatted.append(str(int(item)))
        else:
            formatted.append(str(item))
    return " ".join(formatted)


def resolve_list_sequencer_bindings(instance: dict) -> ResolvedSurface | None:
    inputs_by_name = _items_by_name(instance.get("inputs"))
    state_by_name = _items_by_name(instance.get("state"))
    inputs: dict[str, dict] = {}
    state: dict[str, dict] = {}

    for key, inport_name, _label in FIELD_SPECS:
        input_item = inputs_by_name.get(_normalized_name(inport_name))
        if input_item is None:
            return None
        inputs[key] = input_item
        ack_item = state_by_name.get(_normalized_name(f"{inport_name}Ack"))
        if ack_item is not None:
            state[f"{key}_ack"] = ack_item

    return ResolvedSurface(
        instance_id=str(instance.get("id", "")),
        inputs=inputs,
        state=state,
    )
