#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner
"""

from __future__ import annotations

import socket
from typing import Any

from shadowbox.editors.step16 import build_cells, is_step16_param
from shadowbox.editors.ttid import get_root_names, is_pc_on, is_ttid_param, note_name
from shadowbox.rnbo import RNBO_PORT
from shadowbox.ui import REMOVE_INSTANCE_CONFIRM_ITEMS, ROUTING_GROUP_ITEMS, SYSTEM_AUDIO_ITEMS, SYSTEM_MENU_ITEMS


def shorten(text: str, max_chars: int) -> str:
    text = str(text)
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def shorten_param_name(name: str) -> str:
    parts = [p for p in str(name).split("/") if p]
    if len(parts) < 2:
        return str(name)
    parents = "/".join(p[0] for p in parts[:-1] if p)
    return f"{parents}/{parts[-1]}" if parents else parts[-1]


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
            return "-"
        if len(value) == 1:
            return str(value[0])
        return f"{len(value)} conns"
    if value is None:
        return "-"
    return str(value)


def param_unit(param: dict | None) -> str:
    if not isinstance(param, dict):
        return ""
    metadata = param.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    for key in ("unit", "units"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def format_param_value(param: dict | None, value: Any) -> str:
    text = format_display_value(value)
    unit = param_unit(param)
    if not unit or text in ("-", ""):
        return text
    return f"{text}{unit}"


def activity_frame(ticks: int) -> str:
    return ["-", "\\", "|", "/"][ticks % 4]


class ShadowboxRenderer:
    def __init__(self, display):
        self.display = display

    @property
    def is_tall(self) -> bool:
        return getattr(self.display, "height", 32) >= 64

    @property
    def content_rows(self) -> list[int]:
        return [10, 20, 30, 40, 50] if self.is_tall else [8, 16, 24]

    def text_center(self, text: str, y: int) -> None:
        x = max(0, (self.display.width - (len(str(text)) * 6)) // 2)
        self.display.text(str(text), x, y)

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        self.display.text(shorten(title, 19), 0, 0)
        if busy:
            self.display.text(activity_frame(ticks), 120, 0)

    def list_window(self, selected_idx: int, total: int):
        rows = self.content_rows
        visible = len(rows)
        if total <= 0:
            return [], 0, rows
        selected_idx = max(0, min(selected_idx, total - 1))
        if total <= visible:
            return list(range(total)), selected_idx, rows[:total]
        half = visible // 2
        start = max(0, min(selected_idx - half, total - visible))
        indices = list(range(start, start + visible))
        return indices, selected_idx - start, rows

    def draw_menu_row(self, y: int, selected: bool, label: str) -> None:
        prefix = "> " if selected else "  "
        self.display.text((prefix + shorten(label, 19))[:21], 0, y)

    def draw_value_row(self, y: int, selected: bool, name: str, value: Any) -> None:
        prefix = "> " if selected else "  "
        left = shorten(shorten_param_name(name), 9)
        right = shorten(format_display_value(value), 9)
        self.display.text(f"{prefix}{left:<9} {right:>9}"[:21], 0, y)

    def draw_param_value_row(self, y: int, selected: bool, param: dict) -> None:
        prefix = "> " if selected else "  "
        left = shorten(shorten_param_name(param.get("name", "")), 9)
        right = shorten(format_param_value(param, param.get("value")), 9)
        self.display.text(f"{prefix}{left:<9} {right:>9}"[:21], 0, y)

    def draw_string_list(self, items: list[str], selected_idx: int) -> None:
        indices, selected_row, rows = self.list_window(selected_idx, len(items))
        for row_idx, item_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, items[item_idx])

    def draw_param_list(self, params: list[dict], selected_idx: int) -> None:
        indices, selected_row, rows = self.list_window(selected_idx, len(params) + 1)
        for row_idx, item_idx in enumerate(indices):
            if item_idx == 0:
                self.draw_menu_row(rows[row_idx], row_idx == selected_row, "..")
            else:
                param = params[item_idx - 1]
                self.draw_param_value_row(rows[row_idx], row_idx == selected_row, param)

    def draw_preset_list(self, presets: list[dict], selected_idx: int) -> None:
        self.draw_string_list([".."] + [str(item.get("name", "")) for item in presets], selected_idx)

    def draw_enum_list(self, ui, selected_idx: int) -> None:
        labels = [str(item) for item in ui.active_enum_options]
        self.draw_string_list(labels, selected_idx)

    def draw_routing_list(self, ports: list[dict], selected_idx: int) -> None:
        indices, selected_row, rows = self.list_window(selected_idx, len(ports) + 1)
        for row_idx, item_idx in enumerate(indices):
            if item_idx == 0:
                self.draw_menu_row(rows[row_idx], row_idx == selected_row, "..")
            else:
                port = ports[item_idx - 1]
                value = port.get("connections", [])
                self.draw_value_row(rows[row_idx], row_idx == selected_row, port.get("name", ""), value)

    def draw_routing_targets(self, ui, selected_idx: int) -> None:
        port = ui.selected_routing_port
        labels = ["..", "DISCONNECT"] + ui.active_routing_targets
        self.draw_string_list(labels, selected_idx)
        if port and self.is_tall:
            current = port.get("connections", [])
            current_text = "none" if not current else shorten(format_display_value(current), 18)
            self.text_center(current_text, 56)

    def _is_bool_param(self, param: dict, value: Any) -> bool:
        metadata = param.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("bool", "is_bool", "boolean"):
                meta_value = metadata.get(key)
                if isinstance(meta_value, bool):
                    return meta_value
                if isinstance(meta_value, str) and meta_value.strip().lower() in ("1", "true", "yes", "bool", "boolean"):
                    return True
        if param.get("type", "") in ("T", "F"):
            return True
        return param.get("min") == 0 and param.get("max") == 1 or isinstance(value, bool)

    def _is_enum_param(self, param: dict) -> bool:
        return isinstance(param.get("vals"), list) and len(param.get("vals")) > 0

    def _is_small_int_param(self, param: dict) -> bool:
        ptype = param.get("type", "")
        pmin = param.get("min")
        pmax = param.get("max")
        return ptype in ("i", "h", "I", "c") and pmin is not None and pmax is not None and (pmax - pmin) <= 16

    def _fill_rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        for yy in range(y, y + h):
            self.display.hline(x, yy, w, on)

    def _draw_continuous_bar(self, norm: float, x: int, y: int, w: int, h: int) -> None:
        norm = max(0.0, min(1.0, norm))
        fill_w = int(norm * (w - 2))
        self.display.rect(x, y, w, h, True, False)
        if fill_w > 0:
            self.display.rect(x + 1, y + 1, fill_w, h - 2, True, True)

    def _draw_steps(self, active_idx: int, steps: int, x: int, y: int, w: int, h: int) -> None:
        gap = 2
        step_w = max(1, (w - (gap * (steps - 1))) // steps)
        for i in range(steps):
            sx = x + i * (step_w + gap)
            self.display.rect(sx, y, step_w, h, True, i <= active_idx)

    def _draw_bool_block(self, on: bool, x: int, y: int, w: int, h: int) -> None:
        self.display.rect(x, y, w, h, True, on)

    def _draw_enum_slots(self, vals: list[Any], value: Any, x: int, y: int, w: int, h: int) -> None:
        try:
            idx = vals.index(value)
        except ValueError:
            idx = 0
        self._draw_steps(idx, len(vals), x, y, w, h)

    def _draw_choice_box(self, x: int, y: int, w: int, h: int, label: str, active: bool) -> None:
        self.display.rect(x, y, w, h, True, active)
        text_w = len(label) * 6
        tx = x + max(0, (w - text_w) // 2)
        ty = y + max(0, (h - 8) // 2)
        self.display.text(label, tx, ty)

    def draw_bool_edit(self, name: str, value: Any) -> None:
        if self.is_tall:
            self.text_center(shorten(name, 21), 4)
            box_y = 22
            box_h = 22
            box_w = 54
            self._draw_choice_box(6, box_y, box_w, box_h, "OFF", not bool(value))
            self._draw_choice_box(68, box_y, box_w, box_h, "ON", bool(value))
            self.text_center("press = commit", 54)
        else:
            self.text_center(shorten(name, 21), 0)
            self.text_center("ON" if bool(value) else "OFF", 12)
            self.display.text("< OFF   ON >", 20, 24)

    def draw_enum_edit(self, name: str, vals: list[Any], value: Any) -> None:
        try:
            idx = vals.index(value)
        except ValueError:
            idx = 0

        current = shorten(format_display_value(vals[idx]), 21)
        prev_value = shorten(format_display_value(vals[(idx - 1) % len(vals)]), 12) if vals else ""
        next_value = shorten(format_display_value(vals[(idx + 1) % len(vals)]), 12) if vals else ""
        position = f"{idx + 1}/{len(vals)}" if vals else ""

        if self.is_tall:
            self.text_center(shorten(name, 21), 2)
            self.text_center(current, 24)
            self.draw_menu_row(42, False, prev_value)
            row = f"{position:>4} {next_value}"[:21]
            self.display.text(row, 0, 52)
        else:
            self.text_center(shorten(name, 21), 0)
            self.text_center(current, 12)
            self.text_center(position, 24)

    def _draw_ttid_keyboard(self, mask: int, selected_pc: int, x: int, y: int, w: int, h: int) -> None:
        white_h = h
        black_h = max(8, int(h * 0.58))
        white_w = w // 7
        black_w = max(4, white_w // 2)
        white_pcs = [0, 2, 4, 5, 7, 9, 11]
        white_names = ["C", "D", "E", "F", "G", "A", "B"]
        black_positions = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}

        for i, pc in enumerate(white_pcs):
            wx = x + i * white_w
            ww = white_w if i < 6 else (x + w) - wx
            on = is_pc_on(mask, pc)
            kind = white_names[i]
            neck_h = black_h
            body_y = y + black_h
            body_h = white_h - black_h
            neck_w = max(3, (ww * 13) // 16)
            if kind in ("C", "F"):
                neck_x = wx
            elif kind in ("E", "B"):
                neck_x = wx + ww - neck_w
            else:
                neck_x = wx + (ww - neck_w) // 2
            if on:
                self._fill_rect(neck_x + 1, y + 1, max(0, neck_w - 2), max(0, neck_h - 1), True)
                self._fill_rect(wx + 1, body_y, max(0, ww - 2), max(0, body_h - 1), True)

        self.display.rect(x, y, w, h, True, False)
        for i in range(1, 7):
            self.display.vline(x + i * white_w, y, h, True)

        black_rects = {}
        for pc, white_index in black_positions.items():
            bx = x + ((white_index + 1) * white_w) - (black_w // 2)
            black_rects[pc] = (bx, y, black_w, black_h)
            self._fill_rect(bx, y, black_w, black_h, False)
            self.display.rect(bx, y, black_w, black_h, True, False)
            if is_pc_on(mask, pc):
                self._fill_rect(bx + 1, y + 1, black_w - 2, black_h - 2, True)

        if selected_pc < 12:
            if selected_pc in black_rects:
                bx, by, bw, _ = black_rects[selected_pc]
                self._fill_rect(bx, max(0, by - 4), bw, 3, True)
            else:
                white_index = white_pcs.index(selected_pc)
                wx = x + white_index * white_w
                self._fill_rect(wx + 2, max(0, y - 4), max(3, white_w - 4), 3, True)

    def draw_edit_ttid(self, state, param) -> None:
        title = shorten(shorten_param_name(param.get("name", "")), 21)
        mask = int(state.edit_value or 0)
        mode = state.edit_ttid_mode
        if self.is_tall:
            self.text_center(title, 2)
            if mode == "keyboard":
                self._draw_ttid_keyboard(mask, state.edit_ttid_selected_pc, 4, 16, 120, 32)
                if state.edit_ttid_selected_pc == 12:
                    self.display.rect(92, 52, 32, 10, True, False)
                    self.text_center("LOAD", 54)
                    self.display.text(str(mask), 4, 54)
                else:
                    pc = state.edit_ttid_selected_pc
                    self.display.text(note_name(pc), 4, 54)
                    self.display.text("ON" if is_pc_on(mask, pc) else "OFF", 28, 54)
                    self.display.text(str(mask), 84, 54)
            elif mode == "load_root":
                roots = get_root_names()
                self.text_center("load root", 16)
                self.text_center(roots[state.edit_ttid_load_root % 12], 32)
                self.text_center("press -> scale", 54)
            else:
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                self.text_center("load scale", 14)
                self.text_center(shorten(names[idx], 18), 30)
                self.text_center("press -> apply", 54)
        else:
            self.text_center(title, 0)
            if mode == "keyboard":
                line = "LOAD" if state.edit_ttid_selected_pc == 12 else f"{note_name(state.edit_ttid_selected_pc)} {'ON' if is_pc_on(mask, state.edit_ttid_selected_pc) else 'OFF'}"
                self.text_center(line, 12)
                self.text_center(str(mask), 24)
            elif mode == "load_root":
                self.text_center("root", 12)
                self.text_center(get_root_names()[state.edit_ttid_load_root % 12], 24)
            else:
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                self.text_center(shorten(names[idx], 21), 18)

    def draw_edit_step16(self, ui, param, state) -> None:
        title = shorten(shorten_param_name(param.get("name", "")), 21)
        cells = build_cells(int(state.edit_value or 0), state.edit_step16_focus, ui.active_step16_playhead)

        if self.is_tall:
            self.text_center(title, 2)
            origin_x = 8
            origin_y = 16
            cell_w = 12
            cell_h = 16
            gap = 3
            text_y = 54
        else:
            self.text_center(title, 0)
            origin_x = 8
            origin_y = 10
            cell_w = 11
            cell_h = 8
            gap = 3
            text_y = 24

        for cell in cells:
            col = cell.index % 8
            row = cell.index // 8
            x = origin_x + col * (cell_w + gap)
            y = origin_y + row * (cell_h + gap)

            self.display.rect(x, y, cell_w, cell_h, True, cell.active)

            if cell.playing:
                self.display.rect(max(0, x - 1), max(0, y - 1), cell_w + 2, cell_h + 2, True, False)

            if cell.focused:
                fx = x + 2
                fy = y + 2
                fw = max(1, cell_w - 4)
                self._fill_rect(fx, fy, fw, 2, not cell.active)

        focus_label = f"{state.edit_step16_focus + 1:02d}"
        playhead = ui.active_step16_playhead
        play_label = "--" if playhead is None else f"{playhead + 1:02d}"
        self.text_center(f"F{focus_label} P{play_label} {int(state.edit_value or 0)}", text_y)

    def draw_edit(self, ui, selected_param: dict, state) -> None:
        if selected_param is None:
            self.text_center("no param", 16)
            return
        if is_ttid_param(selected_param):
            self.draw_edit_ttid(state, selected_param)
            return
        if is_step16_param(selected_param):
            self.draw_edit_step16(ui, selected_param, state)
            return

        title_y, gfx_x, gfx_y, gfx_w, gfx_h, value_y = (4, 4, 20, 120, 24, 52) if self.is_tall else (0, 4, 12, 120, 12, 26)
        name = shorten_param_name(selected_param.get("name", ""))
        value = state.edit_value
        self.text_center(shorten(name, 21), title_y)

        vals = selected_param.get("vals")
        pmin = selected_param.get("min")
        pmax = selected_param.get("max")

        if self._is_bool_param(selected_param, value):
            self.draw_bool_edit(name, value)
        elif self._is_enum_param(selected_param):
            self.draw_enum_edit(name, vals, value)
        elif self._is_small_int_param(selected_param):
            active_idx = int(round(value - pmin)) if isinstance(value, (int, float)) and pmin is not None else 0
            self._draw_steps(active_idx, int(pmax - pmin) + 1, gfx_x, gfx_y, gfx_w, gfx_h)
            self.text_center(shorten(format_param_value(selected_param, value), 21), value_y)
        else:
            norm = 0.0
            if isinstance(value, (int, float)) and pmin is not None and pmax is not None and (pmax - pmin) > 0:
                norm = (value - pmin) / (pmax - pmin)
            self._draw_continuous_bar(norm, gfx_x, gfx_y, gfx_w, gfx_h)
            self.text_center(shorten(format_param_value(selected_param, value), 21), value_y)

    def draw_splash(self, title: str = "SHADOWBOX") -> None:
        self.display.clear()
        self.text_center(title, 28 if self.is_tall else 12)
        self.display.show()

    def draw_status(self, ui) -> None:
        rows = self.content_rows
        self.draw_value_row(rows[0], False, "inst", len(ui.state.instances))
        self.draw_value_row(rows[1], False, "cpu", "-" if ui.state.system.get("status", {}).get("cpu_load") is None else f"{ui.state.system['status']['cpu_load']:.1f}")
        self.draw_value_row(rows[2], False, "xruns", ui.state.system.get("status", {}).get("xruns", "-"))
        if self.is_tall:
            self.draw_value_row(rows[3], False, "rnbo", ui.state.system.get("status", {}).get("runner_version", "-"))

    def draw_system_audio(self, ui) -> None:
        self.draw_string_list([".."] + SYSTEM_AUDIO_ITEMS, ui.state.system_audio_cursor)

    def draw_system_audio_device(self, ui) -> None:
        self.draw_string_list([".."] + [str(item) for item in ui.audio_options], ui.state.audio_device_cursor)

    def draw_system_audio_rate(self, ui) -> None:
        self.draw_string_list([".."] + [str(item) for item in ui.sample_rate_options], ui.state.sample_rate_cursor)

    def draw_system_audio_buffer(self, ui) -> None:
        self.draw_string_list([".."] + [str(item) for item in ui.buffer_size_options], ui.state.buffer_size_cursor)

    def draw_network(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("1.1.1.1", 80))
            ip = sock.getsockname()[0]
            sock.close()
        except Exception:
            ip = "?"
        rows = self.content_rows
        self.draw_value_row(rows[0], False, "ip", ip)
        self.draw_value_row(rows[1], False, "osc", RNBO_PORT)

    def draw_startup(self, ui) -> None:
        rows = self.content_rows
        self.draw_value_row(rows[1], False, "startup", "ON" if ui.state.startup_enabled else "OFF")
        if self.is_tall:
            self.text_center("press = toggle", 56)

    def draw_maint(self) -> None:
        if self.is_tall:
            self.text_center("jack restart", 20)
            self.text_center("press to run", 40)
        else:
            self.display.text("jack restart", 0, 10)
            self.display.text("short press", 0, 22)

    def draw(self, ui) -> None:
        state = ui.state
        self.display.clear()

        if state.ui_mode == "EDIT":
            self.draw_edit(ui, ui.selected_param, state)
            self.display.show()
            return

        header = {
            "TOP": "TOP",
            "INSTANCE_LIST": "INSTANCES",
            "PATCHER_PICKER": "ADD INSTANCE" if state.patcher_picker_context == "add" else "REPLACE",
            "INSTANCE_MENU": ui.active_instance.get("label", "INSTANCE") if ui.active_instance else "INSTANCE",
            "REMOVE_INSTANCE_PICKER": "REMOVE",
            "REMOVE_INSTANCE_CONFIRM": "REMOVE",
            "PRESET_LIST": "PRESETS",
            "PARAM_LIST": "PARAMETERS",
            "ENUM_LIST": shorten(shorten_param_name(ui.selected_param.get("name", "")), 19) if ui.selected_param else "ENUM",
            "ROUTING_GROUP": state.active_transport.upper(),
            "ROUTING_PORTS": f"{state.active_transport[:1].upper()}{state.active_transport[1:]} {state.active_routing_direction[:1].upper()}{state.active_routing_direction[1:]}",
            "ROUTING_TARGETS": ui.selected_routing_port.get("name", "TARGET") if ui.selected_routing_port else "TARGET",
            "SYSTEM_MENU": "SYSTEM",
            "SYSTEM_AUDIO": "AUDIO",
            "SYSTEM_AUDIO_DEVICE": "DEVICE",
            "SYSTEM_AUDIO_RATE": "RATE",
            "SYSTEM_AUDIO_BUFFER": "BUFFER",
            "STATUS": "STATUS",
            "NETWORK": "NETWORK",
            "STARTUP": "STARTUP",
            "MAINT": "MAINT",
        }.get(state.ui_mode, state.ui_mode)
        self.draw_header(header, busy=state.busy, ticks=state.activity_ticks)

        if state.ui_mode == "TOP":
            self.draw_string_list(ui.top_level_items, state.top_index)
        elif state.ui_mode == "INSTANCE_LIST":
            items = [".."] + [str(item.get("label", "")) for item in state.instances]
            if ui.can_add_instance:
                items.append("ADD INSTANCE")
            if ui.can_remove_instances:
                items.append("REMOVE INSTANCE")
            self.draw_string_list(items, state.instance_cursor)
        elif state.ui_mode == "REMOVE_INSTANCE_PICKER":
            self.draw_string_list([".."] + [str(item.get("label", "")) for item in state.instances], state.remove_instance_picker_cursor)
        elif state.ui_mode == "PATCHER_PICKER":
            self.draw_string_list([".."] + state.patchers, state.patcher_cursor)
        elif state.ui_mode == "INSTANCE_MENU":
            self.draw_string_list([".."] + ui.instance_menu_items, state.instance_menu_cursor)
        elif state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self.draw_string_list(REMOVE_INSTANCE_CONFIRM_ITEMS, state.remove_instance_confirm_cursor)
        elif state.ui_mode == "PRESET_LIST":
            self.draw_preset_list(ui.active_presets, state.preset_cursor) if ui.active_presets else self.draw_string_list(["..", "no presets"], state.preset_cursor)
        elif state.ui_mode == "PARAM_LIST":
            self.draw_param_list(ui.active_params, state.param_cursor) if ui.active_params else self.draw_string_list(["..", "no params"], state.param_cursor)
        elif state.ui_mode == "ENUM_LIST":
            self.draw_enum_list(ui, state.enum_cursor)
        elif state.ui_mode == "ROUTING_GROUP":
            self.draw_string_list([".."] + ROUTING_GROUP_ITEMS, state.routing_group_cursor)
        elif state.ui_mode == "ROUTING_PORTS":
            self.draw_routing_list(ui.active_routing_ports, state.routing_port_cursor) if ui.active_routing_ports else self.draw_string_list(["..", "no ports"], state.routing_port_cursor)
        elif state.ui_mode == "ROUTING_TARGETS":
            self.draw_routing_targets(ui, state.routing_target_cursor)
        elif state.ui_mode == "SYSTEM_MENU":
            self.draw_string_list([".."] + SYSTEM_MENU_ITEMS, state.system_cursor)
        elif state.ui_mode == "STATUS":
            self.draw_status(ui)
        elif state.ui_mode == "SYSTEM_AUDIO":
            self.draw_system_audio(ui)
        elif state.ui_mode == "SYSTEM_AUDIO_DEVICE":
            self.draw_system_audio_device(ui)
        elif state.ui_mode == "SYSTEM_AUDIO_RATE":
            self.draw_system_audio_rate(ui)
        elif state.ui_mode == "SYSTEM_AUDIO_BUFFER":
            self.draw_system_audio_buffer(ui)
        elif state.ui_mode == "NETWORK":
            self.draw_network()
        elif state.ui_mode == "STARTUP":
            self.draw_startup(ui)
        elif state.ui_mode == "MAINT":
            self.draw_maint()

        self.display.show()
