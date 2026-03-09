"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


STATE_PATH = Path.home() / "rnbo-ui" / "shadowbox_state.json"

TOP_LEVEL_ITEMS = ["PATCH", "PARAM", "SYSTEM"]
SYSTEM_ITEMS = ["STATUS", "AUDIO", "NETWORK", "STARTUP", "MAINT"]


# ============================================================
# ACTIONS
# ============================================================

@dataclass
class UIAction:
    kind: str
    path: Optional[str] = None
    value: Any = None
    patch_name: Optional[str] = None
    device_name: Optional[str] = None


# ============================================================
# STATE
# ============================================================

@dataclass
class UIState:
    patches: list[str] = field(default_factory=list)
    current_patch: str = ""
    params: list[dict] = field(default_factory=list)
    system: dict = field(default_factory=dict)

    ui_mode: str = "TOP"
    top_index: int = 0
    patch_index: int = 0
    param_index: int = 0

    system_index: int = 0
    system_screen: str = "MENU"
    audio_card_index: int = 0

    edit_value: Any = None

    busy: bool = False
    busy_reason: str = ""
    activity_ticks: int = 0

    last_loaded: str = ""
    auto_load_last_patch: bool = True
    saved_audio_card: str = ""


# ============================================================
# HELPERS
# ============================================================

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


def clamp_index(idx: int, items: list[Any]) -> int:
    if not items:
        return 0
    return max(0, min(idx, len(items) - 1))


def restore_named_index(items: list[str], saved_name: str = "", saved_idx: int = 0) -> int:
    if not items:
        return 0
    if saved_name in items:
        return items.index(saved_name)
    return clamp_index(int(saved_idx), items)


def restore_param_index(params: list[dict], state: dict) -> int:
    if not params:
        return 0

    saved_name = state.get("param_name", "")
    if saved_name:
        for i, p in enumerate(params):
            if p.get("name") == saved_name:
                return i

    return clamp_index(int(state.get("param_index", 0)), params)


def clamp(v: float, lo: Optional[float], hi: Optional[float]) -> float:
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def is_boolish(param: dict) -> bool:
    vals = param.get("vals")
    if vals and len(vals) == 2:
        return True

    pmin = param.get("min")
    pmax = param.get("max")
    ptype = param.get("type", "")

    if ptype in ("T", "F"):
        return True

    return pmin == 0 and pmax == 1


def numeric_step(param: dict) -> float:
    pmin = param.get("min")
    pmax = param.get("max")
    ptype = param.get("type", "")

    if ptype in ("i", "h", "I", "c"):
        return 1

    if pmin is not None and pmax is not None:
        span = pmax - pmin
        if span <= 0:
            return 0.01
        if span <= 1:
            return 0.01
        if span <= 10:
            return 0.05
        if span <= 100:
            return 0.5
        return max(span / 128.0, 0.5)

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

    return value


def apply_edit_delta(param: dict, current_value: Any, delta: int) -> Any:
    vals = param.get("vals")

    if vals:
        if current_value not in vals:
            current_value = vals[0]
        idx = vals.index(current_value)
        idx = (idx + delta) % len(vals)
        return vals[idx]

    if is_boolish(param):
        return 0 if bool(current_value) else 1

    step = numeric_step(param)

    if isinstance(current_value, (int, float)):
        new_value = current_value + (step * delta)
        if param.get("type", "") in ("i", "h", "I", "c"):
            new_value = int(round(new_value))
        return clamp(new_value, param.get("min"), param.get("max"))

    return current_value


# ============================================================
# EVENTS
# ============================================================

@dataclass
class UIEvent:
    kind: str
    delta: int = 0


# ============================================================
# UI
# ============================================================

class ShadowboxUI:
    def __init__(self, rnbo=None):
        self.rnbo = rnbo
        self.state = UIState()
        self._actions: list[UIAction] = []
        self._saved_state_cache = load_state_file()

    # ----------------------------
    # persistence
    # ----------------------------

    def restore_from_saved_state(self) -> None:
        saved = self._saved_state_cache

        self.state.ui_mode = saved.get("ui_mode", "TOP")
        self.state.top_index = restore_named_index(
            TOP_LEVEL_ITEMS,
            saved.get("top_name", ""),
            saved.get("top_index", 0),
        )
        self.state.system_index = restore_named_index(
            SYSTEM_ITEMS,
            saved.get("system_name", ""),
            saved.get("system_index", 0),
        )
        self.state.system_screen = saved.get("system_screen", "MENU")
        self.state.auto_load_last_patch = bool(saved.get("auto_load_last_patch", True))
        self.state.last_loaded = saved.get("last_loaded", "")
        self.state.saved_audio_card = saved.get("saved_audio_card", "")

        self.state.patch_index = restore_named_index(
            self.state.patches,
            saved.get("selected_patch", ""),
            saved.get("selected_index", 0),
        )
        self.state.param_index = restore_param_index(self.state.params, saved)
        self._sync_audio_index()

    def save_state(self) -> None:
        save_state_file(
            {
                "selected_patch": self.selected_patch_name,
                "selected_index": self.state.patch_index,
                "last_loaded": self.state.last_loaded,
                "ui_mode": self.state.ui_mode,
                "top_name": TOP_LEVEL_ITEMS[self.state.top_index] if TOP_LEVEL_ITEMS else "",
                "top_index": self.state.top_index,
                "param_name": self.selected_param.get("name", "") if self.selected_param else "",
                "param_index": self.state.param_index,
                "system_name": SYSTEM_ITEMS[self.state.system_index] if SYSTEM_ITEMS else "",
                "system_index": self.state.system_index,
                "system_screen": self.state.system_screen,
                "saved_audio_card": self.state.system.get("audio", {}).get("current_card", ""),
                "auto_load_last_patch": self.state.auto_load_last_patch,
            }
        )

    def should_autoload_last_patch(self) -> bool:
        return self.state.auto_load_last_patch

    def get_last_patch_name(self) -> str:
        return self.state.last_loaded

    # ----------------------------
    # busy state
    # ----------------------------

    def set_busy(self, busy: bool, reason: str = "") -> None:
        self.state.busy = busy
        self.state.busy_reason = reason
        if busy:
            self.state.activity_ticks += 1

    # ----------------------------
    # runner snapshot
    # ----------------------------

    def apply_runner_snapshot(self, snapshot) -> None:
        old_patch_name = self.selected_patch_name
        old_param_name = self.selected_param.get("name", "") if self.selected_param else ""

        self.state.patches = snapshot.patches
        self.state.current_patch = snapshot.current_patch
        self.state.params = snapshot.params
        self.state.system = snapshot.system

        if self.state.patches:
            if old_patch_name in self.state.patches:
                self.state.patch_index = self.state.patches.index(old_patch_name)
            else:
                self.state.patch_index = clamp_index(self.state.patch_index, self.state.patches)
        else:
            self.state.patch_index = 0

        if self.state.params:
            found = None
            if old_param_name:
                for i, p in enumerate(self.state.params):
                    if p.get("name") == old_param_name:
                        found = i
                        break
            self.state.param_index = found if found is not None else clamp_index(self.state.param_index, self.state.params)
        else:
            self.state.param_index = 0

        self._sync_audio_index()

        if self.state.ui_mode == "EDIT" and self.selected_param:
            self.state.edit_value = normalize_current_value_for_edit(self.selected_param)

    # ----------------------------
    # derived properties
    # ----------------------------

    @property
    def selected_patch_name(self) -> str:
        if self.state.patches and 0 <= self.state.patch_index < len(self.state.patches):
            return self.state.patches[self.state.patch_index]
        return ""

    @property
    def selected_param(self) -> Optional[dict]:
        if self.state.params and 0 <= self.state.param_index < len(self.state.params):
            return self.state.params[self.state.param_index]
        return None

    @property
    def audio_options(self) -> list[str]:
        return self.state.system.get("audio", {}).get("card_options", [])

    @property
    def current_audio_card(self) -> str:
        return self.state.system.get("audio", {}).get("current_card", "")

    def _sync_audio_index(self) -> None:
        options = self.audio_options
        if self.current_audio_card in options:
            self.state.audio_card_index = options.index(self.current_audio_card)
        else:
            self.state.audio_card_index = 0

    # ----------------------------
    # action queue
    # ----------------------------

    def queue_action(self, action: UIAction) -> None:
        self._actions.append(action)

    def pop_actions(self) -> list[UIAction]:
        actions = self._actions[:]
        self._actions.clear()
        return actions

    # ----------------------------
    # events
    # ----------------------------

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

        self.state.activity_ticks += 1

        if self.state.ui_mode == "TOP":
            self.state.top_index = (self.state.top_index + delta) % len(TOP_LEVEL_ITEMS)

        elif self.state.ui_mode == "PATCH":
            if self.state.patches:
                self.state.patch_index = (self.state.patch_index + delta) % len(self.state.patches)

        elif self.state.ui_mode == "PARAM":
            if self.state.params:
                self.state.param_index = (self.state.param_index + delta) % len(self.state.params)

        elif self.state.ui_mode == "EDIT":
            param = self.selected_param
            if param is not None:
                step_dir = 1 if delta > 0 else -1
                self.state.edit_value = apply_edit_delta(param, self.state.edit_value, step_dir)

                # optimistic local update
                param["value"] = self.state.edit_value

                self.queue_action(
                    UIAction(
                        kind="set_param",
                        path=param.get("path"),
                        value=self.state.edit_value,
                    )
                )

        elif self.state.ui_mode == "SYSTEM":
            if self.state.system_screen == "MENU":
                self.state.system_index = (self.state.system_index + delta) % len(SYSTEM_ITEMS)

            elif self.state.system_screen == "AUDIO":
                if self.audio_options:
                    self.state.audio_card_index = (self.state.audio_card_index + delta) % len(self.audio_options)

            elif self.state.system_screen == "STARTUP":
                self.state.auto_load_last_patch = not self.state.auto_load_last_patch
                self.queue_action(UIAction(kind="save_state"))

        self.queue_action(UIAction(kind="save_state"))

    def _handle_short_press(self) -> None:
        self.state.activity_ticks += 1

        if self.state.ui_mode == "TOP":
            self.state.ui_mode = TOP_LEVEL_ITEMS[self.state.top_index]

        elif self.state.ui_mode == "PATCH":
            patch = self.selected_patch_name
            if patch:
                self.state.last_loaded = patch
                self.queue_action(UIAction(kind="load_patch", patch_name=patch))

        elif self.state.ui_mode == "PARAM":
            param = self.selected_param
            if param is not None:
                self.state.edit_value = normalize_current_value_for_edit(param)
                self.state.ui_mode = "EDIT"

        elif self.state.ui_mode == "EDIT":
            pass

        elif self.state.ui_mode == "SYSTEM":
            if self.state.system_screen == "MENU":
                self.state.system_screen = SYSTEM_ITEMS[self.state.system_index]

            elif self.state.system_screen == "AUDIO":
                if self.audio_options:
                    chosen = self.audio_options[self.state.audio_card_index]
                    self.queue_action(UIAction(kind="set_audio_device", device_name=chosen))

            elif self.state.system_screen == "STARTUP":
                self.state.auto_load_last_patch = not self.state.auto_load_last_patch
                self.queue_action(UIAction(kind="save_state"))

            elif self.state.system_screen == "MAINT":
                self.queue_action(UIAction(kind="restart_jack"))

        self.queue_action(UIAction(kind="save_state"))

    def _handle_long_press(self) -> None:
        # Long press always means ESC / back
        if self.state.ui_mode == "EDIT":
            self.state.ui_mode = "PARAM"
        elif self.state.ui_mode == "SYSTEM" and self.state.system_screen != "MENU":
            self.state.system_screen = "MENU"
        elif self.state.ui_mode != "TOP":
            self.state.ui_mode = "TOP"

        self.state.activity_ticks += 1
        self.queue_action(UIAction(kind="save_state"))
