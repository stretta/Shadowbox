#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

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


STATE_PATH = Path.home() / "rnbo-ui" / "shadowbox_state.json"

ROUTING_GROUP_ITEMS = ["INPUTS", "OUTPUTS"]
SYSTEM_AUDIO_ITEMS = ["DEVICE", "SAMPLE RATE", "BUFFER SIZE"]
REMOVE_INSTANCE_CONFIRM_ITEMS = ["..", "REMOVE"]
MAINT_ITEMS_REFRESH = "REFRESH"
MAINT_ITEMS_RESTART_JACK = "RESTART JACK"


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

    busy: bool = False
    busy_reason: str = ""
    activity_ticks: int = 0

    saved_audio_card: str = ""
    startup_enabled: bool = False
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
    ptype = param.get("type", "") if isinstance(param, dict) else ""
    if ptype in ("i", "h", "I", "c"):
        return True
    return _metadata_text(param, "edit_as").lower() == "int"


def edit_step(param: dict | None) -> float | None:
    numeric = _metadata_number(param, "edit_step")
    if numeric is None or numeric <= 0:
        return None
    return numeric


def is_boolish(param: dict) -> bool:
    pmin = param.get("min")
    pmax = param.get("max")
    ptype = param.get("type", "")
    metadata = param.get("metadata", {})

    if isinstance(metadata, dict):
        for key in ("bool", "is_bool", "boolean"):
            value = metadata.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes", "bool", "boolean"):
                return True

    if ptype in ("T", "F"):
        return True
    return pmin == 0 and pmax == 1


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


class ShadowboxUI:
    def __init__(self, rnbo=None):
        self.rnbo = rnbo
        self.state = UIState()
        self._actions: list[UIAction] = []
        self._saved_state_cache = load_state_file()
        self._edit_original_value: Any = None

    def restore_from_saved_state(self) -> None:
        saved = self._saved_state_cache
        self.state.top_index = clamp_index(int(saved.get("top_index", 0)), len(self.top_level_items))
        self.state.saved_audio_card = str(saved.get("saved_audio_card", ""))
        self.state.startup_enabled = bool(saved.get("startup_enabled", False))

    def save_state(self) -> None:
        save_state_file(
            {
                "top_index": self.state.top_index,
                "saved_audio_card": self.current_audio_card,
                "startup_enabled": self.state.startup_enabled,
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
        self._edit_original_value = None

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
        self.state.preset_cursor = clamp_index(self.state.preset_cursor, len(self.active_presets) + 1)
        self.state.maint_cursor = clamp_index(self.state.maint_cursor, len(self.maint_menu_items) + 1)
        self.state.routing_port_cursor = clamp_index(self.state.routing_port_cursor, len(self.active_routing_ports) + 1)
        self.state.routing_target_cursor = clamp_index(self.state.routing_target_cursor, len(self.active_routing_targets) + 2)

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
        return ["INSTANCES", "SYSTEM"]

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
        items = ["STATUS", "AUDIO", "NETWORK", "STARTUP", "ABOUT"]
        if self.maint_menu_items:
            items.append("MAINT")
        return items

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
        idx = self.state.preset_cursor - 1
        if idx >= 0 and idx < len(self.active_presets):
            return self.active_presets[idx]
        return None

    @property
    def current_preset_name(self) -> str:
        instance_id = str(self.state.active_instance_id)
        if not instance_id:
            return ""
        return str(self.state.current_presets.get(instance_id, ""))

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
            "INSTANCE_LIST",
            "PATCHER_PICKER",
            "INSTANCE_MENU",
            "REMOVE_INSTANCE_PICKER",
            "REMOVE_INSTANCE_CONFIRM",
            "PRESET_LIST",
            "ROUTING_GROUP",
            "ROUTING_PORTS",
            "EDIT",
            "ENUM_LIST",
            "ROUTING_TARGETS",
            "SYSTEM_AUDIO_DEVICE",
            "SYSTEM_AUDIO_RATE",
            "SYSTEM_AUDIO_BUFFER",
        }

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

        if self.state.ui_mode == "TOP":
            self.state.top_index = self._cycle(self.state.top_index, len(self.top_level_items), step)
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
            self.state.preset_cursor = self._cycle(self.state.preset_cursor, len(self.active_presets) + 1, step)
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
        elif self.state.ui_mode == "STARTUP":
            self.state.startup_enabled = not self.state.startup_enabled
            self.queue_action(UIAction(kind="save_state"))
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
                self.state.edit_value = apply_edit_delta(param, self.state.edit_value, step)
                param["value"] = self.state.edit_value
                if not is_discrete_param(param):
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))

        self.queue_action(UIAction(kind="save_state"))

    def _handle_short_press(self) -> None:
        self.state.activity_ticks += 1

        if self.state.ui_mode == "TOP":
            if self.top_level_items[self.state.top_index] == "INSTANCES":
                self.state.ui_mode = "INSTANCE_LIST"
                self.state.instance_cursor = 1 if self.state.instances or self.can_add_instance or self.can_remove_instances else 0
                if self.state.instances:
                    self.state.active_instance_id = str(self.state.instances[0].get("id", ""))
            else:
                self.state.ui_mode = "SYSTEM_MENU"
                self.state.system_cursor = 1

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
                    self.state.preset_cursor = 1 if self.active_presets else 0
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

        elif self.state.ui_mode == "STARTUP":
            self.state.startup_enabled = not self.state.startup_enabled
            self.queue_action(UIAction(kind="save_state"))

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
                self.state.ui_mode = "PARAM_LIST"
            else:
                if param is not None and is_discrete_param(param):
                    self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self.state.edit_value))
                self.state.ui_mode = "PARAM_LIST"
                self._edit_original_value = None

        self.queue_action(UIAction(kind="save_state"))

    def _handle_long_press(self) -> None:
        if self.state.ui_mode == "EDIT":
            param = self.selected_param
            if param is not None and is_ttid_param(param):
                self.state.edit_value = None
                self.state.edit_ttid_mode = "keyboard"
                self.state.edit_ttid_selected_pc = 0
                self.state.edit_ttid_load_root = 0
                self.state.edit_ttid_scale_index = 0
                self.state.ui_mode = "PARAM_LIST"
            elif param is not None and is_step16_param(param):
                self.state.edit_value = None
                self.state.edit_step16_focus = 0
                self._edit_original_value = None
                self.state.ui_mode = "PARAM_LIST"
            elif param is not None and is_pitch_display_param(param):
                self.state.edit_value = None
                self._edit_original_value = None
                self.state.ui_mode = "PARAM_LIST"
            else:
                if param is not None and self._edit_original_value is not None:
                    param["value"] = self._edit_original_value
                    if is_step16_param(param) or not is_discrete_param(param):
                        self.queue_action(UIAction(kind="set_param", path=param.get("path"), value=self._edit_original_value))
                self.state.edit_value = None
                self.state.edit_step16_focus = 0
                self._edit_original_value = None
                self.state.ui_mode = "PARAM_LIST"
        elif self.state.ui_mode == "ENUM_LIST":
            self.state.edit_value = None
            self._edit_original_value = None
            self.state.ui_mode = "PARAM_LIST"
        elif self.state.ui_mode in ("PRESET_LIST", "PARAM_LIST", "ROUTING_GROUP"):
            self.state.ui_mode = "INSTANCE_MENU"
        elif self.state.ui_mode == "ROUTING_PORTS":
            self.state.ui_mode = "ROUTING_GROUP"
        elif self.state.ui_mode == "ROUTING_TARGETS":
            self.state.ui_mode = "ROUTING_PORTS"
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
        elif self.state.ui_mode in ("STATUS", "NETWORK", "STARTUP", "ABOUT", "MAINT"):
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode in ("SYSTEM_AUDIO_DEVICE", "SYSTEM_AUDIO_RATE", "SYSTEM_AUDIO_BUFFER"):
            self.state.ui_mode = "SYSTEM_AUDIO"
        elif self.state.ui_mode == "SYSTEM_AUDIO":
            self.state.ui_mode = "SYSTEM_MENU"
        elif self.state.ui_mode == "SYSTEM_MENU":
            self.state.ui_mode = "TOP"

        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))
