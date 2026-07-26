#!/usr/bin/env python3

from __future__ import annotations

from shadowbox.surfaces.base import ResolvedSurface


ROW_COUNT = 8
ROW_KEYS = tuple(f"row_{index}" for index in range(1, ROW_COUNT + 1))
ROW_LABELS = {key: str(index) for index, key in enumerate(ROW_KEYS, start=1)}


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


def _row_input(inputs_by_name: dict[str, dict], row: int) -> dict | None:
    canonical = inputs_by_name.get(f"{row}row")
    if canonical is not None:
        return canonical

    # Older ListVelSequencer exports shipped row 4 as `4ow`. Keep numeric
    # prefix matching narrow so those exports remain editable without letting
    # unrelated inports satisfy the surface contract.
    candidates = [
        item
        for name, item in inputs_by_name.items()
        if name.startswith(str(row)) and name.endswith(("row", "ow"))
    ]
    return candidates[0] if len(candidates) == 1 else None


def resolve_list_vel_sequencer_bindings(instance: dict) -> ResolvedSurface | None:
    params_by_name = _items_by_name(instance.get("params"))
    inputs_by_name = _items_by_name(instance.get("inputs"))
    state_by_name = _items_by_name(instance.get("state"))
    params: dict[str, dict] = {}
    inputs: dict[str, dict] = {}
    state: dict[str, dict] = {}

    for row, key in enumerate(ROW_KEYS, start=1):
        map_param = params_by_name.get(f"{row}map")
        input_item = _row_input(inputs_by_name, row)
        if map_param is None or input_item is None:
            return None
        params[f"{key}_map"] = map_param
        inputs[key] = input_item
        ack_item = state_by_name.get(f"{row}rowack")
        if ack_item is not None:
            state[f"{key}_ack"] = ack_item

    return ResolvedSurface(
        instance_id=str(instance.get("id", "")),
        params=params,
        inputs=inputs,
        state=state,
    )
