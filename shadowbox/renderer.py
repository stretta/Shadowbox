#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner
"""

from __future__ import annotations

import socket
from typing import Any

from shadowbox.editors.pitch_display import is_pitch_display_param, normalize_pitch_to_midi_note
from shadowbox.editors.step16 import build_cells, is_step16_param
from shadowbox.editors.ttid import get_root_names, is_pc_on, is_ttid_param, note_name
from shadowbox.rnbo import RNBO_PORT
from shadowbox.ui import (
    REMOVE_INSTANCE_CONFIRM_ITEMS,
    ROUTING_GROUP_ITEMS,
    SYSTEM_AUDIO_ITEMS,
    display_as_int,
    display_precision,
    edit_as_int,
)
from shadowbox.version import SHADOWBOX_BUILD_INFO, SHADOWBOX_VERSION


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


def format_display_value(value: Any, precision: int | None = None, integer_style: bool = False) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if integer_style:
            return str(int(round(value)))
        if precision is not None:
            return f"{value:.{precision}f}"
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
    text = format_display_value(
        value,
        precision=display_precision(param),
        integer_style=display_as_int(param),
    )
    unit = param_unit(param)
    if not unit or text in ("-", ""):
        return text
    return f"{text}{unit}"


def activity_frame(ticks: int) -> str:
    return ["-", "\\", "|", "/"][ticks % 4]


class ShadowboxRenderer:
    def __init__(self, display):
        self.display = display

    def _text(self, text: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        self.display.text_with_style(str(text), x, y, scale, weight, on=on)

    def _measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return self.display.measure_text(str(text), scale, weight)

    def _line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return self.display.line_height(scale, weight)

    def _truncate_to_width(self, text: str, max_width: int, scale: int = 1, weight: str = "regular") -> str:
        text = str(text)
        if max_width <= 0:
            return ""
        if self._measure_text(text, scale, weight)[0] <= max_width:
            return text
        ellipsis = "..."
        if self._measure_text(ellipsis, scale, weight)[0] > max_width:
            return ""
        truncated = text
        while truncated:
            truncated = truncated[:-1]
            candidate = truncated + ellipsis
            if self._measure_text(candidate, scale, weight)[0] <= max_width:
                return candidate
        return ellipsis

    def _draw_right_aligned(self, text: str, right_x: int, y: int, scale: int = 1, weight: str = "regular") -> None:
        text_w, _ = self._measure_text(text, scale, weight)
        self._text(text, max(0, right_x - text_w), y, scale, weight)

    def _current_row_weight(self, base_weight: str | None = None, current: bool = False) -> str:
        weight = base_weight or "regular"
        if not current:
            return weight
        upgrades = {
            "thin": "regular",
            "thin-italic": "italic",
            "regular": "medium",
            "italic": "medium-italic",
            "medium": "semibold",
            "medium-italic": "semibold-italic",
            "semibold": "bold",
            "semibold-italic": "bold-italic",
            "bold": "bold",
            "bold-italic": "bold-italic",
        }
        return upgrades.get(weight, "medium")

    def _oled_row_prefix(self, selected: bool, current: bool) -> str:
        return f"{'*' if current else ' '}{'>' if selected else ' '}"

    def _draw_full_tft_row(
        self,
        y: int,
        prefix: str,
        left: str,
        right: str = "",
        selected: bool = False,
        text_weight: str | None = None,
    ) -> None:
        left_x = self.full_tft_text_x
        right_x = self.display.width - self.full_tft_right_padding
        text_weight = text_weight or "regular"
        prefix_text = f"{prefix} "
        prefix_w, _ = self._measure_text(prefix_text, 2, text_weight)
        right_text = str(right)
        right_w = self._measure_text(right_text, 2, "medium")[0] if right_text else 0
        gap = 12 if right_text else 0
        available_left = max(0, right_x - left_x - prefix_w - right_w - gap)
        left_text = self._truncate_to_width(left, available_left, 2, text_weight)
        self._text(prefix_text, left_x, y, 2, text_weight)
        self._text(left_text, left_x + prefix_w, y, 2, text_weight)
        if right_text:
            fitted_right = self._truncate_to_width(right_text, max(0, right_x - left_x - prefix_w - gap), 2, "medium")
            self._draw_right_aligned(fitted_right, right_x, y, 2, "medium")

    @property
    def full_tft_text_x(self) -> int:
        return 8

    @property
    def full_tft_right_padding(self) -> int:
        return 8

    @property
    def layout_mode(self) -> str:
        width = getattr(self.display, "width", 128)
        height = getattr(self.display, "height", 32)
        if width >= 320 and height >= 240:
            return "tft_full"
        if width >= 160 or height >= 96:
            return "tft"
        return "oled"

    @property
    def is_tft(self) -> bool:
        return self.layout_mode in {"tft", "tft_full"}

    @property
    def is_full_tft(self) -> bool:
        return self.layout_mode == "tft_full"

    @property
    def is_tall(self) -> bool:
        return getattr(self.display, "height", 32) >= 64

    @property
    def header_height(self) -> int:
        if self.is_full_tft:
            return self._line_height(2, "semibold") + 8
        if self.is_tft:
            return 10
        return 8

    @property
    def content_top(self) -> int:
        return self.header_height + (4 if self.is_full_tft else 2 if self.is_tft else 0)

    @property
    def content_bottom(self) -> int:
        return max(self.content_top, self.display.height - (10 if self.is_full_tft else 8 if self.is_tft else 0))

    @property
    def content_rows(self) -> list[int]:
        if self.is_full_tft:
            rows = list(range(self.content_top + 8, self.content_bottom, self._line_height(2) + 4))
            return rows or [self.content_top + 4]
        if self.is_tft:
            return [12, 22, 32, 42, 52, 62, 72, 82, 92, 102, 112]
        return [10, 20, 30, 40, 50] if self.is_tall else [8, 16, 24]

    @property
    def text_cols(self) -> int:
        if self.is_full_tft:
            usable_width = max(
                0,
                getattr(self.display, "width", 320) - self.full_tft_text_x - self.full_tft_right_padding,
            )
            sample_w, _ = self._measure_text("abcdefghijklmnopqrstuvwxyz", 2, "regular")
            avg_char_w = max(1, sample_w // 26)
            return max(8, usable_width // avg_char_w)
        return max(8, getattr(self.display, "width", 128) // 6)

    @property
    def header_cols(self) -> int:
        return max(8, self.text_cols - 2)

    @property
    def title_cols(self) -> int:
        return max(8, self.text_cols - 1)

    @property
    def value_name_cols(self) -> int:
        if self.is_full_tft:
            return 30
        return 13 if self.is_tft else 9

    @property
    def value_cols(self) -> int:
        if self.is_full_tft:
            return 18
        return 11 if self.is_tft else 9

    @property
    def value_row_cols(self) -> int:
        return max(12, self.text_cols - 2)

    def text_center(self, text: str, y: int) -> None:
        if self.is_full_tft:
            self.text_center_scaled(text, y, 2)
            return
        text = str(text)
        weight = "regular"
        x = max(0, (self.display.width - self._measure_text(text, 1, weight)[0]) // 2)
        self._text(text, x, y, 1, weight)

    def text_center_scaled(self, text: str, y: int, scale: int = 1) -> None:
        text = str(text)
        scale = max(1, int(scale))
        weight = "medium" if self.is_full_tft and scale >= 2 else "regular"
        x = max(0, (self.display.width - self._measure_text(text, scale, weight)[0]) // 2)
        self._text(text, x, y, scale, weight)

    def _draw_centered_segments(self, segments: list[tuple[str, int, str]], y: int) -> None:
        visible_segments = [(str(text), max(1, int(scale)), weight) for text, scale, weight in segments if str(text)]
        if not visible_segments:
            return
        total_w = sum(self._measure_text(text, scale, weight)[0] for text, scale, weight in visible_segments)
        x = max(0, (self.display.width - total_w) // 2)
        for text, scale, weight in visible_segments:
            self._text(text, x, y, scale, weight)
            x += self._measure_text(text, scale, weight)[0]

    def _measure_shadowbox_logo(self, scale: int) -> tuple[int, int, int]:
        left_w, left_h = self._measure_text("SHADOW", scale, "thin")
        right_w, right_h = self._measure_text("BOX", scale, "bold")
        return left_w + right_w, max(left_h, right_h), left_w

    def _draw_shadowbox_logo(self, y: int, scale: int) -> int:
        total_w, text_h, left_w = self._measure_shadowbox_logo(scale)
        x = max(0, (self.display.width - total_w) // 2)
        self._text("SHADOW", x, y, scale, "thin")
        self._text("BOX", x + left_w, y, scale, "bold")
        return text_h

    def edit_header_title(self, param: dict | None) -> str:
        if not param:
            return "EDIT"
        return shorten(shorten_param_name(param.get("name", "")), 19 if self.is_full_tft else self.header_cols)

    def edit_content_top(self, block_height: int) -> int:
        available_top = self.content_top
        available_height = max(0, self.display.height - available_top)
        return max(available_top, available_top + ((available_height - block_height) // 2))

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        self._text(shorten(title, self.header_cols), 0, 0)
        if busy:
            self._text(activity_frame(ticks), max(0, self.display.width - 8), 0)

    def _draw_panel(self, x: int, y: int, w: int, h: int, title: str | None = None) -> None:
        if self.is_full_tft:
            if title:
                self._text(self._truncate_to_width(title, max(0, w - 8), 2, "semibold"), x + 4, y + 2, 2, "semibold")
            return
        self.display.rect(x, y, w, h, True, False)
        if title:
            self._text(shorten(title, max(1, (w // 6) - 2)), x + 4, y + 2)
            self.display.hline(x + 1, y + (12 if self.is_full_tft else 10), max(0, w - 2), True)

    def _draw_text_block(self, x: int, y: int, lines: list[str], max_chars: int | None = None, line_step: int = 12) -> None:
        width_chars = max_chars if max_chars is not None else max(1, (self.display.width - x) // 6)
        for idx, line in enumerate(lines):
            if self.is_full_tft:
                self._text(self._truncate_to_width(line, self.display.width - x - self.full_tft_right_padding, 2), x, y + idx * line_step, 2)
            else:
                self._text(shorten(line, width_chars), x, y + idx * line_step)

    def _draw_info_rows(self, rows: list[tuple[str, Any]], top_padding: int = 8) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
        if self.is_full_tft:
            y_positions = self._panel_list_rows(panel_y, panel_h)
            for idx, (label, value) in enumerate(rows[: len(y_positions)]):
                self._draw_full_tft_row(y_positions[idx], " ", str(label), format_display_value(value))
            return
        left_x = 8
        right_x = self.display.width - 8
        y_positions = self._panel_list_rows(panel_y, panel_h)
        line_rows = rows[: len(y_positions)]
        if not line_rows:
            return
        label_width = max(self._measure_text(str(label).lower())[0] for label, _ in line_rows)
        value_x = min(right_x - 24, left_x + label_width + 12)
        for idx, (label, value) in enumerate(line_rows):
            y = max(panel_y + top_padding, y_positions[idx])
            label_text = str(label).lower()
            value_text = format_display_value(value)
            self._text(label_text, left_x, y)
            fitted_value = self._truncate_to_width(value_text, max(0, right_x - value_x), 1, "regular")
            self._draw_right_aligned(fitted_value, right_x, y)

    def _content_panel_box(self) -> tuple[int, int, int, int]:
        x = 0
        y = self.content_top
        w = self.display.width
        h = max(0, self.display.height - y)
        return x, y, w, h

    def _panel_list_rows(self, panel_y: int, panel_h: int) -> list[int]:
        if self.is_full_tft:
            start = panel_y + 8
            end = panel_y + max(8, panel_h - 20)
            rows = list(range(start, end, self._line_height(2) + 4))
            return rows or [start]
        return [14, 22, 30, 38, 46, 54, 62, 70, 78, 86, 94, 102, 110]

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
        current = False
        prefix = self._oled_row_prefix(selected, current)
        text = (prefix + shorten(label, self.value_row_cols))[: self.text_cols]
        if self.is_full_tft:
            self._draw_full_tft_row(y, ">" if selected else " ", label, selected=selected)
            return
        self._text(text, 0, y)

    def draw_current_menu_row(self, y: int, selected: bool, current: bool, label: str, text_weight: str | None = None) -> None:
        prefix = self._oled_row_prefix(selected, current)
        text = (prefix + shorten(label, self.value_row_cols))[: self.text_cols]
        weight = self._current_row_weight(text_weight, current)
        if self.is_full_tft:
            self._draw_full_tft_row(y, ">" if selected else " ", label, selected=selected, text_weight=weight)
            return
        if self.is_tft and selected:
            self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
        x = 6 if self.is_tft else 0
        self._text(text if not self.is_tft else f"{'>' if selected else ' '} {shorten(label, 50)}"[: self.text_cols], x, y, weight=weight)

    def draw_value_row(self, y: int, selected: bool, name: str, value: Any, current: bool = False) -> None:
        prefix = self._oled_row_prefix(selected, current)
        left = shorten(shorten_param_name(name), self.value_name_cols)
        right = shorten(format_display_value(value), self.value_cols)
        row = f"{prefix}{left:<{self.value_name_cols}} {right:>{self.value_cols}}"
        left_weight = self._current_row_weight(current=current)
        if self.is_full_tft:
            self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected, text_weight=left_weight)
            return
        self._text(row[: self.text_cols], 0, y, weight=left_weight)

    def draw_param_value_row(self, y: int, selected: bool, param: dict, current: bool = False) -> None:
        prefix = self._oled_row_prefix(selected, current)
        left = shorten(shorten_param_name(param.get("name", "")), self.value_name_cols)
        right = shorten(format_param_value(param, param.get("value")), self.value_cols)
        row = f"{prefix}{left:<{self.value_name_cols}} {right:>{self.value_cols}}"
        left_weight = self._current_row_weight(current=current)
        if self.is_full_tft:
            self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected, text_weight=left_weight)
            return
        self._text(row[: self.text_cols], 0, y, weight=left_weight)

    def draw_string_list(
        self,
        items: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        if self.is_tft:
            self._draw_string_list_tft(items, selected_idx, current_indices=current_indices, item_weights=item_weights)
            return
        indices, selected_row, rows = self.list_window(selected_idx, len(items))
        for row_idx, item_idx in enumerate(indices):
            self.draw_current_menu_row(
                rows[row_idx],
                row_idx == selected_row,
                item_idx in (current_indices or set()),
                items[item_idx],
                text_weight=(item_weights or {}).get(item_idx),
            )

    def _draw_string_list_tft(
        self,
        items: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        visible = len(rows)
        total = len(items)
        if total <= 0:
            return
        selected_idx = max(0, min(selected_idx, total - 1))
        if total <= visible:
            indices = list(range(total))
            selected_row = selected_idx
        else:
            half = visible // 2
            start = max(0, min(selected_idx - half, total - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_idx - start

        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row
            if selected and not self.is_full_tft:
                self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
            current = item_idx in (current_indices or set())
            prefix = ">" if selected else " "
            line_limit = self.text_cols - 3 if self.is_full_tft else 50
            weight = self._current_row_weight((item_weights or {}).get(item_idx), current=current)
            if self.is_full_tft:
                self._draw_full_tft_row(y, prefix, shorten(str(items[item_idx]), line_limit), selected=selected, text_weight=weight)
            else:
                self._text(f"{prefix} {shorten(str(items[item_idx]), line_limit)}"[: self.text_cols], 6, y, weight=weight)

    def draw_param_list(self, params: list[dict], selected_idx: int) -> None:
        if self.is_tft:
            self._draw_param_list_tft(params, selected_idx)
            return
        indices, selected_row, rows = self.list_window(selected_idx, len(params) + 1)
        for row_idx, item_idx in enumerate(indices):
            if item_idx == 0:
                self.draw_menu_row(rows[row_idx], row_idx == selected_row, "..")
            else:
                param = params[item_idx - 1]
                self.draw_param_value_row(rows[row_idx], row_idx == selected_row, param)

    def _tft_value_columns(self) -> tuple[int, int]:
        if self.is_full_tft:
            right_cols = 8
            left_cols = max(8, self.text_cols - right_cols - 3)
            return left_cols, right_cols
        right_cols = max(6, min(12, (self.text_cols - 4) // 3))
        left_cols = max(8, self.text_cols - right_cols - 3)
        return left_cols, right_cols

    def _draw_param_list_tft(self, params: list[dict], selected_idx: int) -> None:
        items = [None] + list(params)
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        visible = len(rows)
        total = len(items)
        selected_idx = max(0, min(selected_idx, total - 1))
        if total <= visible:
            indices = list(range(total))
            selected_row = selected_idx
        else:
            half = visible // 2
            start = max(0, min(selected_idx - half, total - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_idx - start

        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row
            if item_idx == 0:
                if selected and not self.is_full_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
                if self.is_full_tft:
                    self._draw_full_tft_row(y, ">" if selected else " ", "..", selected=selected)
                else:
                    self._text(("> " if selected else "  ") + "..", 6, y)
            else:
                param = items[item_idx]
                prefix = "> " if selected else "  "
                if selected and not self.is_full_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
                left_cols, right_cols = self._tft_value_columns()
                left = shorten(shorten_param_name(param.get("name", "")), left_cols)
                right = shorten(format_param_value(param, param.get("value")), right_cols)
                row = f"{prefix}{left:<{left_cols}} {right:>{right_cols}}"[: self.text_cols]
                if self.is_full_tft:
                    self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected)
                else:
                    self._text(row, 6, y)

    def draw_preset_list(self, ui, presets: list[dict], selected_idx: int) -> None:
        current_indices = {
            idx + 1 for idx, item in enumerate(presets) if str(item.get("name", "")) == ui.current_preset_name
        }
        self.draw_string_list([".."] + [str(item.get("name", "")) for item in presets], selected_idx, current_indices=current_indices)

    def draw_instance_list(self, ui) -> None:
        items = [".."] + [str(item.get("label", "")) for item in ui.state.instances]
        action_start = len(items)
        if ui.can_add_instance:
            items.append("ADD INSTANCE")
        if ui.can_remove_instances:
            items.append("REMOVE INSTANCE")
        if self.is_tft:
            self._draw_instance_list_tft(items, ui.state.instance_cursor, action_start)
            return
        self.draw_string_list(items, ui.state.instance_cursor)

    def _draw_instance_list_tft(self, items: list[str], selected_idx: int, action_start: int) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        visible = len(rows)
        total = len(items)
        if total <= 0:
            return
        selected_idx = max(0, min(selected_idx, total - 1))
        if total <= visible:
            indices = list(range(total))
            selected_row = selected_idx
        else:
            half = visible // 2
            start = max(0, min(selected_idx - half, total - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_idx - start

        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row
            label = str(items[item_idx])
            prefix = ">" if selected else " "
            text_weight = "semibold" if item_idx >= action_start else None
            if self.is_full_tft:
                self._draw_full_tft_row(y, prefix, label, selected=selected, text_weight=text_weight)
            else:
                if selected:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                self._text(f"{prefix} {shorten(label, 50)}"[: self.text_cols], 6, y, weight=text_weight or "regular")

    def draw_enum_list(self, ui, selected_idx: int) -> None:
        labels = [str(item) for item in ui.active_enum_options]
        current_indices = {
            idx for idx, item in enumerate(ui.active_enum_options) if item == ui.current_enum_value
        }
        self.draw_string_list(labels, selected_idx, current_indices=current_indices)

    def draw_routing_list(self, ports: list[dict], selected_idx: int) -> None:
        if self.is_tft:
            self._draw_routing_list_tft(ports, selected_idx)
            return
        indices, selected_row, rows = self.list_window(selected_idx, len(ports) + 1)
        for row_idx, item_idx in enumerate(indices):
            if item_idx == 0:
                self.draw_menu_row(rows[row_idx], row_idx == selected_row, "..")
            else:
                port = ports[item_idx - 1]
                value = port.get("connections", [])
                self.draw_value_row(rows[row_idx], row_idx == selected_row, port.get("name", ""), value)

    def _draw_routing_list_tft(self, ports: list[dict], selected_idx: int) -> None:
        items = [None] + list(ports)
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        visible = len(rows)
        total = len(items)
        selected_idx = max(0, min(selected_idx, total - 1)) if total else 0
        if total <= visible:
            indices = list(range(total))
            selected_row = selected_idx
        else:
            half = visible // 2
            start = max(0, min(selected_idx - half, total - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_idx - start

        left_cols, right_cols = self._tft_value_columns()
        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row
            if item_idx == 0:
                if selected and not self.is_full_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                if self.is_full_tft:
                    self._draw_full_tft_row(y, ">" if selected else " ", "..", selected=selected)
                else:
                    self._text(("> " if selected else "  ") + "..", 6, y)
                continue

            port = items[item_idx]
            left = shorten(shorten_param_name(port.get("name", "")), left_cols)
            right = shorten(format_display_value(port.get("connections", [])), right_cols)
            if self.is_full_tft:
                self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected)
            else:
                if selected:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                row = f"{'> ' if selected else '  '}{left:<{left_cols}} {right:>{right_cols}}"[: self.text_cols]
                self._text(row, 6, y)

    def draw_routing_targets(self, ui, selected_idx: int) -> None:
        port = ui.selected_routing_port
        labels = ["..", "DISCONNECT"] + ui.active_routing_targets
        current_indices = {1} if not ui.current_routing_targets else {
            idx + 2 for idx, item in enumerate(ui.active_routing_targets) if item in ui.current_routing_targets
        }
        item_weights = {
            idx + 2: "italic"
            for idx, item in enumerate(ui.active_routing_targets)
            if item in ui.used_routing_targets
        }
        if self.is_tft:
            self._draw_routing_targets_tft(
                port,
                labels,
                selected_idx,
                current_indices=current_indices,
                item_weights=item_weights,
            )
            return
        self.draw_string_list(labels, selected_idx, current_indices=current_indices, item_weights=item_weights)
        if port and self.is_tall:
            current = port.get("connections", [])
            current_text = "none" if not current else shorten(format_display_value(current), self.title_cols)
            self.text_center(current_text, self.content_rows[-1] + 2 if self.is_tft else 56)

    def _draw_routing_targets_tft(
        self,
        port: dict | None,
        labels: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        if rows:
            rows = rows[:-1] or rows
        visible = len(rows)
        total = len(labels)
        if total > 0 and visible > 0:
            selected_idx = max(0, min(selected_idx, total - 1))
            if total <= visible:
                indices = list(range(total))
                selected_row = selected_idx
            else:
                half = visible // 2
                start = max(0, min(selected_idx - half, total - visible))
                indices = list(range(start, start + visible))
                selected_row = selected_idx - start

            for row_idx, item_idx in enumerate(indices):
                y = rows[row_idx]
                selected = row_idx == selected_row
                if selected and not self.is_full_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                current = item_idx in (current_indices or set())
                prefix = ">" if selected else " "
                line_limit = self.text_cols - 3 if self.is_full_tft else 50
                weight = self._current_row_weight((item_weights or {}).get(item_idx), current=current)
                if self.is_full_tft:
                    self._draw_full_tft_row(y, prefix, shorten(str(labels[item_idx]), line_limit), selected=selected, text_weight=weight)
                else:
                    self._text(f"{prefix} {shorten(str(labels[item_idx]), line_limit)}"[: self.text_cols], 6, y, weight=weight)

        if not port:
            return
        current = port.get("connections", [])
        current_text = "CURRENT: none" if not current else f"CURRENT: {format_display_value(current)}"
        if self.is_full_tft:
            fitted = self._truncate_to_width(current_text, self.display.width - 16, 1, "regular")
            self._text(fitted, 8, self.display.height - 12, 1, "regular")
        else:
            self._text(shorten(current_text, self.text_cols - 2), 8, self.display.height - 8)

    def _draw_edit_caption(self, text: str, y: int) -> None:
        if not self.is_tft:
            return
        if self.is_full_tft:
            self.text_center_scaled(text, y, 1)
        else:
            self.text_center(text, y)

    def _is_bool_param(self, param: dict, value: Any) -> bool:
        metadata = param.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("bool", "is_bool", "boolean"):
                meta_value = metadata.get(key)
                if isinstance(meta_value, bool):
                    return meta_value
                if isinstance(meta_value, str) and meta_value.strip().lower() in ("1", "true", "yes", "bool", "boolean"):
                    return True
        return False

    def _is_enum_param(self, param: dict) -> bool:
        return isinstance(param.get("vals"), list) and len(param.get("vals")) > 0

    def _is_small_int_param(self, param: dict) -> bool:
        pmin = param.get("min")
        pmax = param.get("max")
        return (
            edit_as_int(param)
            and pmin is not None
            and pmax is not None
            and (pmax - pmin) <= 16
        )

    def _fill_rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        for yy in range(y, y + h):
            self.display.hline(x, yy, w, on)

    def _parse_float(self, value: Any) -> float | None:
        if value in (None, "", "-"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _clamp(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _midi_note_name(self, midi_note: int) -> str:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        note = int(midi_note)
        return f"{names[note % 12]}{(note // 12) - 1}"

    def _pitch_display_segments(self, pitch_value: Any, scale: int) -> list[tuple[str, int, str]]:
        midi_note = normalize_pitch_to_midi_note(pitch_value)
        if midi_note is None:
            fallback = shorten(format_display_value(pitch_value), 10)
            return [(fallback if fallback not in ("", "-") else "--", scale, "medium")]

        left_weight = "regular"
        right_weight = "semibold" if self.is_full_tft else "medium"
        return [
            (str(midi_note), scale, left_weight),
            (" ", scale, left_weight),
            (self._midi_note_name(midi_note), scale, right_weight),
        ]

    def _draw_pitch_meter(
        self,
        cents_value: float | None,
        x: int,
        y: int,
        w: int,
        h: int,
        max_cents: float = 50.0,
        in_tune_cents: float = 3.0,
    ) -> None:
        if w <= 8 or h <= 3:
            return

        mid_x = x + (w // 2)
        line_y = y + (h // 2)
        usable_half = max(1, (w // 2) - 3)
        zone_half_w = max(2, int(round((in_tune_cents / max_cents) * usable_half)))

        self.display.hline(x, line_y, w, True)

        tick_h = max(3, h - 2)
        center_tick_h = h
        for fraction in (0.25, 0.5, 0.75):
            tick_x = x + int(round((w - 1) * fraction))
            current_h = center_tick_h if abs(fraction - 0.5) < 1e-6 else tick_h
            self.display.vline(tick_x, y + max(0, (h - current_h) // 2), current_h, True)

        zone_h = max(3, h - 4)
        zone_y = y + max(0, (h - zone_h) // 2)
        self.display.rect(mid_x - zone_half_w, zone_y, (zone_half_w * 2) + 1, zone_h, True, False)
        self.display.vline(mid_x, y, h, True)

        if cents_value is None:
            marker_w = 6 if self.is_full_tft else 4
            marker_h = max(3, h - 2)
            self.display.rect(mid_x - (marker_w // 2), y + max(0, (h - marker_h) // 2), marker_w, marker_h, True, False)
            return

        normalized = self._clamp(cents_value / max_cents, -1.0, 1.0)
        marker_x = mid_x + int(round(normalized * usable_half))
        is_in_tune = abs(cents_value) <= in_tune_cents
        marker_w = 8 if self.is_full_tft and is_in_tune else 6 if self.is_full_tft else 5 if is_in_tune else 4 if self.is_tft else 4 if is_in_tune else 3
        marker_h = max(3, h - 2)
        marker_left = int(self._clamp(marker_x - (marker_w // 2), x, x + w - marker_w))
        self.display.rect(
            marker_left,
            y + max(0, (h - marker_h) // 2),
            marker_w,
            marker_h,
            True,
            is_in_tune,
        )

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
        if self.is_full_tft:
            prefix = "> " if active else "  "
            self._text(prefix + label, x, y, 2, "medium" if active else "regular")
            return
        self.display.rect(x, y, w, h, True, active)
        text_w = len(label) * 6
        tx = x + max(0, (w - text_w) // 2)
        ty = y + max(0, (h - 8) // 2)
        self._text(label, tx, ty)

    def draw_bool_edit(self, name: str, value: Any) -> None:
        if self.is_tall:
            if self.is_tft:
                if self.is_full_tft:
                    block_h = 98
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("toggle", top)
                    box_y = top + 16
                    gap = 48
                    left = 44
                    self._draw_choice_box(left, box_y, 0, 0, "OFF", not bool(value))
                    self._draw_choice_box(left + 96 + gap, box_y, 0, 0, "ON", bool(value))
                    self.text_center("press = commit", top + 86)
                else:
                    block_h = 60
                    top = self.edit_content_top(block_h)
                    self.text_center("toggle", top)
                    box_y = top + 14
                    box_h = 30
                    box_w = 64
                    self._draw_choice_box(12, box_y, box_w, box_h, "OFF", not bool(value))
                    self._draw_choice_box(84, box_y, box_w, box_h, "ON", bool(value))
                    self.text_center("press = commit", top + 54)
            else:
                block_h = 40
                top = self.edit_content_top(block_h)
                box_y = top
                box_h = 22
                box_w = 54
                self._draw_choice_box(6, box_y, box_w, box_h, "OFF", not bool(value))
                self._draw_choice_box(68, box_y, box_w, box_h, "ON", bool(value))
                self.text_center("press = commit", top + 32)
        else:
            block_h = 20
            top = self.edit_content_top(block_h)
            self.text_center("ON" if bool(value) else "OFF", top)
            self._text("< OFF   ON >", 20, top + 12)

    def draw_enum_edit(self, name: str, vals: list[Any], value: Any) -> None:
        try:
            idx = vals.index(value)
        except ValueError:
            idx = 0

        current = shorten(format_display_value(vals[idx]), self.title_cols)
        prev_value = shorten(format_display_value(vals[(idx - 1) % len(vals)]), self.value_name_cols) if vals else ""
        next_value = shorten(format_display_value(vals[(idx + 1) % len(vals)]), self.value_name_cols) if vals else ""
        position = f"{idx + 1}/{len(vals)}" if vals else ""

        if self.is_tall:
            if self.is_tft:
                if self.is_full_tft:
                    block_h = 116
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("select value", top + 8)
                    self.text_center_scaled(current, top + 36, 2)
                    self.text_center(f"{prev_value}  {position}  {next_value}", top + 64)
                    self.text_center("press = commit", top + 100)
                else:
                    block_h = 60
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("select value", top)
                    self.text_center(current, top + 14)
                    self._draw_choice_box(10, top + 30, 54, 18, prev_value or "-", False)
                    self._draw_choice_box(74, top + 30, 54, 18, next_value or "-", False)
                    self.text_center(position, top + 52)
            else:
                block_h = 36
                top = self.edit_content_top(block_h)
                self.text_center(current, top)
                self.draw_menu_row(top + 18, False, prev_value)
                row = f"{position:>4} {next_value}"[:21]
                self._text(row, 0, top + 28)
        else:
            block_h = 20
            top = self.edit_content_top(block_h)
            self.text_center(current, top)
            self.text_center(position, top + 12)

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
        mask = int(state.edit_value or 0)
        mode = state.edit_ttid_mode
        if self.is_tall:
            if mode == "keyboard":
                if self.is_full_tft:
                    block_h = 134
                    top = self.edit_content_top(block_h)
                    self._draw_ttid_keyboard(mask, state.edit_ttid_selected_pc, 20, top, 280, 104)
                else:
                    block_h = 48
                    top = self.edit_content_top(block_h)
                    self._draw_ttid_keyboard(mask, state.edit_ttid_selected_pc, 4, top, 120, 32)
                if state.edit_ttid_selected_pc == 12:
                    if self.is_full_tft:
                        self._text("> LOAD", 196, top + 126, 2, "medium")
                        self._text(str(mask), 24, top + 126, 2, "medium")
                    else:
                        self.display.rect(92, top + 46, 32, 10, True, False)
                        self.text_center("LOAD", top + 48)
                        self._text(str(mask), 4, top + 48)
                else:
                    pc = state.edit_ttid_selected_pc
                    if self.is_full_tft:
                        self._text(note_name(pc), 24, top + 126, 2, "medium")
                        self._text("ON" if is_pc_on(mask, pc) else "OFF", 72, top + 126, 2, "medium")
                        self._draw_right_aligned(str(mask), self.display.width - 24, top + 126, 2, "medium")
                    else:
                        self._text(note_name(pc), 4, top + 48)
                        self._text("ON" if is_pc_on(mask, pc) else "OFF", 28, top + 48)
                        self._text(str(mask), 84, top + 48)
            elif mode == "load_root":
                roots = get_root_names()
                if self.is_full_tft:
                    block_h = 116
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load root", top + 8)
                    self.text_center_scaled(roots[state.edit_ttid_load_root % 12], top + 44, 2)
                    self.text_center("press -> scale", top + 106)
                else:
                    block_h = 46
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load root", top)
                    self.text_center(roots[state.edit_ttid_load_root % 12], top + 16)
                    self.text_center("press -> scale", top + 38)
            else:
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                if self.is_full_tft:
                    block_h = 116
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load scale", top + 8)
                    self.text_center_scaled(shorten(names[idx], 18), top + 44, 2)
                    self.text_center("press -> apply", top + 106)
                else:
                    block_h = 48
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load scale", top)
                    self.text_center(shorten(names[idx], 18), top + 16)
                    self.text_center("press -> apply", top + 40)
        else:
            block_h = 20
            top = self.edit_content_top(block_h)
            if mode == "keyboard":
                line = "LOAD" if state.edit_ttid_selected_pc == 12 else f"{note_name(state.edit_ttid_selected_pc)} {'ON' if is_pc_on(mask, state.edit_ttid_selected_pc) else 'OFF'}"
                self.text_center(line, top)
                self.text_center(str(mask), top + 12)
            elif mode == "load_root":
                self.text_center("root", top)
                self.text_center(get_root_names()[state.edit_ttid_load_root % 12], top + 12)
            else:
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                self.text_center(shorten(names[idx], 21), top + 6)

    def draw_edit_step16(self, ui, param, state) -> None:
        cells = build_cells(int(state.edit_value or 0), state.edit_step16_focus, ui.active_step16_playhead)

        if self.is_tall:
            if self.is_full_tft:
                origin_x = 20
                block_h = 144
                top = self.edit_content_top(block_h)
                origin_y = top + 12
                cell_w = 30
                cell_h = 48
                gap = 6
                text_y = top + 130
            else:
                origin_x = 8
                block_h = 64
                top = self.edit_content_top(block_h)
                origin_y = top + 8
                cell_w = 12
                cell_h = 16
                gap = 3
                text_y = top + 48
        else:
            origin_x = 8
            block_h = 22
            top = self.edit_content_top(block_h)
            origin_y = top
            cell_w = 11
            cell_h = 8
            gap = 3
            text_y = top + 14

        for cell in cells:
            col = cell.index % 8
            row = cell.index // 8
            x = origin_x + col * (cell_w + gap)
            y = origin_y + row * (cell_h + gap)

            self.display.rect(x, y, cell_w, cell_h, True, cell.active)

            if cell.focused:
                self.display.rect(max(0, x - 1), max(0, y - 1), cell_w + 2, cell_h + 2, True, False)

            if cell.playing:
                inset_x = 4
                inset_top = 4
                inset_bottom = 4
                fx = x + inset_x
                fy = y + inset_top
                fw = max(1, cell_w - (inset_x * 2))
                fh = max(2, min(cell_h - (inset_top + inset_bottom), max(2, cell_h // 6)))
                self._fill_rect(fx, fy, fw, fh, not cell.active)

        focus_label = f"{state.edit_step16_focus + 1:02d}"
        playhead = ui.active_step16_playhead
        play_label = "--" if playhead is None else f"{playhead + 1:02d}"
        self.text_center(f"F{focus_label} P{play_label} {int(state.edit_value or 0)}", text_y)

    def draw_edit_pitch_display(self, ui, param) -> None:
        pitch_item = ui.active_pitch_display_pitch
        cents_item = ui.active_pitch_display_cents
        pitch_value = pitch_item.get("value") if pitch_item else None

        cents_value = cents_item.get("value") if cents_item else None
        cents_float = self._parse_float(cents_value)
        cents_text = shorten(
            f"{cents_float:+.1f}c" if cents_float is not None else format_display_value(cents_value),
            10,
        )

        if self.is_full_tft:
            pitch_scale = 5
            cents_scale = 2
            status_scale = 2
            meter_w = min(self.display.width - 40, 220)
            meter_h = 18
            pitch_segments = self._pitch_display_segments(pitch_value, pitch_scale)
            pitch_h = max(self._measure_text(text, scale, weight)[1] for text, scale, weight in pitch_segments)
            cents_h = self._measure_text(cents_text, cents_scale, "medium")[1]
            status_h = self._measure_text("IN TUNE", status_scale, "medium")[1]
            total_h = pitch_h + 24 + meter_h + 16 + cents_h + 8 + status_h
            start_y = self.edit_content_top(total_h)
            pitch_y = start_y
            meter_y = pitch_y + pitch_h + 24
            cents_y = meter_y + meter_h + 16
            status_y = cents_y + cents_h + 8
        elif self.is_tall:
            pitch_scale = 3 if self.is_tft else 2
            cents_scale = 1 if self.is_tft else 1
            status_scale = 1
            meter_w = min(self.display.width - 18, 110 if self.is_tft else 92)
            meter_h = 9 if self.is_tft else 7
            pitch_segments = self._pitch_display_segments(pitch_value, pitch_scale)
            pitch_h = max(self._measure_text(text, scale, weight)[1] for text, scale, weight in pitch_segments)
            cents_h = self._measure_text(cents_text, cents_scale)[1]
            status_h = self._measure_text("CENTER", status_scale)[1]
            total_h = pitch_h + 8 + meter_h + 6 + cents_h + 2 + status_h
            start_y = self.edit_content_top(total_h)
            pitch_y = start_y
            meter_y = pitch_y + pitch_h + 8
            cents_y = meter_y + meter_h + 6
            status_y = cents_y + cents_h + 2
        else:
            pitch_scale = 2
            cents_scale = 1
            status_scale = 1
            meter_w = min(self.display.width - 18, 92)
            meter_h = 5
            pitch_segments = self._pitch_display_segments(pitch_value, pitch_scale)
            pitch_h = max(self._measure_text(text, scale, weight)[1] for text, scale, weight in pitch_segments)
            cents_h = self._measure_text(cents_text, cents_scale)[1]
            total_h = pitch_h + 4 + meter_h + 2 + cents_h
            start_y = self.edit_content_top(total_h)
            pitch_y = start_y
            meter_y = pitch_y + pitch_h + 4
            cents_y = meter_y + meter_h + 2
            status_y = None

        meter_x = max(0, (self.display.width - meter_w) // 2)

        self._draw_centered_segments(pitch_segments, pitch_y)
        self._draw_pitch_meter(cents_float, meter_x, meter_y, meter_w, meter_h)
        self.text_center_scaled(cents_text, cents_y, cents_scale)

        if status_y is not None:
            if cents_float is None:
                status_text = "LISTENING"
            elif abs(cents_float) <= 3:
                status_text = "IN TUNE"
            elif cents_float < 0:
                status_text = "FLAT"
            else:
                status_text = "SHARP"
            self.text_center_scaled(status_text, status_y, status_scale)

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
        if is_pitch_display_param(selected_param):
            self.draw_edit_pitch_display(ui, selected_param)
            return

        if self.is_full_tft:
            block_h = 96
            top = self.edit_content_top(block_h)
            gfx_x, gfx_y, gfx_w, gfx_h, value_y = (16, top, self.display.width - 32, 40, top + 64)
        else:
            if self.is_tall:
                block_h = 56
                top = self.edit_content_top(block_h)
                gfx_x, gfx_y, gfx_w, gfx_h, value_y = (4, top, 120, 24, top + 32)
            else:
                block_h = 26
                top = self.edit_content_top(block_h)
                gfx_x, gfx_y, gfx_w, gfx_h, value_y = (4, top, 120, 12, top + 14)
        name = shorten_param_name(selected_param.get("name", ""))
        value = state.edit_value

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
        if self.is_tft:
            scale = 3 if self.is_full_tft else 2
            if title == "SHADOWBOX":
                _, text_h, _ = self._measure_shadowbox_logo(scale)
                y = max(0, (self.display.height - text_h) // 2)
                self._draw_shadowbox_logo(y, scale)
            else:
                text_height = 7 * scale
                y = max(0, (self.display.height - text_height) // 2)
                self.text_center_scaled(title, y, scale)
        else:
            self.text_center(title, 28 if self.is_tall else 12)
        self.display.show()

    def draw_startup_status(self, title: str, status_line: str = "", hint_line: str = "") -> None:
        self.display.clear()
        if self.is_tft:
            title_scale = 3 if self.is_full_tft else 2
            status_scale = 1
            hint_scale = 1
            status_gap = 22 if self.is_full_tft else 14
            hint_gap = 16 if self.is_full_tft else 12
            if title == "SHADOWBOX":
                _, title_h, _ = self._measure_shadowbox_logo(title_scale)
            else:
                title_h = self._measure_text(title, title_scale, "medium")[1]

            status_h = self._measure_text(status_line, status_scale)[1] if status_line else 0
            hint_h = self._measure_text(hint_line, hint_scale)[1] if hint_line else 0
            block_h = title_h
            if status_h:
                block_h += status_gap + status_h
            if hint_h:
                block_h += hint_gap + hint_h
            title_y = max(0, (self.display.height - block_h) // 2)

            if title == "SHADOWBOX":
                self._draw_shadowbox_logo(title_y, title_scale)
            else:
                self.text_center_scaled(title, title_y, title_scale)

            status_y = title_y + title_h + status_gap
            if status_line:
                self.text_center_scaled(shorten(status_line, 44 if self.is_full_tft else 28), status_y, status_scale)
            if hint_line:
                self.text_center_scaled(
                    shorten(hint_line, 34 if self.is_full_tft else 24),
                    status_y + status_h + hint_gap,
                    hint_scale,
                )
        else:
            self.text_center(title, 28 if self.is_tall else 12)
            if status_line:
                self.text_center(shorten(status_line, self.text_cols), 44 if self.is_tall else 22)
            if hint_line and self.is_tall:
                self.text_center(shorten(hint_line, self.text_cols), 56)
        self.display.show()

    def draw_status(self, ui) -> None:
        if self.is_tft:
            status = ui.state.system.get("status", {})
            cpu_load = status.get("cpu_load")
            cpu_text = "-" if cpu_load is None else f"{cpu_load:.1f}"
            self._draw_info_rows(
                [
                    ("INSTANCES", len(ui.state.instances)),
                    ("CPU", cpu_text),
                    ("XRUNS", status.get("xruns", "-")),
                    ("RNBO", status.get("runner_version", "-")),
                    ("SET", ui.state.system.get("set_name", "-")),
                ]
            )
            return
        rows = self.content_rows
        self.draw_value_row(rows[0], False, "inst", len(ui.state.instances))
        self.draw_value_row(rows[1], False, "cpu", "-" if ui.state.system.get("status", {}).get("cpu_load") is None else f"{ui.state.system['status']['cpu_load']:.1f}")
        self.draw_value_row(rows[2], False, "xruns", ui.state.system.get("status", {}).get("xruns", "-"))
        if self.is_tall:
            self.draw_value_row(rows[3], False, "rnbo", ui.state.system.get("status", {}).get("runner_version", "-"))

    def draw_system_audio(self, ui) -> None:
        self.draw_string_list([".."] + SYSTEM_AUDIO_ITEMS, ui.state.system_audio_cursor)

    def draw_system_audio_device(self, ui) -> None:
        current_indices = {
            idx + 1 for idx, item in enumerate(ui.audio_options) if str(item) == str(ui.current_audio_card)
        }
        self.draw_string_list([".."] + [str(item) for item in ui.audio_options], ui.state.audio_device_cursor, current_indices=current_indices)

    def draw_system_audio_rate(self, ui) -> None:
        current_indices = {
            idx + 1 for idx, item in enumerate(ui.sample_rate_options) if item == ui.current_sample_rate
        }
        self.draw_string_list([".."] + [str(item) for item in ui.sample_rate_options], ui.state.sample_rate_cursor, current_indices=current_indices)

    def draw_system_audio_buffer(self, ui) -> None:
        current_indices = {
            idx + 1 for idx, item in enumerate(ui.buffer_size_options) if item == ui.current_buffer_size
        }
        self.draw_string_list([".."] + [str(item) for item in ui.buffer_size_options], ui.state.buffer_size_cursor, current_indices=current_indices)

    def draw_network(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("1.1.1.1", 80))
            ip = sock.getsockname()[0]
            sock.close()
        except Exception:
            ip = "?"
        if self.is_tft:
            self._draw_info_rows(
                [
                    ("IP", ip),
                    ("OSC", RNBO_PORT),
                    ("HOST", "127.0.0.1"),
                ],
                top_padding=18 if not self.is_full_tft else 8,
            )
            return
        rows = self.content_rows
        self.draw_value_row(rows[0], False, "ip", ip)
        self.draw_value_row(rows[1], False, "osc", RNBO_PORT)

    def draw_about(self) -> None:
        version_text = SHADOWBOX_VERSION
        build_text = f"build {SHADOWBOX_BUILD_INFO}"
        if self.is_tft:
            panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
            self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
            logo_scale = 3 if self.is_full_tft else 2
            text_lines = [
                version_text,
                build_text,
                "stretta.com",
                "github.com/stretta/Shadowbox",
            ]
            logo_h = self._measure_shadowbox_logo(logo_scale)[1]
            line_h = max(self._measure_text(line, 1, "regular")[1] for line in text_lines)
            logo_gap = 14 if self.is_full_tft else 10
            line_gap = 8 if self.is_full_tft else 4
            block_h = logo_h + logo_gap + (line_h * len(text_lines)) + (line_gap * (len(text_lines) - 1))
            y = panel_y + max(0, (panel_h - block_h) // 2)
            y += self._draw_shadowbox_logo(y, logo_scale) + logo_gap
            for idx, line in enumerate(text_lines):
                self.text_center_scaled(line, y, 1)
                y += line_h
                if idx < len(text_lines) - 1:
                    y += line_gap
            return
        rows = self.content_rows
        title_row = rows[0]
        version_row = rows[1] if len(rows) > 1 else rows[0]
        meta_row = rows[2] if len(rows) > 2 else rows[-1]
        self.text_center("SHADOWBOX", title_row)
        self.text_center(version_text, version_row)
        self.text_center(SHADOWBOX_BUILD_INFO, meta_row)
        if self.is_tall and len(rows) > 3:
            self.text_center("stretta.com", rows[3])
        if self.is_tall and len(rows) > 4:
            self.text_center("github.com/stretta/Shadowbox", rows[4])

    def draw_brick_panel(self, ui) -> None:
        game = ui.brick_panel
        panel_x = 2
        panel_y = self.content_top + 2
        panel_w = max(20, self.display.width - 4)
        panel_h = max(20, self.display.height - panel_y - 2)
        status_h = 16 if self.is_full_tft else 12 if self.is_tft or self.is_tall else 8
        arena_h = max(12, panel_h - status_h)

        self.display.rect(panel_x, panel_y, panel_w, arena_h, True, False)

        inner_x = panel_x + 1
        inner_y = panel_y + 1
        inner_w = max(1, panel_w - 2)
        inner_h = max(1, arena_h - 2)

        brick_gap_px = 1 if inner_w < 120 else 2
        brick_h = max(3, int(inner_h * ((game.brick_bottom - game.brick_top) / game.brick_rows)) - brick_gap_px)
        brick_w = max(4, int(inner_w / game.brick_cols) - brick_gap_px)
        brick_top = inner_y + int(inner_h * game.brick_top)

        for row_idx, row in enumerate(game.bricks):
            for col_idx, alive in enumerate(row):
                if not alive:
                    continue
                brick_x = inner_x + int((col_idx / game.brick_cols) * inner_w)
                brick_y = brick_top + row_idx * (brick_h + brick_gap_px)
                self._fill_rect(brick_x, brick_y, brick_w, brick_h, True)

        paddle_w = max(8, int(inner_w * game.paddle_width))
        paddle_h = 3 if self.is_tft else 2
        paddle_x = inner_x + int(inner_w * game.paddle_left)
        paddle_y = inner_y + int(inner_h * game.paddle_y)
        paddle_x = min(inner_x + inner_w - paddle_w, max(inner_x, paddle_x))
        paddle_y = min(inner_y + inner_h - paddle_h, max(inner_y, paddle_y))
        self._fill_rect(paddle_x, paddle_y, paddle_w, paddle_h, True)

        ball_size = 4 if self.is_tft else 3
        ball_x = inner_x + int(inner_w * game.ball_x) - (ball_size // 2)
        ball_y = inner_y + int(inner_h * game.ball_y) - (ball_size // 2)
        ball_x = min(inner_x + inner_w - ball_size, max(inner_x, ball_x))
        ball_y = min(inner_y + inner_h - ball_size, max(inner_y, ball_y))
        self._fill_rect(ball_x, ball_y, ball_size, ball_size, True)

        score_text = f"{game.score:03d}"
        lives_text = f"L{game.lives}"
        status_y = panel_y + arena_h + 2
        self._text(score_text, panel_x, status_y)
        self._draw_right_aligned(lives_text, panel_x + panel_w, status_y)

        if game.status_text:
            message_y = inner_y + max(4, (inner_h // 2) - 4)
            self.text_center(game.status_text, message_y)

    def draw_maint(self, ui) -> None:
        self.draw_string_list([".."] + ui.maint_menu_items, ui.state.maint_cursor)

    def _draw_instances_icon(self, x: int, y: int, on: bool = True) -> None:
        self.display.rect(x + 18, y + 10, 24, 18, on, False)
        self.display.rect(x + 10, y + 20, 24, 18, on, False)
        self.display.rect(x + 26, y + 20, 24, 18, on, False)
        self.display.rect(x + 18, y + 30, 24, 18, on, False)

        for dot_x, dot_y in ((22, 14), (30, 14), (26, 24), (34, 24), (42, 24), (26, 34), (34, 34)):
            self.display.rect(x + dot_x, y + dot_y, 4, 4, on, True)

    def _draw_system_icon(self, x: int, y: int, on: bool = True) -> None:
        self.display.rect(x + 18, y + 18, 24, 24, on, False)
        self.display.rect(x + 24, y + 24, 12, 12, on, False)

        teeth = [
            (26, 8, 8, 8),
            (26, 44, 8, 8),
            (8, 26, 8, 8),
            (44, 26, 8, 8),
            (14, 14, 8, 8),
            (38, 14, 8, 8),
            (14, 38, 8, 8),
            (38, 38, 8, 8),
        ]
        for dx, dy, w, h in teeth:
            self.display.rect(x + dx, y + dy, w, h, on, True)

    def _draw_tft_home_card(self, x: int, y: int, w: int, h: int, label: str, selected: bool) -> None:
        if selected:
            underline_y = y + h - (14 if self.is_full_tft else 8)
            underline_x = x + (10 if self.is_full_tft else 6)
            underline_w = max(12, w - ((20 if self.is_full_tft else 12)))
            self.display.hline(underline_x, underline_y, underline_w, True)
            if self.is_full_tft:
                self.display.hline(underline_x, underline_y + 1, underline_w, True)

        icon_size = 60 if self.is_full_tft else 40
        icon_x = x + max(8, (w - icon_size) // 2)
        icon_y = y + (18 if self.is_full_tft else 12)
        if label == "SYSTEM":
            self._draw_system_icon(icon_x, icon_y, on=True)
        else:
            self._draw_instances_icon(icon_x, icon_y, on=True)

        text_scale = 2 if self.is_full_tft else 1
        text_weight = "semibold" if selected and self.is_full_tft else "medium" if selected else "regular"
        text_w, text_h = self._measure_text(label, text_scale, text_weight)
        text_x = x + max(0, (w - text_w) // 2)
        text_y = y + h - text_h - (24 if self.is_full_tft else 14)
        self._text(label, text_x, text_y, text_scale, text_weight, on=True)

    def draw_top_menu_tft(self, items: list[str], selected_idx: int) -> None:
        total = len(items)
        if total <= 0:
            return
        selected_idx = max(0, min(selected_idx, total - 1))

        avail_top = self.content_top
        avail_h = max(0, self.display.height - avail_top)
        gap = 18 if self.is_full_tft else 10
        card_w = min(136 if self.is_full_tft else 70, max(56, (self.display.width - (gap * 3)) // 2))
        card_h = min(146 if self.is_full_tft else 82, max(56, avail_h - (24 if self.is_full_tft else 12)))
        total_w = (card_w * total) + (gap * (total - 1))
        start_x = max(4, (self.display.width - total_w) // 2)
        start_y = max(avail_top + 6, avail_top + ((avail_h - card_h) // 2) - (8 if self.is_full_tft else 0))

        for idx, label in enumerate(items):
            x = start_x + idx * (card_w + gap)
            self._draw_tft_home_card(x, start_y, card_w, card_h, str(label), idx == selected_idx)

    def draw(self, ui) -> None:
        state = ui.state
        self.display.clear()

        header = {
            "TOP": "SHADOWBOX",
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
            "ABOUT": "ABOUT",
            "BRICK_PANEL": "BRICK PANEL",
            "MAINT": "MAINT",
        }.get(state.ui_mode, state.ui_mode)
        if state.ui_mode == "EDIT":
            header = self.edit_header_title(ui.selected_param)
        self.draw_header(header, busy=state.busy, ticks=state.activity_ticks)

        if state.ui_mode == "EDIT":
            self.draw_edit(ui, ui.selected_param, state)
        elif state.ui_mode == "TOP":
            if self.is_tft:
                self.draw_top_menu_tft(ui.top_level_items, state.top_index)
            else:
                self.draw_string_list(ui.top_level_items, state.top_index)
        elif state.ui_mode == "INSTANCE_LIST":
            self.draw_instance_list(ui)
        elif state.ui_mode == "REMOVE_INSTANCE_PICKER":
            self.draw_string_list(
                [".."] + [str(item.get("label", "")) for item in state.instances]
                if state.instances
                else ["..", "no instances"],
                state.remove_instance_picker_cursor,
            )
        elif state.ui_mode == "PATCHER_PICKER":
            self.draw_string_list([".."] + state.patchers if state.patchers else ["..", "no patchers"], state.patcher_cursor)
        elif state.ui_mode == "INSTANCE_MENU":
            self.draw_string_list([".."] + ui.instance_menu_items, state.instance_menu_cursor)
        elif state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            self.draw_string_list(REMOVE_INSTANCE_CONFIRM_ITEMS, state.remove_instance_confirm_cursor)
        elif state.ui_mode == "PRESET_LIST":
            self.draw_preset_list(ui, ui.active_presets, state.preset_cursor) if ui.active_presets else self.draw_string_list(["..", "no presets"], state.preset_cursor)
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
            self.draw_string_list([".."] + ui.system_menu_items, state.system_cursor)
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
        elif state.ui_mode == "ABOUT":
            self.draw_about()
        elif state.ui_mode == "BRICK_PANEL":
            self.draw_brick_panel(ui)
        elif state.ui_mode == "MAINT":
            self.draw_maint(ui)

        self.display.show()


class OledShadowboxRenderer(ShadowboxRenderer):
    pass


class TftShadowboxRenderer(ShadowboxRenderer):
    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        banner_h = self.header_height
        pad_x = 4
        text_scale = 2 if self.is_full_tft else 1
        text_weight = "semibold" if self.is_full_tft else "regular"
        fitted = self._truncate_to_width(title, self.display.width - (pad_x * 2) - 20, text_scale, text_weight)
        _, text_h = self._measure_text(fitted, text_scale, text_weight)
        text_y = max(1, (banner_h - text_h) // 2)
        self.display.rect(0, 0, self.display.width, banner_h, True, True)
        self._text(fitted, pad_x, text_y, text_scale, text_weight, on=False)
        if busy:
            spinner_scale = 2 if self.is_full_tft else 1
            spinner = activity_frame(ticks)
            spinner_w, spinner_h = self._measure_text(spinner, spinner_scale, "medium")
            spinner_y = max(1, (banner_h - spinner_h) // 2)
            self._text(spinner, max(pad_x, self.display.width - pad_x - spinner_w), spinner_y, spinner_scale, "medium", on=False)


def create_renderer(display) -> ShadowboxRenderer:
    width = getattr(display, "width", 128)
    height = getattr(display, "height", 32)
    if width >= 160 or height >= 96:
        return TftShadowboxRenderer(display=display)
    return OledShadowboxRenderer(display=display)
