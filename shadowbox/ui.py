#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from shadowbox.brick_panel import BRICK_PANEL_TRIGGER_PRESSES, BrickPanelGame
from shadowbox.editors.ttid import (
    apply_scale_to_mask,
    get_scale_names,
    is_ttid_param,
    normalize_ttid,
    toggle_bit,
)
from shadowbox.editors.pitch_display import (
    cents_state_key,
    is_pitch_display_param,
    pitch_state_key,
)
from shadowbox.editors.step16 import (
    clamp_playhead,
    is_step16_param,
    move_focus as move_step16_focus,
    normalize_mask as normalize_step16_mask,
    playhead_state_key,
    toggle_step as toggle_step16,
)
from shadowbox.rnbo import RNBO_PORT


STATE_PATH = Path.home() / "rnbo-ui" / "shadowbox_state.json"

ROUTING_GROUP_ITEMS = ["INPUTS", "OUTPUTS"]
SYSTEM_AUDIO_ITEMS = ["DEVICE", "SAMPLE RATE", "BUFFER SIZE"]
REMOVE_INSTANCE_CONFIRM_ITEMS = ["..", "REMOVE"]
MAINT_ITEMS_REFRESH = "REFRESH"
MAINT_ITEMS_RESTART_JACK = "RESTART JACK"
NAME_EDITOR_EDIT = "EDIT NAME"
NAME_EDITOR_GENERATE = "GENERATE NAME"
NAME_EDITOR_ADD_DATE = "ADD DATE"
NAME_EDITOR_DELETE = "DELETE CHAR"
NAME_EDITOR_CLEAR = "CLEAR NAME"
NAME_EDITOR_SAVE = "SAVE"
NAME_EDITOR_CANCEL = "CANCEL"
NAME_OVERWRITE_CONFIRM_ITEMS = ["..", "OVERWRITE"]
NAME_ERROR_DISMISS = "EDIT NAME"
NAME_EDITOR_MAX_LEN = 24
NAME_EDITOR_CHAR_OPTIONS: list[tuple[str, str]] = [
    ("SPACE", " "),
    ("-", "-"),
    ("_", "_"),
] + [(char, char) for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"]
NAME_INLINE_DELETE_LABEL = "DEL"
NEW_GRAPH_SET_NAME = "New Graph"


@dataclass
class UIAction:
    kind: str
    path: Optional[str] = None
    value: Any = None
    device_name: Optional[str] = None


@dataclass
class UIState:
    instances: list[dict] = field(default_factory=list)
    patchers: list[str] = field(default_factory=list)
    add_instance_path: str = ""
    remove_instance_path: str = ""
    system: dict = field(default_factory=dict)

    ui_mode: str = "TOP"
    top_index: int = 0
    instance_cursor: int = 0
    patcher_cursor: int = 0
    instance_menu_cursor: int = 0
    remove_instance_confirm_cursor: int = 0
    remove_instance_picker_cursor: int = 0
    preset_cursor: int = 0
    param_cursor: int = 0
    enum_cursor: int = 0
    routing_group_cursor: int = 0
    routing_port_cursor: int = 0
    routing_target_cursor: int = 0
    routing_overview_cursor: int = 0
    graph_menu_cursor: int = 0
    graph_set_cursor: int = 0
    graph_preset_cursor: int = 0
    graph_startup_cursor: int = 0
    graph_startup_set_cursor: int = 0
    system_cursor: int = 0
    system_audio_cursor: int = 0
    maint_cursor: int = 0
    audio_device_cursor: int = 0
    sample_rate_cursor: int = 0
    buffer_size_cursor: int = 0

    active_instance_id: str = ""
    active_transport: str = "audio"
    active_routing_direction: str = "inputs"
    patcher_picker_context: str = "add"
    pending_remove_instance_id: str = ""
    remove_instance_origin: str = ""

    edit_value: Any = None
    edit_ttid_mode: str = "keyboard"
    edit_ttid_selected_pc: int = 0
    edit_ttid_load_root: int = 0
    edit_ttid_scale_names: list[str] = field(default_factory=list)
    edit_ttid_scale_index: int = 0
    edit_step16_focus: int = 0
    name_editor_context: str = ""
    name_editor_return_mode: str = ""
    name_editor_path: str = ""
    name_editor_draft: str = ""
    name_editor_target_name: str = ""
    name_editor_cursor: int = 1
    name_inline_cursor: int = 0
    name_inline_edit_mode: bool = False
    name_inline_preview_index: int = 0
    name_overwrite_cursor: int = 1
    name_error_message: str = ""

    busy: bool = False
    busy_reason: str = ""
    activity_ticks: int = 0

    saved_audio_card: str = ""
    current_presets: dict[str, str] = field(default_factory=dict)


def load_state_file() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_state_file(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2))


def clamp_index(idx: int, count: int) -> int:
    if count <= 0:
        return 0
    return max(0, min(idx, count - 1))


def clamp(v: float, lo: Optional[float], hi: Optional[float]) -> float:
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value, 0)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return float(value)


def _metadata_dict(param: dict | None) -> dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    metadata = param.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _metadata_text(param: dict | None, key: str) -> str:
    value = _metadata_dict(param).get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _metadata_number(param: dict | None, key: str) -> float | None:
    value = _metadata_dict(param).get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            numeric = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def display_precision(param: dict | None) -> int | None:
    numeric = _metadata_number(param, "display_precision")
    if numeric is None:
        return None
    rounded = int(round(numeric))
    if rounded < 0 or abs(numeric - rounded) > 1e-9:
        return None
    return rounded


def display_as_int(param: dict | None) -> bool:
    return _metadata_text(param, "display_as").lower() == "int"


def edit_as_int(param: dict | None) -> bool:
    return _metadata_text(param, "edit_as").lower() == "int"


def edit_step(param: dict | None) -> float | None:
    numeric = _metadata_number(param, "edit_step")
    if numeric is None or numeric <= 0:
        return None
    return numeric


def is_boolish(param: dict) -> bool:
    metadata = param.get("metadata", {})

    if isinstance(metadata, dict):
        for key in ("bool", "is_bool", "boolean"):
            value = metadata.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes", "bool", "boolean"):
                return True

    return False


def numeric_step(param: dict) -> float:
    pmin = param.get("min")
    pmax = param.get("max")
    explicit_step = edit_step(param)

    if explicit_step is not None:
        return explicit_step

    if edit_as_int(param):
        return 1
    if pmin is not None and pmax is not None:
        span = abs(pmax - pmin)
        if span <= 0:
            return 0.01
        if span <= 1:
            return 0.01
        if span <= 10:
            return 0.05
        if span <= 100:
            return 0.5
        if span <= 1000:
            return 1.0
        return max(span / 128.0, 1.0)
    return 0.01


def normalize_current_value_for_edit(param: dict) -> Any:
    value = param.get("value")
    vals = param.get("vals")

    if vals:
        if isinstance(value, list) and value:
            value = value[0]
        if value in vals:
            return value
        return vals[0]

    if is_boolish(param):
        if isinstance(value, list) and value:
            value = value[0]
        return 1 if value else 0

    if isinstance(value, list):
        value = value[0] if value else 0

    if value is None:
        return param["min"] if param.get("min") is not None else 0
    if edit_as_int(param) and isinstance(value, (int, float)):
        return int(round(value))
    return value


def apply_edit_delta(param: dict, current_value: Any, delta: int) -> Any:
    vals = param.get("vals")

    if vals:
        if current_value not in vals:
            current_value = vals[0]
        idx = vals.index(current_value)
        return vals[(idx + delta) % len(vals)]

    if is_boolish(param):
        return 0 if bool(current_value) else 1

    step = numeric_step(param)
    if isinstance(current_value, (int, float)):
        if edit_as_int(param):
            current_value = int(round(current_value))
        new_value = current_value + (step * delta)
        if edit_as_int(param):
            new_value = int(round(new_value))
        return clamp(new_value, param.get("min"), param.get("max"))
    return current_value


def is_discrete_param(param: dict) -> bool:
    return is_boolish(param) or (isinstance(param.get("vals"), list) and len(param.get("vals")) > 0)


def is_enum_param(param: dict) -> bool:
    return (not is_boolish(param)) and isinstance(param.get("vals"), list) and len(param.get("vals")) > 0


@dataclass
class UIEvent:
    kind: str
    delta: int = 0


@dataclass
class MenuRow:
    label: str
    current: bool = False
    emphasis: str = ""
    action: bool = False


@dataclass
class ValueRow:
    label: str
    value: Any
    current: bool = False
    emphasis: str = ""


class ShadowboxUI:
    def __init__(self, rnbo=None):
        self.rnbo = rnbo
        self.state = UIState()
        self._actions: list[UIAction] = []
        self._saved_state_cache = load_state_file()
        self._edit_original_value: Any = None
        self.brick_panel = BrickPanelGame()
        self._about_press_count = 0
        self.float_edit_accel_fast_seconds = max(0.0, _env_float("SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS", 0.35))
        self.float_edit_accel_fast_multiplier = max(1, _env_int("SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER", 2))
        self.float_edit_accel_turbo_seconds = max(0.0, _env_float("SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS", 0.018))
        self.float_edit_accel_turbo_multiplier = max(1, _env_int("SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER", 3))
        self._last_float_edit_detent_at: float | None = None

    def _reset_float_edit_acceleration(self) -> None:
        self._last_float_edit_detent_at = None

    def _is_float_edit_param(self, param: dict | None) -> bool:
        return bool(
            param
            and not is_ttid_param(param)
            and not is_step16_param(param)
            and not is_pitch_display_param(param)
            and not is_discrete_param(param)
            and not edit_as_int(param)
        )

    def _accelerate_float_edit_delta(self, param: dict | None, delta: int) -> int:
        if delta == 0 or not self._is_float_edit_param(param):
            self._reset_float_edit_acceleration()
            return delta

        now = time.monotonic()
        multiplier = 1
        if self._last_float_edit_detent_at is not None:
            elapsed = now - self._last_float_edit_detent_at
            if self.float_edit_accel_turbo_seconds > 0 and elapsed <= self.float_edit_accel_turbo_seconds:
                multiplier = self.float_edit_accel_turbo_multiplier
            elif self.float_edit_accel_fast_seconds > 0 and elapsed <= self.float_edit_accel_fast_seconds:
                multiplier = self.float_edit_accel_fast_multiplier
        self._last_float_edit_detent_at = now
        return delta * multiplier

    def restore_from_saved_state(self) -> None:
        saved = self._saved_state_cache
        self.state.top_index = clamp_index(int(saved.get("top_index", 0)), len(self.top_level_items))
        self.state.saved_audio_card = str(saved.get("saved_audio_card", ""))

    def save_state(self) -> None:
        save_state_file(
            {
                "top_index": self.state.top_index,
                "saved_audio_card": self.current_audio_card,
            }
        )

    def reset_to_top(self) -> None:
        self.state.ui_mode = "TOP"
        self.state.top_index = 0
        self.state.instance_cursor = 1 if self.state.instances or self.can_add_instance or self.can_remove_instances else 0
        self.state.patcher_cursor = 1 if self.state.patchers else 0
        self.state.instance_menu_cursor = 1 if self.instance_menu_items else 0
        self.state.remove_instance_confirm_cursor = 1
        self.state.remove_instance_picker_cursor = 1 if self.state.instances else 0
        self.state.preset_cursor = 0
        self.state.param_cursor = 0
        self.state.enum_cursor = 0
        self.state.routing_group_cursor = 1
        self.state.routing_port_cursor = 0
        self.state.routing_target_cursor = 0
        self.state.routing_overview_cursor = 1 if self.state.instances else 0
        self.state.graph_menu_cursor = 1 if self.graph_menu_items else 0
        self.state.graph_set_cursor = 1 if self.available_set_names else 0
        self.state.graph_preset_cursor = self.graph_preset_initial_cursor()
        self.state.graph_startup_cursor = 1 if self.graph_startup_menu_items else 0
        self.state.graph_startup_set_cursor = 1 if self.available_set_names else 0
        self.state.system_cursor = 1
        self.state.system_audio_cursor = 1
        self.state.maint_cursor = 1 if self.maint_menu_items else 0
        self.state.audio_device_cursor = 1 if self.audio_options else 0
        self.state.sample_rate_cursor = 1 if self.sample_rate_options else 0
        self.state.buffer_size_cursor = 1 if self.buffer_size_options else 0
        self.state.active_instance_id = str(self.state.instances[0]["id"]) if self.state.instances else ""
        self.state.active_transport = "audio"
        self.state.active_routing_direction = "inputs"
        self.state.patcher_picker_context = "add"
        self.state.pending_remove_instance_id = ""
        self.state.remove_instance_origin = ""
        self.state.edit_value = None
        self.state.edit_ttid_mode = "keyboard"
        self.state.edit_ttid_selected_pc = 0
        self.state.edit_ttid_load_root = 0
        self.state.edit_ttid_scale_names = []
        self.state.edit_ttid_scale_index = 0
        self.state.edit_step16_focus = 0
        self.state.name_editor_context = ""
        self.state.name_editor_return_mode = ""
        self.state.name_editor_path = ""
        self.state.name_editor_draft = ""
        self.state.name_editor_target_name = ""
        self.state.name_editor_cursor = 1
        self.state.name_inline_cursor = 0
        self.state.name_inline_edit_mode = False
        self.state.name_inline_preview_index = 0
        self.state.name_overwrite_cursor = 1
        self.state.name_error_message = ""
        self._edit_original_value = None
        self._about_press_count = 0
        self._reset_float_edit_acceleration()
        self.brick_panel.reset()

    def set_busy(self, busy: bool, reason: str = "") -> None:
        self.state.busy = busy
        self.state.busy_reason = reason
        if busy:
            self.state.activity_ticks += 1

    def apply_runner_snapshot(self, snapshot) -> None:
        current_id = str(self.state.active_instance_id)
        current_param_path = self.selected_param.get("path") if self.selected_param else ""

        self.state.instances = snapshot.instances
        self.state.patchers = snapshot.patchers
        self.state.add_instance_path = snapshot.add_instance_path
        self.state.remove_instance_path = snapshot.remove_instance_path
        self.state.system = snapshot.system
        self._sync_audio_index()
        self._cleanup_current_presets()

        if self.state.instances:
            instance_ids = [str(item.get("id", "")) for item in self.state.instances]
            if current_id in instance_ids:
                self.state.active_instance_id = current_id
                self.state.instance_cursor = instance_ids.index(current_id) + 1
            else:
                self.state.active_instance_id = instance_ids[0]
                self.state.instance_cursor = 1
        else:
            self.state.active_instance_id = ""
            self.state.instance_cursor = 0
        self.state.instance_cursor = clamp_index(
            self.state.instance_cursor if self.state.instance_cursor > 0 else 1,
            len(self.state.instances) + 1 + (1 if self.can_add_instance else 0) + (1 if self.can_remove_instances else 0),
        )
        self.state.patcher_cursor = clamp_index(self.state.patcher_cursor if self.state.patcher_cursor > 0 else 1, len(self.state.patchers) + 1)
        self.state.instance_menu_cursor = clamp_index(self.state.instance_menu_cursor, len(self.instance_menu_items) + 1)
        self.state.remove_instance_picker_cursor = clamp_index(self.state.remove_instance_picker_cursor, len(self.state.instances) + 1)

        self.state.param_cursor = clamp_index(self.state.param_cursor, len(self.active_params) + 1)
        self.state.preset_cursor = clamp_index(self.state.preset_cursor, len(self.preset_menu_items))
        self.state.maint_cursor = clamp_index(self.state.maint_cursor, len(self.maint_menu_items) + 1)
        self.state.routing_port_cursor = clamp_index(self.state.routing_port_cursor, len(self.active_routing_ports) + 1)
        self.state.routing_target_cursor = clamp_index(self.state.routing_target_cursor, len(self.active_routing_targets) + 2)
        self.state.routing_overview_cursor = clamp_index(
            self.state.routing_overview_cursor if self.state.routing_overview_cursor > 0 else 1,
            len(self.routing_overview_rows),
        )
        self.state.graph_menu_cursor = clamp_index(self.state.graph_menu_cursor, len(self.graph_menu_items) + 1)
        self.state.graph_set_cursor = clamp_index(self.state.graph_set_cursor, len(self.available_set_names) + 1)
        self.state.graph_preset_cursor = clamp_index(self.state.graph_preset_cursor, len(self.graph_preset_menu_items))
        self.state.graph_startup_cursor = clamp_index(self.state.graph_startup_cursor, len(self.graph_startup_menu_items) + 1)
        self.state.graph_startup_set_cursor = clamp_index(self.state.graph_startup_set_cursor, len(self.available_set_names) + 1)

        if self.state.ui_mode == "EDIT" and self.selected_param:
            if current_param_path and self.selected_param.get("path") != current_param_path:
                self.state.ui_mode = "PARAM_LIST"
                self.state.edit_value = None
            elif is_ttid_param(self.selected_param):
                self.state.edit_value = normalize_ttid(self.state.edit_value)
            elif is_step16_param(self.selected_param):
                self.state.edit_value = normalize_step16_mask(self.state.edit_value)
            else:
                self.state.edit_value = normalize_current_value_for_edit(self.selected_param)

    def apply_instance_state_update(self, instance_id: str, path: str, value: Any) -> bool:
        instance_id = str(instance_id)
        path = str(path)
        if not instance_id or not path:
            return False

        for instance in self.state.instances:
            if str(instance.get("id", "")) != instance_id:
                continue
            for item in instance.get("state", []):
                if str(item.get("path", "")) == path:
                    item["value"] = value
                    return True
        return False

    def _cleanup_current_presets(self) -> None:
        valid_ids = {str(item.get("id", "")) for item in self.state.instances if str(item.get("id", ""))}
        self.state.current_presets = {
            instance_id: preset_name
            for instance_id, preset_name in self.state.current_presets.items()
            if instance_id in valid_ids and preset_name
        }

    @property
    def top_level_items(self) -> list[str]:
        return ["GRAPHS", "INSTANCES", "SYSTEM"]

    @property
    def instance_menu_items(self) -> list[str]:
        items = ["PARAMETERS", "PRESETS", "AUDIO", "MIDI"]
        if self.can_replace_instance:
            items.append("REPLACE INSTANCE")
        if self.can_remove_instance:
            items.append("REMOVE INSTANCE")
        return items

    @property
    def can_add_instance(self) -> bool:
        return bool(self.state.add_instance_path)

    @property
    def can_replace_instance(self) -> bool:
        return bool(self.active_instance and self.state.add_instance_path)

    @property
    def can_remove_instance(self) -> bool:
        return bool(self.active_instance and self.state.remove_instance_path)

    @property
    def can_remove_instances(self) -> bool:
        return bool(self.state.remove_instance_path)

    @property
    def can_restart_jack(self) -> bool:
        return bool(self.state.system.get("maint", {}).get("jack_restart_path"))

    @property
    def system_menu_items(self) -> list[str]:
        items = ["STATUS", "AUDIO", "NETWORK", "ABOUT"]
        if self.maint_menu_items:
            items.append("MAINT")
        return items

    @property
    def graph_menu_items(self) -> list[str]:
        items = ["CURRENT GRAPH", "LOAD GRAPH"]
        if self.new_graph_available:
            items.insert(1, "NEW GRAPH")
        items.extend(["AUDIO OVERVIEW", "MIDI OVERVIEW"])
        if self.graph_preset_menu_enabled:
            items.append("GRAPH PRESETS")
        if self.graph_save_path:
            items.append("SAVE GRAPH")
        if self.graph_rename_path and self.current_set_name != "(untitled)":
            items.append("RENAME GRAPH")
        items.append("STARTUP")
        return items

    @property
    def available_set_names(self) -> list[str]:
        sets = self.state.system.get("sets", {})
        names = sets.get("available_sets", []) if isinstance(sets, dict) else []
        return [str(item) for item in names if str(item)]

    @property
    def new_graph_available(self) -> bool:
        return bool(self.graph_load_path and NEW_GRAPH_SET_NAME in self.available_set_names)

    @property
    def graph_set_current_indices(self) -> set[int]:
        current_name = self.current_set_name
        return {
            idx + 1
            for idx, item in enumerate(self.available_set_names)
            if str(item) == current_name
        }

    @property
    def graph_set_item_weights(self) -> dict[int, str]:
        if not self.current_set_dirty:
            return {}
        return {
            idx: "italic"
            for idx in self.graph_set_current_indices
        }

    @property
    def graph_set_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        current_indices = self.graph_set_current_indices
        dirty_weights = self.graph_set_item_weights
        for idx, item in enumerate(self.available_set_names, start=1):
            rows.append(
                MenuRow(
                    str(item),
                    current=idx in current_indices,
                    emphasis="italic" if dirty_weights.get(idx) == "italic" else "",
                )
            )
        if len(rows) == 1:
            rows.append(MenuRow("no saved graphs"))
        return rows

    @property
    def set_presets(self) -> dict:
        presets = self.state.system.get("set_presets", {})
        return presets if isinstance(presets, dict) else {}

    @property
    def graph_preset_menu_enabled(self) -> bool:
        return bool(self.available_graph_preset_names or self.graph_preset_action_items)

    @property
    def available_graph_preset_names(self) -> list[str]:
        names = self.set_presets.get("available_presets", [])
        return [str(item) for item in names if str(item)]

    @property
    def current_graph_preset_name(self) -> str:
        return str(self.set_presets.get("loaded_name", "") or "").strip()

    @property
    def graph_preset_load_path(self) -> str:
        return str(self.set_presets.get("load_path", "") or "")

    @property
    def graph_preset_save_path(self) -> str:
        return str(self.set_presets.get("save_path", "") or "")

    @property
    def graph_preset_rename_path(self) -> str:
        return str(self.set_presets.get("rename_path", "") or "")

    @property
    def graph_preset_destroy_path(self) -> str:
        return str(self.set_presets.get("destroy_path", "") or "")

    @property
    def graph_preset_count(self) -> int:
        count = self.set_presets.get("count", 0)
        return int(count) if isinstance(count, int) else 0

    @property
    def graph_preset_action_items(self) -> list[str]:
        items: list[str] = []
        if self.graph_preset_save_path:
            items.append("SAVE PRESET")
        if self.graph_preset_rename_path and self.current_graph_preset_name:
            items.append("RENAME PRESET")
        if self.graph_preset_destroy_path and self.current_graph_preset_name:
            items.append("DELETE PRESET")
        return items

    @property
    def graph_preset_menu_items(self) -> list[str]:
        return [".."] + self.graph_preset_action_items + self.available_graph_preset_names

    @property
    def graph_preset_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        for item in self.graph_preset_action_items:
            rows.append(MenuRow(str(item), action=True))
        if not self.available_graph_preset_names and not self.graph_preset_action_items:
            rows.append(MenuRow("no graph presets"))
            return rows
        current_indices = self.graph_preset_current_indices
        offset = 1 + len(self.graph_preset_action_items)
        for idx, item in enumerate(self.available_graph_preset_names):
            rows.append(MenuRow(str(item), current=(offset + idx) in current_indices))
        return rows

    @property
    def graph_preset_current_indices(self) -> set[int]:
        offset = 1 + len(self.graph_preset_action_items)
        return {
            offset + idx
            for idx, item in enumerate(self.available_graph_preset_names)
            if str(item) == self.current_graph_preset_name
        }

    def graph_preset_initial_cursor(self) -> int:
        if self.available_graph_preset_names:
            return 1 + len(self.graph_preset_action_items)
        if self.graph_preset_action_items:
            return 1
        return 0

    @property
    def current_set_name(self) -> str:
        value = self.state.system.get("set_name", "")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "(untitled)"

    @property
    def current_set_dirty(self) -> bool:
        sets = self.state.system.get("sets", {})
        return bool(sets.get("dirty")) if isinstance(sets, dict) else False

    @property
    def startup_graph_label(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return "OFF"
        if sets.get("auto_start_last") is True:
            return "LAST"
        initial_value = str(sets.get("initial_value", "") or "").strip()
        if initial_value:
            return initial_value
        return "OFF"

    @property
    def graph_load_path(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return ""
        return str(sets.get("load_path", "") or "")

    @property
    def graph_save_path(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return ""
        return str(sets.get("save_path", "") or "")

    @property
    def graph_rename_path(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return ""
        return str(sets.get("rename_path", "") or "")

    @property
    def graph_startup_auto_last_path(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return ""
        return str(sets.get("auto_start_last_path", "") or "")

    @property
    def graph_startup_initial_path(self) -> str:
        sets = self.state.system.get("sets", {})
        if not isinstance(sets, dict):
            return ""
        return str(sets.get("initial_path", "") or "")

    @property
    def graph_startup_menu_items(self) -> list[str]:
        items: list[str] = []
        if self.graph_startup_auto_last_path:
            items.append("RESTORE LAST")
        if self.graph_startup_initial_path and self.available_set_names:
            items.append("LOAD NAMED GRAPH")
        if self.graph_startup_auto_last_path or self.graph_startup_initial_path:
            items.append("OFF")
        return items

    @property
    def graph_startup_current_indices(self) -> set[int]:
        label = self.startup_graph_label
        indices: set[int] = set()
        for idx, item in enumerate(self.graph_startup_menu_items, start=1):
            if item == "RESTORE LAST" and label == "LAST":
                indices.add(idx)
            elif item == "LOAD NAMED GRAPH" and label not in {"LAST", "OFF"}:
                indices.add(idx)
            elif item == "OFF" and label == "OFF":
                indices.add(idx)
        return indices

    @property
    def graph_startup_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        items = self.graph_startup_menu_items
        if not items:
            rows.append(MenuRow("no startup options"))
            return rows
        current_indices = self.graph_startup_current_indices
        for idx, item in enumerate(items, start=1):
            rows.append(MenuRow(str(item), current=idx in current_indices))
        return rows

    @property
    def graph_status_value_rows(self) -> list[ValueRow]:
        rows = [
            ValueRow("graph", self.current_set_name, current=True, emphasis="italic" if self.current_set_dirty else ""),
            ValueRow("dirty", "YES" if self.current_set_dirty else "NO", current=self.current_set_dirty),
        ]
        if self.available_set_names or True:
            rows.append(ValueRow("graphs", len(self.available_set_names)))
        if self.graph_preset_menu_enabled:
            rows.append(ValueRow("preset", self.current_graph_preset_name or "-", current=bool(self.current_graph_preset_name)))
        return rows

    @property
    def graph_startup_value_rows(self) -> list[ValueRow]:
        sets = self.state.system.get("sets", {})
        auto_last = "ON" if sets.get("auto_start_last") is True else "OFF"
        initial = str(sets.get("initial_value", "") or "-")
        startup_label = self.startup_graph_label
        rows = [
            ValueRow("startup", startup_label, current=True),
            ValueRow("auto", auto_last.lower(), current=startup_label == "LAST"),
        ]
        if startup_label not in {"LAST", "OFF"}:
            rows.append(ValueRow("initial", initial, current=True))
        else:
            rows.append(ValueRow("initial", initial))
        return rows

    @property
    def status_value_rows(self) -> list[ValueRow]:
        status = self.state.system.get("status", {})
        rows = [
            ValueRow("inst", len(self.state.instances)),
            ValueRow("cpu", "-" if status.get("cpu_load") is None else f"{status['cpu_load']:.1f}"),
            ValueRow("xruns", status.get("xruns", "-"), current=bool(status.get("xruns"))),
        ]
        if self.is_runner_version_available:
            rows.append(ValueRow("rnbo", status.get("runner_version", "-")))
        return rows

    @property
    def network_value_rows(self) -> list[ValueRow]:
        return [
            ValueRow("ip", self.network_ip_address),
            ValueRow("osc", self.network_osc_port),
        ]

    def suggested_set_save_name(self) -> str:
        base_name = self.current_set_name
        if base_name == "(untitled)":
            base_name = "graph"
        slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", base_name.strip().lower())).strip("-")
        if not slug:
            slug = "graph"
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        return f"{slug}-{timestamp}"

    def suggested_preset_save_name(self) -> str:
        base_name = self.current_preset_name
        if not base_name and self.active_instance:
            base_name = str(self.active_instance.get("label", "") or "")
        if not base_name:
            base_name = "preset"
        slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", base_name.strip().lower())).strip("-")
        if not slug:
            slug = "preset"
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        return f"{slug}-{timestamp}"

    def suggested_graph_preset_save_name(self) -> str:
        base_name = self.current_graph_preset_name or self.current_set_name
        if base_name == "(untitled)":
            base_name = "preset"
        slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", base_name.strip().lower())).strip("-")
        if not slug:
            slug = "preset"
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        return f"{slug}-{timestamp}"

    def append_date_token(self, value: str, include_time: bool = False) -> str:
        token = time.strftime("%Y%m%d-%H%M%S" if include_time else "%Y%m%d", time.localtime())
        base = str(value or "").strip()
        if not base:
            return token[:NAME_EDITOR_MAX_LEN]
        base = base.rstrip(" -_")
        combined = f"{base}-{token}" if base else token
        if len(combined) <= NAME_EDITOR_MAX_LEN:
            return combined
        suffix = f"-{token}"
        keep = max(0, NAME_EDITOR_MAX_LEN - len(suffix))
        trimmed = base[:keep].rstrip(" -_")
        return f"{trimmed}{suffix}" if trimmed else token[:NAME_EDITOR_MAX_LEN]

    def normalize_name_draft(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:NAME_EDITOR_MAX_LEN]

    @property
    def name_editor_actions(self) -> list[str]:
        return [
            self.name_editor_confirm_label,
            NAME_EDITOR_GENERATE,
            NAME_EDITOR_ADD_DATE,
            NAME_EDITOR_EDIT,
            NAME_EDITOR_CLEAR,
            NAME_EDITOR_DELETE,
            NAME_EDITOR_CANCEL,
        ]

    @property
    def name_editor_items(self) -> list[str]:
        draft = self.state.name_editor_draft if self.state.name_editor_draft else "(empty)"
        return [f"NAME: {draft}"] + self.name_editor_actions

    @property
    def name_editor_title(self) -> str:
        if self.state.name_editor_context == "save_set":
            return "SAVE GRAPH"
        if self.state.name_editor_context == "rename_set":
            return "RENAME GRAPH"
        if self.state.name_editor_context == "save_graph_preset":
            return "SAVE GRAPH PRESET"
        if self.state.name_editor_context == "rename_graph_preset":
            return "RENAME GRAPH PRESET"
        if self.state.name_editor_context == "save_preset":
            return "SAVE PRESET"
        if self.state.name_editor_context == "rename_preset":
            return "RENAME PRESET"
        return "NAME"

    @property
    def name_editor_confirm_label(self) -> str:
        if self.state.name_editor_context in {"rename_set", "rename_graph_preset", "rename_preset"}:
            return "RENAME"
        return NAME_EDITOR_SAVE

    def _begin_name_editor(self, context: str, path: str, initial_draft: str, return_mode: str) -> None:
        self.state.name_editor_context = context
        self.state.name_editor_path = str(path or "")
        self.state.name_editor_return_mode = return_mode
        self.state.name_editor_draft = self.normalize_name_draft(initial_draft)
        self.state.name_editor_target_name = ""
        self.state.name_editor_cursor = 1
        self.state.name_inline_cursor = max(0, len(self.state.name_editor_draft) - 1)
        self.state.name_inline_edit_mode = False
        self.state.name_inline_preview_index = 0
        self.state.name_overwrite_cursor = 1
        self.state.name_error_message = ""
        self.state.ui_mode = "NAME_EDITOR"

    def _begin_rename_name_editor(self, context: str, path: str, current_name: str, return_mode: str) -> None:
        self._begin_name_editor(context=context, path=path, initial_draft=current_name, return_mode=return_mode)
        self.state.name_editor_target_name = self.normalize_name_draft(current_name)

    def _cancel_name_editor(self) -> None:
        self.state.ui_mode = self.state.name_editor_return_mode or "GRAPH_MENU"
        self.state.name_editor_cursor = 1
        self.state.name_inline_edit_mode = False
        self.state.name_overwrite_cursor = 1
        self.state.name_error_message = ""

    def _char_option_index(self, char: str) -> int:
        for idx, (_, value) in enumerate(NAME_EDITOR_CHAR_OPTIONS):
            if value == char:
                return idx
        return 0

    @property
    def inline_name_option_count(self) -> int:
        return len(NAME_EDITOR_CHAR_OPTIONS) + 1

    @property
    def inline_name_text(self) -> str:
        draft = self.state.name_editor_draft
        pos = max(0, min(self.state.name_inline_cursor, len(draft)))
        if self.state.name_inline_edit_mode:
            if self.state.name_inline_preview_index >= len(NAME_EDITOR_CHAR_OPTIONS):
                text = draft
                caret_pos = min(pos, len(text))
            else:
                preview_char = NAME_EDITOR_CHAR_OPTIONS[self.state.name_inline_preview_index][1]
                if pos < len(draft):
                    text = draft[:pos] + preview_char + draft[pos + 1 :]
                else:
                    text = draft + preview_char
                caret_pos = pos
        else:
            text = draft
            caret_pos = min(pos, len(text))
        if not text:
            return "[_]"
        if caret_pos >= len(text):
            return f"{text}[_]"
        return f"{text[:caret_pos]}[{text[caret_pos]}]{text[caret_pos + 1:]}"

    @property
    def inline_name_status(self) -> str:
        return "EDIT" if self.state.name_inline_edit_mode else "MOVE"

    def _begin_inline_name_edit(self) -> None:
        draft = self.state.name_editor_draft
        pos = max(0, min(self.state.name_inline_cursor, len(draft)))
        current_char = draft[pos] if pos < len(draft) and draft else "A"
        self.state.name_inline_preview_index = self._char_option_index(current_char)
        self.state.name_inline_edit_mode = True
        self.state.ui_mode = "NAME_INLINE_EDITOR"

    def _commit_inline_name_char(self) -> None:
        draft = self.state.name_editor_draft
        pos = max(0, min(self.state.name_inline_cursor, len(draft)))
        if self.state.name_inline_preview_index >= len(NAME_EDITOR_CHAR_OPTIONS):
            if not draft:
                self.state.name_inline_edit_mode = False
                return
            if pos < len(draft):
                draft = draft[:pos] + draft[pos + 1 :]
                self.state.name_inline_cursor = min(pos, len(draft))
            elif pos > 0:
                draft = draft[: pos - 1] + draft[pos:]
                self.state.name_inline_cursor = pos - 1
            self.state.name_editor_draft = self.normalize_name_draft(draft)
            self.state.name_inline_edit_mode = False
            return
        char = NAME_EDITOR_CHAR_OPTIONS[self.state.name_inline_preview_index][1]
        if pos < len(draft):
            draft = draft[:pos] + char + draft[pos + 1 :]
        else:
            if len(draft) >= NAME_EDITOR_MAX_LEN:
                return
            draft = draft + char
        self.state.name_editor_draft = self.normalize_name_draft(draft)
        self.state.name_inline_cursor = min(len(self.state.name_editor_draft), pos + 1)
        self.state.name_inline_edit_mode = False

    def _exit_inline_name_editor(self) -> None:
        self.state.name_inline_edit_mode = False
        self.state.ui_mode = "NAME_EDITOR"

    def _regenerate_name_draft(self) -> None:
        if self.state.name_editor_context == "save_set":
            self.state.name_editor_draft = self.normalize_name_draft(self.suggested_set_save_name())
        elif self.state.name_editor_context == "save_graph_preset":
            self.state.name_editor_draft = self.normalize_name_draft(self.suggested_graph_preset_save_name())
        elif self.state.name_editor_context == "save_preset":
            self.state.name_editor_draft = self.normalize_name_draft(self.suggested_preset_save_name())

    def _name_exists(self, value: str) -> bool:
        normalized = self.normalize_name_draft(value)
        if not normalized:
            return False
        if self.state.name_editor_context in {"save_set", "rename_set"}:
            return normalized in self.available_set_names and normalized != self.state.name_editor_target_name
        if self.state.name_editor_context in {"save_graph_preset", "rename_graph_preset"}:
            return normalized in self.available_graph_preset_names and normalized != self.state.name_editor_target_name
        if self.state.name_editor_context in {"save_preset", "rename_preset"}:
            preset_names = {str(item.get("name", "")) for item in self.active_presets if str(item.get("name", ""))}
            return normalized in preset_names and normalized != self.state.name_editor_target_name
        return False

    def _show_name_error(self, message: str) -> None:
        self.state.name_error_message = str(message or "NAME ERROR")
        self.state.ui_mode = "NAME_ERROR"

    def _show_overwrite_confirm(self) -> None:
        self.state.name_overwrite_cursor = 1
        self.state.ui_mode = "NAME_OVERWRITE_CONFIRM"

    @property
    def overwrite_confirm_items(self) -> list[str]:
        return NAME_OVERWRITE_CONFIRM_ITEMS

    @property
    def name_error_items(self) -> list[str]:
        return ["..", NAME_ERROR_DISMISS]

    @property
    def name_error_title(self) -> str:
        return self.state.name_error_message or "NAME ERROR"

    def _queue_confirmed_name_action(self, value: str) -> None:
        if self.state.name_editor_context == "save_set" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            self.queue_action(UIAction(kind="save_set", path=self.state.name_editor_path, value=value))
        elif self.state.name_editor_context == "rename_set" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            self.queue_action(UIAction(kind="rename_set", path=self.state.name_editor_path, value=value))
        elif self.state.name_editor_context == "save_graph_preset" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            self.queue_action(UIAction(kind="save_graph_preset", path=self.state.name_editor_path, value=value))
        elif self.state.name_editor_context == "rename_graph_preset" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            self.queue_action(
                UIAction(
                    kind="rename_graph_preset",
                    path=self.state.name_editor_path,
                    value=[self.state.name_editor_target_name, value],
                )
            )
        elif self.state.name_editor_context == "save_preset" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            self.queue_action(UIAction(kind="save_preset", path=self.state.name_editor_path, value=value))
        elif self.state.name_editor_context == "rename_preset" and self.state.name_editor_path:
            self.state.name_editor_draft = value
            if self.current_preset_name == self.state.name_editor_target_name:
                self.remember_loaded_preset(value)
            self.queue_action(UIAction(kind="rename_preset", path=self.state.name_editor_path, value=value))

    def _submit_name_editor(self) -> None:
        value = self.normalize_name_draft(self.state.name_editor_draft)
        if not value:
            self._show_name_error("ENTER NAME")
            return
        if self.state.name_editor_context in {"save_set", "save_graph_preset", "save_preset"} and self._name_exists(value):
            self.state.name_editor_draft = value
            self._show_overwrite_confirm()
            return
        if self.state.name_editor_context in {"rename_set", "rename_graph_preset", "rename_preset"} and self._name_exists(value):
            self.state.name_editor_draft = value
            self._show_name_error("NAME EXISTS")
            return
        self._queue_confirmed_name_action(value)

    @property
    def maint_menu_items(self) -> list[str]:
        items = [MAINT_ITEMS_REFRESH]
        if self.can_restart_jack:
            items.append(MAINT_ITEMS_RESTART_JACK)
        return items

    @property
    def active_instance(self) -> Optional[dict]:
        for instance in self.state.instances:
            if str(instance.get("id", "")) == str(self.state.active_instance_id):
                return instance
        return None

    @property
    def active_presets(self) -> list[dict]:
        instance = self.active_instance
        if not instance:
            return []
        return list(instance.get("presets", []))

    @property
    def active_preset_save_path(self) -> str:
        if not self.active_instance:
            return ""
        return str(self.active_instance.get("preset_save_path", "") or "")

    @property
    def active_preset_rename_path(self) -> str:
        if not self.active_instance:
            return ""
        return str(self.active_instance.get("preset_rename_path", "") or "")

    @property
    def preset_action_items(self) -> list[str]:
        items: list[str] = []
        if self.active_preset_save_path:
            items.append("SAVE PRESET")
        if self.active_preset_rename_path and self.current_preset_name:
            items.append("RENAME PRESET")
        return items

    @property
    def preset_menu_items(self) -> list[str]:
        return [".."] + self.preset_action_items + [str(item.get("name", "")) for item in self.active_presets]

    @property
    def preset_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        for item in self.preset_action_items:
            rows.append(MenuRow(str(item), action=True))
        if not self.active_presets and not self.preset_action_items:
            rows.append(MenuRow("no presets"))
            return rows
        current_indices = self.preset_current_indices
        offset = 1 + len(self.preset_action_items)
        for idx, item in enumerate(self.active_presets):
            rows.append(MenuRow(str(item.get("name", "")), current=(offset + idx) in current_indices))
        return rows

    @property
    def active_params(self) -> list[dict]:
        instance = self.active_instance
        if not instance:
            return []
        return list(instance.get("params", []))

    @property
    def active_state_values(self) -> list[dict]:
        instance = self.active_instance
        if not instance:
            return []
        return list(instance.get("state", []))

    @property
    def active_routing_ports(self) -> list[dict]:
        instance = self.active_instance
        if not instance:
            return []
        routing = instance.get("routing", {})
        branch = routing.get(self.state.active_transport, {})
        return list(branch.get(self.state.active_routing_direction, []))

    def _routing_branch(self, instance: dict | None, transport: str) -> dict:
        if not isinstance(instance, dict):
            return {}
        routing = instance.get("routing", {})
        if not isinstance(routing, dict):
            return {}
        branch = routing.get(str(transport), {})
        return branch if isinstance(branch, dict) else {}

    def _short_routing_target(self, target: Any) -> str:
        text = str(target or "").strip()
        if not text:
            return ""
        match = re.fullmatch(r"system:(capture|playback)_(\d+)", text)
        if match:
            return f"{'C' if match.group(1) == 'capture' else 'P'}{int(match.group(2))}"
        if ":" in text:
            text = text.split(":", 1)[1]
        return text

    def _compress_routing_tokens(self, tokens: list[str]) -> list[str]:
        compressed: list[str] = []
        index = 0
        while index < len(tokens):
            match = re.fullmatch(r"([A-Za-z]+)(\d+)", tokens[index])
            if not match:
                compressed.append(tokens[index])
                index += 1
                continue

            prefix = match.group(1)
            start = int(match.group(2))
            end = start
            lookahead = index + 1
            while lookahead < len(tokens):
                next_match = re.fullmatch(r"([A-Za-z]+)(\d+)", tokens[lookahead])
                if not next_match or next_match.group(1) != prefix:
                    break
                next_value = int(next_match.group(2))
                if next_value != end + 1:
                    break
                end = next_value
                lookahead += 1

            compressed.append(f"{prefix}{start}-{end}" if end > start else f"{prefix}{start}")
            index = lookahead
        return compressed

    def _routing_connection_summary(self, ports: list[dict]) -> str:
        tokens: list[str] = []
        for port in ports:
            if not isinstance(port, dict):
                continue
            connections = [self._short_routing_target(item) for item in port.get("connections", []) if str(item).strip()]
            if connections:
                tokens.extend(item for item in connections if item)
        if not tokens:
            return "-"
        return ",".join(self._compress_routing_tokens(tokens))

    def _instance_routing_summary(self, instance: dict | None, transport: str) -> str:
        branch = self._routing_branch(instance, transport)
        inputs = branch.get("inputs", [])
        outputs = branch.get("outputs", [])
        input_summary = self._routing_connection_summary(inputs if isinstance(inputs, list) else [])
        output_summary = self._routing_connection_summary(outputs if isinstance(outputs, list) else [])
        return f"I:{input_summary} O:{output_summary}"

    @property
    def routing_overview_rows(self) -> list[ValueRow]:
        rows: list[ValueRow] = []
        transport = self.state.active_transport
        active_id = str(self.state.active_instance_id)
        for instance in self.state.instances:
            label = str(instance.get("label", "") or instance.get("name", "") or instance.get("id", "")).strip() or "instance"
            rows.append(
                ValueRow(
                    label,
                    self._instance_routing_summary(instance, transport),
                    current=str(instance.get("id", "")) == active_id,
                )
            )
        return rows

    @property
    def selected_routing_overview_instance(self) -> Optional[dict]:
        idx = self.state.routing_overview_cursor - 1
        if 0 <= idx < len(self.state.instances):
            return self.state.instances[idx]
        return None

    @property
    def selected_param(self) -> Optional[dict]:
        idx = self.state.param_cursor - 1
        if idx >= 0 and idx < len(self.active_params):
            return self.active_params[idx]
        return None

    @property
    def active_enum_options(self) -> list[Any]:
        param = self.selected_param
        if not param:
            return []
        vals = param.get("vals", [])
        return list(vals) if isinstance(vals, list) else []

    @property
    def current_enum_value(self) -> Any:
        param = self.selected_param
        if not param:
            return None
        return param.get("value")

    @property
    def selected_preset(self) -> Optional[dict]:
        idx = self.state.preset_cursor - 1 - len(self.preset_action_items)
        if idx >= 0 and idx < len(self.active_presets):
            return self.active_presets[idx]
        return None

    @property
    def selected_graph_preset_name(self) -> str:
        idx = self.state.graph_preset_cursor - 1 - len(self.graph_preset_action_items)
        if 0 <= idx < len(self.available_graph_preset_names):
            return str(self.available_graph_preset_names[idx])
        return ""

    @property
    def current_preset_name(self) -> str:
        if self.active_instance:
            published_name = str(self.active_instance.get("current_preset_name", "") or "").strip()
            if published_name:
                return published_name
        instance_id = str(self.state.active_instance_id)
        if not instance_id:
            return ""
        return str(self.state.current_presets.get(instance_id, ""))

    @property
    def preset_current_indices(self) -> set[int]:
        offset = 1 + len(self.preset_action_items)
        return {
            offset + idx
            for idx, item in enumerate(self.active_presets)
            if str(item.get("name", "")) == self.current_preset_name
        }

    def preset_initial_cursor(self) -> int:
        if self.active_presets:
            return 1 + len(self.preset_action_items)
        if self.preset_action_items:
            return 1
        return 0

    @property
    def instance_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        current_indices = self.instance_current_indices
        for idx, item in enumerate(self.state.instances, start=1):
            rows.append(MenuRow(str(item.get("label", "")), current=idx in current_indices))
        if self.can_add_instance:
            rows.append(MenuRow("ADD INSTANCE", action=True))
        if self.can_remove_instances:
            rows.append(MenuRow("REMOVE INSTANCE", action=True))
        return rows

    @property
    def instance_current_indices(self) -> set[int]:
        active_id = str(self.state.active_instance_id)
        if not active_id:
            return set()
        return {
            idx + 1
            for idx, item in enumerate(self.state.instances)
            if str(item.get("id", "")) == active_id
        }

    @property
    def remove_instance_target(self) -> Optional[dict]:
        if self.state.pending_remove_instance_id:
            for instance in self.state.instances:
                if str(instance.get("id", "")) == str(self.state.pending_remove_instance_id):
                    return instance
        if self.active_instance is not None:
            return self.active_instance
        return None

    @property
    def current_audio_card(self) -> str:
        return self.state.system.get("audio", {}).get("current_card", "")

    @property
    def is_runner_version_available(self) -> bool:
        return bool(str(self.state.system.get("status", {}).get("runner_version", "") or "").strip())

    @property
    def network_osc_port(self) -> int:
        return RNBO_PORT

    @property
    def network_ip_address(self) -> str:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("1.1.1.1", 80))
            return str(sock.getsockname()[0] or "?")
        except Exception:
            return "?"
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    @property
    def audio_options(self) -> list[str]:
        return self.state.system.get("audio", {}).get("card_options", [])

    @property
    def sample_rate_options(self) -> list[int]:
        audio = self.state.system.get("audio", {})
        options = audio.get("sample_rate_options", [])
        if isinstance(options, list) and options:
            return [int(v) for v in options]

        minimum = audio.get("sample_rate_min")
        maximum = audio.get("sample_rate_max")
        current = audio.get("sample_rate")
        defaults = [22050, 32000, 44100, 48000, 88200, 96000]
        filtered = []
        for value in defaults:
            if minimum is not None and value < float(minimum):
                continue
            if maximum is not None and value > float(maximum):
                continue
            filtered.append(value)
        if current is not None:
            current_int = int(float(current))
            if current_int not in filtered:
                filtered.append(current_int)
        return sorted(set(filtered))

    @property
    def buffer_size_options(self) -> list[int]:
        options = self.state.system.get("audio", {}).get("period_frames_options", [])
        return [int(v) for v in options] if isinstance(options, list) else []

    @property
    def current_sample_rate(self) -> Optional[int]:
        value = self.state.system.get("audio", {}).get("sample_rate")
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @property
    def current_buffer_size(self) -> Optional[int]:
        value = self.state.system.get("audio", {}).get("period_frames")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def selected_routing_port(self) -> Optional[dict]:
        idx = self.state.routing_port_cursor - 1
        if idx >= 0 and idx < len(self.active_routing_ports):
            return self.active_routing_ports[idx]
        return None

    @property
    def active_routing_targets(self) -> list[str]:
        port = self.selected_routing_port
        if not port:
            return []
        return [str(item) for item in port.get("targets", []) if str(item)]

    @property
    def current_routing_targets(self) -> list[str]:
        port = self.selected_routing_port
        if not port:
            return []
        return [str(item) for item in port.get("connections", []) if str(item)]

    @property
    def routing_target_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        disconnect_current = not self.current_routing_targets
        rows.append(MenuRow("DISCONNECT", current=disconnect_current))
        current_targets = set(self.current_routing_targets)
        used_targets = self.used_routing_targets
        for item in self.active_routing_targets:
            rows.append(
                MenuRow(
                    str(item),
                    current=str(item) in current_targets,
                    emphasis="italic" if str(item) in used_targets else "",
                )
            )
        return rows

    @property
    def used_routing_targets(self) -> set[str]:
        port = self.selected_routing_port
        if not port:
            return set()

        selected_path = str(port.get("path", ""))
        available_targets = set(self.active_routing_targets)
        if not available_targets:
            return set()

        used_targets: set[str] = set()
        for instance in self.state.instances:
            routing = instance.get("routing", {})
            branch = routing.get(self.state.active_transport, {})
            ports = branch.get(self.state.active_routing_direction, [])
            if not isinstance(ports, list):
                continue
            for other_port in ports:
                if not isinstance(other_port, dict):
                    continue
                if str(other_port.get("path", "")) == selected_path:
                    continue
                for connection in other_port.get("connections", []):
                    target = str(connection)
                    if target in available_targets:
                        used_targets.add(target)
        return used_targets

    @property
    def routing_port_current_indices(self) -> set[int]:
        return {
            idx + 1
            for idx, port in enumerate(self.active_routing_ports)
            if isinstance(port, dict) and any(str(item) for item in port.get("connections", []))
        }

    def _sync_audio_index(self) -> None:
        if self.current_audio_card in self.audio_options:
            self.state.audio_device_cursor = self.audio_options.index(self.current_audio_card) + 1
        else:
            self.state.audio_device_cursor = 1 if self.audio_options else 0
        current_rate = self.state.system.get("audio", {}).get("sample_rate")
        rate_options = self.sample_rate_options
        if current_rate is not None and int(float(current_rate)) in rate_options:
            self.state.sample_rate_cursor = rate_options.index(int(float(current_rate))) + 1
        else:
            self.state.sample_rate_cursor = 1 if rate_options else 0
        current_buffer = self.state.system.get("audio", {}).get("period_frames")
        buffer_options = self.buffer_size_options
        if current_buffer in buffer_options:
            self.state.buffer_size_cursor = buffer_options.index(int(current_buffer)) + 1
        else:
            self.state.buffer_size_cursor = 1 if buffer_options else 0

    @property
    def audio_device_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        for item in self.audio_options:
            rows.append(MenuRow(str(item), current=str(item) == str(self.current_audio_card)))
        return rows

    @property
    def sample_rate_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        current_rate = self.current_sample_rate
        for item in self.sample_rate_options:
            rows.append(MenuRow(str(item), current=item == current_rate))
        return rows

    @property
    def buffer_size_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        current_buffer = self.current_buffer_size
        for item in self.buffer_size_options:
            rows.append(MenuRow(str(item), current=item == current_buffer))
        return rows

    def _cycle(self, current: int, count: int, delta: int) -> int:
        if count <= 0:
            return 0
        return (current + delta) % count

    def _begin_ttid_edit(self, param: dict) -> None:
        self.state.edit_value = normalize_ttid(param.get("value", 0))
        self.state.edit_ttid_mode = "keyboard"
        self.state.edit_ttid_selected_pc = 0
        self.state.edit_ttid_load_root = 0
        scale_names = get_scale_names() or ["major"]
        self.state.edit_ttid_scale_names = scale_names
        self.state.edit_ttid_scale_index = 0

    def _current_ttid_scale_name(self) -> str:
        names = self.state.edit_ttid_scale_names or ["major"]
        idx = max(0, min(self.state.edit_ttid_scale_index, len(names) - 1))
        return names[idx]

    def _find_active_state_value(self, key: str) -> Optional[dict]:
        key = str(key).strip().lower()
        if not key:
            return None
        for item in self.active_state_values:
            name = str(item.get("name", "")).strip().lower()
            path = str(item.get("path", "")).strip().lower()
            metadata = item.get("metadata", {})
            ui_role = str(metadata.get("ui_role", "")).strip().lower() if isinstance(metadata, dict) else ""
            if name == key or name.endswith(f"/{key}") or path.endswith(f"/{key}") or ui_role == key:
                return item
        return None

    def active_pitch_display_state_value(self, param: dict | None, key_name: str) -> Optional[dict]:
        key = str(key_name).strip()
        if not key:
            return None
        return self._find_active_state_value(key)

    def remember_loaded_preset(self, preset_name: Any) -> None:
        instance_id = str(self.state.active_instance_id)
        preset_text = str(preset_name or "")
        if not instance_id or not preset_text:
            return
        self.state.current_presets[instance_id] = preset_text

    @property
    def active_pitch_display_pitch(self) -> Optional[dict]:
        return self.active_pitch_display_state_value(self.selected_param, pitch_state_key(self.selected_param))

    @property
    def active_pitch_display_cents(self) -> Optional[dict]:
        return self.active_pitch_display_state_value(self.selected_param, cents_state_key(self.selected_param))

    @property
    def active_step16_playhead(self) -> Optional[int]:
        item = self._find_active_state_value(playhead_state_key(self.selected_param))
        if item is None:
            return None
        return clamp_playhead(item.get("value"))

    @property
    def uses_turbo_rendering(self) -> bool:
        if self.state.ui_mode == "BRICK_PANEL":
            return True
        return False

    def _apply_ttid_scale_load(self) -> None:
        mask = apply_scale_to_mask(
            self.state.edit_ttid_load_root,
            self._current_ttid_scale_name(),
        )
        self.state.edit_value = normalize_ttid(mask)
        param = self.selected_param
        if param is not None:
            param["value"] = self.state.edit_value
            self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))

    def queue_action(self, action: UIAction) -> None:
        self._actions.append(action)

    def pop_actions(self) -> list[UIAction]:
        actions = self._actions[:]
        self._actions.clear()
        return actions

    def should_pause_refresh(self) -> bool:
        if self.state.ui_mode == "EDIT" and self.selected_param:
            if is_step16_param(self.selected_param) or is_pitch_display_param(self.selected_param):
                return False
        return self.state.ui_mode in {
            "GRAPH_MENU",
            "GRAPH_SET_LIST",
            "GRAPH_STARTUP",
            "GRAPH_STARTUP_SET_LIST",
            "NAME_EDITOR",
            "NAME_INLINE_EDITOR",
            "NAME_OVERWRITE_CONFIRM",
            "NAME_ERROR",
            "INSTANCE_LIST",
            "PATCHER_PICKER",
            "INSTANCE_MENU",
            "REMOVE_INSTANCE_PICKER",
            "REMOVE_INSTANCE_CONFIRM",
            "PRESET_LIST",
            "ROUTING_GROUP",
            "ROUTING_PORTS",
            "AUDIO_ROUTING_OVERVIEW",
            "MIDI_ROUTING_OVERVIEW",
            "EDIT",
            "ENUM_LIST",
            "ROUTING_TARGETS",
            "SYSTEM_AUDIO_DEVICE",
            "SYSTEM_AUDIO_RATE",
            "SYSTEM_AUDIO_BUFFER",
            "BRICK_PANEL",
        }

    def advance_frame(self, frame_scale: float = 1.0) -> None:
        if self.state.ui_mode == "BRICK_PANEL":
            self.brick_panel.update(frame_scale=frame_scale)

    def handle_event(self, event: UIEvent) -> None:
        if event.kind == "rotate":
            self._handle_rotate(event.delta)
        elif event.kind == "short_press":
            self._handle_short_press()
        elif event.kind == "long_press":
            self._handle_long_press()

    def _handle_rotate(self, delta: int) -> None:
        if delta == 0:
            return
        step = delta
        self.state.activity_ticks += 1

        if self.state.ui_mode == "BRICK_PANEL":
            self.brick_panel.rotate(step)
        elif self.state.ui_mode == "ABOUT":
            self._about_press_count = 0
        elif self.state.ui_mode == "TOP":
            self.state.top_index = self._cycle(self.state.top_index, len(self.top_level_items), step)
        elif self.state.ui_mode == "GRAPH_MENU":
            self.state.graph_menu_cursor = self._cycle(self.state.graph_menu_cursor, len(self.graph_menu_items) + 1, step)
        elif self.state.ui_mode == "GRAPH_SET_LIST":
            self.state.graph_set_cursor = self._cycle(self.state.graph_set_cursor, len(self.available_set_names) + 1, step)
        elif self.state.ui_mode == "GRAPH_PRESET_LIST":
            self.state.graph_preset_cursor = self._cycle(self.state.graph_preset_cursor, len(self.graph_preset_menu_items), step)
        elif self.state.ui_mode == "GRAPH_STARTUP":
            self.state.graph_startup_cursor = self._cycle(self.state.graph_startup_cursor, len(self.graph_startup_menu_items) + 1, step)
        elif self.state.ui_mode == "GRAPH_STARTUP_SET_LIST":
            self.state.graph_startup_set_cursor = self._cycle(self.state.graph_startup_set_cursor, len(self.available_set_names) + 1, step)
        elif self.state.ui_mode == "NAME_EDITOR":
            self.state.name_editor_cursor = self._cycle(self.state.name_editor_cursor, len(self.name_editor_items), step)
        elif self.state.ui_mode == "NAME_INLINE_EDITOR":
            if self.state.name_inline_edit_mode:
                self.state.name_inline_preview_index = self._cycle(self.state.name_inline_preview_index, self.inline_name_option_count, step)
            else:
                max_pos = min(len(self.state.name_editor_draft), NAME_EDITOR_MAX_LEN - 1 if len(self.state.name_editor_draft) >= NAME_EDITOR_MAX_LEN else len(self.state.name_editor_draft))
                self.state.name_inline_cursor = self._cycle(self.state.name_inline_cursor, max_pos + 1, step)
        elif self.state.ui_mode == "NAME_OVERWRITE_CONFIRM":
            self.state.name_overwrite_cursor = self._cycle(self.state.name_overwrite_cursor, len(self.overwrite_confirm_items), step)
        elif self.state.ui_mode == "NAME_ERROR":
            self.state.name_overwrite_cursor = self._cycle(self.state.name_overwrite_cursor, len(self.name_error_items), step)
        elif self.state.ui_mode == "INSTANCE_LIST":
            self.state.instance_cursor = self._cycle(
                self.state.instance_cursor,
                len(self.state.instances) + 1 + (1 if self.can_add_instance else 0) + (1 if self.can_remove_instances else 0),
                step,
            )
            idx = self.state.instance_cursor - 1
            if idx >= 0 and idx < len(self.state.instances):
                self.state.active_instance_id = str(self.state.instances[idx].get("id", ""))
        elif self.state.ui_mode == "REMOVE_INSTANCE_PICKER":
            self.state.remove_instance_picker_cursor = self._cycle(self.state.remove_instance_picker_cursor, len(self.state.instances) + 1, step)
        elif self.state.ui_mode == "PATCHER_PICKER":
            self.state.patcher_cursor = self._cycle(self.state.patcher_cursor, len(self.state.patchers) + 1, step)
        elif self.state.ui_mode == "INSTANCE_MENU":
            self.state.instance_menu_cursor = self._cycle(self.state.instance_menu_cursor, len(self.instance_menu_items) + 1, step)
        elif self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self.state.remove_instance_confirm_cursor = self._cycle(self.state.remove_instance_confirm_cursor, len(REMOVE_INSTANCE_CONFIRM_ITEMS), step)
        elif self.state.ui_mode == "PRESET_LIST":
            self.state.preset_cursor = self._cycle(self.state.preset_cursor, len(self.preset_menu_items), step)
        elif self.state.ui_mode == "PARAM_LIST":
            self.state.param_cursor = self._cycle(self.state.param_cursor, len(self.active_params) + 1, step)
        elif self.state.ui_mode == "ENUM_LIST":
            self.state.enum_cursor = self._cycle(self.state.enum_cursor, len(self.active_enum_options), step)
            if self.active_enum_options:
                self.state.edit_value = self.active_enum_options[self.state.enum_cursor]
        elif self.state.ui_mode == "ROUTING_GROUP":
            self.state.routing_group_cursor = self._cycle(self.state.routing_group_cursor, len(ROUTING_GROUP_ITEMS) + 1, step)
        elif self.state.ui_mode == "ROUTING_PORTS":
            self.state.routing_port_cursor = self._cycle(self.state.routing_port_cursor, len(self.active_routing_ports) + 1, step)
        elif self.state.ui_mode == "ROUTING_TARGETS":
            self.state.routing_target_cursor = self._cycle(self.state.routing_target_cursor, len(self.active_routing_targets) + 2, step)
        elif self.state.ui_mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            self.state.routing_overview_cursor = self._cycle(self.state.routing_overview_cursor, len(self.routing_overview_rows), step)
            selected = self.selected_routing_overview_instance
            if selected is not None:
                self.state.active_instance_id = str(selected.get("id", ""))
        elif self.state.ui_mode == "SYSTEM_MENU":
            self.state.system_cursor = self._cycle(self.state.system_cursor, len(self.system_menu_items) + 1, step)
        elif self.state.ui_mode == "SYSTEM_AUDIO":
            self.state.system_audio_cursor = self._cycle(self.state.system_audio_cursor, len(SYSTEM_AUDIO_ITEMS) + 1, step)
        elif self.state.ui_mode == "MAINT":
            self.state.maint_cursor = self._cycle(self.state.maint_cursor, len(self.maint_menu_items) + 1, step)
        elif self.state.ui_mode == "SYSTEM_AUDIO_DEVICE":
            self.state.audio_device_cursor = self._cycle(self.state.audio_device_cursor, len(self.audio_options) + 1, step)
        elif self.state.ui_mode == "SYSTEM_AUDIO_RATE":
            self.state.sample_rate_cursor = self._cycle(self.state.sample_rate_cursor, len(self.sample_rate_options) + 1, step)
        elif self.state.ui_mode == "SYSTEM_AUDIO_BUFFER":
            self.state.buffer_size_cursor = self._cycle(self.state.buffer_size_cursor, len(self.buffer_size_options) + 1, step)
        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
            if param is None:
                return
            if is_ttid_param(param):
                if self.state.edit_ttid_mode == "keyboard":
                    self.state.edit_ttid_selected_pc = (self.state.edit_ttid_selected_pc + step) % 13
                elif self.state.edit_ttid_mode == "load_root":
                    self.state.edit_ttid_load_root = (self.state.edit_ttid_load_root + step) % 12
                elif self.state.edit_ttid_mode == "load_scale":
                    names = self.state.edit_ttid_scale_names
                    if names:
                        self.state.edit_ttid_scale_index = (self.state.edit_ttid_scale_index + step) % len(names)
            elif is_step16_param(param):
                steps = abs(step)
                direction = 1 if step > 0 else -1
                for _ in range(steps):
                    self.state.edit_step16_focus = move_step16_focus(self.state.edit_step16_focus, direction)
            elif is_pitch_display_param(param):
                return
            else:
                step = self._accelerate_float_edit_delta(param, step)
                self.state.edit_value = apply_edit_delta(param, self.state.edit_value, step)
                param["value"] = self.state.edit_value
                if not is_discrete_param(param):
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))

        self.queue_action(UIAction(kind="save_state"))

    def _handle_short_press(self) -> None:
        self.state.activity_ticks += 1

        if self.state.ui_mode == "ABOUT":
            self._about_press_count += 1
            if self._about_press_count >= BRICK_PANEL_TRIGGER_PRESSES:
                self._about_press_count = 0
                self.brick_panel.reset()
                self.state.ui_mode = "BRICK_PANEL"
            self.queue_action(UIAction(kind="save_state"))
            return

        if self.state.ui_mode == "BRICK_PANEL":
            self.brick_panel.press()
            self.queue_action(UIAction(kind="save_state"))
            return

        if self.state.ui_mode == "TOP":
            if self.top_level_items[self.state.top_index] == "GRAPHS":
                self.state.ui_mode = "GRAPH_MENU"
                self.state.graph_menu_cursor = 1 if self.graph_menu_items else 0
            elif self.top_level_items[self.state.top_index] == "INSTANCES":
                self.state.ui_mode = "INSTANCE_LIST"
                self.state.instance_cursor = 1 if self.state.instances or self.can_add_instance or self.can_remove_instances else 0
                if self.state.instances:
                    self.state.active_instance_id = str(self.state.instances[0].get("id", ""))
            else:
                self.state.ui_mode = "SYSTEM_MENU"
                self.state.system_cursor = 1

        elif self.state.ui_mode == "GRAPH_MENU":
            if self.state.graph_menu_cursor == 0:
                self.state.ui_mode = "TOP"
            else:
                choice = self.graph_menu_items[self.state.graph_menu_cursor - 1]
                if choice == "CURRENT GRAPH":
                    self.state.ui_mode = "GRAPH_STATUS"
                elif choice == "NEW GRAPH" and self.new_graph_available:
                    self.queue_action(
                        UIAction(
                            kind="load_set",
                            path=self.graph_load_path,
                            value=NEW_GRAPH_SET_NAME,
                        )
                    )
                elif choice == "LOAD GRAPH":
                    self.state.ui_mode = "GRAPH_SET_LIST"
                    self.state.graph_set_cursor = 1 if self.available_set_names else 0
                elif choice == "AUDIO OVERVIEW":
                    self.state.active_transport = "audio"
                    self.state.ui_mode = "AUDIO_ROUTING_OVERVIEW"
                    self.state.routing_overview_cursor = self.instance_cursor_for_active_instance()
                elif choice == "MIDI OVERVIEW":
                    self.state.active_transport = "midi"
                    self.state.ui_mode = "MIDI_ROUTING_OVERVIEW"
                    self.state.routing_overview_cursor = self.instance_cursor_for_active_instance()
                elif choice == "GRAPH PRESETS":
                    self.state.ui_mode = "GRAPH_PRESET_LIST"
                    self.state.graph_preset_cursor = self.graph_preset_initial_cursor()
                elif choice == "SAVE GRAPH" and self.graph_save_path:
                    self._begin_name_editor(
                        context="save_set",
                        path=self.graph_save_path,
                        initial_draft=self.suggested_set_save_name(),
                        return_mode="GRAPH_MENU",
                    )
                elif choice == "RENAME GRAPH" and self.graph_rename_path:
                    self._begin_rename_name_editor(
                        context="rename_set",
                        path=self.graph_rename_path,
                        current_name=self.current_set_name,
                        return_mode="GRAPH_MENU",
                    )
                elif choice == "STARTUP":
                    self.state.ui_mode = "GRAPH_STARTUP"
                    self.state.graph_startup_cursor = 1 if self.graph_startup_menu_items else 0

        elif self.state.ui_mode == "GRAPH_SET_LIST":
            if self.state.graph_set_cursor == 0:
                self.state.ui_mode = "GRAPH_MENU"
            elif self.graph_load_path and self.available_set_names:
                idx = self.state.graph_set_cursor - 1
                if 0 <= idx < len(self.available_set_names):
                    self.queue_action(
                        UIAction(
                            kind="load_set",
                            path=self.graph_load_path,
                            value=self.available_set_names[idx],
                        )
                    )

        elif self.state.ui_mode == "GRAPH_PRESET_LIST":
            if self.state.graph_preset_cursor == 0:
                self.state.ui_mode = "GRAPH_MENU"
            else:
                action_idx = self.state.graph_preset_cursor - 1
                if 0 <= action_idx < len(self.graph_preset_action_items):
                    choice = self.graph_preset_action_items[action_idx]
                    if choice == "SAVE PRESET" and self.graph_preset_save_path:
                        self._begin_name_editor(
                            context="save_graph_preset",
                            path=self.graph_preset_save_path,
                            initial_draft=self.suggested_graph_preset_save_name(),
                            return_mode="GRAPH_PRESET_LIST",
                        )
                    elif choice == "RENAME PRESET" and self.graph_preset_rename_path and self.current_graph_preset_name:
                        self._begin_rename_name_editor(
                            context="rename_graph_preset",
                            path=self.graph_preset_rename_path,
                            current_name=self.current_graph_preset_name,
                            return_mode="GRAPH_PRESET_LIST",
                        )
                    elif choice == "DELETE PRESET" and self.graph_preset_destroy_path and self.current_graph_preset_name:
                        self.queue_action(
                            UIAction(
                                kind="delete_graph_preset",
                                path=self.graph_preset_destroy_path,
                                value=self.current_graph_preset_name,
                            )
                        )
                elif self.graph_preset_load_path:
                    preset_name = self.selected_graph_preset_name
                    if preset_name:
                        self.queue_action(
                            UIAction(
                                kind="load_graph_preset",
                                path=self.graph_preset_load_path,
                                value=preset_name,
                            )
                        )

        elif self.state.ui_mode == "GRAPH_STARTUP":
            if self.state.graph_startup_cursor == 0:
                self.state.ui_mode = "GRAPH_MENU"
            else:
                choice = self.graph_startup_menu_items[self.state.graph_startup_cursor - 1]
                if choice == "LOAD NAMED GRAPH":
                    self.state.ui_mode = "GRAPH_STARTUP_SET_LIST"
                    self.state.graph_startup_set_cursor = 1 if self.available_set_names else 0
                elif choice == "RESTORE LAST":
                    updates: list[tuple[str, Any]] = []
                    if self.graph_startup_auto_last_path:
                        updates.append((self.graph_startup_auto_last_path, True))
                    if self.graph_startup_initial_path:
                        updates.append((self.graph_startup_initial_path, ""))
                    if updates:
                        self.queue_action(UIAction(kind="set_graph_startup", value=updates))
                elif choice == "OFF":
                    updates = []
                    if self.graph_startup_auto_last_path:
                        updates.append((self.graph_startup_auto_last_path, False))
                    if self.graph_startup_initial_path:
                        updates.append((self.graph_startup_initial_path, ""))
                    if updates:
                        self.queue_action(UIAction(kind="set_graph_startup", value=updates))

        elif self.state.ui_mode == "GRAPH_STARTUP_SET_LIST":
            if self.state.graph_startup_set_cursor == 0:
                self.state.ui_mode = "GRAPH_STARTUP"
            else:
                idx = self.state.graph_startup_set_cursor - 1
                if 0 <= idx < len(self.available_set_names):
                    updates = []
                    if self.graph_startup_auto_last_path:
                        updates.append((self.graph_startup_auto_last_path, False))
                    if self.graph_startup_initial_path:
                        updates.append((self.graph_startup_initial_path, self.available_set_names[idx]))
                    if updates:
                        self.queue_action(UIAction(kind="set_graph_startup", value=updates))

        elif self.state.ui_mode == "NAME_EDITOR":
            if self.state.name_editor_cursor > 0:
                choice = self.name_editor_items[self.state.name_editor_cursor]
                if choice == self.name_editor_confirm_label:
                    self._submit_name_editor()
                elif choice == NAME_EDITOR_GENERATE:
                    self._regenerate_name_draft()
                elif choice == NAME_EDITOR_ADD_DATE:
                    self.state.name_editor_draft = self.append_date_token(self.state.name_editor_draft)
                elif choice == NAME_EDITOR_EDIT:
                    self._begin_inline_name_edit()
                elif choice == NAME_EDITOR_CLEAR:
                    self.state.name_editor_draft = ""
                elif choice == NAME_EDITOR_DELETE:
                    self.state.name_editor_draft = self.state.name_editor_draft[:-1]
                elif choice == NAME_EDITOR_CANCEL:
                    self._cancel_name_editor()

        elif self.state.ui_mode == "NAME_INLINE_EDITOR":
            if self.state.name_inline_edit_mode:
                self._commit_inline_name_char()
            else:
                self._begin_inline_name_edit()

        elif self.state.ui_mode == "NAME_OVERWRITE_CONFIRM":
            if self.state.name_overwrite_cursor == 0:
                self.state.ui_mode = "NAME_EDITOR"
            elif self.overwrite_confirm_items[self.state.name_overwrite_cursor] == "OVERWRITE":
                self._queue_confirmed_name_action(self.normalize_name_draft(self.state.name_editor_draft))

        elif self.state.ui_mode == "NAME_ERROR":
            self.state.ui_mode = "NAME_EDITOR"
            self.state.name_overwrite_cursor = 1

        elif self.state.ui_mode == "INSTANCE_LIST":
            if self.state.instance_cursor == 0:
                self.state.ui_mode = "TOP"
            elif self.state.instance_cursor == len(self.state.instances) + 1 and self.can_add_instance:
                self.state.ui_mode = "PATCHER_PICKER"
                self.state.patcher_picker_context = "add"
                self.state.patcher_cursor = 1 if self.state.patchers else 0
            elif self.state.instance_cursor == len(self.state.instances) + 1 + (1 if self.can_add_instance else 0) and self.can_remove_instances:
                self.state.ui_mode = "REMOVE_INSTANCE_PICKER"
                self.state.remove_instance_picker_cursor = 1 if self.state.instances else 0
                self.state.remove_instance_origin = "instance_list"
            elif self.active_instance is not None:
                self.state.ui_mode = "INSTANCE_MENU"
                self.state.instance_menu_cursor = 1

        elif self.state.ui_mode == "REMOVE_INSTANCE_PICKER":
            if self.state.remove_instance_picker_cursor == 0:
                self.state.ui_mode = "INSTANCE_LIST"
            else:
                idx = self.state.remove_instance_picker_cursor - 1
                if 0 <= idx < len(self.state.instances):
                    self.state.pending_remove_instance_id = str(self.state.instances[idx].get("id", ""))
                    self.state.ui_mode = "REMOVE_INSTANCE_CONFIRM"
                    self.state.remove_instance_confirm_cursor = 1

        elif self.state.ui_mode == "PATCHER_PICKER":
            if self.state.patcher_cursor == 0:
                self.state.ui_mode = "TOP" if self.state.patcher_picker_context == "add" else "INSTANCE_MENU"
            else:
                idx = self.state.patcher_cursor - 1
                if 0 <= idx < len(self.state.patchers):
                    patcher_name = self.state.patchers[idx]
                    if self.state.patcher_picker_context == "replace" and self.active_instance is not None:
                        self.queue_action(
                            UIAction(
                                kind="replace_instance",
                                path=self.state.add_instance_path,
                                value=[int(self.state.active_instance_id), patcher_name],
                            )
                        )
                    else:
                        self.queue_action(
                            UIAction(
                                kind="add_instance",
                                path=self.state.add_instance_path,
                                value=[-1, patcher_name],
                            )
                        )

        elif self.state.ui_mode == "INSTANCE_MENU":
            if self.state.instance_menu_cursor == 0:
                self.state.ui_mode = "INSTANCE_LIST"
            else:
                choice = self.instance_menu_items[self.state.instance_menu_cursor - 1]
                if choice == "PARAMETERS":
                    self.state.ui_mode = "PARAM_LIST"
                    self.state.param_cursor = 1 if self.active_params else 0
                elif choice == "PRESETS":
                    self.state.ui_mode = "PRESET_LIST"
                    self.state.preset_cursor = self.preset_initial_cursor()
                elif choice == "AUDIO":
                    self.state.active_transport = "audio"
                    self.state.ui_mode = "ROUTING_GROUP"
                    self.state.routing_group_cursor = 1
                elif choice == "MIDI":
                    self.state.active_transport = "midi"
                    self.state.ui_mode = "ROUTING_GROUP"
                    self.state.routing_group_cursor = 1
                elif choice == "REPLACE INSTANCE":
                    self.state.ui_mode = "PATCHER_PICKER"
                    self.state.patcher_picker_context = "replace"
                    self.state.patcher_cursor = 1 if self.state.patchers else 0
                elif choice == "REMOVE INSTANCE":
                    self.state.pending_remove_instance_id = self.state.active_instance_id
                    self.state.remove_instance_origin = "instance_menu"
                    self.state.ui_mode = "REMOVE_INSTANCE_CONFIRM"
                    self.state.remove_instance_confirm_cursor = 1

        elif self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            if self.state.remove_instance_confirm_cursor == 0:
                self.state.ui_mode = "REMOVE_INSTANCE_PICKER" if self.state.remove_instance_origin == "instance_list" else "INSTANCE_MENU"
            elif self.remove_instance_target is not None:
                self.queue_action(
                    UIAction(
                        kind="remove_instance",
                        path=self.state.remove_instance_path,
                        value=int(self.remove_instance_target.get("id")),
                    )
                )

        elif self.state.ui_mode == "PRESET_LIST":
            if self.state.preset_cursor == 0:
                self.state.ui_mode = "INSTANCE_MENU"
            else:
                action_idx = self.state.preset_cursor - 1
                if 0 <= action_idx < len(self.preset_action_items):
                    choice = self.preset_action_items[action_idx]
                    if choice == "SAVE PRESET" and self.active_preset_save_path:
                        self._begin_name_editor(
                            context="save_preset",
                            path=self.active_preset_save_path,
                            initial_draft=self.suggested_preset_save_name(),
                            return_mode="PRESET_LIST",
                        )
                    elif choice == "RENAME PRESET" and self.active_preset_rename_path and self.current_preset_name:
                        self._begin_rename_name_editor(
                            context="rename_preset",
                            path=self.active_preset_rename_path,
                            current_name=self.current_preset_name,
                            return_mode="PRESET_LIST",
                        )
                else:
                    preset = self.selected_preset
                    if preset:
                        self.remember_loaded_preset(preset.get("name"))
                        self.queue_action(UIAction(kind="load_preset", path=preset.get("path"), value=preset.get("value")))

        elif self.state.ui_mode == "PARAM_LIST":
            if self.state.param_cursor == 0:
                self.state.ui_mode = "INSTANCE_MENU"
            else:
                param = self.selected_param
                if param:
                    self._edit_original_value = param.get("value")
                    if is_ttid_param(param):
                        self._begin_ttid_edit(param)
                        self.state.ui_mode = "EDIT"
                    elif is_step16_param(param):
                        self.state.edit_value = normalize_step16_mask(param.get("value", 0))
                        self.state.edit_step16_focus = 0
                        self.state.ui_mode = "EDIT"
                    elif is_pitch_display_param(param):
                        self.state.edit_value = None
                        self.state.ui_mode = "EDIT"
                    elif is_enum_param(param):
                        self.state.edit_value = normalize_current_value_for_edit(param)
                        options = self.active_enum_options
                        self.state.enum_cursor = options.index(self.state.edit_value) if self.state.edit_value in options else 0
                        self.state.ui_mode = "ENUM_LIST"
                    else:
                        self.state.edit_value = normalize_current_value_for_edit(param)
                        self.state.ui_mode = "EDIT"
                    self._reset_float_edit_acceleration()

        elif self.state.ui_mode == "ENUM_LIST":
            param = self.selected_param
            if param is not None and self.active_enum_options:
                self.state.edit_value = self.active_enum_options[self.state.enum_cursor]
                param["value"] = self.state.edit_value
                self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
                self.state.ui_mode = "PARAM_LIST"
                self._edit_original_value = None

        elif self.state.ui_mode == "ROUTING_GROUP":
            if self.state.routing_group_cursor == 0:
                self.state.ui_mode = "INSTANCE_MENU"
            else:
                self.state.active_routing_direction = "inputs" if self.state.routing_group_cursor == 1 else "outputs"
                self.state.ui_mode = "ROUTING_PORTS"
                self.state.routing_port_cursor = 1 if self.active_routing_ports else 0

        elif self.state.ui_mode == "ROUTING_PORTS":
            if self.state.routing_port_cursor == 0:
                self.state.ui_mode = "ROUTING_GROUP"
            elif self.selected_routing_port is not None:
                self.state.ui_mode = "ROUTING_TARGETS"
                self.state.routing_target_cursor = 1

        elif self.state.ui_mode == "ROUTING_TARGETS":
            if self.state.routing_target_cursor == 0:
                self.state.ui_mode = "ROUTING_PORTS"
            else:
                port = self.selected_routing_port
                if port is not None and port.get("path"):
                    if self.state.routing_target_cursor == 1:
                        value: list[str] = []
                    else:
                        target_idx = self.state.routing_target_cursor - 2
                        targets = self.active_routing_targets
                        if target_idx < 0 or target_idx >= len(targets):
                            value = list(port.get("connections", []))
                        else:
                            value = [targets[target_idx]]
                    self.queue_action(
                        UIAction(
                            kind="set_routing",
                            path=port.get("path"),
                            value=value,
                        )
                    )

        elif self.state.ui_mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            selected = self.selected_routing_overview_instance
            if selected is not None:
                self.state.active_instance_id = str(selected.get("id", ""))
                self.state.instance_menu_cursor = 1
                self.state.ui_mode = "INSTANCE_MENU"

        elif self.state.ui_mode == "SYSTEM_MENU":
            if self.state.system_cursor == 0:
                self.state.ui_mode = "TOP"
            else:
                choice = self.system_menu_items[self.state.system_cursor - 1]
                if choice == "AUDIO":
                    self.state.ui_mode = "SYSTEM_AUDIO"
                    self.state.system_audio_cursor = 1
                elif choice == "MAINT":
                    self.state.ui_mode = "MAINT"
                    self.state.maint_cursor = 1 if self.maint_menu_items else 0
                else:
                    self._about_press_count = 0
                    self.state.ui_mode = choice

        elif self.state.ui_mode == "SYSTEM_AUDIO":
            if self.state.system_audio_cursor == 0:
                self.state.ui_mode = "SYSTEM_MENU"
            else:
                choice = SYSTEM_AUDIO_ITEMS[self.state.system_audio_cursor - 1]
                if choice == "DEVICE":
                    self.state.ui_mode = "SYSTEM_AUDIO_DEVICE"
                    self._sync_audio_index()
                elif choice == "SAMPLE RATE":
                    self.state.ui_mode = "SYSTEM_AUDIO_RATE"
                    self._sync_audio_index()
                elif choice == "BUFFER SIZE":
                    self.state.ui_mode = "SYSTEM_AUDIO_BUFFER"
                    self._sync_audio_index()

        elif self.state.ui_mode == "SYSTEM_AUDIO_DEVICE":
            if self.state.audio_device_cursor == 0:
                self.state.ui_mode = "SYSTEM_AUDIO"
            elif self.audio_options:
                chosen = self.audio_options[self.state.audio_device_cursor - 1]
                self.queue_action(UIAction(kind="set_audio_device", device_name=chosen))

        elif self.state.ui_mode == "SYSTEM_AUDIO_RATE":
            if self.state.sample_rate_cursor == 0:
                self.state.ui_mode = "SYSTEM_AUDIO"
            elif self.sample_rate_options:
                audio = self.state.system.get("audio", {})
                path = audio.get("sample_rate_path")
                value = self.sample_rate_options[self.state.sample_rate_cursor - 1]
                self.queue_action(UIAction(kind="set_jack_config", path=path, value=value))

        elif self.state.ui_mode == "SYSTEM_AUDIO_BUFFER":
            if self.state.buffer_size_cursor == 0:
                self.state.ui_mode = "SYSTEM_AUDIO"
            elif self.buffer_size_options:
                audio = self.state.system.get("audio", {})
                path = audio.get("period_frames_path")
                value = self.buffer_size_options[self.state.buffer_size_cursor - 1]
                self.queue_action(UIAction(kind="set_jack_config", path=path, value=value))

        elif self.state.ui_mode == "MAINT":
            if self.state.maint_cursor == 0:
                self.state.ui_mode = "SYSTEM_MENU"
            else:
                choice = self.maint_menu_items[self.state.maint_cursor - 1]
                if choice == MAINT_ITEMS_REFRESH:
                    self.queue_action(UIAction(kind="refresh_snapshot"))
                elif choice == MAINT_ITEMS_RESTART_JACK:
                    self.queue_action(UIAction(kind="restart_jack"))

        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
            if param is not None and is_ttid_param(param):
                if self.state.edit_ttid_mode == "keyboard":
                    if self.state.edit_ttid_selected_pc < 12:
                        self.state.edit_value = toggle_bit(
                            normalize_ttid(self.state.edit_value),
                            self.state.edit_ttid_selected_pc,
                        )
                        param["value"] = self.state.edit_value
                        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
                    else:
                        self.state.edit_ttid_mode = "load_root"
                elif self.state.edit_ttid_mode == "load_root":
                    self.state.edit_ttid_mode = "load_scale"
                elif self.state.edit_ttid_mode == "load_scale":
                    self._apply_ttid_scale_load()
                    self.state.edit_ttid_mode = "keyboard"
                    self.state.edit_ttid_selected_pc = self.state.edit_ttid_load_root
            elif param is not None and is_step16_param(param):
                self.state.edit_value = toggle_step16(self.state.edit_value, self.state.edit_step16_focus)
                param["value"] = self.state.edit_value
                self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
            elif param is not None and is_pitch_display_param(param):
                self.state.edit_value = None
                self._edit_original_value = None
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
            else:
                if param is not None and is_discrete_param(param):
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
                self._edit_original_value = None

        self.queue_action(UIAction(kind="save_state"))

    def _handle_long_press(self) -> None:
        if self.state.ui_mode == "BRICK_PANEL":
            self._about_press_count = 0
            self.state.ui_mode = "ABOUT"
        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
            if param is not None and is_ttid_param(param):
                self.state.edit_value = None
                self.state.edit_ttid_mode = "keyboard"
                self.state.edit_ttid_selected_pc = 0
                self.state.edit_ttid_load_root = 0
                self.state.edit_ttid_scale_index = 0
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
            elif param is not None and is_step16_param(param):
                self.state.edit_value = None
                self.state.edit_step16_focus = 0
                self._edit_original_value = None
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
            elif param is not None and is_pitch_display_param(param):
                self.state.edit_value = None
                self._edit_original_value = None
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
            else:
                if param is not None and self._edit_original_value is not None:
                    param["value"] = self._edit_original_value
                    if is_step16_param(param) or not is_discrete_param(param):
                        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self._edit_original_value))
                self.state.edit_value = None
                self.state.edit_step16_focus = 0
                self._edit_original_value = None
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
        elif self.state.ui_mode == "ENUM_LIST":
            self.state.edit_value = None
            self._edit_original_value = None
            self._reset_float_edit_acceleration()
            self.state.ui_mode = "PARAM_LIST"
        elif self.state.ui_mode in ("PRESET_LIST", "PARAM_LIST", "ROUTING_GROUP"):
            self.state.ui_mode = "INSTANCE_MENU"
        elif self.state.ui_mode == "ROUTING_PORTS":
            self.state.ui_mode = "ROUTING_GROUP"
        elif self.state.ui_mode == "ROUTING_TARGETS":
            self.state.ui_mode = "ROUTING_PORTS"
        elif self.state.ui_mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            self.state.ui_mode = "GRAPH_MENU"
        elif self.state.ui_mode == "GRAPH_STARTUP_SET_LIST":
            self.state.ui_mode = "GRAPH_STARTUP"
        elif self.state.ui_mode == "NAME_INLINE_EDITOR":
            self._exit_inline_name_editor()
        elif self.state.ui_mode in {"NAME_OVERWRITE_CONFIRM", "NAME_ERROR"}:
            self.state.ui_mode = "NAME_EDITOR"
        elif self.state.ui_mode == "NAME_EDITOR":
            self._cancel_name_editor()
        elif self.state.ui_mode in ("GRAPH_STATUS", "GRAPH_STARTUP"):
            self.state.ui_mode = "GRAPH_MENU"
        elif self.state.ui_mode in {"GRAPH_SET_LIST", "GRAPH_PRESET_LIST"}:
            self.state.ui_mode = "GRAPH_MENU"
        elif self.state.ui_mode == "GRAPH_MENU":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "INSTANCE_MENU":
            self.state.ui_mode = "INSTANCE_LIST"
        elif self.state.ui_mode == "INSTANCE_LIST":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "REMOVE_INSTANCE_PICKER":
            self.state.ui_mode = "INSTANCE_LIST"
        elif self.state.ui_mode == "PATCHER_PICKER":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self.state.ui_mode = "REMOVE_INSTANCE_PICKER" if self.state.remove_instance_origin == "instance_list" else "INSTANCE_MENU"
        elif self.state.ui_mode in ("STATUS", "NETWORK", "ABOUT", "MAINT"):
            self._about_press_count = 0
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode in ("SYSTEM_AUDIO_DEVICE", "SYSTEM_AUDIO_RATE", "SYSTEM_AUDIO_BUFFER"):
            self.state.ui_mode = "SYSTEM_AUDIO"
        elif self.state.ui_mode == "SYSTEM_AUDIO":
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode == "SYSTEM_MENU":
            self.state.ui_mode = "TOP"

        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def instance_cursor_for_active_instance(self) -> int:
        active_id = str(self.state.active_instance_id)
        if not active_id:
            return 1 if self.state.instances else 0
        for idx, item in enumerate(self.state.instances, start=1):
            if str(item.get("id", "")) == active_id:
                return idx
        return 1 if self.state.instances else 0
