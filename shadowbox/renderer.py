#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

from __future__ import annotations

import socket
from typing import Any

from shadowbox.rnbo import RNBO_PORT


TOP_LEVEL_ITEMS = ["PATCH", "PARAM", "SYSTEM"]
SYSTEM_ITEMS = ["STATUS", "AUDIO", "NETWORK", "STARTUP", "MAINT"]


def shorten(text: str, max_chars: int) -> str:
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def format_display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.1f}"
        if abs(value) >= 10:
            return f"{value:.2f}"
        return f"{value:.3f}"

    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) == 1:
            return format_display_value(value[0])
        return "list"

    if value is None:
        return "-"

    return str(value)


def list_window(selected_idx: int, total: int):
    if total <= 0:
        return [], 0, []

    if total == 1:
        return [selected_idx], 0, [16]

    if total == 2:
        other = 1 - selected_idx
        return [selected_idx, other], 0, [12, 20]

    indices = [
        (selected_idx - 1) % total,
        selected_idx,
        (selected_idx + 1) % total,
    ]
    return indices, 1, [8, 16, 24]


def activity_frame(ticks: int) -> str:
    frames = ["-", "\\", "|", "/"]
    return frames[ticks % len(frames)]


class ShadowboxRenderer:
    def __init__(self, display):
        self.display = display

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        self.display.text(shorten(title, 19), 0, 0)
        if busy:
            self.display.text(activity_frame(ticks), 120, 0)

    def draw_menu_row(self, y: int, selected: bool, label: str) -> None:
        prefix = "> " if selected else "  "
        self.display.text((prefix + shorten(label, 19))[:21], 0, y)

    def draw_value_row(self, y: int, selected: bool, name: str, value: Any) -> None:
        prefix = "> " if selected else "  "

        left_width = 9
        right_width = 9

        left = shorten(name, left_width)
        right = shorten(format_display_value(value), right_width)

        line = f"{prefix}{left:<{left_width}} {right:>{right_width}}"
        self.display.text(line[:21], 0, y)

    def draw_splash(self, title: str = "SHADOWBOX") -> None:
        self.display.clear()
        self.display.text(title, 34, 12)
        self.display.show()

    def draw_top(self, state) -> None:
        indices, selected_row, rows = list_window(state.top_index, len(TOP_LEVEL_ITEMS))
        for row_idx, item_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, TOP_LEVEL_ITEMS[item_idx])

    def draw_patch_list(self, state) -> None:
        indices, selected_row, rows = list_window(state.patch_index, len(state.patches))
        for row_idx, patch_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, state.patches[patch_idx])

    def draw_param_list(self, state) -> None:
        if not state.params:
            self.display.text("  no params", 0, 16)
            self.display.text("  long press <", 0, 24)
            return

        indices, selected_row, rows = list_window(state.param_index, len(state.params))
        for row_idx, p_idx in enumerate(indices):
            p = state.params[p_idx]
            self.draw_value_row(
                rows[row_idx],
                row_idx == selected_row,
                p.get("name", ""),
                p.get("value"),
            )

    def draw_edit(self, state) -> None:
        param = None
        if state.params and 0 <= state.param_index < len(state.params):
            param = state.params[state.param_index]

        if param is None:
            self.display.text("  no param", 0, 16)
            return

        self.display.text(shorten(param.get("name", ""), 21), 0, 10)
        self.display.text(shorten(format_display_value(state.edit_value), 21), 0, 22)

    def draw_system_menu(self, state) -> None:
        indices, selected_row, rows = list_window(state.system_index, len(SYSTEM_ITEMS))
        for row_idx, item_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, SYSTEM_ITEMS[item_idx])

    def draw_status(self, state) -> None:
        patch = state.current_patch or "-"
        cpu = state.system.get("status", {}).get("cpu_load", None)
        xr = state.system.get("status", {}).get("xruns", None)

        self.draw_value_row(8, False, "patch", patch)
        self.draw_value_row(16, False, "cpu", "-" if cpu is None else f"{cpu:.1f}")
        self.draw_value_row(24, False, "xruns", "-" if xr is None else xr)

    def draw_audio(self, state) -> None:
        audio = state.system.get("audio", {})
        options = audio.get("card_options", [])

        if options and 0 <= state.audio_card_index < len(options):
            device = options[state.audio_card_index]
        else:
            device = audio.get("current_card", "-")

        rate = audio.get("sample_rate", None)
        buf = audio.get("period_frames", None)

        self.draw_value_row(8, False, "device", device or "-")
        self.draw_value_row(16, False, "rate", "-" if rate is None else int(rate))
        self.draw_value_row(24, False, "buffer", "-" if buf is None else buf)

    def draw_network(self, state) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "?"

        self.draw_value_row(8, False, "ip", ip)
        self.draw_value_row(16, False, "osc", RNBO_PORT)
        self.display.text("long press <", 0, 24)

    def draw_startup(self, state) -> None:
        self.draw_value_row(10, False, "autoload", "ON" if state.auto_load_last_patch else "OFF")
        self.display.text("short press tog", 0, 24)

    def draw_maint(self, state) -> None:
        self.display.text("jack restart", 0, 10)
        self.display.text("short press", 0, 22)

    def draw(self, state) -> None:
        self.display.clear()

        header = state.ui_mode
        if state.ui_mode == "PARAM" and state.params:
            header = f"PARAM {state.param_index + 1}/{len(state.params)}"
        elif state.ui_mode == "SYSTEM":
            header = state.system_screen

        self.draw_header(header, busy=state.busy, ticks=state.activity_ticks)

        if state.ui_mode == "TOP":
            self.draw_top(state)
        elif state.ui_mode == "PATCH":
            self.draw_patch_list(state)
        elif state.ui_mode == "PARAM":
            self.draw_param_list(state)
        elif state.ui_mode == "EDIT":
            self.draw_edit(state)
        elif state.ui_mode == "SYSTEM":
            if state.system_screen == "MENU":
                self.draw_system_menu(state)
            elif state.system_screen == "STATUS":
                self.draw_status(state)
            elif state.system_screen == "AUDIO":
                self.draw_audio(state)
            elif state.system_screen == "NETWORK":
                self.draw_network(state)
            elif state.system_screen == "STARTUP":
                self.draw_startup(state)
            elif state.system_screen == "MAINT":
                self.draw_maint(state)

        self.display.show()
