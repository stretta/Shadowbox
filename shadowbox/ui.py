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
    pitch_state_key,
)
from shadowbox.editors.scope import (
    append_scope_samples,
    normalize_scope_samples,
)
from shadowbox.editors.step16 import (
    is_step16_param,
    move_focus as move_step16_focus,
    normalize_mask as normalize_step16_mask,
    playhead_state_key,
    playhead_stage_index,
    toggle_step as toggle_step16,
)
from shadowbox.rnbo import RNBO_HOST, RNBO_PORT
from shadowbox.surfaces import resolve_instance_surface, surface_spec_for_key
from shadowbox.surfaces.list_sequencer import FIELD_KEYS, SIGNED_FIELD_KEYS, format_list_value
from shadowbox.surfaces.list_vel_sequencer import ROW_KEYS
from shadowbox.surfaces.organ import FOOTAGES
from shadowbox.transpose_control import (
    ROLE_CHROMATIC,
    ROLE_LABELS,
    ROLE_NONE,
    ROLE_SCALAR,
    common_target_range,
    normalize_role,
    split_midi_port_identity,
    target_status,
)


STATE_PATH = Path.home() / "rnbo-ui" / "shadowbox_state.json"

ROUTING_GROUP_ITEMS = ["INPUTS", "OUTPUTS"]
SYSTEM_AUDIO_ITEMS = ["DEVICE", "SAMPLE RATE", "BUFFER SIZE"]
TRANSPOSE_AUTHORITY_LABELS = {
    "unconfigured": "UNCONFIGURED",
    "standalone": "LOCAL",
    "shadowscore": "SHADOWSCORE",
}
REMOVE_INSTANCE_CONFIRM_ITEMS = ["..", "REMOVE"]
REMOVE_INSTANCE_CONFIRM_BUTTONS = ["CANCEL", "REMOVE"]
MAINT_ITEMS_REFRESH = "REFRESH"
MAINT_ITEMS_RESTART_JACK = "RESTART JACK"
NAME_EDITOR_EDIT = "EDIT NAME"
NAME_EDITOR_GENERATE = "GENERATE NAME"
NAME_EDITOR_ADD_DATE = "ADD DATE"
NAME_EDITOR_DELETE = "DELETE CHAR"
NAME_EDITOR_CLEAR = "CLEAR NAME"
NAME_EDITOR_SAVE = "SAVE"
NAME_EDITOR_CANCEL = "CANCEL"
WIFI_PASSWORD_EDIT = "EDIT"
NAME_OVERWRITE_CONFIRM_ITEMS = ["..", "OVERWRITE"]
NAME_OVERWRITE_CONFIRM_BUTTONS = ["CANCEL", "OVERWRITE"]
NAME_ERROR_DISMISS = "EDIT NAME"
NAME_ERROR_BUTTONS = ["EDIT NAME"]
PRESET_ACTION_SAVE = "SAVE"
PRESET_ACTION_SAVE_AS = "SAVE AS..."
PRESET_ACTION_REMOVE = "REMOVE"
SET_MENU_CURRENT = "CURRENT SET"
SET_MENU_LOAD = "LOAD SET"
NAME_EDITOR_MAX_LEN = 24
WIFI_PASSWORD_MAX_LEN = 63
NAME_EDITOR_CHAR_OPTIONS: list[tuple[str, str]] = [
    ("SPACE", " "),
    ("-", "-"),
    ("_", "_"),
] + [(char, char) for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.!@#$%&*+=?/,:;~"]
NAME_TOUCH_LETTER_ROWS: list[list[str]] = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
NAME_TOUCH_NUMBER_ROWS: list[list[str]] = [
    list("1234567890"),
    list("-_.!@#"),
    list("$%&*+=?"),
]
NAME_TOUCH_KEY_VALUES: list[str] = list(dict.fromkeys([char for row in NAME_TOUCH_LETTER_ROWS + NAME_TOUCH_NUMBER_ROWS for char in row]))
NAME_INLINE_DELETE_LABEL = "DEL"
NEW_GRAPH_SET_NAME = "New Graph"
TOUCH_PAGE_ROWS = 5


@dataclass
class UIAction:
    kind: str
    path: Optional[str] = None
    value: Any = None
    device_name: Optional[str] = None
    ssid: Optional[str] = None


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
    preset_remove_cursor: int = 0
    param_cursor: int = 0
    enum_cursor: int = 0
    routing_group_cursor: int = 0
    routing_port_cursor: int = 0
    routing_target_cursor: int = 0
    routing_add_cursor: int = 0
    routing_disconnect_cursor: int = 0
    routing_overview_cursor: int = 0
    graph_menu_cursor: int = 0
    graph_set_cursor: int = 0
    graph_load_set_cursor: int = 0
    graph_preset_cursor: int = 0
    graph_preset_remove_cursor: int = 0
    graph_startup_cursor: int = 0
    graph_startup_set_cursor: int = 0
    system_cursor: int = 0
    network_cursor: int = 0
    wifi_network_cursor: int = 0
    system_audio_cursor: int = 0
    transport_cursor: int = 0
    transpose_cursor: int = 0
    transpose_controller_cursor: int = 0
    transpose_role_cursor: int = 0
    transpose_authority_cursor: int = 0
    maint_cursor: int = 0
    software_update_cursor: int = 0
    audio_device_cursor: int = 0
    sample_rate_cursor: int = 0
    buffer_size_cursor: int = 0

    active_instance_id: str = ""
    active_transport: str = "audio"
    active_routing_direction: str = "inputs"
    patcher_picker_context: str = "add"
    pending_remove_instance_id: str = ""
    remove_instance_origin: str = ""
    pending_add_instance_count: int = 0
    midi_learn_instance_id: str = ""
    midi_learn_param_path: str = ""

    transpose_authority: str = "unconfigured"
    transpose_chromatic: int = 0
    transpose_scalar: int = 0
    transpose_controller_identity: str = ""
    transpose_controller_role: str = ROLE_NONE
    transpose_controller_devices: list[Any] = field(default_factory=list)
    transpose_controller_connected_identity: str = ""
    transpose_last_source: str = "Local"
    transpose_edit_role: str = ""

    edit_value: Any = None
    edit_numeric_draft: str = ""
    edit_ttid_mode: str = "keyboard"
    edit_ttid_selected_pc: int = 0
    edit_ttid_load_root: int = 0
    edit_ttid_scale_names: list[str] = field(default_factory=list)
    edit_ttid_scale_index: int = 0
    edit_step16_focus: int = 0
    edit_scope_samples: list[float] = field(default_factory=list)
    active_surface_key: str = ""
    surface_focus: int = 0
    surface_state: dict[str, Any] = field(default_factory=dict)
    surface_touch_capture: int | None = None
    name_editor_context: str = ""
    name_editor_return_mode: str = ""
    name_editor_path: str = ""
    name_editor_draft: str = ""
    name_editor_target_name: str = ""
    pending_wifi_ssid: str = ""
    name_editor_cursor: int = 1
    name_inline_cursor: int = 0
    name_inline_edit_mode: bool = False
    name_inline_preview_index: int = 0
    name_keyboard_shift: bool = False
    name_keyboard_mode: str = "letters"
    name_overwrite_cursor: int = 1
    name_error_message: str = ""
    network_error_message: str = ""
    status_message: str = ""
    status_frames: int = 0
    software_update: dict = field(default_factory=dict)

    busy: bool = False
    busy_reason: str = ""
    activity_ticks: int = 0

    audio_restart_device: str = ""
    audio_restart_return_mode: str = "SYSTEM_AUDIO_DEVICE"

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


def normalize_transpose_authority(value: Any) -> str:
    authority = str(value or "").strip().lower()
    return authority if authority in TRANSPOSE_AUTHORITY_LABELS else "unconfigured"


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


def quantize_edit_value(param: dict | None, value: Any) -> Any:
    if not isinstance(param, dict) or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value

    pmin = param.get("min")
    pmax = param.get("max")
    numeric = float(value)
    if isinstance(pmin, (int, float)):
        numeric = max(float(pmin), numeric)
    if isinstance(pmax, (int, float)):
        numeric = min(float(pmax), numeric)

    step = edit_step(param)
    if step is not None:
        origin = float(pmin) if isinstance(pmin, (int, float)) else 0.0
        grid_index = math.floor(((numeric - origin) / step) + 0.5)
        if isinstance(pmin, (int, float)):
            grid_index = max(math.ceil((float(pmin) - origin) / step), grid_index)
        if isinstance(pmax, (int, float)):
            grid_index = min(math.floor((float(pmax) - origin) / step), grid_index)
        numeric = origin + (grid_index * step)

    if edit_as_int(param):
        return int(round(numeric))
    return numeric


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
    if isinstance(value, (int, float)):
        return quantize_edit_value(param, value)
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
        current_value = quantize_edit_value(param, current_value)
        new_value = current_value + (step * delta)
        return quantize_edit_value(param, new_value)
    return current_value


def is_discrete_param(param: dict) -> bool:
    return is_boolish(param) or (isinstance(param.get("vals"), list) and len(param.get("vals")) > 0)


def is_enum_param(param: dict) -> bool:
    return (not is_boolish(param)) and isinstance(param.get("vals"), list) and len(param.get("vals")) > 0


@dataclass
class UIEvent:
    kind: str
    delta: int = 0
    index: int | None = None
    button_id: str = ""
    value: float | None = None
    pressed: bool = False


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
        self.render_revision = 0
        self.last_render_reason = "startup"
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

    def _toggle_bool_param(self, param: dict) -> None:
        current_value = normalize_current_value_for_edit(param)
        toggled_value = 0 if bool(current_value) else 1
        param["value"] = toggled_value
        self.state.edit_value = toggled_value
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=toggled_value))

    def restore_from_saved_state(self) -> None:
        saved = self._saved_state_cache
        self.state.top_index = clamp_index(int(saved.get("top_index", 0)), len(self.top_level_items))
        self.state.saved_audio_card = str(saved.get("saved_audio_card", ""))
        transpose = saved.get("transpose_control", {})
        if not isinstance(transpose, dict):
            transpose = {}
        self.state.transpose_authority = normalize_transpose_authority(transpose.get("authority"))
        self.state.transpose_chromatic = int(transpose.get("chromatic", 0) or 0)
        self.state.transpose_scalar = int(transpose.get("scalar", 0) or 0)
        self.state.transpose_controller_identity = str(transpose.get("controller_identity", "") or "")
        self.state.transpose_controller_role = normalize_role(transpose.get("controller_role"))
        self.state.transpose_last_source = str(transpose.get("last_source", "Local") or "Local")

    def save_state(self) -> None:
        save_state_file(
            {
                "top_index": self.state.top_index,
                "saved_audio_card": self.current_audio_card,
                "transpose_control": {
                    "version": 1,
                    "authority": normalize_transpose_authority(self.state.transpose_authority),
                    "chromatic": int(self.state.transpose_chromatic),
                    "scalar": int(self.state.transpose_scalar),
                    "controller_identity": self.state.transpose_controller_identity,
                    "controller_role": normalize_role(self.state.transpose_controller_role),
                    "last_source": self.state.transpose_last_source,
                },
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
        self.state.routing_add_cursor = 0
        self.state.routing_overview_cursor = 1 if self.state.instances else 0
        self.state.graph_menu_cursor = 1 if self.graph_menu_items else 0
        self.state.graph_set_cursor = self.graph_set_initial_cursor()
        self.state.graph_load_set_cursor = self.graph_load_set_initial_cursor()
        self.state.graph_preset_cursor = self.graph_preset_initial_cursor()
        self.state.graph_preset_remove_cursor = 1 if self.available_graph_preset_names else 0
        self.state.graph_startup_cursor = 1 if self.graph_startup_menu_items else 0
        self.state.graph_startup_set_cursor = 1 if self.available_set_names else 0
        self.state.system_cursor = 1
        self.state.network_cursor = 1 if self.network_value_rows else 0
        self.state.wifi_network_cursor = self.wifi_network_initial_cursor()
        self.state.system_audio_cursor = 1
        self.state.transport_cursor = 1
        self.state.transpose_cursor = 2
        self.state.transpose_controller_cursor = 0
        self.state.transpose_role_cursor = 0
        self.state.transpose_authority_cursor = 0
        self.state.maint_cursor = 1 if self.maint_menu_items else 0
        self.state.software_update_cursor = self.software_update_check_cursor
        self.state.audio_device_cursor = 1 if self.audio_options else 0
        self.state.sample_rate_cursor = 1 if self.sample_rate_options else 0
        self.state.buffer_size_cursor = 1 if self.buffer_size_options else 0
        self.state.active_instance_id = str(self.state.instances[0]["id"]) if self.state.instances else ""
        self.state.active_transport = "audio"
        self.state.active_routing_direction = "inputs"
        self.state.patcher_picker_context = "add"
        self.state.pending_remove_instance_id = ""
        self.state.remove_instance_origin = ""
        self.state.midi_learn_instance_id = ""
        self.state.midi_learn_param_path = ""
        self.state.edit_value = None
        self.state.edit_numeric_draft = ""
        self.state.edit_ttid_mode = "keyboard"
        self.state.edit_ttid_selected_pc = 0
        self.state.edit_ttid_load_root = 0
        self.state.edit_ttid_scale_names = []
        self.state.edit_ttid_scale_index = 0
        self.state.edit_step16_focus = 0
        self.state.edit_scope_samples = []
        self.state.name_editor_context = ""
        self.state.name_editor_return_mode = ""
        self.state.name_editor_path = ""
        self.state.name_editor_draft = ""
        self.state.name_editor_target_name = ""
        self.state.pending_wifi_ssid = ""
        self.state.name_editor_cursor = 1
        self.state.name_inline_cursor = 0
        self.state.name_inline_edit_mode = False
        self.state.name_inline_preview_index = 0
        self.state.name_overwrite_cursor = 1
        self.state.name_error_message = ""
        self.state.network_error_message = ""
        self.state.status_message = ""
        self.state.status_frames = 0
        self._edit_original_value = None
        self._about_press_count = 0
        self._reset_float_edit_acceleration()
        self.brick_panel.reset()

    def set_busy(self, busy: bool, reason: str = "") -> None:
        self.state.busy = busy
        self.state.busy_reason = reason
        if busy:
            self.state.activity_ticks += 1
        self.request_render("busy")

    def begin_audio_restart(self, device_name: str = "", return_mode: str = "SYSTEM_AUDIO_DEVICE") -> None:
        self.state.audio_restart_device = str(device_name or "").strip()
        self.state.audio_restart_return_mode = str(return_mode or "SYSTEM_AUDIO_DEVICE")
        self.state.ui_mode = "SYSTEM_AUDIO_RESTART"
        self.set_busy(True, "audio")

    def finish_audio_restart(self) -> None:
        device_name = self.state.audio_restart_device
        self.state.ui_mode = self.state.audio_restart_return_mode
        self.set_busy(False)
        self.set_status_message(f"{device_name} ready" if device_name else "JACK ready")

    def fail_audio_restart(self, message: str) -> None:
        self.state.ui_mode = self.state.audio_restart_return_mode
        self.set_busy(False)
        self.set_status_message(str(message or "JACK restart failed"), frames=60)

    def request_render(self, reason: str = "state") -> int:
        self.render_revision += 1
        self.last_render_reason = str(reason)
        return self.render_revision

    def set_status_message(self, message: str, frames: int = 36) -> None:
        self.state.status_message = str(message or "")
        self.state.status_frames = max(0, int(frames))
        if self.state.status_message:
            self.state.activity_ticks += 1
        self.request_render("status")

    def set_software_update_status(self, status: dict) -> None:
        next_status = dict(status or {})
        if "targets" not in next_status:
            next_status = {"targets": {"shadowbox": next_status}, **next_status}
        self.state.software_update = next_status
        self.state.software_update_cursor = clamp_index(
            self.state.software_update_cursor if self.state.software_update_cursor > 0 else 1,
            len(self.software_update_rows),
        )
        self.state.activity_ticks += 1
        self.request_render("software_update")

    def apply_runner_snapshot(self, snapshot) -> None:
        current_id = str(self.state.active_instance_id)
        current_param_path = self.selected_param.get("path") if self.selected_param else ""
        pending_add_instance_count = self.state.pending_add_instance_count

        self.state.instances = snapshot.instances
        self.state.patchers = snapshot.patchers
        self.state.add_instance_path = snapshot.add_instance_path
        self.state.remove_instance_path = snapshot.remove_instance_path
        cached_network = self.state.system.get("network", {}) if isinstance(self.state.system, dict) else {}
        self.state.system = dict(snapshot.system)
        if cached_network:
            self.state.system["network"] = cached_network
        self._sync_audio_index()
        self._cleanup_current_presets()

        if pending_add_instance_count > 0 and len(self.state.instances) > pending_add_instance_count - 1:
            new_index = len(self.state.instances) - 1
            self.state.active_instance_id = str(self.state.instances[new_index].get("id", ""))
            self.state.instance_cursor = new_index + 1
            self.state.pending_add_instance_count = 0
        elif self.state.instances:
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
        self.state.preset_remove_cursor = clamp_index(self.state.preset_remove_cursor, len(self.active_presets) + 1)
        self.state.maint_cursor = clamp_index(self.state.maint_cursor, len(self.maint_menu_items) + 1)
        self.state.network_cursor = clamp_index(
            self.state.network_cursor if self.state.network_cursor > 0 else 1,
            len(self.network_value_rows),
        )
        self.state.software_update_cursor = clamp_index(
            self.state.software_update_cursor if self.state.software_update_cursor > 0 else 1,
            len(self.software_update_rows),
        )
        self.state.wifi_network_cursor = clamp_index(self.state.wifi_network_cursor, len(self.wifi_network_rows))
        self.state.routing_port_cursor = clamp_index(self.state.routing_port_cursor, len(self.active_routing_ports) + 1)
        self.state.routing_target_cursor = clamp_index(self.state.routing_target_cursor, len(self.routing_assignment_rows))
        self.state.routing_add_cursor = clamp_index(self.state.routing_add_cursor, len(self.available_routing_add_targets) + 1)
        self.state.routing_overview_cursor = clamp_index(
            self.state.routing_overview_cursor if self.state.routing_overview_cursor > 0 else 1,
            len(self.routing_overview_rows),
        )
        self.state.graph_menu_cursor = clamp_index(self.state.graph_menu_cursor, len(self.graph_menu_items) + 1)
        self.state.graph_set_cursor = clamp_index(self.state.graph_set_cursor, len(self.graph_set_menu_items))
        self.state.graph_load_set_cursor = clamp_index(self.state.graph_load_set_cursor, len(self.graph_load_set_menu_items))
        self.state.graph_preset_cursor = clamp_index(self.state.graph_preset_cursor, len(self.graph_preset_menu_items))
        self.state.graph_preset_remove_cursor = clamp_index(self.state.graph_preset_remove_cursor, len(self.available_graph_preset_names) + 1)
        self.state.graph_startup_cursor = clamp_index(self.state.graph_startup_cursor, len(self.graph_startup_menu_items) + 1)
        self.state.graph_startup_set_cursor = clamp_index(self.state.graph_startup_set_cursor, len(self.available_set_names) + 1)

        if self.state.ui_mode == "INSTANCE_SURFACE":
            active = self.active_instance_surface
            if active is None:
                self._exit_instance_surface()
            elif self.state.active_surface_key == "time_domain_scope":
                samples = active[1].state.get("samples")
                if samples is not None and not self.state.edit_scope_samples:
                    self.state.edit_scope_samples = normalize_scope_samples(samples.get("value"))
                anchor = active[1].params.get("sample_rate")
                if anchor is not None:
                    self.state.edit_value = normalize_current_value_for_edit(anchor)
            elif self.state.active_surface_key in {"list_sequencer", "list_vel_sequencer"}:
                drafts = self._list_surface_drafts()
                dirty = self.state.surface_state.get("dirty", {})
                for key in self._list_surface_keys():
                    ack = active[1].state.get(f"{key}_ack")
                    if ack is not None and not (isinstance(dirty, dict) and dirty.get(key)):
                        drafts[key] = format_list_value(ack.get("value"))
        elif self.state.ui_mode == "EDIT" and self.selected_param:
            if current_param_path and self.selected_param.get("path") != current_param_path:
                self.state.ui_mode = "PARAM_LIST"
                self.state.edit_value = None
            elif is_ttid_param(self.selected_param):
                self.state.edit_value = normalize_ttid(self.state.edit_value)
            elif is_step16_param(self.selected_param):
                self.state.edit_value = normalize_step16_mask(self.state.edit_value)
            else:
                self.state.edit_value = normalize_current_value_for_edit(self.selected_param)
        self.request_render("runner_snapshot")

    def apply_network_snapshot(self, network: dict) -> None:
        system = dict(self.state.system or {})
        previous = system.get("network", {}) if isinstance(system.get("network", {}), dict) else {}
        merged = dict(previous)
        merged.update(dict(network or {}))
        # Status-only refreshes preserve the cached Wi-Fi list.
        if "wifi_networks" not in network and "wifi_networks" in previous:
            merged["wifi_networks"] = previous["wifi_networks"]
        system["network"] = merged
        self.state.system = system
        self.state.network_cursor = clamp_index(self.state.network_cursor or 1, len(self.network_value_rows))
        self.state.wifi_network_cursor = clamp_index(self.state.wifi_network_cursor, len(self.wifi_network_rows))
        self.request_render("network_snapshot")

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
                    if (
                        (
                            self.state.ui_mode == "INSTANCE_SURFACE"
                            and self.state.active_surface_key == "time_domain_scope"
                            and self.surface_state_binding("samples") is item
                        )
                    ):
                        self.state.edit_scope_samples = append_scope_samples(self.state.edit_scope_samples, value)
                    elif self._list_surface_ready() and self.state.active_instance_id == instance_id:
                        active = self.active_instance_surface
                        dirty = self.state.surface_state.get("dirty", {})
                        if active is not None:
                            for key in self._list_surface_keys():
                                if active[1].state.get(f"{key}_ack") is item:
                                    if not (isinstance(dirty, dict) and dirty.get(key)):
                                        self._list_surface_drafts()[key] = format_list_value(value)
                                    break
                    if self.state.ui_mode in {"EDIT", "INSTANCE_SURFACE"} and self.state.active_instance_id == instance_id:
                        self.request_render("osc_state")
                    return True
        return False

    def apply_instance_param_update(self, instance_id: str, path: str, value: Any) -> bool:
        instance_id = str(instance_id)
        path = str(path)
        if not instance_id or not path:
            return False

        for instance in self.state.instances:
            if str(instance.get("id", "")) != instance_id:
                continue
            for param in instance.get("params", []):
                param_path = str(param.get("path", ""))
                if param_path != path:
                    continue
                previous = param.get("value")
                values_match = previous == value
                if isinstance(previous, (int, float)) and isinstance(value, (int, float)):
                    values_match = abs(float(previous) - float(value)) < 1e-9
                if values_match:
                    return True
                param["value"] = value
                if self.state.ui_mode == "EDIT" and self.selected_param is param:
                    self.state.edit_value = normalize_current_value_for_edit(param)
                if (
                    self.state.ui_mode == "INSTANCE_SURFACE"
                    and self.state.active_instance_id == instance_id
                    and self.surface_param_binding_for_path(path) is not None
                ):
                    if self.state.active_surface_key == "time_domain_scope":
                        self.state.edit_value = normalize_current_value_for_edit(param)
                    self.request_render("osc_surface_param")
                elif self.state.active_instance_id == instance_id and self.state.ui_mode in {"PARAM_LIST", "EDIT"}:
                    self.request_render("osc_param")
                return True
        return False

    def _selected_param_meta_path(self) -> str:
        param = self.selected_param
        path = str(param.get("path", "") or "") if isinstance(param, dict) else ""
        return f"{path}/meta" if path else ""

    def _selected_instance_midi_report_path(self) -> str:
        instance_id = str(self.state.active_instance_id or "").strip()
        return f"/rnbo/inst/{instance_id}/midi/last/report" if instance_id else ""

    def _replace_selected_param_midi_mapping(self, mapping: dict[str, Any] | None) -> bool:
        param = self.selected_param
        if not isinstance(param, dict):
            return False
        meta_path = self._selected_param_meta_path()
        if not meta_path:
            return False

        metadata = param.get("metadata", {})
        next_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        if mapping:
            next_metadata["midi"] = mapping
        else:
            next_metadata.pop("midi", None)
        param["metadata"] = next_metadata
        self.queue_action(UIAction(kind="send_osc", path=meta_path, value=json.dumps(next_metadata, separators=(",", ":"))))
        self.queue_action(UIAction(kind="save_midi_profile", value=str(self.state.active_instance_id or "")))
        return True

    def apply_instance_midi_learn_update(self, instance_id: str, path: str, value: Any) -> bool:
        instance_id = str(instance_id)
        if not self.state.midi_learn_param_path or instance_id != str(self.state.midi_learn_instance_id):
            return False
        if str(path) != f"/rnbo/inst/{instance_id}/midi/last/value":
            return False

        if isinstance(value, str):
            try:
                mapping = json.loads(value)
            except Exception:
                return False
        elif isinstance(value, dict):
            mapping = value
        else:
            return False
        if not isinstance(mapping, dict) or "chan" not in mapping or "ctrl" not in mapping:
            return False

        target_path = self.state.midi_learn_param_path
        previous_cursor = self.state.param_cursor
        for instance in self.state.instances:
            if str(instance.get("id", "")) != instance_id:
                continue
            for idx, param in enumerate(instance.get("params", []), start=1):
                if str(param.get("path", "")) != target_path:
                    continue
                self.state.active_instance_id = instance_id
                self.state.param_cursor = idx
                normalized = {"chan": mapping.get("chan"), "ctrl": mapping.get("ctrl")}
                self._replace_selected_param_midi_mapping(normalized)
                self.state.midi_learn_instance_id = ""
                self.state.midi_learn_param_path = ""
                report_path = f"/rnbo/inst/{instance_id}/midi/last/report"
                self.queue_action(UIAction(kind="send_osc", path=report_path, value=False))
                return True
        self.state.param_cursor = previous_cursor
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
        return ["SETS", "INSTANCES", "SYSTEM"]

    @property
    def instance_menu_items(self) -> list[str]:
        items = []
        if self.available_instance_surface is not None:
            items.append(self.available_instance_surface[0].title)
        items.extend(["PARAMETERS", "PRESETS", "AUDIO", "MIDI"])
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
        items = ["STATUS", "AUDIO"]
        if self.transport_available:
            items.append("TRANSPORT")
        if self.graph_startup_menu_items:
            items.append("STARTUP")
        items.extend(["TRANSPOSE", "NETWORK", "UPDATE", "ABOUT"])
        if self.maint_menu_items:
            items.append("MAINT")
        return items

    @property
    def transport_available(self) -> bool:
        transport = self.state.system.get("transport", {})
        return bool(transport.get("rolling_path") and transport.get("bpm_path"))

    @property
    def transport_rows(self) -> list[ValueRow]:
        transport = self.state.system.get("transport", {})
        rolling = transport.get("rolling")
        bpm = transport.get("bpm")
        bpm_text = f"{float(bpm):.1f} BPM" if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) else "-"
        return [
            ValueRow("state", "RUNNING" if rolling is True else "STOPPED" if rolling is False else "UNKNOWN", current=rolling is True),
            ValueRow("tempo", bpm_text),
        ]

    @property
    def transport_tempo_edit_param(self) -> dict:
        transport = self.state.system.get("transport", {})
        return {
            "name": "Tempo",
            "path": transport.get("bpm_path", ""),
            "value": transport.get("bpm"),
            "min": 20.0,
            "max": 300.0,
            "metadata": {"display_precision": 1, "edit_step": 1.0},
        }

    def apply_transport_update(self, path: str, value: Any) -> bool:
        transport = self.state.system.get("transport", {})
        if not isinstance(transport, dict):
            return False
        if str(path) == str(transport.get("rolling_path", "")):
            next_value = bool(value)
            if transport.get("rolling") == next_value:
                return False
            transport["rolling"] = next_value
        elif str(path) == str(transport.get("bpm_path", "")) and isinstance(value, (int, float)) and not isinstance(value, bool):
            next_value = float(value)
            if transport.get("bpm") == next_value:
                return False
            transport["bpm"] = next_value
            if self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
                self.state.edit_value = next_value
        else:
            return False
        self.request_render("transport")
        return True

    @property
    def transpose_controller_display(self) -> str:
        identity = self.state.transpose_controller_identity
        if not identity:
            return "NONE"
        device = next(
            (item for item in self.state.transpose_controller_devices if getattr(item, "identity", "") == identity),
            None,
        )
        if device is not None:
            name = str(getattr(device, "display_name", "") or "MIDI")
            return name if self.state.transpose_controller_connected_identity == identity else f"{name} OFFLINE"
        client_name, port_name = split_midi_port_identity(identity)
        name = f"{client_name}: {port_name}" if client_name and port_name != client_name else client_name or port_name or "MIDI"
        return f"{name} OFFLINE"

    @property
    def transpose_rows(self) -> list[ValueRow]:
        chromatic_status = target_status(self.state.instances, ROLE_CHROMATIC, self.state.transpose_chromatic)
        scalar_status = target_status(self.state.instances, ROLE_SCALAR, self.state.transpose_scalar)

        def value_text(value: int, status) -> str:
            prefix = f"{value:+d}"
            if status.mixed:
                return f"{prefix} MIXED {status.matching}/{status.compatible}"
            return f"{prefix} {status.matching}/{status.compatible}"

        return [
            ValueRow(
                "authority",
                TRANSPOSE_AUTHORITY_LABELS[normalize_transpose_authority(self.state.transpose_authority)],
                current=self.state.transpose_authority == "standalone",
            ),
            ValueRow("chromatic", value_text(self.state.transpose_chromatic, chromatic_status), current=chromatic_status.mixed),
            ValueRow("scalar", value_text(self.state.transpose_scalar, scalar_status), current=scalar_status.mixed),
            ValueRow("controller", self.transpose_controller_display, current=bool(self.state.transpose_controller_connected_identity)),
            ValueRow("function", ROLE_LABELS[normalize_role(self.state.transpose_controller_role)]),
            ValueRow("source", self.state.transpose_last_source),
        ]

    @property
    def transpose_controller_items(self) -> list[str]:
        return ["..", "NONE"] + [label for _identity, label in self.transpose_controller_choices]

    @property
    def transpose_controller_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        configured = self.state.transpose_controller_identity
        seen: set[str] = set()
        for device in self.state.transpose_controller_devices:
            identity = str(getattr(device, "identity", "") or "")
            if not identity or identity in seen:
                continue
            seen.add(identity)
            choices.append((identity, str(getattr(device, "display_name", "") or identity)))
        if configured and configured not in seen:
            choices.append((configured, self.transpose_controller_display))
        return choices

    @property
    def transpose_role_items(self) -> list[str]:
        return ["..", ROLE_LABELS[ROLE_NONE], ROLE_LABELS[ROLE_CHROMATIC], ROLE_LABELS[ROLE_SCALAR]]

    @property
    def transpose_authority_items(self) -> list[str]:
        return ["..", "UNCONFIGURED", "LOCAL", "SHADOWSCORE"]

    @property
    def transpose_edit_param(self) -> dict:
        role = normalize_role(self.state.transpose_edit_role)
        minimum, maximum = common_target_range(self.state.instances, role)
        name = "Chromatic Transpose" if role == ROLE_CHROMATIC else "Scalar Transpose"
        return {
            "name": name,
            "min": minimum,
            "max": maximum,
            "metadata": {"edit_as": "int", "display_as": "int", "edit_step": 1},
        }

    def set_transpose_devices(self, devices: list[Any], connected_identity: str = "") -> None:
        old = (
            [(getattr(item, "identity", ""), getattr(item, "address", "")) for item in self.state.transpose_controller_devices],
            self.state.transpose_controller_connected_identity,
        )
        self.state.transpose_controller_devices = list(devices)
        self.state.transpose_controller_connected_identity = str(connected_identity or "")
        new = (
            [(getattr(item, "identity", ""), getattr(item, "address", "")) for item in self.state.transpose_controller_devices],
            self.state.transpose_controller_connected_identity,
        )
        if new != old:
            self.request_render("transpose_devices")

    def set_transpose_value(self, role: str, value: Any, source: str) -> bool:
        if normalize_transpose_authority(self.state.transpose_authority) != "standalone":
            self.set_status_message("Select LOCAL transpose authority")
            return False
        role = normalize_role(role)
        if role not in {ROLE_CHROMATIC, ROLE_SCALAR}:
            return False
        param = {
            "name": ROLE_LABELS[role],
            "min": -60,
            "max": 67,
            "metadata": {"edit_as": "int", "display_as": "int", "edit_step": 1},
        }
        numeric = quantize_edit_value(param, value)
        numeric = int(numeric)
        field_name = "transpose_chromatic" if role == ROLE_CHROMATIC else "transpose_scalar"
        previous = int(getattr(self.state, field_name))
        source_text = str(source or "Local")
        changed = previous != numeric or self.state.transpose_last_source != source_text
        setattr(self.state, field_name, numeric)
        self.state.transpose_last_source = source_text
        if self.state.transpose_edit_role == role:
            self.state.edit_value = numeric
        if changed:
            self.queue_action(UIAction(kind="set_transpose", path=role, value=numeric))
            self.queue_action(UIAction(kind="save_state"))
            self.state.activity_ticks += 1
            self.request_render("transpose_value")
        return changed

    def apply_transpose_midi_note(self, note: int, device_name: str = "MIDI") -> bool:
        role = normalize_role(self.state.transpose_controller_role)
        if role == ROLE_NONE:
            return False
        return self.set_transpose_value(role, int(note) - 60, f"MIDI {device_name}")

    def set_transpose_authority(self, authority: str) -> bool:
        authority = normalize_transpose_authority(authority)
        if authority == self.state.transpose_authority:
            return False
        self.state.transpose_authority = authority
        self.state.transpose_last_source = "Local" if authority == "standalone" else "ShadowScore" if authority == "shadowscore" else "None"
        self.queue_action(UIAction(kind="set_transpose_authority", value=authority))
        self.queue_action(UIAction(kind="save_state"))
        self.request_render("transpose_authority")
        return True

    @property
    def graph_menu_items(self) -> list[str]:
        items: list[str] = self.graph_action_items
        if self.graph_preset_menu_enabled:
            items.append("SET PRESETS")
        items.extend(["AUDIO OVERVIEW", "MIDI OVERVIEW"])
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
    def graph_action_items(self) -> list[str]:
        if not self.graph_save_path:
            return []
        items: list[str] = []
        if self.current_set_name != "(untitled)":
            items.append(PRESET_ACTION_SAVE)
        items.append(PRESET_ACTION_SAVE_AS)
        return items

    @property
    def graph_set_menu_items(self) -> list[str]:
        return ["..", SET_MENU_CURRENT, SET_MENU_LOAD]

    @property
    def graph_set_rows(self) -> list[MenuRow]:
        return [MenuRow(".."), MenuRow(SET_MENU_CURRENT, current=True), MenuRow(SET_MENU_LOAD)]

    def graph_set_initial_cursor(self) -> int:
        return 1

    @property
    def graph_load_set_menu_items(self) -> list[str]:
        return [".."] + self.available_set_names if self.available_set_names else ["..", "no saved sets"]

    @property
    def graph_load_set_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        if not self.available_set_names:
            rows.append(MenuRow("no saved sets"))
            return rows
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
        return rows

    def graph_load_set_initial_cursor(self) -> int:
        return 1 if self.available_set_names else 0

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
            items.extend([PRESET_ACTION_SAVE, PRESET_ACTION_SAVE_AS])
        if self.graph_preset_destroy_path and self.available_graph_preset_names:
            items.append(PRESET_ACTION_REMOVE)
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
            rows.append(MenuRow("no set presets"))
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
            items.append("LOAD NAMED SET")
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
            elif item == "LOAD NAMED SET" and label not in {"LAST", "OFF"}:
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
            ValueRow("set", self.current_set_name, current=True, emphasis="italic" if self.current_set_dirty else ""),
            ValueRow("dirty", "YES" if self.current_set_dirty else "NO", current=self.current_set_dirty),
        ]
        if self.available_set_names or True:
            rows.append(ValueRow("sets", len(self.available_set_names)))
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
        rows = [
            ValueRow("setup", self.network_setup_action_label, current=self.network_direct_setup_active),
            ValueRow("state", self.network_setup_state_text, current=self.network_direct_setup_active or bool(self.state.network_error_message)),
            ValueRow("wired", "LINK" if self.network_wired_link else "DOWN", current=self.network_direct_setup_ready),
            ValueRow("eth ip", self.network_wired_ip_address),
            ValueRow("wifi", self.network_wifi_action_label, current=self.network_wifi_connected),
            ValueRow("wifi ip", self.network_wifi_ip_address),
        ]
        if self.state.network_error_message:
            rows.append(ValueRow("error", self.state.network_error_message, current=True, emphasis="italic"))
        elif self.network_direct_setup_ready and not self.network_direct_setup_active:
            rows.append(ValueRow("hint", "DIRECT READY", current=True))
        rows.extend(
            [
                ValueRow("host", self.network_host_display),
                ValueRow("osc", self.network_osc_port),
            ]
        )
        return rows

    @property
    def software_update_value_rows(self) -> list[ValueRow]:
        targets = self.software_update_targets
        shadowbox = targets.get("shadowbox", {})
        shadowscore = targets.get("shadowscore", {})
        rows = self._software_update_target_rows("box", shadowbox)
        if shadowscore:
            rows.extend(self._software_update_target_rows("score", shadowscore))
        return rows

    @property
    def software_update_targets(self) -> dict:
        update = self.state.software_update
        targets = update.get("targets") if isinstance(update, dict) else None
        if isinstance(targets, dict):
            return targets
        return {"shadowbox": update if isinstance(update, dict) else {}}

    def _software_update_target_rows(self, prefix: str, update: dict) -> list[ValueRow]:
        state = str(update.get("state", "unknown") or "unknown")
        message = str(update.get("message", "not checked") or "not checked")
        rows = [
            ValueRow(prefix, message.upper(), current=state in {"available", "error", "dirty", "diverged", "applying", "missing"}),
            ValueRow(f"{prefix} local", update.get("local", "-"), current=state in {"current", "ahead"}),
        ]
        remote = update.get("remote", "")
        if remote and remote != "-":
            rows.append(ValueRow(f"{prefix} remote", remote, current=state == "available"))
        return rows

    @property
    def software_update_menu_items(self) -> list[str]:
        if str(self.state.software_update.get("state", "")) == "applying":
            return ["CANCEL UPDATE"]
        targets = self.software_update_targets
        items = ["CHECK"]
        if bool(targets.get("shadowbox", {}).get("available")):
            items.append("UPDATE BOX")
        shadowscore = targets.get("shadowscore", {})
        if str(shadowscore.get("state", "")) == "missing":
            items.append("INSTALL SCORE")
        elif bool(shadowscore.get("available")):
            items.append("UPDATE SCORE")
        return items

    @property
    def software_update_check_cursor(self) -> int:
        return len(self.software_update_value_rows) + 1

    @property
    def software_update_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        for row in self.software_update_value_rows:
            rows.append(
                MenuRow(
                    f"{str(row.label).upper()}: {str(row.value)}",
                    current=row.current,
                    emphasis=row.emphasis,
                )
            )
        rows.extend(MenuRow(item, action=True) for item in self.software_update_menu_items)
        return rows

    @property
    def wifi_network_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        networks = self.available_wifi_networks
        if not self.network_wifi_available:
            rows.append(MenuRow("wifi unavailable"))
            return rows
        if not networks:
            rows.append(MenuRow("no networks"))
        else:
            current_ssid = self.network_wifi_ssid
            for item in networks:
                ssid = str(item.get("ssid", "") or "").strip()
                if not ssid:
                    continue
                rows.append(MenuRow(ssid, current=bool(item.get("connected")) or ssid == current_ssid))
            if len(rows) == 1:
                rows.append(MenuRow("no networks"))
        rows.append(MenuRow("RESCAN", action=True))
        return rows

    def wifi_network_initial_cursor(self) -> int:
        return 1 if self.available_wifi_networks else max(0, len(self.wifi_network_rows) - 1)

    def suggested_set_save_name(self) -> str:
        base_name = self.current_set_name
        if base_name == "(untitled)":
            base_name = "set"
        slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", base_name.strip().lower())).strip("-")
        if not slug:
            slug = "set"
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

    def _editor_draft_limit(self) -> int:
        return WIFI_PASSWORD_MAX_LEN if self.state.name_editor_context in {"wifi_password", "software_update_password"} else NAME_EDITOR_MAX_LEN

    def normalize_editor_draft(self, value: str) -> str:
        if self.state.name_editor_context in {"wifi_password", "software_update_password"}:
            return str(value or "")[:WIFI_PASSWORD_MAX_LEN]
        return self.normalize_name_draft(value)

    @property
    def name_editor_actions(self) -> list[str]:
        if self.state.name_editor_context in {"wifi_password", "software_update_password"}:
            return [
                self.name_editor_confirm_label,
                WIFI_PASSWORD_EDIT,
                NAME_EDITOR_CLEAR,
                NAME_EDITOR_DELETE,
                NAME_EDITOR_CANCEL,
            ]
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
        label = "PASS" if self.state.name_editor_context in {"wifi_password", "software_update_password"} else "NAME"
        return [f"{label}: {draft}"] + self.name_editor_actions

    @property
    def name_editor_title(self) -> str:
        if self.state.name_editor_context == "save_set":
            return "SAVE SET"
        if self.state.name_editor_context == "rename_set":
            return "RENAME SET"
        if self.state.name_editor_context == "save_graph_preset":
            return "SAVE SET PRESET"
        if self.state.name_editor_context == "rename_graph_preset":
            return "RENAME SET PRESET"
        if self.state.name_editor_context == "save_preset":
            return "SAVE PRESET"
        if self.state.name_editor_context == "rename_preset":
            return "RENAME PRESET"
        if self.state.name_editor_context == "wifi_password":
            return "WIFI PASSWORD"
        if self.state.name_editor_context == "software_update_password":
            return "SUDO PASSWORD"
        return "NAME"

    @property
    def name_editor_confirm_label(self) -> str:
        if self.state.name_editor_context in {"rename_set", "rename_graph_preset", "rename_preset"}:
            return "RENAME"
        if self.state.name_editor_context == "wifi_password":
            return "CONNECT"
        if self.state.name_editor_context == "software_update_password":
            return "UPDATE"
        return NAME_EDITOR_SAVE

    def _begin_name_editor(self, context: str, path: str, initial_draft: str, return_mode: str) -> None:
        self.state.name_editor_context = context
        self.state.name_editor_path = str(path or "")
        self.state.name_editor_return_mode = return_mode
        self.state.name_editor_draft = self.normalize_editor_draft(initial_draft)
        self.state.name_editor_target_name = ""
        self.state.name_editor_cursor = 1
        self.state.name_inline_cursor = max(0, len(self.state.name_editor_draft) - 1)
        self.state.name_inline_edit_mode = False
        self.state.name_inline_preview_index = 0
        self.state.name_keyboard_shift = False
        self.state.name_keyboard_mode = "letters"
        self.state.name_overwrite_cursor = 1
        self.state.name_error_message = ""
        self.state.ui_mode = "NAME_EDITOR"

    def _begin_rename_name_editor(self, context: str, path: str, current_name: str, return_mode: str) -> None:
        self._begin_name_editor(context=context, path=path, initial_draft=current_name, return_mode=return_mode)
        self.state.name_editor_target_name = self.normalize_name_draft(current_name)

    def _cancel_name_editor(self) -> None:
        if self.state.name_editor_context in {"wifi_password", "software_update_password"}:
            self.state.name_editor_draft = ""
        if self.state.name_editor_context == "wifi_password":
            self.state.pending_wifi_ssid = ""
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
            self.state.name_editor_draft = self.normalize_editor_draft(draft)
            self.state.name_inline_edit_mode = False
            return
        char = NAME_EDITOR_CHAR_OPTIONS[self.state.name_inline_preview_index][1]
        if pos < len(draft):
            draft = draft[:pos] + char + draft[pos + 1 :]
        else:
            if len(draft) >= self._editor_draft_limit():
                return
            draft = draft + char
        self.state.name_editor_draft = self.normalize_editor_draft(draft)
        self.state.name_inline_cursor = min(len(self.state.name_editor_draft), pos + 1)
        self.state.name_inline_edit_mode = False

    def _exit_inline_name_editor(self) -> None:
        self.state.name_inline_edit_mode = False
        self.state.ui_mode = "NAME_EDITOR"

    def _append_name_keyboard_text(self, text: str) -> None:
        if not text:
            return
        draft = self.state.name_editor_draft
        if not draft and str(text).isspace():
            return
        remaining = max(0, self._editor_draft_limit() - len(draft))
        if remaining <= 0:
            return
        self.state.name_editor_draft = self.normalize_editor_draft(draft + str(text)[:remaining])
        self.state.name_inline_cursor = max(0, len(self.state.name_editor_draft) - 1)

    def _handle_name_keyboard_key(self, key_index: int | None) -> None:
        if self.state.ui_mode != "NAME_EDITOR" or key_index is None:
            return
        idx = int(key_index)
        if idx < 0 or idx >= len(NAME_TOUCH_KEY_VALUES):
            return
        char = NAME_TOUCH_KEY_VALUES[idx]
        if self.state.name_keyboard_shift and char.isalpha():
            char = char.upper()
            self.state.name_keyboard_shift = False
        self._append_name_keyboard_text(char)
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_name_keyboard_backspace(self) -> None:
        if self.state.ui_mode != "NAME_EDITOR":
            return
        self.state.name_editor_draft = self.state.name_editor_draft[:-1]
        self.state.name_inline_cursor = max(0, len(self.state.name_editor_draft) - 1)
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_name_keyboard_space(self) -> None:
        if self.state.ui_mode != "NAME_EDITOR":
            return
        self._append_name_keyboard_text(" ")
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_name_keyboard_shift(self) -> None:
        if self.state.ui_mode != "NAME_EDITOR":
            return
        self.state.name_keyboard_shift = not self.state.name_keyboard_shift
        self.state.name_keyboard_mode = "letters"
        self.queue_action(UIAction(kind="save_state"))

    def _handle_name_keyboard_mode(self) -> None:
        if self.state.ui_mode != "NAME_EDITOR":
            return
        self.state.name_keyboard_mode = "numbers" if self.state.name_keyboard_mode == "letters" else "letters"
        self.state.name_keyboard_shift = False
        self.queue_action(UIAction(kind="save_state"))

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
        elif self.state.name_editor_context == "wifi_password" and self.state.pending_wifi_ssid:
            self.queue_action(UIAction(kind="connect_wifi_new", ssid=self.state.pending_wifi_ssid, value=value))
            self.state.ui_mode = "WIFI_NETWORKS"
            self.state.name_editor_draft = ""
            self.state.pending_wifi_ssid = ""
        elif self.state.name_editor_context == "software_update_password":
            self.queue_action(UIAction(kind="apply_software_update", path=self.state.name_editor_path, value=value))
            self.state.ui_mode = "SOFTWARE_UPDATE"
            self.state.name_editor_draft = ""
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
        value = self.normalize_editor_draft(self.state.name_editor_draft)
        if not value:
            self._show_name_error(
                "ENTER PASSWORD"
                if self.state.name_editor_context in {"wifi_password", "software_update_password"}
                else "ENTER NAME"
            )
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
    def available_instance_surface(self):
        return resolve_instance_surface(self.active_instance)

    @property
    def active_instance_surface(self):
        resolved = self.available_instance_surface
        if resolved is None or resolved[0].key != self.state.active_surface_key:
            return None
        return resolved

    @property
    def active_surface_title(self) -> str:
        active = self.active_instance_surface
        return active[0].title if active else "SURFACE"

    @property
    def active_surface_frame_rate(self) -> float | None:
        spec = surface_spec_for_key(self.state.active_surface_key)
        return spec.frame_rate if spec else None

    def surface_param_binding(self, key: str) -> dict | None:
        active = self.active_instance_surface
        return active[1].params.get(str(key)) if active else None

    def surface_state_binding(self, key: str) -> dict | None:
        active = self.active_instance_surface
        return active[1].state.get(str(key)) if active else None

    def surface_input_binding(self, key: str) -> dict | None:
        active = self.active_instance_surface
        return active[1].inputs.get(str(key)) if active else None

    def surface_param_binding_for_path(self, path: str) -> dict | None:
        active = self.active_instance_surface
        if active is None:
            return None
        return next(
            (param for param in active[1].params.values() if str(param.get("path", "")) == str(path)),
            None,
        )

    @property
    def active_surface_pitch(self) -> dict | None:
        return self.surface_state_binding("pitch")

    @property
    def active_surface_cents(self) -> dict | None:
        return self.surface_state_binding("cents")

    def _begin_instance_surface(self) -> bool:
        available = self.available_instance_surface
        if available is None:
            return False
        spec, resolved = available
        self.state.active_surface_key = spec.key
        self.state.surface_focus = 0
        self.state.surface_state = {"adjusting": False}
        self.state.surface_touch_capture = None
        self.state.edit_scope_samples = []
        if spec.key == "time_domain_scope":
            anchor = resolved.params.get("sample_rate")
            samples = resolved.state.get("samples")
            self.state.edit_value = normalize_current_value_for_edit(anchor) if anchor else None
            self.state.edit_scope_samples = normalize_scope_samples(samples.get("value") if samples else None)
        elif spec.key in {"list_sequencer", "list_vel_sequencer"}:
            drafts = {}
            keys = FIELD_KEYS if spec.key == "list_sequencer" else ROW_KEYS
            for key in keys:
                ack = resolved.state.get(f"{key}_ack")
                drafts[key] = format_list_value(ack.get("value")) if ack else ""
            self.state.surface_state.update({"drafts": drafts, "dirty": {}})
            for input_item in resolved.inputs.values():
                self.queue_action(UIAction(kind="send_osc", path=input_item.get("path"), value=[-999]))
        else:
            self.state.edit_value = None
        self.state.ui_mode = "INSTANCE_SURFACE"
        return True

    def _exit_instance_surface(self) -> None:
        self.state.ui_mode = "INSTANCE_MENU"
        self.state.active_surface_key = ""
        self.state.surface_focus = 0
        self.state.surface_state = {}
        self.state.surface_touch_capture = None
        self.state.edit_scope_samples = []
        self.state.edit_value = None

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
    def active_preset_destroy_path(self) -> str:
        if not self.active_instance:
            return ""
        return str(self.active_instance.get("preset_destroy_path", "") or "")

    @property
    def preset_action_items(self) -> list[str]:
        items: list[str] = []
        if self.active_preset_save_path:
            items.extend([PRESET_ACTION_SAVE, PRESET_ACTION_SAVE_AS])
        if self.active_preset_destroy_path and self.active_presets:
            items.append(PRESET_ACTION_REMOVE)
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
    def selected_graph_preset_remove_name(self) -> str:
        idx = self.state.graph_preset_remove_cursor - 1
        if 0 <= idx < len(self.available_graph_preset_names):
            return str(self.available_graph_preset_names[idx])
        return ""

    @property
    def selected_preset_remove_name(self) -> str:
        idx = self.state.preset_remove_cursor - 1
        if 0 <= idx < len(self.active_presets):
            return str(self.active_presets[idx].get("name", "") or "")
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
    def network_info(self) -> dict:
        value = self.state.system.get("network", {})
        return value if isinstance(value, dict) else {}

    @property
    def network_ip_address(self) -> str:
        primary = str(self.network_info.get("primary_ipv4", "") or "").strip()
        if primary:
            return primary
        if self.network_direct_setup_ready:
            return self.network_wired_ip_address
        return "?"

    @property
    def network_wired_link(self) -> bool:
        return bool(self.network_info.get("wired_link"))

    @property
    def network_wired_ip_address(self) -> str:
        return str(self.network_info.get("wired_ipv4", "") or "").strip() or "-"

    @property
    def network_wifi_connected(self) -> bool:
        return bool(self.network_info.get("wifi_connected"))

    @property
    def network_wifi_available(self) -> bool:
        return bool(self.network_info.get("wifi_name"))

    @property
    def network_wifi_ssid(self) -> str:
        return str(self.network_info.get("wifi_ssid", "") or "").strip()

    @property
    def network_wifi_action_label(self) -> str:
        if not self.network_wifi_available:
            return "N/A"
        if self.network_wifi_ssid:
            return self.network_wifi_ssid
        return "ON" if self.network_wifi_connected else "CHOOSE"

    @property
    def network_wifi_ip_address(self) -> str:
        return str(self.network_info.get("wifi_ipv4", "") or "").strip() or "-"

    @property
    def available_wifi_networks(self) -> list[dict]:
        raw = self.network_info.get("wifi_networks", [])
        if not isinstance(raw, list):
            return []
        networks: list[dict] = []
        seen: set[str] = set()
        for item in raw:
            if isinstance(item, dict):
                connection_id = str(item.get("id", "") or "").strip()
                ssid = str(item.get("ssid", "") or "").strip()
                saved = bool(item.get("saved", True))
                connected = bool(item.get("connected"))
                signal = item.get("signal", "")
                security = item.get("security", "")
            else:
                connection_id = ""
                ssid = str(item or "").strip()
                saved = True
                connected = False
                signal = ""
                security = ""
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append(
                {
                    "id": connection_id or ssid,
                    "ssid": ssid,
                    "saved": saved,
                    "connected": connected,
                    "signal": signal,
                    "security": security,
                }
            )
        return networks

    @property
    def selected_wifi_network_connection_id(self) -> str:
        idx = self.state.wifi_network_cursor - 1
        if 0 <= idx < len(self.available_wifi_networks):
            network = self.available_wifi_networks[idx]
            return str(network.get("id", "") or network.get("ssid", "") or "").strip()
        return ""

    @property
    def selected_wifi_network(self) -> dict:
        idx = self.state.wifi_network_cursor - 1
        if 0 <= idx < len(self.available_wifi_networks):
            return self.available_wifi_networks[idx]
        return {}

    @staticmethod
    def _wifi_security_requires_password(security: object) -> bool:
        text = str(security or "").strip()
        return bool(text and text != "--")

    def _begin_wifi_password_editor(self, ssid: str) -> None:
        self.state.pending_wifi_ssid = str(ssid or "").strip()
        self._begin_name_editor(
            context="wifi_password",
            path="",
            initial_draft="",
            return_mode="WIFI_NETWORKS",
        )

    @property
    def network_direct_setup_ready(self) -> bool:
        return bool(self.network_info.get("direct_setup_ready"))

    @property
    def network_direct_setup_available(self) -> bool:
        return bool(self.network_info.get("direct_setup_available"))

    @property
    def network_direct_setup_active(self) -> bool:
        return bool(self.network_info.get("direct_setup_active"))

    @property
    def network_direct_setup_ip(self) -> str:
        return str(self.network_info.get("direct_setup_ip", "") or "").strip()

    @property
    def network_setup_action_label(self) -> str:
        if not self.network_direct_setup_available:
            return "UNAVAIL"
        return "DISABLE" if self.network_direct_setup_active else "ENABLE"

    @property
    def network_setup_state_text(self) -> str:
        if self.state.network_error_message:
            return "ERROR"
        if self.network_direct_setup_active:
            return "ACTIVE"
        return "OFF"

    @property
    def network_host_display(self) -> str:
        hostname_local = str(self.network_info.get("hostname_local", "") or "").strip()
        if hostname_local:
            return hostname_local
        hostname = str(self.network_info.get("hostname", "") or "").strip()
        return hostname or RNBO_HOST

    def set_network_error(self, message: str) -> None:
        self.state.network_error_message = str(message or "").strip()

    def clear_network_error(self) -> None:
        self.state.network_error_message = ""

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
    def routing_assignment_rows(self) -> list[MenuRow]:
        rows = [MenuRow("..")]
        current = self.current_routing_targets
        if current:
            rows.extend(MenuRow(str(item), current=True) for item in current)
        else:
            rows.append(MenuRow("no assignments"))
        rows.append(MenuRow("ADD", action=True))
        rows.append(MenuRow("REMOVE", action=True))
        return rows

    @property
    def instance_assigned_routing_targets(self) -> set[str]:
        assigned: set[str] = set()
        branch = self._routing_branch(self.active_instance, self.state.active_transport)
        ports = branch.get(self.state.active_routing_direction, [])
        if not isinstance(ports, list):
            return assigned
        for port in ports:
            if not isinstance(port, dict):
                continue
            for connection in port.get("connections", []):
                target = str(connection)
                if target:
                    assigned.add(target)
        return assigned

    @property
    def available_routing_add_targets(self) -> list[str]:
        assigned = self.instance_assigned_routing_targets
        return [target for target in self.active_routing_targets if target not in assigned]

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

    def _cycle_one_based(self, current: int, count: int, delta: int) -> int:
        if count <= 0:
            return 0
        base = current - 1 if current > 0 else 0
        return ((base + delta) % count) + 1

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
        if self.state.ui_mode == "INSTANCE_SURFACE" and self.state.active_surface_key == "tuner":
            return self.active_surface_pitch
        return self.active_pitch_display_state_value(self.selected_param, pitch_state_key(self.selected_param))

    @property
    def active_pitch_display_cents(self) -> Optional[dict]:
        if self.state.ui_mode == "INSTANCE_SURFACE" and self.state.active_surface_key == "tuner":
            return self.active_surface_cents
        return self.active_pitch_display_state_value(self.selected_param, cents_state_key(self.selected_param))

    @property
    def active_step16_playhead(self) -> Optional[int]:
        state_key = playhead_state_key(self.selected_param)
        item = self._find_active_state_value(state_key)
        if item is None:
            return None
        return playhead_stage_index(item.get("value"), state_key)

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
        return self.state.ui_mode in {
            "GRAPH_MENU",
            "GRAPH_SET_LIST",
            "GRAPH_LOAD_SET_LIST",
            "GRAPH_PRESET_LIST",
            "GRAPH_PRESET_REMOVE_PICKER",
            "GRAPH_STARTUP",
            "GRAPH_STARTUP_SET_LIST",
            "WIFI_NETWORKS",
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
            "PRESET_REMOVE_PICKER",
            "ROUTING_GROUP",
            "ROUTING_PORTS",
            "AUDIO_ROUTING_OVERVIEW",
            "MIDI_ROUTING_OVERVIEW",
            "EDIT",
            "ENUM_LIST",
            "ROUTING_TARGETS",
            "ROUTING_ADD_PICKER",
            "ROUTING_DISCONNECT_PICKER",
            "SYSTEM_AUDIO_DEVICE",
            "SYSTEM_AUDIO_RATE",
            "SYSTEM_AUDIO_BUFFER",
            "SYSTEM_AUDIO_RESTART",
            "SYSTEM_TRANSPORT_TEMPO_EDIT",
            "SYSTEM_TRANSPOSE_CONTROLLER",
            "SYSTEM_TRANSPOSE_ROLE",
            "SYSTEM_TRANSPOSE_AUTHORITY",
            "SYSTEM_TRANSPOSE_EDIT",
            "BRICK_PANEL",
        }

    def advance_frame(self, frame_scale: float = 1.0) -> None:
        if self.state.ui_mode == "BRICK_PANEL":
            self.brick_panel.update(frame_scale=frame_scale)
        if self.state.busy:
            self.state.activity_ticks += max(1, int(round(frame_scale)))
        if self.state.status_frames > 0:
            self.state.status_frames = max(0, self.state.status_frames - max(1, int(round(frame_scale))))
            if self.state.status_frames == 0:
                self.state.status_message = ""

    def handle_event(self, event: UIEvent) -> None:
        if event.kind == "step":
            self._handle_step(event.delta)
        elif event.kind == "short_press":
            self._handle_short_press()
        elif event.kind == "long_press":
            self._handle_long_press()
        elif event.kind == "tap_row":
            self._handle_tap_row(event.index)
        elif event.kind == "tap_back":
            self._handle_tap_back()
        elif event.kind == "tap_button":
            self._handle_tap_button(event.button_id)
        elif event.kind == "page_up":
            self._handle_touch_page(-1)
        elif event.kind == "page_down":
            self._handle_touch_page(1)
        elif event.kind == "set_edit_value":
            self._handle_touch_edit_value(event.value, pressed=bool(getattr(event, "pressed", False)))
        elif event.kind == "set_surface_value":
            self._handle_surface_value(event.index, event.value, pressed=bool(getattr(event, "pressed", False)))
        elif event.kind == "set_surface_range":
            self._handle_analog_pitch_range(event.button_id, event.value)
        elif event.kind == "toggle_surface_value":
            self._handle_surface_toggle(event.index)
        elif event.kind == "select_list_field":
            self._handle_list_field_select(event.index)
        elif event.kind == "edit_list_key":
            self._handle_list_key(event.button_id)
        elif event.kind == "toggle_list_sign":
            self._handle_list_sign()
        elif event.kind == "send_list_field":
            self._send_list_field()
        elif event.kind == "step_list_field":
            self._handle_list_field_step(event.delta)
        elif event.kind == "keypad_digit":
            self._handle_keypad_digit(event.button_id)
        elif event.kind == "keypad_decimal":
            self._handle_keypad_decimal()
        elif event.kind == "keypad_backspace":
            self._handle_keypad_backspace()
        elif event.kind == "keypad_sign":
            self._handle_keypad_sign()
        elif event.kind == "keypad_space":
            self._handle_keypad_space()
        elif event.kind == "keypad_enter":
            self._handle_keypad_enter()
        elif event.kind == "keypad_step":
            self._handle_keypad_step(event.delta)
        elif event.kind == "set_ttid_pc":
            self._handle_touch_ttid_pc(event.index)
        elif event.kind == "set_ttid_root":
            self._handle_touch_ttid_root(event.index)
        elif event.kind == "set_ttid_scale":
            self._handle_touch_ttid_scale(event.index)
        elif event.kind == "step_ttid_scale":
            self._handle_touch_ttid_scale_step(event.index)
        elif event.kind == "load_ttid_scale":
            self._handle_touch_ttid_load()
        elif event.kind == "tap_step16":
            self._handle_touch_step16_cell(event.index)
        elif event.kind == "tap_name_key":
            self._handle_name_keyboard_key(event.index)
        elif event.kind == "name_backspace":
            self._handle_name_keyboard_backspace()
        elif event.kind == "name_space":
            self._handle_name_keyboard_space()
        elif event.kind == "name_shift":
            self._handle_name_keyboard_shift()
        elif event.kind == "name_keyboard_mode":
            self._handle_name_keyboard_mode()

    def _handle_touch_edit_value(self, normalized_value: float | None, *, pressed: bool = False) -> None:
        surface_scope = self.state.ui_mode == "INSTANCE_SURFACE" and self.state.active_surface_key == "time_domain_scope"
        if surface_scope:
            param = self.surface_param_binding("sample_rate")
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_EDIT":
            param = self.transpose_edit_param
        elif self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
            param = self.transport_tempo_edit_param
        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
        else:
            return
        if normalized_value is None:
            return
        if param is None or is_ttid_param(param) or is_step16_param(param) or is_enum_param(param):
            return
        self.state.edit_numeric_draft = ""
        pmin = param.get("min")
        pmax = param.get("max")
        if not isinstance(pmin, (int, float)) or not isinstance(pmax, (int, float)) or pmax <= pmin:
            return

        fraction = max(0.0, min(1.0, float(normalized_value)))
        value: Any = pmin + ((pmax - pmin) * fraction)
        value = quantize_edit_value(param, value)

        previous = self.state.edit_value
        if isinstance(previous, (int, float)) and abs(float(previous) - float(value)) < 1e-9:
            if not pressed:
                self.queue_action(UIAction(kind="save_state"))
            return

        self.state.edit_value = value
        param["value"] = value
        self.state.activity_ticks += 1
        normalized_path = str(param.get("normalized_path", "") or "")
        if surface_scope and normalized_path:
            quantized_fraction = (float(value) - float(pmin)) / (float(pmax) - float(pmin))
            self.queue_action(UIAction(kind="set_param", path=normalized_path, value=quantized_fraction))
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_EDIT":
            self.set_transpose_value(self.state.transpose_edit_role, value, "Touchscreen")
        elif self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
            self.state.system["transport"]["bpm"] = value
            self.queue_action(UIAction(kind="set_transport", path=param.get("path"), value=value))
        elif not is_discrete_param(param):
            self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
        if not pressed:
            self.queue_action(UIAction(kind="save_state"))

    def _handle_surface_value(self, index: int | None, normalized_value: float | None, *, pressed: bool = False) -> None:
        if self.state.ui_mode != "INSTANCE_SURFACE" or normalized_value is None or index is None:
            return
        if self.state.active_surface_key == "organ":
            focus = max(0, min(len(FOOTAGES) - 1, int(index)))
            param = self.surface_param_binding(FOOTAGES[focus])
            if param is None:
                return
            pmin, pmax = param.get("min"), param.get("max")
            if not isinstance(pmin, (int, float)) or not isinstance(pmax, (int, float)) or pmax <= pmin:
                return
            fraction = max(0.0, min(1.0, float(normalized_value)))
            value = pmin + ((pmax - pmin) * fraction)
            value = quantize_edit_value(param, value)
            previous = param.get("value")
            if isinstance(previous, (int, float)) and abs(float(previous) - float(value)) < 1e-9:
                return
            param["value"] = value
            self.state.surface_focus = focus
            self.state.surface_touch_capture = focus if pressed else None
            self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
            self.request_render("organ_touch")
            return
        if self.state.active_surface_key != "analog_sequencer":
            return
        stage = max(1, min(16, int(index) + 1))
        param = self.surface_param_binding(f"stage_{stage:02d}_value")
        if param is None:
            return
        pmin, pmax = self.analog_stage_pitch_bounds(param)
        if not isinstance(pmin, (int, float)) or not isinstance(pmax, (int, float)) or pmax <= pmin:
            return
        fraction = max(0.0, min(1.0, float(normalized_value)))
        value = pmin + ((pmax - pmin) * fraction)
        value = quantize_edit_value(param, value)
        previous = param.get("value")
        if isinstance(previous, (int, float)) and abs(float(previous) - float(value)) < 1e-9:
            return
        param["value"] = value
        self.state.surface_focus = stage - 1
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
        self.request_render("surface_touch")

    @property
    def analog_pitch_range(self) -> tuple[int, int]:
        pitch_range = self.state.surface_state.setdefault("pitch_range", {"low": 24, "high": 72})
        if not isinstance(pitch_range, dict):
            pitch_range = {"low": 24, "high": 72}
            self.state.surface_state["pitch_range"] = pitch_range
        try:
            low = max(0, min(127, int(round(float(pitch_range.get("low", 24))))))
            high = max(0, min(127, int(round(float(pitch_range.get("high", 72))))))
        except (TypeError, ValueError):
            low, high = 24, 72
        low = min(low, high)
        pitch_range.update({"low": low, "high": high})
        return low, high

    def analog_stage_pitch_bounds(self, param: dict | None) -> tuple[float | None, float | None]:
        if not isinstance(param, dict):
            return None, None
        wire_min, wire_max = param.get("min"), param.get("max")
        if not isinstance(wire_min, (int, float)) or not isinstance(wire_max, (int, float)):
            return None, None
        low, high = self.analog_pitch_range
        bounded_low = max(float(wire_min), float(low))
        bounded_high = min(float(wire_max), float(high))
        if bounded_low <= bounded_high:
            return bounded_low, bounded_high
        nearest = max(float(wire_min), min(float(wire_max), float(low)))
        return nearest, nearest

    def _handle_analog_pitch_range(self, boundary: str, normalized_value: float | None) -> None:
        if self.state.ui_mode != "INSTANCE_SURFACE" or self.state.active_surface_key != "analog_sequencer":
            return
        if boundary not in {"low", "high"} or normalized_value is None:
            return
        low, high = self.analog_pitch_range
        value = max(0, min(127, int(round(max(0.0, min(1.0, float(normalized_value))) * 127.0))))
        if boundary == "low":
            low = min(value, high)
        else:
            high = max(value, low)
        self.state.surface_state["pitch_range"] = {"low": low, "high": high}

        for stage in range(1, 17):
            param = self.surface_param_binding(f"stage_{stage:02d}_value")
            if param is None or not isinstance(param.get("value"), (int, float)):
                continue
            pmin, pmax = self.analog_stage_pitch_bounds(param)
            if pmin is None or pmax is None:
                continue
            clipped = quantize_edit_value(param, max(pmin, min(pmax, float(param["value"]))))
            if abs(float(clipped) - float(param["value"])) < 1e-9:
                continue
            param["value"] = clipped
            self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=clipped))
        self.request_render("analog_pitch_range")

    def _handle_surface_toggle(self, index: int | None) -> None:
        if self.state.ui_mode != "INSTANCE_SURFACE" or index is None:
            return
        if self.state.active_surface_key != "analog_sequencer":
            return
        stage = max(1, min(16, int(index) + 1))
        param = self.surface_param_binding(f"stage_{stage:02d}_enabled")
        if param is None:
            return
        value = 0 if bool(param.get("value")) else 1
        param["value"] = value
        self.state.surface_focus = stage - 1
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
        self.request_render("surface_toggle")

    def _list_surface_ready(self) -> bool:
        return (
            self.state.ui_mode == "INSTANCE_SURFACE"
            and self.state.active_surface_key in {"list_sequencer", "list_vel_sequencer"}
        )

    def _list_surface_keys(self) -> tuple[str, ...]:
        if self.state.active_surface_key == "list_vel_sequencer":
            return ROW_KEYS
        return FIELD_KEYS

    def _list_surface_key(self) -> str | None:
        if not self._list_surface_ready():
            return None
        keys = self._list_surface_keys()
        focus = max(0, min(len(keys) - 1, int(self.state.surface_focus)))
        return keys[focus]

    def _list_surface_drafts(self) -> dict[str, str]:
        drafts = self.state.surface_state.setdefault("drafts", {})
        return drafts if isinstance(drafts, dict) else {}

    def _mark_list_field_dirty(self, key: str) -> None:
        dirty = self.state.surface_state.setdefault("dirty", {})
        if isinstance(dirty, dict):
            dirty[key] = True

    def _handle_list_field_select(self, index: int | None) -> None:
        if not self._list_surface_ready() or index is None:
            return
        keys = self._list_surface_keys()
        self.state.surface_focus = max(0, min(len(keys) - 1, int(index)))
        self.request_render("list_field")

    def _handle_list_field_step(self, delta: int) -> None:
        if not self._list_surface_ready() or delta == 0:
            return
        self.state.surface_focus = self._cycle(self.state.surface_focus, len(self._list_surface_keys()), int(delta))
        self.request_render("list_field")

    def _numeric_keypad_param(self) -> dict | None:
        param = self.selected_param
        if (
            self.state.ui_mode != "EDIT"
            or param is None
            or is_ttid_param(param)
            or is_step16_param(param)
            or is_discrete_param(param)
            or not isinstance(self.state.edit_value, (int, float))
        ):
            return None
        return param

    def _handle_keypad_digit(self, digit: str) -> None:
        if self._list_surface_ready():
            self._handle_list_key(digit)
            return
        if self._numeric_keypad_param() is None or digit not in "0123456789":
            return
        draft = self.state.edit_numeric_draft
        if len(draft) >= 24:
            return
        self.state.edit_numeric_draft = f"{draft}{digit}"
        self.request_render("numeric_keypad")

    def _handle_keypad_decimal(self) -> None:
        if self._list_surface_ready():
            self._handle_list_key("backspace")
            return
        param = self._numeric_keypad_param()
        if param is None or edit_as_int(param):
            return
        draft = self.state.edit_numeric_draft
        if "." in draft:
            return
        self.state.edit_numeric_draft = "-0." if draft == "-" else f"{draft or '0'}."
        self.request_render("numeric_keypad")

    def _handle_keypad_backspace(self) -> None:
        if self._list_surface_ready():
            self._handle_list_key("backspace")
            return
        if self._numeric_keypad_param() is None or not self.state.edit_numeric_draft:
            return
        self.state.edit_numeric_draft = self.state.edit_numeric_draft[:-1]
        self.request_render("numeric_keypad")

    def _handle_keypad_sign(self) -> None:
        if self._list_surface_ready():
            self._handle_list_sign()
            return
        param = self._numeric_keypad_param()
        if param is None:
            return
        pmin = param.get("min")
        if isinstance(pmin, (int, float)) and pmin >= 0:
            return
        draft = self.state.edit_numeric_draft
        self.state.edit_numeric_draft = draft[1:] if draft.startswith("-") else f"-{draft}"
        self.request_render("numeric_keypad")

    def _handle_keypad_space(self) -> None:
        if self._list_surface_ready():
            self._handle_list_key("space")
        elif self._numeric_keypad_param() is not None and self.state.edit_numeric_draft:
            self.state.edit_numeric_draft = self.state.edit_numeric_draft[:-1]
            self.request_render("numeric_keypad")

    def _handle_keypad_step(self, delta: int) -> None:
        if self._list_surface_ready():
            self._handle_list_field_step(delta)

    def _commit_numeric_keypad_draft(self) -> bool:
        param = self._numeric_keypad_param()
        draft = self.state.edit_numeric_draft
        if param is None or not draft or draft in {"-", ".", "-."}:
            return False
        try:
            value: Any = float(draft)
        except ValueError:
            return False
        if not math.isfinite(value):
            return False
        value = quantize_edit_value(param, value)
        param["value"] = value
        self.state.edit_value = value
        self.state.edit_numeric_draft = ""
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
        return True

    def _handle_keypad_enter(self) -> None:
        if self._list_surface_ready():
            self._send_list_field()
            return
        if self._numeric_keypad_param() is None:
            return
        if self.state.edit_numeric_draft and not self._commit_numeric_keypad_draft():
            return
        self._reset_float_edit_acceleration()
        self.state.ui_mode = "PARAM_LIST"
        self._edit_original_value = None
        self.queue_action(UIAction(kind="save_state"))

    def _handle_list_key(self, key_value: str) -> None:
        field_key = self._list_surface_key()
        if field_key is None:
            return
        drafts = self._list_surface_drafts()
        draft = str(drafts.get(field_key, ""))
        if key_value.isdigit() and len(key_value) == 1:
            draft += key_value
        elif key_value == "space":
            if draft and not draft.endswith(" "):
                draft += " "
        elif key_value == "backspace":
            draft = draft[:-1]
        else:
            return
        drafts[field_key] = draft
        self._mark_list_field_dirty(field_key)
        self.request_render("list_key")

    def _handle_list_sign(self) -> None:
        field_key = self._list_surface_key()
        if field_key not in SIGNED_FIELD_KEYS:
            return
        drafts = self._list_surface_drafts()
        draft = str(drafts.get(field_key, ""))
        token_start = draft.rfind(" ") + 1
        token = draft[token_start:]
        if token.startswith("-"):
            draft = draft[:token_start] + token[1:]
        else:
            draft = draft[:token_start] + "-" + token
        drafts[field_key] = draft
        self._mark_list_field_dirty(field_key)
        self.request_render("list_sign")

    def _parse_list_draft(self, field_key: str, draft: str) -> list[int] | None:
        tokens = str(draft).split()
        if not tokens:
            return []
        if any(re.fullmatch(r"-?\d+", token) is None for token in tokens):
            return None
        values = [int(token) for token in tokens]
        if field_key in {"steps", "steps_secondary"} and any(value not in {0, 1} for value in values):
            return None
        if self.state.active_surface_key == "list_vel_sequencer" and any(value < 0 or value > 127 for value in values):
            return None
        return values

    def _send_list_field(self) -> bool:
        field_key = self._list_surface_key()
        if field_key is None:
            return False
        input_item = self.surface_input_binding(field_key)
        if input_item is None:
            return False
        values = self._parse_list_draft(field_key, self._list_surface_drafts().get(field_key, ""))
        if values is None:
            self.set_status_message("INVALID LIST", frames=48)
            return False
        self.queue_action(UIAction(kind="send_osc", path=input_item.get("path"), value=values))
        self.set_status_message("LIST SENT", frames=24)
        return True

    def _handle_touch_ttid_pc(self, pc_index: int | None) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_ttid_param(param) or self.state.edit_ttid_mode != "keyboard":
            return
        if pc_index is None:
            return
        pc = int(pc_index)
        if pc == 12:
            self._handle_touch_ttid_load()
            return
        if pc < 0 or pc > 11:
            return
        self.state.activity_ticks += 1
        self.state.edit_ttid_selected_pc = pc
        self.state.edit_value = toggle_bit(normalize_ttid(self.state.edit_value), pc)
        param["value"] = self.state.edit_value
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
        self.queue_action(UIAction(kind="save_state"))

    def _handle_touch_ttid_root(self, root_index: int | None) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_ttid_param(param):
            return
        if root_index is None:
            return
        self.state.edit_ttid_load_root = int(root_index) % 12
        self.state.edit_ttid_mode = "keyboard"
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_touch_ttid_scale(self, scale_index: int | None) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_ttid_param(param):
            return
        names = self.state.edit_ttid_scale_names or ["major"]
        if scale_index is None or not names:
            return
        self.state.edit_ttid_scale_index = max(0, min(len(names) - 1, int(scale_index)))
        self.state.edit_ttid_mode = "keyboard"
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_touch_ttid_scale_step(self, direction: int | None) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_ttid_param(param):
            return
        names = self.state.edit_ttid_scale_names or ["major"]
        if not names:
            return
        step = -1 if direction is not None and int(direction) < 0 else 1
        self.state.edit_ttid_scale_index = (self.state.edit_ttid_scale_index + step) % len(names)
        self.state.edit_ttid_mode = "keyboard"
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_touch_ttid_load(self) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_ttid_param(param):
            return
        self._apply_ttid_scale_load()
        self.state.edit_ttid_mode = "keyboard"
        self.state.edit_ttid_selected_pc = self.state.edit_ttid_load_root
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))

    def _handle_touch_step16_cell(self, step_index: int | None) -> None:
        param = self.selected_param
        if self.state.ui_mode != "EDIT" or param is None or not is_step16_param(param) or step_index is None:
            return
        step = int(step_index) % 16
        self.state.edit_step16_focus = step
        self.state.edit_value = toggle_step16(normalize_step16_mask(self.state.edit_value), step)
        param["value"] = self.state.edit_value
        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
        self.queue_action(UIAction(kind="save_state"))

    def _handle_tap_back(self) -> None:
        if self.state.ui_mode == "INSTANCE_SURFACE":
            self._exit_instance_surface()
            self.queue_action(UIAction(kind="save_state"))
            return
        if self.state.ui_mode == "EDIT":
            self.state.edit_value = None
            self.state.edit_numeric_draft = ""
            self.state.edit_ttid_mode = "keyboard"
            self.state.edit_ttid_selected_pc = 0
            self.state.edit_ttid_load_root = 0
            self.state.edit_ttid_scale_index = 0
            self.state.edit_step16_focus = 0
            self.state.edit_scope_samples = []
            self._edit_original_value = None
            self._reset_float_edit_acceleration()
            self.state.ui_mode = "PARAM_LIST"
            self.queue_action(UIAction(kind="save_state"))
            return

        self._handle_long_press()

    def _handle_tap_button(self, button_id: str) -> None:
        button = re.sub(r"\s+", "_", str(button_id or "").strip().lower())

        if self.state.ui_mode == "EDIT":
            if button == "learn":
                param = self.selected_param
                report_path = self._selected_instance_midi_report_path()
                if isinstance(param, dict) and report_path:
                    self.state.midi_learn_instance_id = str(self.state.active_instance_id or "")
                    self.state.midi_learn_param_path = str(param.get("path", "") or "")
                    self.queue_action(UIAction(kind="send_osc", path=report_path, value=True))
                    self.queue_action(UIAction(kind="save_state"))
                return
            if button == "clear":
                self._replace_selected_param_midi_mapping(None)
                self.state.midi_learn_instance_id = ""
                self.state.midi_learn_param_path = ""
                report_path = self._selected_instance_midi_report_path()
                if report_path:
                    self.queue_action(UIAction(kind="send_osc", path=report_path, value=False))
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "NAME_OVERWRITE_CONFIRM":
            if button == "cancel" or button == "back":
                self.state.ui_mode = "NAME_EDITOR"
                self.state.name_overwrite_cursor = 1
                self.queue_action(UIAction(kind="save_state"))
                return
            if button == "overwrite":
                self._queue_confirmed_name_action(self.normalize_name_draft(self.state.name_editor_draft))
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "NAME_ERROR":
            if button in {"edit_name", "cancel", "back"}:
                self.state.ui_mode = "NAME_EDITOR"
                self.state.name_overwrite_cursor = 1
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "NAME_EDITOR":
            if button in {"save", "rename", "done", "primary"}:
                self._submit_name_editor()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"clear", "clear_name"}:
                self.state.name_editor_draft = ""
                self.state.name_inline_cursor = 0
                self.queue_action(UIAction(kind="save_state"))
                return
            if button == "generate":
                self._regenerate_name_draft()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"add_date", "date"}:
                self.state.name_editor_draft = self.append_date_token(self.state.name_editor_draft)
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            if button in {"cancel", "back"}:
                self._cancel_remove_instance_confirm()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button == "remove":
                self._confirm_remove_instance()
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "INSTANCE_LIST":
            if button in {"add_instance", "add"} and self.can_add_instance:
                self.state.ui_mode = "PATCHER_PICKER"
                self.state.patcher_picker_context = "add"
                self.state.patcher_cursor = 1 if self.state.patchers else 0
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"remove_instance", "remove"} and self.can_remove_instances:
                self.state.ui_mode = "REMOVE_INSTANCE_PICKER"
                self.state.remove_instance_picker_cursor = 1 if self.state.instances else 0
                self.state.remove_instance_origin = "instance_list"
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "GRAPH_SET_LIST":
            if button == "save":
                self._save_current_graph_or_open_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"save_as", "save_as..."}:
                self._begin_graph_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "GRAPH_PRESET_LIST":
            if button == "save":
                self._save_current_graph_preset_or_open_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"save_as", "save_as..."}:
                self._begin_graph_preset_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button == "remove" and self.graph_preset_destroy_path:
                self.state.ui_mode = "GRAPH_PRESET_REMOVE_PICKER"
                self.state.graph_preset_remove_cursor = 1 if self.available_graph_preset_names else 0
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "PRESET_LIST":
            if button == "save":
                self._save_current_preset_or_open_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"save_as", "save_as..."}:
                self._begin_preset_save_as()
                self.queue_action(UIAction(kind="save_state"))
                return
            if button == "remove" and self.active_preset_destroy_path:
                self.state.ui_mode = "PRESET_REMOVE_PICKER"
                self.state.preset_remove_cursor = 1 if self.active_presets else 0
                self.queue_action(UIAction(kind="save_state"))
                return

        if self.state.ui_mode == "ROUTING_TARGETS":
            if button == "add":
                self.state.ui_mode = "ROUTING_ADD_PICKER"
                self.state.routing_add_cursor = 1 if self.available_routing_add_targets else 0
                self.queue_action(UIAction(kind="save_state"))
                return
            if button in {"remove", "disconnect"}:
                self.state.ui_mode = "ROUTING_DISCONNECT_PICKER"
                self.state.routing_disconnect_cursor = 1 if self.current_routing_targets else 0
                self.queue_action(UIAction(kind="save_state"))
                return

        if button in {"back", "cancel"}:
            self._handle_long_press()
        else:
            self._handle_short_press()

    def _handle_touch_page(self, direction: int) -> None:
        if direction == 0:
            return
        mode = self.state.ui_mode

        def scroll_cursor(
            attr: str,
            count: int,
            *,
            first_index: int = 1,
            page_rows: int = TOUCH_PAGE_ROWS,
        ) -> bool:
            if count <= 0:
                return False
            last_index = first_index + count - 1
            current = int(getattr(self.state, attr))
            if current < first_index or current > last_index:
                current = first_index
            page_step = (1 if direction > 0 else -1) * max(1, int(page_rows))
            setattr(self.state, attr, max(first_index, min(last_index, current + page_step)))
            self.state.activity_ticks += 1
            return True

        if mode == "INSTANCE_LIST":
            if scroll_cursor("instance_cursor", len(self.state.instances)):
                self.state.active_instance_id = str(self.state.instances[self.state.instance_cursor - 1].get("id", ""))
            return
        if mode == "REMOVE_INSTANCE_PICKER":
            scroll_cursor("remove_instance_picker_cursor", len(self.state.instances))
            return
        if mode == "PATCHER_PICKER":
            scroll_cursor("patcher_cursor", len(self.state.patchers))
            return
        if mode == "INSTANCE_MENU":
            scroll_cursor("instance_menu_cursor", len(self.instance_menu_items))
            return
        if mode == "PARAM_LIST":
            scroll_cursor("param_cursor", len(self.active_params))
            return
        if mode == "ENUM_LIST":
            if scroll_cursor("enum_cursor", len(self.active_enum_options), first_index=0, page_rows=4):
                self.state.edit_value = self.active_enum_options[self.state.enum_cursor]
            return
        if mode == "PRESET_LIST":
            scroll_cursor("preset_cursor", len(self.preset_menu_items), first_index=0)
            return
        if mode == "PRESET_REMOVE_PICKER":
            scroll_cursor("preset_remove_cursor", len(self.active_presets))
            return
        if mode == "GRAPH_MENU":
            scroll_cursor("graph_menu_cursor", len(self.graph_menu_items))
            return
        if mode == "GRAPH_SET_LIST":
            scroll_cursor("graph_set_cursor", len(self.graph_set_menu_items), first_index=0)
            return
        if mode == "GRAPH_LOAD_SET_LIST":
            scroll_cursor("graph_load_set_cursor", len(self.available_set_names), first_index=1)
            return
        if mode == "GRAPH_PRESET_LIST":
            scroll_cursor("graph_preset_cursor", len(self.graph_preset_menu_items), first_index=0)
            return
        if mode == "GRAPH_PRESET_REMOVE_PICKER":
            scroll_cursor("graph_preset_remove_cursor", len(self.available_graph_preset_names))
            return
        if mode == "GRAPH_STARTUP":
            scroll_cursor("graph_startup_cursor", len(self.graph_startup_menu_items))
            return
        if mode == "GRAPH_STARTUP_SET_LIST":
            scroll_cursor("graph_startup_set_cursor", len(self.available_set_names))
            return
        if mode == "ROUTING_GROUP":
            scroll_cursor("routing_group_cursor", len(ROUTING_GROUP_ITEMS))
            return
        if mode == "ROUTING_PORTS":
            scroll_cursor("routing_port_cursor", len(self.active_routing_ports))
            return
        if mode == "ROUTING_TARGETS":
            scroll_cursor("routing_target_cursor", len(self.current_routing_targets))
            return
        if mode == "ROUTING_ADD_PICKER":
            scroll_cursor("routing_add_cursor", len(self.available_routing_add_targets))
            return
        if mode == "ROUTING_DISCONNECT_PICKER":
            scroll_cursor("routing_disconnect_cursor", len(self.current_routing_targets))
            return
        if mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            scroll_cursor("routing_overview_cursor", len(self.routing_overview_rows))
            return
        if mode == "SYSTEM_MENU":
            scroll_cursor("system_cursor", len(self.system_menu_items))
            return
        if mode == "SYSTEM_TRANSPORT":
            scroll_cursor("transport_cursor", len(self.transport_rows), first_index=1)
            return
        if mode == "SYSTEM_AUDIO":
            scroll_cursor("system_audio_cursor", len(SYSTEM_AUDIO_ITEMS))
            return
        if mode == "SYSTEM_TRANSPOSE":
            scroll_cursor("transpose_cursor", len(self.transpose_rows), first_index=1)
            return
        if mode == "SYSTEM_TRANSPOSE_CONTROLLER":
            scroll_cursor("transpose_controller_cursor", len(self.transpose_controller_items))
            return
        if mode == "SYSTEM_TRANSPOSE_ROLE":
            scroll_cursor("transpose_role_cursor", len(self.transpose_role_items))
            return
        if mode == "SYSTEM_TRANSPOSE_AUTHORITY":
            scroll_cursor("transpose_authority_cursor", len(self.transpose_authority_items))
            return
        if mode == "SYSTEM_AUDIO_DEVICE":
            scroll_cursor("audio_device_cursor", len(self.audio_options))
            return
        if mode == "SYSTEM_AUDIO_RATE":
            scroll_cursor("sample_rate_cursor", len(self.sample_rate_options))
            return
        if mode == "SYSTEM_AUDIO_BUFFER":
            scroll_cursor("buffer_size_cursor", len(self.buffer_size_options))
            return
        if mode == "NETWORK":
            scroll_cursor("network_cursor", len(self.network_value_rows))
            return
        if mode == "SOFTWARE_UPDATE":
            scroll_cursor("software_update_cursor", len(self.software_update_rows) - 1, first_index=0)
            return
        if mode == "WIFI_NETWORKS":
            scroll_cursor("wifi_network_cursor", len(self.wifi_network_rows), first_index=0)
            return
        if mode == "MAINT":
            scroll_cursor("maint_cursor", len(self.maint_menu_items))
            return

    def _set_touch_cursor(self, attr: str, row_index: int, count: int) -> bool:
        if count <= 0:
            return False
        setattr(self.state, attr, clamp_index(row_index, count))
        return True

    def _cancel_remove_instance_confirm(self) -> None:
        self.state.pending_remove_instance_id = ""
        if self.state.remove_instance_origin == "instance_list":
            self.state.ui_mode = "REMOVE_INSTANCE_PICKER"
        else:
            self.state.ui_mode = "INSTANCE_MENU"
        self.state.remove_instance_origin = ""

    def _confirm_remove_instance(self) -> None:
        target = self.remove_instance_target
        if target is not None and self.state.remove_instance_path:
            self.queue_action(
                UIAction(
                    kind="remove_instance",
                    path=self.state.remove_instance_path,
                    value=int(target.get("id")),
                )
            )
        self.state.pending_remove_instance_id = ""
        self.state.ui_mode = "REMOVE_INSTANCE_PICKER" if self.state.remove_instance_origin == "instance_list" else "INSTANCE_MENU"
        self.state.remove_instance_origin = ""

    def _begin_graph_preset_save_as(self) -> None:
        if not self.graph_preset_save_path:
            return
        self._begin_name_editor(
            context="save_graph_preset",
            path=self.graph_preset_save_path,
            initial_draft=self.suggested_graph_preset_save_name(),
            return_mode="GRAPH_PRESET_LIST",
        )

    def _save_current_graph_preset_or_open_save_as(self) -> None:
        if not self.graph_preset_save_path:
            return
        name = self.current_graph_preset_name
        if not name:
            self._begin_graph_preset_save_as()
            return
        self.queue_action(UIAction(kind="save_graph_preset", path=self.graph_preset_save_path, value=name))

    @property
    def selected_graph_set_name(self) -> str:
        idx = self.state.graph_load_set_cursor - 1
        if 0 <= idx < len(self.available_set_names):
            return str(self.available_set_names[idx])
        return ""

    def _begin_graph_save_as(self) -> None:
        if not self.graph_save_path:
            return
        self._begin_name_editor(
            context="save_set",
            path=self.graph_save_path,
            initial_draft=self.suggested_set_save_name(),
            return_mode="GRAPH_MENU",
        )

    def _save_current_graph_or_open_save_as(self) -> None:
        if not self.graph_save_path:
            return
        name = self.current_set_name
        if not name or name == "(untitled)":
            self._begin_graph_save_as()
            return
        self.queue_action(UIAction(kind="save_set", path=self.graph_save_path, value=name))

    def _begin_preset_save_as(self) -> None:
        if not self.active_preset_save_path:
            return
        self._begin_name_editor(
            context="save_preset",
            path=self.active_preset_save_path,
            initial_draft=self.suggested_preset_save_name(),
            return_mode="PRESET_LIST",
        )

    def _save_current_preset_or_open_save_as(self) -> None:
        if not self.active_preset_save_path:
            return
        name = self.current_preset_name
        if not name:
            self._begin_preset_save_as()
            return
        self.queue_action(UIAction(kind="save_preset", path=self.active_preset_save_path, value=name))

    def _handle_tap_row(self, index: int | None) -> None:
        if index is None:
            return
        row_index = max(0, int(index))
        mode = self.state.ui_mode
        handled = False

        if mode == "TOP":
            handled = self._set_touch_cursor("top_index", row_index, len(self.top_level_items))
        elif mode == "GRAPH_MENU":
            handled = self._set_touch_cursor("graph_menu_cursor", row_index, len(self.graph_menu_items) + 1)
        elif mode == "GRAPH_SET_LIST":
            handled = self._set_touch_cursor("graph_set_cursor", row_index, len(self.graph_set_menu_items))
        elif mode == "GRAPH_LOAD_SET_LIST":
            handled = self._set_touch_cursor("graph_load_set_cursor", row_index, len(self.graph_load_set_menu_items))
        elif mode == "GRAPH_PRESET_LIST":
            if row_index > 0:
                row_index += len(self.graph_preset_action_items)
            handled = self._set_touch_cursor("graph_preset_cursor", row_index, len(self.graph_preset_menu_items))
        elif mode == "GRAPH_PRESET_REMOVE_PICKER":
            handled = self._set_touch_cursor("graph_preset_remove_cursor", row_index, len(self.available_graph_preset_names) + 1)
        elif mode == "GRAPH_STARTUP":
            handled = self._set_touch_cursor("graph_startup_cursor", row_index, len(self.graph_startup_menu_items) + 1)
        elif mode == "GRAPH_STARTUP_SET_LIST":
            handled = self._set_touch_cursor("graph_startup_set_cursor", row_index, len(self.available_set_names) + 1)
        elif mode == "NAME_EDITOR":
            handled = self._set_touch_cursor("name_editor_cursor", row_index, len(self.name_editor_items))
        elif mode == "NAME_OVERWRITE_CONFIRM":
            handled = self._set_touch_cursor("name_overwrite_cursor", row_index, len(self.overwrite_confirm_items))
        elif mode == "NAME_ERROR":
            handled = self._set_touch_cursor("name_overwrite_cursor", row_index, len(self.name_error_items))
        elif mode == "INSTANCE_LIST":
            handled = self._set_touch_cursor("instance_cursor", row_index, len(self.instance_rows))
            selected_idx = self.state.instance_cursor - 1
            if 0 <= selected_idx < len(self.state.instances):
                self.state.active_instance_id = str(self.state.instances[selected_idx].get("id", ""))
        elif mode == "REMOVE_INSTANCE_PICKER":
            handled = self._set_touch_cursor("remove_instance_picker_cursor", row_index, len(self.state.instances) + 1)
        elif mode == "PATCHER_PICKER":
            handled = self._set_touch_cursor("patcher_cursor", row_index, len(self.state.patchers) + 1)
        elif mode == "INSTANCE_MENU":
            handled = self._set_touch_cursor("instance_menu_cursor", row_index, len(self.instance_menu_items) + 1)
        elif mode == "REMOVE_INSTANCE_CONFIRM":
            handled = self._set_touch_cursor("remove_instance_confirm_cursor", row_index, len(REMOVE_INSTANCE_CONFIRM_ITEMS))
        elif mode == "PRESET_LIST":
            if row_index > 0:
                row_index += len(self.preset_action_items)
            handled = self._set_touch_cursor("preset_cursor", row_index, len(self.preset_menu_items))
        elif mode == "PRESET_REMOVE_PICKER":
            handled = self._set_touch_cursor("preset_remove_cursor", row_index, len(self.active_presets) + 1)
        elif mode == "PARAM_LIST":
            handled = self._set_touch_cursor("param_cursor", row_index, len(self.active_params) + 1)
        elif mode == "ENUM_LIST":
            handled = self._set_touch_cursor("enum_cursor", row_index, len(self.active_enum_options))
        elif mode == "ROUTING_GROUP":
            handled = self._set_touch_cursor("routing_group_cursor", row_index, len(ROUTING_GROUP_ITEMS) + 1)
        elif mode == "ROUTING_PORTS":
            handled = self._set_touch_cursor("routing_port_cursor", row_index, len(self.active_routing_ports) + 1)
        elif mode == "ROUTING_TARGETS":
            handled = self._set_touch_cursor("routing_target_cursor", row_index, len(self.routing_assignment_rows))
        elif mode == "ROUTING_ADD_PICKER":
            handled = self._set_touch_cursor("routing_add_cursor", row_index, len(self.available_routing_add_targets) + 1)
        elif mode == "ROUTING_DISCONNECT_PICKER":
            handled = self._set_touch_cursor("routing_disconnect_cursor", row_index, len(self.current_routing_targets) + 1)
        elif mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            handled = self._set_touch_cursor("routing_overview_cursor", row_index + 1, len(self.routing_overview_rows))
        elif mode == "SYSTEM_MENU":
            handled = self._set_touch_cursor("system_cursor", row_index, len(self.system_menu_items) + 1)
        elif mode == "SYSTEM_TRANSPORT":
            if self.transport_rows:
                self.state.transport_cursor = max(1, min(row_index, len(self.transport_rows)))
                handled = True
        elif mode == "SYSTEM_TRANSPOSE":
            if self.transpose_rows:
                self.state.transpose_cursor = max(1, min(row_index, len(self.transpose_rows)))
                handled = True
        elif mode == "SYSTEM_TRANSPOSE_CONTROLLER":
            handled = self._set_touch_cursor("transpose_controller_cursor", row_index, len(self.transpose_controller_items))
        elif mode == "SYSTEM_TRANSPOSE_ROLE":
            handled = self._set_touch_cursor("transpose_role_cursor", row_index, len(self.transpose_role_items))
        elif mode == "SYSTEM_TRANSPOSE_AUTHORITY":
            handled = self._set_touch_cursor("transpose_authority_cursor", row_index, len(self.transpose_authority_items))
        elif mode == "NETWORK":
            if self.network_value_rows:
                self.state.network_cursor = max(1, min(row_index, len(self.network_value_rows)))
                handled = True
        elif mode == "SOFTWARE_UPDATE":
            handled = self._set_touch_cursor("software_update_cursor", row_index, len(self.software_update_rows))
        elif mode == "WIFI_NETWORKS":
            handled = self._set_touch_cursor("wifi_network_cursor", row_index, len(self.wifi_network_rows))
        elif mode == "SYSTEM_AUDIO":
            handled = self._set_touch_cursor("system_audio_cursor", row_index, len(SYSTEM_AUDIO_ITEMS) + 1)
        elif mode == "MAINT":
            handled = self._set_touch_cursor("maint_cursor", row_index, len(self.maint_menu_items) + 1)
        elif mode == "SYSTEM_AUDIO_DEVICE":
            handled = self._set_touch_cursor("audio_device_cursor", row_index, len(self.audio_options) + 1)
        elif mode == "SYSTEM_AUDIO_RATE":
            handled = self._set_touch_cursor("sample_rate_cursor", row_index, len(self.sample_rate_options) + 1)
        elif mode == "SYSTEM_AUDIO_BUFFER":
            handled = self._set_touch_cursor("buffer_size_cursor", row_index, len(self.buffer_size_options) + 1)

        if handled:
            self._handle_short_press()

    def _handle_step(self, delta: int) -> None:
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
            self.state.graph_set_cursor = self._cycle(self.state.graph_set_cursor, len(self.graph_set_menu_items), step)
        elif self.state.ui_mode == "GRAPH_LOAD_SET_LIST":
            self.state.graph_load_set_cursor = self._cycle(self.state.graph_load_set_cursor, len(self.graph_load_set_menu_items), step)
        elif self.state.ui_mode == "GRAPH_PRESET_LIST":
            self.state.graph_preset_cursor = self._cycle(self.state.graph_preset_cursor, len(self.graph_preset_menu_items), step)
        elif self.state.ui_mode == "GRAPH_PRESET_REMOVE_PICKER":
            self.state.graph_preset_remove_cursor = self._cycle(self.state.graph_preset_remove_cursor, len(self.available_graph_preset_names) + 1, step)
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
                draft_limit = self._editor_draft_limit()
                max_pos = min(len(self.state.name_editor_draft), draft_limit - 1 if len(self.state.name_editor_draft) >= draft_limit else len(self.state.name_editor_draft))
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
        elif self.state.ui_mode == "INSTANCE_SURFACE":
            if self.state.active_surface_key == "organ":
                if self.state.surface_state.get("adjusting"):
                    focus = max(0, min(len(FOOTAGES) - 1, self.state.surface_focus))
                    param = self.surface_param_binding(FOOTAGES[focus])
                    if param is not None:
                        current = param.get("value")
                        if isinstance(current, (int, float)):
                            value = clamp(float(current) + float(step), param.get("min"), param.get("max"))
                            param["value"] = value
                            self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
                else:
                    self.state.surface_focus = self._cycle(self.state.surface_focus, len(FOOTAGES), step)
            elif self.state.active_surface_key == "time_domain_scope":
                param = self.surface_param_binding("sample_rate")
                if param is not None:
                    step = self._accelerate_float_edit_delta(param, step)
                    self.state.edit_value = apply_edit_delta(param, self.state.edit_value, step)
                    param["value"] = self.state.edit_value
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
            elif self.state.active_surface_key == "analog_sequencer":
                if self.state.surface_state.get("adjusting"):
                    stage = self.state.surface_focus + 1
                    param = self.surface_param_binding(f"stage_{stage:02d}_value")
                    if param is not None:
                        value = apply_edit_delta(param, param.get("value"), step)
                        pmin, pmax = self.analog_stage_pitch_bounds(param)
                        if pmin is not None and pmax is not None:
                            value = max(pmin, min(pmax, value))
                        param["value"] = value
                        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=value))
                else:
                    self.state.surface_focus = self._cycle(self.state.surface_focus, 16, step)
            elif self.state.active_surface_key in {"list_sequencer", "list_vel_sequencer"}:
                self.state.surface_focus = self._cycle(self.state.surface_focus, len(self._list_surface_keys()), step)
        elif self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self.state.remove_instance_confirm_cursor = self._cycle(self.state.remove_instance_confirm_cursor, len(REMOVE_INSTANCE_CONFIRM_ITEMS), step)
        elif self.state.ui_mode == "PRESET_LIST":
            self.state.preset_cursor = self._cycle(self.state.preset_cursor, len(self.preset_menu_items), step)
        elif self.state.ui_mode == "PRESET_REMOVE_PICKER":
            self.state.preset_remove_cursor = self._cycle(self.state.preset_remove_cursor, len(self.active_presets) + 1, step)
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
            self.state.routing_target_cursor = self._cycle(self.state.routing_target_cursor, len(self.routing_assignment_rows), step)
        elif self.state.ui_mode == "ROUTING_ADD_PICKER":
            self.state.routing_add_cursor = self._cycle(self.state.routing_add_cursor, len(self.available_routing_add_targets) + 1, step)
        elif self.state.ui_mode == "ROUTING_DISCONNECT_PICKER":
            self.state.routing_disconnect_cursor = self._cycle(self.state.routing_disconnect_cursor, len(self.current_routing_targets) + 1, step)
        elif self.state.ui_mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            self.state.routing_overview_cursor = self._cycle_one_based(
                self.state.routing_overview_cursor,
                len(self.routing_overview_rows),
                step,
            )
            selected = self.selected_routing_overview_instance
            if selected is not None:
                self.state.active_instance_id = str(selected.get("id", ""))
        elif self.state.ui_mode == "SYSTEM_MENU":
            self.state.system_cursor = self._cycle(self.state.system_cursor, len(self.system_menu_items) + 1, step)
        elif self.state.ui_mode == "SYSTEM_TRANSPORT":
            self.state.transport_cursor = self._cycle_one_based(self.state.transport_cursor, len(self.transport_rows), step)
        elif self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
            current = self.state.edit_value
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                current = self.state.system.get("transport", {}).get("bpm", 120.0)
            value = quantize_edit_value(self.transport_tempo_edit_param, float(current) + step)
            self.state.edit_value = value
            self.state.system["transport"]["bpm"] = value
            self.queue_action(UIAction(kind="set_transport", path=self.transport_tempo_edit_param.get("path"), value=value))
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE":
            self.state.transpose_cursor = self._cycle_one_based(self.state.transpose_cursor, len(self.transpose_rows), step)
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_CONTROLLER":
            self.state.transpose_controller_cursor = self._cycle(self.state.transpose_controller_cursor, len(self.transpose_controller_items), step)
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_ROLE":
            self.state.transpose_role_cursor = self._cycle(self.state.transpose_role_cursor, len(self.transpose_role_items), step)
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_AUTHORITY":
            self.state.transpose_authority_cursor = self._cycle(self.state.transpose_authority_cursor, len(self.transpose_authority_items), step)
        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_EDIT":
            role = normalize_role(self.state.transpose_edit_role)
            current = int(self.state.edit_value or 0)
            value = quantize_edit_value(self.transpose_edit_param, current + step)
            self.set_transpose_value(role, value, "Encoder")
        elif self.state.ui_mode == "NETWORK":
            self.state.network_cursor = self._cycle_one_based(self.state.network_cursor, len(self.network_value_rows), step)
        elif self.state.ui_mode == "SOFTWARE_UPDATE":
            self.state.software_update_cursor = self._cycle(self.state.software_update_cursor, len(self.software_update_rows), step)
        elif self.state.ui_mode == "WIFI_NETWORKS":
            self.state.wifi_network_cursor = self._cycle(self.state.wifi_network_cursor, len(self.wifi_network_rows), step)
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
            self.state.edit_numeric_draft = ""
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
            if self.top_level_items[self.state.top_index] == "SETS":
                self.state.ui_mode = "GRAPH_SET_LIST"
                self.state.graph_set_cursor = self.graph_set_initial_cursor()
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
                self.state.ui_mode = "GRAPH_SET_LIST"
                self.state.graph_set_cursor = self.graph_set_initial_cursor()
            else:
                choice = self.graph_menu_items[self.state.graph_menu_cursor - 1]
                if choice == PRESET_ACTION_SAVE:
                    self._save_current_graph_or_open_save_as()
                elif choice == PRESET_ACTION_SAVE_AS:
                    self._begin_graph_save_as()
                elif choice == "SET PRESETS":
                    self.state.ui_mode = "GRAPH_PRESET_LIST"
                    self.state.graph_preset_cursor = self.graph_preset_initial_cursor()
                elif choice == "AUDIO OVERVIEW":
                    self.state.active_transport = "audio"
                    self.state.ui_mode = "AUDIO_ROUTING_OVERVIEW"
                    self.state.routing_overview_cursor = self.instance_cursor_for_active_instance()
                elif choice == "MIDI OVERVIEW":
                    self.state.active_transport = "midi"
                    self.state.ui_mode = "MIDI_ROUTING_OVERVIEW"
                    self.state.routing_overview_cursor = self.instance_cursor_for_active_instance()

        elif self.state.ui_mode == "GRAPH_SET_LIST":
            if self.state.graph_set_cursor == 0:
                self.state.ui_mode = "TOP"
            else:
                choice = self.graph_set_menu_items[self.state.graph_set_cursor]
                if choice == SET_MENU_CURRENT:
                    self.state.ui_mode = "GRAPH_MENU"
                    self.state.graph_menu_cursor = 1 if self.graph_menu_items else 0
                elif choice == SET_MENU_LOAD:
                    self.state.ui_mode = "GRAPH_LOAD_SET_LIST"
                    self.state.graph_load_set_cursor = self.graph_load_set_initial_cursor()

        elif self.state.ui_mode == "GRAPH_LOAD_SET_LIST":
            if self.state.graph_load_set_cursor == 0:
                self.state.ui_mode = "GRAPH_SET_LIST"
                self.state.graph_set_cursor = 2
            elif self.graph_load_path:
                graph_name = self.selected_graph_set_name
                if graph_name:
                    self.queue_action(
                        UIAction(
                            kind="load_set",
                            path=self.graph_load_path,
                            value=graph_name,
                        )
                    )

        elif self.state.ui_mode == "GRAPH_PRESET_LIST":
            if self.state.graph_preset_cursor == 0:
                self.state.ui_mode = "GRAPH_MENU"
                self.state.graph_menu_cursor = self.graph_menu_items.index("SET PRESETS") + 1 if "SET PRESETS" in self.graph_menu_items else 1
            else:
                action_idx = self.state.graph_preset_cursor - 1
                if 0 <= action_idx < len(self.graph_preset_action_items):
                    choice = self.graph_preset_action_items[action_idx]
                    if choice == PRESET_ACTION_SAVE:
                        self._save_current_graph_preset_or_open_save_as()
                    elif choice == PRESET_ACTION_SAVE_AS:
                        self._begin_graph_preset_save_as()
                    elif choice == PRESET_ACTION_REMOVE and self.graph_preset_destroy_path:
                        self.state.ui_mode = "GRAPH_PRESET_REMOVE_PICKER"
                        self.state.graph_preset_remove_cursor = 1 if self.available_graph_preset_names else 0
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

        elif self.state.ui_mode == "GRAPH_PRESET_REMOVE_PICKER":
            if self.state.graph_preset_remove_cursor == 0:
                self.state.ui_mode = "GRAPH_PRESET_LIST"
            elif self.graph_preset_destroy_path:
                preset_name = self.selected_graph_preset_remove_name
                if preset_name:
                    self.queue_action(UIAction(kind="delete_graph_preset", path=self.graph_preset_destroy_path, value=preset_name))

        elif self.state.ui_mode == "GRAPH_STARTUP":
            if self.state.graph_startup_cursor == 0:
                self.state.ui_mode = "GRAPH_MENU"
            else:
                choice = self.graph_startup_menu_items[self.state.graph_startup_cursor - 1]
                if choice == "LOAD NAMED SET":
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
                elif choice in {NAME_EDITOR_EDIT, WIFI_PASSWORD_EDIT}:
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
                        self.state.pending_add_instance_count = len(self.state.instances) + 1
                        self.queue_action(
                            UIAction(
                                kind="add_instance",
                                path=self.state.add_instance_path,
                                value=[-1, patcher_name],
                            )
                        )
                        self.state.ui_mode = "INSTANCE_LIST"
                        self.state.instance_cursor = max(1, len(self.state.instances) + 1)

        elif self.state.ui_mode == "INSTANCE_MENU":
            if self.state.instance_menu_cursor == 0:
                self.state.ui_mode = "INSTANCE_LIST"
            else:
                choice = self.instance_menu_items[self.state.instance_menu_cursor - 1]
                available = self.available_instance_surface
                if available is not None and choice == available[0].title:
                    self._begin_instance_surface()
                elif choice == "PARAMETERS":
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
                self._cancel_remove_instance_confirm()
            elif self.remove_instance_target is not None:
                self._confirm_remove_instance()

        elif self.state.ui_mode == "PRESET_LIST":
            if self.state.preset_cursor == 0:
                self.state.ui_mode = "INSTANCE_MENU"
            else:
                action_idx = self.state.preset_cursor - 1
                if 0 <= action_idx < len(self.preset_action_items):
                    choice = self.preset_action_items[action_idx]
                    if choice == PRESET_ACTION_SAVE:
                        self._save_current_preset_or_open_save_as()
                    elif choice == PRESET_ACTION_SAVE_AS:
                        self._begin_preset_save_as()
                    elif choice == PRESET_ACTION_REMOVE and self.active_preset_destroy_path:
                        self.state.ui_mode = "PRESET_REMOVE_PICKER"
                        self.state.preset_remove_cursor = 1 if self.active_presets else 0
                else:
                    preset = self.selected_preset
                    if preset:
                        self.remember_loaded_preset(preset.get("name"))
                        self.queue_action(UIAction(kind="load_preset", path=preset.get("path"), value=preset.get("value")))

        elif self.state.ui_mode == "PRESET_REMOVE_PICKER":
            if self.state.preset_remove_cursor == 0:
                self.state.ui_mode = "PRESET_LIST"
            elif self.active_preset_destroy_path:
                preset_name = self.selected_preset_remove_name
                if preset_name:
                    self.queue_action(UIAction(kind="delete_preset", path=self.active_preset_destroy_path, value=preset_name))

        elif self.state.ui_mode == "PARAM_LIST":
            if self.state.param_cursor == 0:
                self.state.ui_mode = "INSTANCE_MENU"
            else:
                param = self.selected_param
                if param:
                    if is_boolish(param):
                        self._toggle_bool_param(param)
                        self._edit_original_value = None
                    elif is_ttid_param(param):
                        self._edit_original_value = param.get("value")
                        self._begin_ttid_edit(param)
                        self.state.ui_mode = "EDIT"
                    elif is_step16_param(param):
                        self._edit_original_value = param.get("value")
                        self.state.edit_value = normalize_step16_mask(param.get("value", 0))
                        self.state.edit_step16_focus = 0
                        self.state.ui_mode = "EDIT"
                    elif is_enum_param(param):
                        self._edit_original_value = param.get("value")
                        self.state.edit_value = normalize_current_value_for_edit(param)
                        options = self.active_enum_options
                        self.state.enum_cursor = options.index(self.state.edit_value) if self.state.edit_value in options else 0
                        self.state.ui_mode = "ENUM_LIST"
                    else:
                        self._edit_original_value = param.get("value")
                        self.state.edit_value = normalize_current_value_for_edit(param)
                        self.state.edit_numeric_draft = ""
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
                self.state.routing_target_cursor = 1 if self.current_routing_targets else 0

        elif self.state.ui_mode == "ROUTING_TARGETS":
            if self.state.routing_target_cursor == 0:
                self.state.ui_mode = "ROUTING_PORTS"
            else:
                rows = self.routing_assignment_rows
                row = rows[self.state.routing_target_cursor] if 0 <= self.state.routing_target_cursor < len(rows) else None
                if row and row.label == "ADD":
                    self.state.ui_mode = "ROUTING_ADD_PICKER"
                    self.state.routing_add_cursor = 1 if self.available_routing_add_targets else 0
                elif row and row.label == "REMOVE":
                    self.state.ui_mode = "ROUTING_DISCONNECT_PICKER"
                    self.state.routing_disconnect_cursor = 1 if self.current_routing_targets else 0

        elif self.state.ui_mode == "ROUTING_ADD_PICKER":
            if self.state.routing_add_cursor == 0:
                self.state.ui_mode = "ROUTING_TARGETS"
            else:
                port = self.selected_routing_port
                targets = self.available_routing_add_targets
                target_idx = self.state.routing_add_cursor - 1
                if port is not None and port.get("path") and 0 <= target_idx < len(targets):
                    current = self.current_routing_targets
                    add_target = targets[target_idx]
                    if add_target not in current:
                        value = current + [add_target]
                    else:
                        value = current
                    self.queue_action(
                        UIAction(
                            kind="set_routing",
                            path=port.get("path"),
                            value=value,
                        )
                    )
                    self.state.ui_mode = "ROUTING_TARGETS"

        elif self.state.ui_mode == "ROUTING_DISCONNECT_PICKER":
            if self.state.routing_disconnect_cursor == 0:
                self.state.ui_mode = "ROUTING_TARGETS"
            else:
                port = self.selected_routing_port
                current = self.current_routing_targets
                target_idx = self.state.routing_disconnect_cursor - 1
                if port is not None and port.get("path") and 0 <= target_idx < len(current):
                    remove_target = current[target_idx]
                    value = [target for target in current if target != remove_target]
                    self.queue_action(
                        UIAction(
                            kind="set_routing",
                            path=port.get("path"),
                            value=value,
                        )
                    )
                    self.state.ui_mode = "ROUTING_TARGETS"

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
                elif choice == "TRANSPORT":
                    self.state.ui_mode = "SYSTEM_TRANSPORT"
                    self.state.transport_cursor = 1
                elif choice == "STARTUP":
                    self.state.ui_mode = "GRAPH_STARTUP"
                    self.state.graph_startup_cursor = 1 if self.graph_startup_menu_items else 0
                elif choice == "NETWORK":
                    self.state.ui_mode = "NETWORK"
                    self.state.network_cursor = 1 if self.network_value_rows else 0
                elif choice == "TRANSPOSE":
                    self.state.ui_mode = "SYSTEM_TRANSPOSE"
                    self.state.transpose_cursor = 2
                elif choice == "UPDATE":
                    self.state.ui_mode = "SOFTWARE_UPDATE"
                    self.state.software_update_cursor = self.software_update_check_cursor
                elif choice == "MAINT":
                    self.state.ui_mode = "MAINT"
                    self.state.maint_cursor = 1 if self.maint_menu_items else 0
                else:
                    self._about_press_count = 0
                    self.state.ui_mode = choice

        elif self.state.ui_mode == "SYSTEM_TRANSPORT":
            transport = self.state.system.get("transport", {})
            if self.state.transport_cursor == 1 and transport.get("rolling_path"):
                rolling = not bool(transport.get("rolling"))
                transport["rolling"] = rolling
                self.queue_action(UIAction(kind="set_transport", path=transport.get("rolling_path"), value=rolling))
            elif self.state.transport_cursor == 2 and transport.get("bpm_path"):
                bpm = transport.get("bpm")
                self.state.edit_value = float(bpm) if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) else 120.0
                self.state.edit_numeric_draft = ""
                self.state.ui_mode = "SYSTEM_TRANSPORT_TEMPO_EDIT"

        elif self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
            self.state.ui_mode = "SYSTEM_TRANSPORT"
            self.state.edit_value = None

        elif self.state.ui_mode == "SYSTEM_TRANSPOSE":
            row = self.transpose_rows[self.state.transpose_cursor - 1] if 0 < self.state.transpose_cursor <= len(self.transpose_rows) else None
            if row is not None and row.label == "authority":
                self.state.ui_mode = "SYSTEM_TRANSPOSE_AUTHORITY"
                authorities = ["unconfigured", "standalone", "shadowscore"]
                self.state.transpose_authority_cursor = authorities.index(normalize_transpose_authority(self.state.transpose_authority)) + 1
            elif row is not None and row.label in {"chromatic", "scalar"}:
                if self.state.transpose_authority != "standalone":
                    self.set_status_message("Select LOCAL transpose authority")
                    self.queue_action(UIAction(kind="save_state"))
                    return
                role = ROLE_CHROMATIC if row.label == "chromatic" else ROLE_SCALAR
                self.state.transpose_edit_role = role
                self.state.edit_value = self.state.transpose_chromatic if role == ROLE_CHROMATIC else self.state.transpose_scalar
                self.state.ui_mode = "SYSTEM_TRANSPOSE_EDIT"
            elif row is not None and row.label == "controller":
                self.state.ui_mode = "SYSTEM_TRANSPOSE_CONTROLLER"
                configured = self.state.transpose_controller_identity
                self.state.transpose_controller_cursor = 1
                for idx, (identity, _label) in enumerate(self.transpose_controller_choices, start=2):
                    if identity == configured:
                        self.state.transpose_controller_cursor = idx
                        break
            elif row is not None and row.label == "function":
                self.state.ui_mode = "SYSTEM_TRANSPOSE_ROLE"
                role_order = [ROLE_NONE, ROLE_CHROMATIC, ROLE_SCALAR]
                self.state.transpose_role_cursor = role_order.index(normalize_role(self.state.transpose_controller_role)) + 1

        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_CONTROLLER":
            cursor = self.state.transpose_controller_cursor
            if cursor == 0:
                self.state.ui_mode = "SYSTEM_TRANSPOSE"
            elif cursor == 1:
                self.state.transpose_controller_identity = ""
                self.state.transpose_controller_role = ROLE_NONE
                self.queue_action(UIAction(kind="configure_transpose_midi", value=""))
                self.queue_action(UIAction(kind="save_state"))
                self.state.ui_mode = "SYSTEM_TRANSPOSE"
            else:
                choices = self.transpose_controller_choices
                index = cursor - 2
                if 0 <= index < len(choices):
                    identity = choices[index][0]
                    self.state.transpose_controller_identity = identity
                    self.queue_action(UIAction(kind="configure_transpose_midi", value=identity))
                    self.queue_action(UIAction(kind="save_state"))
                    self.state.ui_mode = "SYSTEM_TRANSPOSE"

        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_ROLE":
            cursor = self.state.transpose_role_cursor
            if cursor == 0:
                self.state.ui_mode = "SYSTEM_TRANSPOSE"
            else:
                roles = [ROLE_NONE, ROLE_CHROMATIC, ROLE_SCALAR]
                index = cursor - 1
                if 0 <= index < len(roles):
                    self.state.transpose_controller_role = roles[index]
                    self.queue_action(UIAction(kind="save_state"))
                    self.state.ui_mode = "SYSTEM_TRANSPOSE"

        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_AUTHORITY":
            cursor = self.state.transpose_authority_cursor
            if cursor == 0:
                self.state.ui_mode = "SYSTEM_TRANSPOSE"
            else:
                authorities = ["unconfigured", "standalone", "shadowscore"]
                index = cursor - 1
                if 0 <= index < len(authorities):
                    self.set_transpose_authority(authorities[index])
                    self.state.ui_mode = "SYSTEM_TRANSPOSE"

        elif self.state.ui_mode == "SYSTEM_TRANSPOSE_EDIT":
            self.state.ui_mode = "SYSTEM_TRANSPOSE"
            self.state.edit_value = None
            self.state.transpose_edit_role = ""

        elif self.state.ui_mode == "NETWORK":
            selected_row = self.network_value_rows[self.state.network_cursor - 1] if 0 < self.state.network_cursor <= len(self.network_value_rows) else None
            if selected_row and selected_row.label == "setup" and self.network_direct_setup_available:
                if self.network_direct_setup_active:
                    self.queue_action(UIAction(kind="disable_direct_ethernet"))
                else:
                    self.queue_action(UIAction(kind="enable_direct_ethernet"))
            elif selected_row and selected_row.label == "wifi" and self.network_wifi_available:
                self.state.ui_mode = "WIFI_NETWORKS"
                self.state.wifi_network_cursor = self.wifi_network_initial_cursor()

        elif self.state.ui_mode == "SOFTWARE_UPDATE":
            if self.state.software_update_cursor == 0:
                self.state.ui_mode = "SYSTEM_MENU"
            else:
                row = (
                    self.software_update_rows[self.state.software_update_cursor]
                    if self.state.software_update_cursor < len(self.software_update_rows)
                    else None
                )
                if row and row.action:
                    choice = str(row.label)
                    if choice == "CHECK":
                        self.queue_action(UIAction(kind="check_software_update"))
                    elif choice in {"APPLY UPDATE", "UPDATE BOX", "INSTALL SCORE", "UPDATE SCORE"}:
                        target = "shadowscore" if "SCORE" in choice else "shadowbox"
                        self._begin_name_editor(
                            context="software_update_password",
                            path=target,
                            initial_draft="",
                            return_mode="SOFTWARE_UPDATE",
                        )
                    elif choice == "CANCEL UPDATE":
                        self.queue_action(UIAction(kind="cancel_software_update"))

        elif self.state.ui_mode == "WIFI_NETWORKS":
            if self.state.wifi_network_cursor == 0:
                self.state.ui_mode = "NETWORK"
            elif (
                self.network_wifi_available
                and self.state.wifi_network_cursor == len(self.wifi_network_rows) - 1
                and self.wifi_network_rows[self.state.wifi_network_cursor].label == "RESCAN"
            ):
                self.queue_action(UIAction(kind="rescan_wifi"))
            else:
                network = self.selected_wifi_network
                ssid = str(network.get("ssid", "") or "").strip()
                if network.get("saved"):
                    connection_id = str(network.get("id", "") or ssid).strip()
                    if connection_id:
                        self.queue_action(UIAction(kind="connect_wifi", ssid=connection_id))
                elif ssid and self._wifi_security_requires_password(network.get("security", "")):
                    self._begin_wifi_password_editor(ssid)
                elif ssid:
                    self.queue_action(UIAction(kind="connect_wifi_new", ssid=ssid, value=""))

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
                self.begin_audio_restart(chosen, "SYSTEM_AUDIO_DEVICE")
                self.queue_action(UIAction(kind="set_audio_device", device_name=chosen))

        elif self.state.ui_mode == "SYSTEM_AUDIO_RATE":
            if self.state.sample_rate_cursor == 0:
                self.state.ui_mode = "SYSTEM_AUDIO"
            elif self.sample_rate_options:
                audio = self.state.system.get("audio", {})
                path = audio.get("sample_rate_path")
                value = self.sample_rate_options[self.state.sample_rate_cursor - 1]
                self.begin_audio_restart(f"{value} Hz", "SYSTEM_AUDIO_RATE")
                self.queue_action(UIAction(kind="set_jack_config", path=path, value=value))

        elif self.state.ui_mode == "SYSTEM_AUDIO_BUFFER":
            if self.state.buffer_size_cursor == 0:
                self.state.ui_mode = "SYSTEM_AUDIO"
            elif self.buffer_size_options:
                audio = self.state.system.get("audio", {})
                path = audio.get("period_frames_path")
                value = self.buffer_size_options[self.state.buffer_size_cursor - 1]
                self.begin_audio_restart(f"{value} frames", "SYSTEM_AUDIO_BUFFER")
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

        elif self.state.ui_mode == "INSTANCE_SURFACE":
            if self.state.active_surface_key in {"organ", "analog_sequencer"}:
                self.state.surface_state["adjusting"] = not bool(self.state.surface_state.get("adjusting"))
            elif self.state.active_surface_key in {"list_sequencer", "list_vel_sequencer"}:
                self._send_list_field()
            else:
                self._exit_instance_surface()

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
            else:
                if self.state.edit_numeric_draft and not self._commit_numeric_keypad_draft():
                    return
                if param is not None and is_discrete_param(param):
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
                self.state.edit_numeric_draft = ""
                self._reset_float_edit_acceleration()
                self.state.ui_mode = "PARAM_LIST"
                self._edit_original_value = None

        self.queue_action(UIAction(kind="save_state"))

    def _handle_long_press(self) -> None:
        if self.state.ui_mode == "BRICK_PANEL":
            self._about_press_count = 0
            self.state.ui_mode = "ABOUT"
        elif self.state.ui_mode == "INSTANCE_SURFACE":
            self._exit_instance_surface()
        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
            self.state.edit_numeric_draft = ""
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
        elif self.state.ui_mode == "PRESET_REMOVE_PICKER":
            self.state.ui_mode = "PRESET_LIST"
        elif self.state.ui_mode in ("PRESET_LIST", "PARAM_LIST", "ROUTING_GROUP"):
            self.state.ui_mode = "INSTANCE_MENU"
        elif self.state.ui_mode == "ROUTING_PORTS":
            self.state.ui_mode = "ROUTING_GROUP"
        elif self.state.ui_mode == "ROUTING_TARGETS":
            self.state.ui_mode = "ROUTING_PORTS"
        elif self.state.ui_mode == "ROUTING_ADD_PICKER":
            self.state.ui_mode = "ROUTING_TARGETS"
        elif self.state.ui_mode == "ROUTING_DISCONNECT_PICKER":
            self.state.ui_mode = "ROUTING_TARGETS"
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
        elif self.state.ui_mode == "WIFI_NETWORKS":
            self.state.ui_mode = "NETWORK"
        elif self.state.ui_mode == "GRAPH_STATUS":
            self.state.ui_mode = "GRAPH_SET_LIST"
        elif self.state.ui_mode == "GRAPH_STARTUP":
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode == "GRAPH_PRESET_REMOVE_PICKER":
            self.state.ui_mode = "GRAPH_PRESET_LIST"
        elif self.state.ui_mode == "GRAPH_SET_LIST":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "GRAPH_LOAD_SET_LIST":
            self.state.ui_mode = "GRAPH_SET_LIST"
            self.state.graph_set_cursor = 2
        elif self.state.ui_mode == "GRAPH_PRESET_LIST":
            self.state.ui_mode = "GRAPH_MENU"
            self.state.graph_menu_cursor = self.graph_menu_items.index("SET PRESETS") + 1 if "SET PRESETS" in self.graph_menu_items else 1
        elif self.state.ui_mode == "GRAPH_MENU":
            self.state.ui_mode = "GRAPH_SET_LIST"
            self.state.graph_set_cursor = self.graph_set_initial_cursor()
        elif self.state.ui_mode == "INSTANCE_MENU":
            self.state.ui_mode = "INSTANCE_LIST"
        elif self.state.ui_mode == "INSTANCE_LIST":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "REMOVE_INSTANCE_PICKER":
            self.state.ui_mode = "INSTANCE_LIST"
        elif self.state.ui_mode == "PATCHER_PICKER":
            self.state.ui_mode = "TOP"
        elif self.state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self._cancel_remove_instance_confirm()
        elif self.state.ui_mode in ("STATUS", "NETWORK", "SOFTWARE_UPDATE", "ABOUT", "MAINT", "SYSTEM_TRANSPOSE", "SYSTEM_TRANSPORT"):
            self._about_press_count = 0
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode in {"SYSTEM_TRANSPOSE_CONTROLLER", "SYSTEM_TRANSPOSE_ROLE", "SYSTEM_TRANSPOSE_AUTHORITY", "SYSTEM_TRANSPOSE_EDIT"}:
            self.state.ui_mode = "SYSTEM_TRANSPOSE"
            self.state.edit_value = None
            self.state.transpose_edit_role = ""
        elif self.state.ui_mode == "SYSTEM_TRANSPORT_TEMPO_EDIT":
            self.state.ui_mode = "SYSTEM_TRANSPORT"
            self.state.edit_value = None
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
