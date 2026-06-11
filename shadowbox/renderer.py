#!/usr/bin/env python3
"""
Shadowbox
Hardware UI for RNBO Runner
"""

from __future__ import annotations

import re
from typing import Any

from shadowbox.editors.pitch_display import is_pitch_display_param, normalize_pitch_to_midi_note
from shadowbox.editors.scope import is_scope_param, scope_time_seconds
from shadowbox.editors.step16 import build_cells, is_step16_param
from shadowbox.editors.ttid import get_root_names, is_pc_on, is_ttid_param, note_name
from shadowbox.rnbo import RNBO_HOST
from shadowbox.touch import TouchLayout, TouchSample
from shadowbox.ui import (
    MenuRow,
    NAME_EDITOR_CHAR_OPTIONS,
    NAME_TOUCH_KEY_VALUES,
    NAME_TOUCH_LETTER_ROWS,
    NAME_TOUCH_NUMBER_ROWS,
    NAME_INLINE_DELETE_LABEL,
    REMOVE_INSTANCE_CONFIRM_ITEMS,
    REMOVE_INSTANCE_CONFIRM_BUTTONS,
    ROUTING_GROUP_ITEMS,
    NAME_ERROR_BUTTONS,
    NAME_OVERWRITE_CONFIRM_BUTTONS,
    SYSTEM_AUDIO_ITEMS,
    ValueRow,
    display_as_int,
    display_precision,
    edit_as_int,
)
from shadowbox.version import SHADOWBOX_BUILD_INFO, SHADOWBOX_VERSION

STEP16_ENABLED_FILL_LEVEL = int(round(255 * 0.7))

FIVE_INCH_THEME = {
    "bg": (15, 18, 18),
    "panel": (28, 33, 32),
    "panel_alt": (38, 44, 42),
    "panel_pressed": (55, 66, 62),
    "text": (244, 247, 242),
    "muted": (154, 164, 157),
    "line": (67, 77, 73),
    "accent": (21, 193, 129),
    "accent_soft": (65, 116, 96),
    "midi": (110, 151, 168),
    "warning": (249, 172, 60),
    "danger": (235, 88, 76),
}


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
            return value.strip()[:2]
    return ""


def param_midi_mapping_marker(param: dict | None) -> str:
    if not isinstance(param, dict):
        return ""
    metadata = param.get("metadata", {})
    midi = metadata.get("midi") if isinstance(metadata, dict) else None
    if not isinstance(midi, dict):
        return ""
    chan = midi.get("chan")
    ctrl = midi.get("ctrl")
    if chan is None or ctrl is None:
        return ""
    try:
        chan_text = str(int(float(chan)))
        ctrl_text = str(int(float(ctrl)))
    except (TypeError, ValueError):
        return ""
    return f"{chan_text}:{ctrl_text}"


def format_param_value_with_midi(param: dict | None, value: Any) -> str:
    text = format_param_value(param, value)
    marker = param_midi_mapping_marker(param)
    return f"{marker} {text}" if marker and text not in ("", "-") else text


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


def routing_port_display_name(port: dict | None) -> str:
    if not isinstance(port, dict):
        return ""
    display_name = port.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    name = port.get("name")
    return str(name).strip() if name is not None else ""


def activity_frame(ticks: int) -> str:
    return ["-", "\\", "|", "/"][ticks % 4]


class ShadowboxRenderer:
    def __init__(self, display):
        self.display = display
        self.touch_layout: TouchLayout | None = None
        self._touch_state: TouchSample | None = None
        self._touch_mode = False

    def _text(self, text: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        self.display.text_with_style(str(text), x, y, scale, weight, on=on)

    def _theme(self, name: str) -> tuple[int, int, int]:
        return FIVE_INCH_THEME[name]

    def _menu_label(self, text: str) -> str:
        value = str(text)
        if value == "..":
            return value
        if value == "New Graph":
            return "New Set"
        if self.touch_layout_enabled and value.upper() == value and any(ch.isalpha() for ch in value):
            return value.title()
        return value

    def _menu_weight(self, text: str, weight: str = "regular") -> str:
        value = str(text)
        if self.touch_layout_enabled and value.upper() == value and any(ch.isalpha() for ch in value):
            if weight == "regular":
                return "medium"
            if weight == "medium":
                return "semibold"
        return weight

    def _touch_menu_scale(self) -> int:
        return 3 if self.touch_layout_enabled else 1

    def _touch_home_label_scale(self) -> int:
        return 4 if self.touch_layout_enabled else 2 if self.is_full_tft else 1

    def _hero_scale(self, scale: int) -> int:
        if self.is_five_inch_touch:
            return max(1, int(scale) * 2)
        return max(1, int(scale))

    @property
    def has_color(self) -> bool:
        return callable(getattr(self.display, "fill_rect_color", None))

    def _text_theme(self, text: str, x: int, y: int, color: str = "text", scale: int = 1, weight: str = "regular") -> None:
        text_color = getattr(self.display, "text_color", None)
        if callable(text_color):
            text_color(str(text), x, y, self._theme(color), scale, weight)
            return
        self._text(text, x, y, scale, weight)

    def _text_line_theme(self, text: str, x: int, y: int, color: str = "text", scale: int = 1, weight: str = "regular") -> None:
        text_line_color = getattr(self.display, "text_line_color", None)
        if callable(text_line_color):
            text_line_color(str(text), x, y, self._theme(color), scale, weight)
            return
        self._text_theme(text, x, y, color, scale, weight)

    def _fill_theme(self, x: int, y: int, w: int, h: int, color: str) -> None:
        fill_rect_color = getattr(self.display, "fill_rect_color", None)
        if callable(fill_rect_color):
            fill_rect_color(x, y, w, h, self._theme(color))
            return
        self.display.rect(x, y, w, h, True, True)

    def _rect_theme(self, x: int, y: int, w: int, h: int, color: str, fill: bool = False) -> None:
        rect_color = getattr(self.display, "rect_color", None)
        if callable(rect_color):
            rect_color(x, y, w, h, self._theme(color), fill)
            return
        self.display.rect(x, y, w, h, True, fill)

    def _rounded_theme(self, x: int, y: int, w: int, h: int, radius: int, color: str, fill: bool = False) -> None:
        rounded_rect_color = getattr(self.display, "rounded_rect_color", None)
        if callable(rounded_rect_color):
            rounded_rect_color(x, y, w, h, radius, self._theme(color), fill)
            return
        self._rect_theme(x, y, w, h, color, fill)

    def _hline_theme(self, x: int, y: int, w: int, color: str) -> None:
        hline_color = getattr(self.display, "hline_color", None)
        if callable(hline_color):
            hline_color(x, y, w, self._theme(color))
            return
        self.display.hline(x, y, w, True)

    def _vline_theme(self, x: int, y: int, h: int, color: str) -> None:
        vline_color = getattr(self.display, "vline_color", None)
        if callable(vline_color):
            vline_color(x, y, h, self._theme(color))
            return
        self.display.vline(x, y, h, True)

    def _strip_touch_back_item(
        self,
        items: list[Any],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
        action_indices: set[int] | None = None,
    ) -> tuple[list[Any], int, int, set[int] | None, dict[int, str] | None, set[int] | None]:
        if not (self.touch_layout_enabled and items and str(items[0]) == ".."):
            return items, selected_idx, 0, current_indices, item_weights, action_indices

        stripped_items = list(items[1:])
        stripped_selected = max(0, selected_idx - 1)
        stripped_current = None
        if current_indices is not None:
            stripped_current = {idx - 1 for idx in current_indices if idx > 0}
        stripped_weights = None
        if item_weights is not None:
            stripped_weights = {idx - 1: weight for idx, weight in item_weights.items() if idx > 0}
        stripped_actions = None
        if action_indices is not None:
            stripped_actions = {idx - 1 for idx in action_indices if idx > 0}
        return stripped_items, stripped_selected, 1, stripped_current, stripped_weights, stripped_actions

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

    def _wrap_text_to_width(self, text: str, max_width: int, scale: int = 1, weight: str = "regular") -> list[str]:
        text = " ".join(str(text).split())
        if not text or max_width <= 0:
            return []

        lines: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = word if not current else f"{current} {word}"
            if self._measure_text(candidate, scale, weight)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            if self._measure_text(word, scale, weight)[0] <= max_width:
                current = word
                continue
            fitted = self._truncate_to_width(word, max_width, scale, weight)
            if fitted:
                lines.append(fitted)
            current = ""
        if current:
            lines.append(current)
        return lines

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
        module = type(self.display).__module__
        if module.startswith("shadowbox.display.st7735s_hat"):
            return "tft_tiny_text"
        width = getattr(self.display, "width", 128)
        height = getattr(self.display, "height", 32)
        if width >= 320 and height >= 240:
            return "tft_full"
        if width >= 160 or height >= 96:
            return "tft"
        return "oled"

    @property
    def is_tft(self) -> bool:
        return self.layout_mode in {"tft", "tft_full", "tft_tiny_text"}

    @property
    def is_full_tft(self) -> bool:
        return self.layout_mode == "tft_full"

    @property
    def is_tiny_text_tft(self) -> bool:
        return self.layout_mode == "tft_tiny_text"

    @property
    def is_tall(self) -> bool:
        return getattr(self.display, "height", 32) >= 64

    @property
    def is_five_inch_touch(self) -> bool:
        width = getattr(self.display, "width", 128)
        height = getattr(self.display, "height", 32)
        return width >= 640 and height >= 360

    @property
    def touch_layout_enabled(self) -> bool:
        return self._touch_mode and self.is_five_inch_touch

    def set_touch_mode(self, enabled: bool) -> None:
        self._touch_mode = bool(enabled)

    def set_touch_state(self, touch_state: TouchSample | None) -> None:
        self._touch_state = touch_state

    @property
    def header_height(self) -> int:
        if self.is_five_inch_touch:
            return self.display.height // 5
        if self.is_full_tft:
            return self._line_height(2, "semibold") + 8
        if self.is_tiny_text_tft:
            return 16
        if self.is_tft:
            return 10
        return 8

    @property
    def content_top(self) -> int:
        if self.is_five_inch_touch:
            return self.header_height
        return self.header_height + (4 if self.is_full_tft else 2 if self.is_tft else 0)

    @property
    def content_bottom(self) -> int:
        return max(self.content_top, self.display.height - (10 if self.is_full_tft else 8 if self.is_tft else 0))

    @property
    def content_rows(self) -> list[int]:
        if self.is_five_inch_touch:
            _, _, _, _, _, _, rows = self._touch_list_geometry(visible_rows=4)
            return rows
        if self.is_full_tft:
            rows = list(range(self.content_top + 8, self.content_bottom, self._line_height(2) + 4))
            return rows or [self.content_top + 4]
        if self.is_tiny_text_tft:
            return [26, 50, 74, 98]
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
        if self.is_tiny_text_tft:
            return 16
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
        if self.is_tiny_text_tft:
            return 10
        return 13 if self.is_tft else 9

    @property
    def value_cols(self) -> int:
        if self.is_full_tft:
            return 18
        if self.is_tiny_text_tft:
            return 6
        return 11 if self.is_tft else 9

    @property
    def value_row_cols(self) -> int:
        if self.is_tiny_text_tft:
            return 14
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

    def _draw_centered_text(self, text: str, y: int, scale: int = 1, weight: str = "regular") -> None:
        text = str(text)
        scale = max(1, int(scale))
        x = max(0, (self.display.width - self._measure_text(text, scale, weight)[0]) // 2)
        self._text(text, x, y, scale, weight)

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

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0, show_back_button: bool = False) -> None:
        if self.is_tiny_text_tft:
            self._text(shorten(title, self.header_cols), 4, 4)
        else:
            self._text(shorten(title, self.header_cols), 0, 0)
        if busy:
            self._text(activity_frame(ticks), max(0, self.display.width - 8), 0)

    def _draw_panel(self, x: int, y: int, w: int, h: int, title: str | None = None) -> None:
        if self.touch_layout_enabled:
            self._record_touch_target("content_area", x, y, w, h)
        if self.is_five_inch_touch and self.has_color:
            self._fill_theme(x, y, w, h, "bg")
            if title:
                self._text_theme(self._truncate_to_width(title, max(0, w - 32), 2, "semibold"), x + 24, y + 18, "muted", 2, "semibold")
            return
        if self.is_full_tft:
            if title:
                self._text(self._truncate_to_width(title, max(0, w - 8), 2, "semibold"), x + 4, y + 2, 2, "semibold")
            return
        if self.is_tiny_text_tft:
            if title:
                self._text(shorten(title, self.header_cols), x + 4, y + 2)
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
        if self.is_five_inch_touch:
            _, _, _, _, _, _, rows = self._touch_list_geometry(visible_rows=4)
            return rows
        if self.is_full_tft:
            start = panel_y + 8
            end = panel_y + max(8, panel_h - 20)
            rows = list(range(start, end, self._line_height(2) + 4))
            return rows or [start]
        if self.is_tiny_text_tft:
            return list(self.content_rows)
        return [14, 22, 30, 38, 46, 54, 62, 70, 78, 86, 94, 102, 110]

    def _touch_list_geometry(self, visible_rows: int = 4) -> tuple[int, int, int, int, int, int, list[int]]:
        header_bottom = self.content_top
        rail_w = min(120, max(88, self.display.width // 8))
        content_left = 0
        content_right = max(content_left + 160, self.display.width - rail_w - 6)
        content_top = header_bottom
        content_bottom = max(content_top + 1, self.display.height)
        content_h = max(1, content_bottom - content_top)

        row_count = max(1, int(visible_rows))
        row_h = max(1, content_h // row_count)
        gap = 0
        centers = [content_top + (row_h // 2) + idx * row_h for idx in range(row_count)]
        return content_left, content_right, content_top, content_bottom, row_h, gap, centers

    def _begin_touch_layout(self, screen: str) -> None:
        if not self.touch_layout_enabled:
            self.touch_layout = None
            return
        self.touch_layout = TouchLayout(self.display.width, self.display.height)
        self.touch_layout.reset(screen)

    def _record_touch_target(
        self,
        kind: str,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        action_kind: str = "",
        index: int | None = None,
        button_id: str = "",
        label: str = "",
        page: int | None = None,
        page_count: int | None = None,
    ) -> None:
        if self.touch_layout is None:
            return
        self.touch_layout.add_target(
            kind,
            x,
            y,
            w,
            h,
            action_kind=action_kind,
            index=index,
            button_id=button_id,
            label=label,
            page=page,
            page_count=page_count,
        )

    def _touch_pressed(self, *, kind: str | None = None, index: int | None = None, button_id: str = "") -> bool:
        if not self.touch_layout_enabled:
            return False
        touch_state = self._touch_state
        if touch_state is None or not touch_state.pressed:
            return False
        target = self.touch_layout.hit_test(touch_state.normalized_x, touch_state.normalized_y) if self.touch_layout else None
        if target is None:
            return False
        if kind is not None:
            if kind == "card" and target.kind in {"home_card_icon", "home_card_label"}:
                pass
            elif target.kind != kind:
                return False
        if index is not None and target.index != index:
            return False
        if button_id and target.button_id != button_id:
            return False
        return True

    def _draw_touch_row_background(self, x: int, y: int, w: int, h: int, *, current: bool = False, pressed: bool = False) -> None:
        if not (self.touch_layout_enabled and self.has_color):
            if pressed:
                self.display.rect(x + 2, y + 2, max(1, w - 4), max(1, h - 4), True, True)
            return
        fill = "panel_pressed" if pressed else "panel"
        self._rounded_theme(x, y, w, h, 10, fill, True)
        self._rect_theme(x, y, w, h, "line", False)

    def _draw_touch_list_item_background(self, x: int, y: int, w: int, h: int, *, current: bool = False, pressed: bool = False) -> None:
        if not (self.touch_layout_enabled and self.has_color):
            if pressed:
                self.display.rect(x + 2, y + 2, max(1, w - 4), max(1, h - 4), True, True)
            return
        if pressed:
            self._rounded_theme(x, y, w, h, 8, "panel_pressed", True)
        self._hline_theme(x, y + h - 1, w, "line")

    def _draw_touch_row_chevron(self, x: int, y: int, w: int, h: int, scale: int) -> None:
        if not self.touch_layout_enabled:
            return
        weight = "medium"
        chev_w, chev_h = self._measure_text(">", scale, weight)
        chev_x = x + max(0, w - chev_w - 22)
        chev_y = y + max(0, (h - chev_h) // 2)
        if self.has_color:
            self._text_theme(">", chev_x, chev_y, "muted", scale, weight)
        else:
            self._text(">", chev_x, chev_y, scale, weight)

    def _draw_touch_page_rail(self, content_top: int, content_bottom: int, page: int, page_count: int) -> None:
        if not self.touch_layout_enabled:
            return
        rail_w = min(120, max(88, self.display.width // 8))
        rail_x = self.display.width - rail_w
        rail_h = max(1, content_bottom - content_top)
        half_h = max(1, rail_h // 2)
        visual_pad_y = 10 if self.is_five_inch_touch else 0
        visual_top = min(content_bottom - 1, content_top + visual_pad_y)
        visual_bottom = max(visual_top + 1, content_bottom - visual_pad_y)
        visual_h = max(1, visual_bottom - visual_top)
        visual_half_h = max(1, visual_h // 2)
        self._record_touch_target("page_rail", rail_x, content_top, rail_w, rail_h)
        self._record_touch_target("page_up", rail_x, content_top, rail_w, half_h, action_kind="page_up", button_id="page_up")
        self._record_touch_target(
            "page_down",
            rail_x,
            content_top + half_h,
            rail_w,
            rail_h - half_h,
            action_kind="page_down",
            button_id="page_down",
        )

        arrow_scale = 2 if self.display.height >= 360 else 1
        rail_center_x = rail_x + (rail_w // 2)
        if self.has_color:
            self._rounded_theme(rail_x + 14, visual_top, rail_w - 28, visual_h, 10, "panel", True)
            self._hline_theme(rail_x + 28, visual_top + visual_half_h, rail_w - 56, "line")
            arrow_color = "accent" if page > 1 else "muted"
            down_color = "accent" if page < page_count else "muted"
            self._text_theme("^", rail_center_x - (self._measure_text("^", arrow_scale, "medium")[0] // 2), visual_top + 18, arrow_color, arrow_scale, "medium")
            self._text_theme(
                "v",
                rail_center_x - (self._measure_text("v", arrow_scale, "medium")[0] // 2),
                visual_bottom - self._line_height(arrow_scale, "medium") - 18,
                down_color,
                arrow_scale,
                "medium",
            )
        else:
            self._text("^", rail_center_x - (self._measure_text("^", arrow_scale, "medium")[0] // 2), visual_top + 12, arrow_scale, "medium")
            self._text(
                "v",
                rail_center_x - (self._measure_text("v", arrow_scale, "medium")[0] // 2),
                visual_bottom - self._line_height(arrow_scale, "medium") - 12,
                arrow_scale,
                "medium",
            )
        indicator = f"{max(1, int(page))}/{max(1, int(page_count))}"
        ind_w, ind_h = self._measure_text(indicator, arrow_scale, "semibold")
        ind_x = rail_center_x - (ind_w // 2)
        ind_y = visual_top + max(0, (visual_h - ind_h) // 2)
        if self.has_color:
            self._text_theme(indicator, ind_x, ind_y, "text", arrow_scale, "semibold")
        else:
            self._text(indicator, ind_x, ind_y, arrow_scale, "semibold")

    def _inline_name_window(self, ui, max_chars: int) -> str:
        text = str(ui.inline_name_text)
        max_chars = max(3, int(max_chars))
        if len(text) <= max_chars:
            return text
        focus_idx = text.find("[")
        if focus_idx < 0:
            return shorten(text, max_chars)
        start = max(0, min(focus_idx - (max_chars // 2), len(text) - max_chars))
        end = start + max_chars
        window = text[start:end]
        if start > 0 and len(window) >= 3:
            window = "..." + window[3:]
        if end < len(text) and len(window) >= 3:
            window = window[:-3] + "..."
        return window

    def _inline_mode_segments(self, edit_mode: bool) -> list[tuple[str, int, str]]:
        scale = 2 if self.is_full_tft else 1
        inactive = "thin" if self.is_full_tft else "regular"
        active = "bold"
        if edit_mode:
            return [
                ("MOVE", scale, inactive),
                ("   ", scale, "regular"),
                ("[EDIT]", scale, active),
            ]
        return [
            ("[MOVE]", scale, active),
            ("   ", scale, "regular"),
            ("EDIT", scale, inactive),
        ]

    def _inline_char_strip_text(self, ui, max_visible: int) -> str:
        visible = max(3, int(max_visible))
        option_count = len(NAME_EDITOR_CHAR_OPTIONS) + 1
        focus_idx = max(0, min(ui.state.name_inline_preview_index, option_count - 1))
        start = max(0, min(focus_idx - (visible // 2), option_count - visible))
        end = min(option_count, start + visible)
        labels: list[str] = []
        delete_visible = end > len(NAME_EDITOR_CHAR_OPTIONS)
        for idx in range(start, end):
            if idx == len(NAME_EDITOR_CHAR_OPTIONS):
                labels.append("|")
            if idx >= len(NAME_EDITOR_CHAR_OPTIONS):
                label = NAME_INLINE_DELETE_LABEL
            else:
                value = NAME_EDITOR_CHAR_OPTIONS[idx][1]
                label = "_" if value == " " else value
            labels.append(f"[{label}]" if idx == focus_idx else label)
        if start > 0:
            labels.insert(0, "...")
        if end < option_count:
            labels.append("...")
        elif delete_visible:
            labels.append("|")
        return " ".join(labels)

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
        if self.is_tiny_text_tft:
            x = 8
            self._text(f"{'>' if selected else ' '} {shorten(label, self.value_row_cols)}"[: self.text_cols], x, y, weight=weight)
            return
        if self.is_tft and selected:
            self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
        x = 6 if self.is_tft else 0
        self._text(text if not self.is_tft else f"{'>' if selected else ' '} {shorten(label, 50)}"[: self.text_cols], x, y, weight=weight)

    def draw_value_row(
        self,
        y: int,
        selected: bool,
        name: str,
        value: Any,
        current: bool = False,
        emphasis: str | None = None,
    ) -> None:
        prefix = self._oled_row_prefix(selected, current)
        left = shorten(shorten_param_name(name), self.value_name_cols)
        right = shorten(format_display_value(value), self.value_cols)
        row = f"{prefix}{left:<{self.value_name_cols}} {right:>{self.value_cols}}"
        left_weight = self._current_row_weight(emphasis, current=current)
        if self.is_full_tft:
            self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected, text_weight=left_weight)
            return
        self._text(row[: self.text_cols], 0, y, weight=left_weight)

    def draw_param_value_row(self, y: int, selected: bool, param: dict, current: bool = False) -> None:
        prefix = self._oled_row_prefix(selected, current)
        left = shorten(shorten_param_name(param.get("name", "")), self.value_name_cols)
        right = shorten(format_param_value_with_midi(param, param.get("value")), self.value_cols)
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
        action_indices: set[int] | None = None,
    ) -> None:
        items, selected_idx, index_offset, current_indices, item_weights, action_indices = self._strip_touch_back_item(
            list(items),
            selected_idx,
            current_indices=current_indices,
            item_weights=item_weights,
            action_indices=action_indices,
        )
        if self.is_tft:
            self._draw_string_list_tft(
                items,
                selected_idx,
                current_indices=current_indices,
                item_weights=item_weights,
                index_offset=index_offset,
                action_indices=action_indices,
            )
            return
        indices, selected_row, rows = self.list_window(selected_idx, len(items))
        for row_idx, item_idx in enumerate(indices):
            self.draw_current_menu_row(
                rows[row_idx],
                row_idx == selected_row,
                item_idx in (current_indices or set()),
                self._menu_label(items[item_idx]),
                text_weight=self._menu_weight(items[item_idx], (item_weights or {}).get(item_idx) or "regular"),
            )

    def _draw_string_list_tft(
        self,
        items: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
        index_offset: int = 0,
        action_indices: set[int] | None = None,
    ) -> None:
        touch_layout = self._touch_list_geometry(visible_rows=4) if self.touch_layout_enabled else None
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

        if touch_layout is not None:
            content_left, content_right, content_top, content_bottom, row_h, _gap, _row_centers = touch_layout
            page_count = max(1, (total + visible - 1) // max(1, visible))
            current_page = (selected_idx // max(1, visible)) + 1
            self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)
        else:
            content_left, content_right, content_top, content_bottom, row_h = 0, self.display.width, panel_y, panel_h, 0

        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row and not self.touch_layout_enabled
            pressed = False
            is_action = item_idx in (action_indices or set())
            if touch_layout is not None:
                row_top = max(content_top, y - (row_h // 2))
                row_h_px = row_h
                row_w = max(1, content_right - content_left)
                draw_x = content_left
                draw_y = row_top
                draw_w = row_w
                draw_h = row_h_px
                if is_action:
                    draw_x += 12
                    draw_y += 10
                    draw_w = max(1, draw_w - 24)
                    draw_h = max(1, draw_h - 20)
                tap_index = item_idx + index_offset
                self._record_touch_target(
                    "row",
                    draw_x,
                    draw_y,
                    draw_w,
                    draw_h,
                    action_kind="tap_row",
                    index=tap_index,
                    label=self._menu_label(str(items[item_idx])),
                )
                pressed = self._touch_pressed(kind="row", index=tap_index)
                if is_action:
                    self._draw_touch_row_background(
                        draw_x,
                        draw_y,
                        draw_w,
                        draw_h,
                        current=item_idx in (current_indices or set()),
                        pressed=pressed,
                    )
                else:
                    self._draw_touch_list_item_background(
                        content_left,
                        row_top,
                        row_w,
                        row_h_px,
                        current=item_idx in (current_indices or set()),
                        pressed=pressed,
                    )
            if self.is_tiny_text_tft:
                self.draw_current_menu_row(
                    y,
                    selected or pressed,
                    item_idx in (current_indices or set()),
                    self._menu_label(str(items[item_idx])),
                    text_weight=self._menu_weight(str(items[item_idx]), (item_weights or {}).get(item_idx) or "regular"),
                )
                continue
            if not touch_layout and selected and not self.is_full_tft:
                self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
            current = item_idx in (current_indices or set())
            prefix = ">" if selected and not self.touch_layout_enabled else " "
            line_limit = self.text_cols - 3 if self.is_full_tft else 50
            label = self._menu_label(str(items[item_idx]))
            weight = self._menu_weight(label, self._current_row_weight((item_weights or {}).get(item_idx), current=current))
            text_y = y - (self._line_height(2, weight) // 2) if touch_layout is not None and self.is_full_tft else y
            if self.is_full_tft and not self.touch_layout_enabled:
                self._draw_full_tft_row(text_y, prefix, shorten(label, line_limit), selected=selected, text_weight=weight)
            else:
                if self.touch_layout_enabled and self.has_color:
                    scale = self._touch_menu_scale()
                    text_right_pad = 48 if not is_action else 16
                    fitted_label = self._truncate_to_width(label, max(1, draw_w - 32 - text_right_pad), scale, weight)
                    text_w, _text_h = self._measure_text(fitted_label, scale, weight)
                    text_x = draw_x + max(16, (draw_w - text_w) // 2) if is_action else content_left + 30
                    self._text_theme(fitted_label, text_x, y - (self._line_height(scale, weight) // 2), "text", scale, weight)
                    if not is_action:
                        self._draw_touch_row_chevron(content_left, row_top, row_w, row_h_px, scale)
                else:
                    self._text(f"{prefix} {shorten(label, line_limit)}"[: self.text_cols], 6, y, weight=weight)

    def _row_base_weight(self, row: MenuRow | ValueRow) -> str | None:
        if getattr(row, "action", False) and row.emphasis == "italic":
            return "semibold-italic"
        if getattr(row, "action", False):
            return "semibold"
        if row.emphasis:
            return row.emphasis
        return None

    def draw_menu_rows(self, rows: list[MenuRow], selected_idx: int) -> None:
        items = [row.label for row in rows]
        current_indices = {idx for idx, row in enumerate(rows) if row.current}
        action_indices = {idx for idx, row in enumerate(rows) if row.action}
        item_weights = {
            idx: weight
            for idx, row in enumerate(rows)
            if (weight := self._row_base_weight(row))
        }
        self.draw_string_list(
            items,
            selected_idx,
            current_indices=current_indices,
            item_weights=item_weights or None,
            action_indices=action_indices or None,
        )

    def draw_preset_list_with_footer(
        self,
        names: list[str],
        selected_idx: int,
        current_name: str,
        action_labels: list[str],
        empty_label: str = "no presets",
    ) -> None:
        if not self.touch_layout_enabled:
            return
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        touch_layout = self._touch_list_geometry(visible_rows=4)
        content_left, content_right, content_top, content_bottom, row_h, _gap, all_rows = touch_layout
        rows = all_rows[:3]
        visible = max(1, len(rows))
        total = len(names)
        selected_zero = max(0, selected_idx - 1)
        page_count = max(1, (max(0, total) + visible - 1) // visible)
        current_page = (selected_zero // visible) + 1 if total else 1
        self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)

        if total <= 0:
            y = rows[0]
            row_top = max(content_top, y - (row_h // 2))
            row_w = max(1, content_right - content_left)
            self._draw_touch_list_item_background(content_left, row_top, row_w, row_h)
            self._text_theme(
                empty_label,
                content_left + 30,
                y - (self._line_height(3, "regular") // 2),
                "muted",
                3,
                "regular",
            )
        else:
            selected_zero = min(selected_zero, total - 1)
            if total <= visible:
                indices = list(range(total))
            else:
                half = visible // 2
                start = max(0, min(selected_zero - half, total - visible))
                indices = list(range(start, start + visible))

            row_w = max(1, content_right - content_left)
            for row_idx, item_idx in enumerate(indices):
                y = rows[row_idx]
                row_top = max(content_top, y - (row_h // 2))
                label = self._menu_label(names[item_idx])
                tap_index = item_idx + 1
                self._record_touch_target(
                    "row",
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    action_kind="tap_row",
                    index=tap_index,
                    label=label,
                )
                pressed = self._touch_pressed(kind="row", index=tap_index)
                current = str(names[item_idx]) == str(current_name)
                self._draw_touch_list_item_background(content_left, row_top, row_w, row_h, current=current, pressed=pressed)
                text_w = self._truncate_to_width(label, max(1, row_w - 96), 3, "regular")
                self._text_theme(text_w, content_left + 30, y - (self._line_height(3, "regular") // 2), "text", 3, "regular")
                self._draw_touch_row_chevron(content_left, row_top, row_w, row_h, 3)

        if action_labels:
            labels = [label.replace("...", "") for label in action_labels]
            destructive_idx = labels.index("REMOVE") if "REMOVE" in labels else None
            self._draw_touch_footer_button_row(
                labels,
                content_left,
                content_right,
                all_rows[3] if len(all_rows) > 3 else content_bottom - (row_h // 2),
                row_h,
                destructive_idx=destructive_idx,
            )

    def _draw_touch_footer_button_row(
        self,
        labels: list[str],
        content_left: int,
        content_right: int,
        row_center_y: int,
        row_h: int,
        *,
        destructive_idx: int | None = None,
    ) -> None:
        if not labels:
            return
        button_h = max(1, row_h - 20)
        button_gap = 12 if len(labels) > 1 else 0
        available_w = max(1, content_right - content_left - 24 - button_gap * (len(labels) - 1))
        button_w = available_w // len(labels)
        start_x = content_left + 12
        button_y = max(0, row_center_y - (row_h // 2) + 10)
        for idx, label in enumerate(labels):
            button_x = start_x + idx * (button_w + button_gap)
            self._draw_choice_box(
                button_x,
                button_y,
                button_w,
                button_h,
                label,
                False,
                destructive=(destructive_idx is not None and idx == destructive_idx),
            )

    def draw_value_rows(self, rows: list[ValueRow]) -> None:
        for y, row in zip(self.content_rows, rows):
            self.draw_value_row(
                y,
                False,
                row.label,
                row.value,
                current=row.current,
                emphasis=self._row_base_weight(row),
            )

    def _draw_touch_label_value_row(
        self,
        content_left: int,
        row_top: int,
        row_w: int,
        row_h: int,
        row_center_y: int,
        label: str,
        value: str,
        *,
        text_weight: str = "regular",
        value_weight: str = "medium",
        value_prefix: str = "",
        value_prefix_color: str = "midi",
        show_chevron: bool = True,
    ) -> None:
        scale = self._touch_menu_scale()
        line_h = self._line_height(scale, text_weight)
        label_x = content_left + 16
        chevron_w, _chevron_h = self._measure_text(">", scale, value_weight)
        chevron_right_pad = 22
        chevron_x = content_left + max(0, row_w - chevron_w - chevron_right_pad)
        value_right = max(content_left + 120, chevron_x - 18)
        text_available_w = max(1, value_right - label_x)
        text_gap_w = min(28, max(0, text_available_w // 8))
        min_value_w = min(self._measure_text("...", scale, value_weight)[0], max(1, text_available_w - text_gap_w))
        natural_label_w = self._measure_text(label, scale, text_weight)[0]
        natural_value_w = self._measure_text(value, scale, value_weight)[0]
        if natural_label_w + text_gap_w + natural_value_w <= text_available_w:
            label_max_w = natural_label_w
            value_max_w = natural_value_w
        elif natural_label_w <= max(1, text_available_w - text_gap_w - min_value_w):
            label_max_w = natural_label_w
            value_max_w = max(1, text_available_w - text_gap_w - label_max_w)
        else:
            label_floor_w = min(max(1, text_available_w // 3), max(1, text_available_w - text_gap_w - min_value_w))
            value_max_w = min(
                natural_value_w,
                max(1, text_available_w - text_gap_w - label_floor_w),
            )
            fitted_value_probe = self._truncate_to_width(value, value_max_w, scale, value_weight)
            value_probe_w = self._measure_text(fitted_value_probe, scale, value_weight)[0]
            label_max_w = max(1, text_available_w - text_gap_w - value_probe_w)

        fitted_left = self._truncate_to_width(label, label_max_w, scale, text_weight)
        fitted_right = self._truncate_to_width(value, value_max_w, scale, value_weight)
        value_w, _value_h = self._measure_text(fitted_right, scale, value_weight)
        text_y = row_center_y - (line_h // 2)
        self._text_theme(fitted_left, label_x, text_y, "text", scale, text_weight)
        value_x = max(label_x, value_right - value_w)
        if value_prefix and fitted_right.startswith(f"{value_prefix} "):
            prefix_text = f"{value_prefix} "
            prefix_w, _prefix_h = self._measure_text(prefix_text, scale, value_weight)
            self._text_theme(prefix_text, value_x, text_y, value_prefix_color, scale, value_weight)
            self._text_theme(fitted_right[len(prefix_text) :], value_x + prefix_w, text_y, "muted", scale, value_weight)
        else:
            self._text_theme(fitted_right, value_x, text_y, "muted", scale, value_weight)
        if show_chevron:
            self._draw_touch_row_chevron(content_left, row_top, row_w, row_h, scale)

    def draw_selectable_value_rows(self, rows: list[ValueRow], selected_idx: int) -> None:
        if not rows:
            self.draw_string_list(["no instances"], 0)
            return
        if self.is_tft:
            self._draw_selectable_value_rows_tft(rows, selected_idx)
            return

        selected_zero = max(0, min(len(rows) - 1, selected_idx - 1))
        indices, selected_row, y_positions = self.list_window(selected_zero, len(rows))
        for row_idx, item_idx in enumerate(indices):
            row = rows[item_idx]
            self.draw_value_row(
                y_positions[row_idx],
                row_idx == selected_row,
                row.label,
                row.value,
                current=row.current,
                emphasis=self._row_base_weight(row),
            )

    def _draw_selectable_value_rows_tft(self, rows: list[ValueRow], selected_idx: int) -> None:
        touch_layout = self._touch_list_geometry(visible_rows=4) if self.touch_layout_enabled else None
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        y_positions = self._panel_list_rows(panel_y, panel_h)
        visible = len(y_positions)
        total = len(rows)
        if total <= 0 or visible <= 0:
            return

        selected_zero = max(0, min(total - 1, selected_idx - 1))
        if total <= visible:
            indices = list(range(total))
            selected_row = selected_zero
        else:
            half = visible // 2
            start = max(0, min(selected_zero - half, total - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_zero - start

        if touch_layout is not None:
            content_left, content_right, content_top, content_bottom, row_h, _gap, _rows = touch_layout
            page_count = max(1, (total + visible - 1) // max(1, visible))
            current_page = (selected_zero // max(1, visible)) + 1
            self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)
        else:
            content_left, content_right, content_top, content_bottom, row_h = 0, self.display.width, panel_y, panel_h, 0

        left_cols, right_cols = self._tft_value_columns()
        for row_idx, item_idx in enumerate(indices):
            y = y_positions[row_idx]
            row = rows[item_idx]
            selected = row_idx == selected_row and not self.touch_layout_enabled
            pressed = False
            text_weight = self._current_row_weight(row.emphasis or None, current=row.current)
            if self.is_full_tft and not self.touch_layout_enabled:
                self._draw_full_tft_row(
                    y,
                    ">" if selected else " ",
                    shorten(str(row.label), self.value_name_cols),
                    shorten(str(row.value), self.value_cols),
                    selected=selected,
                    text_weight=text_weight,
                )
            else:
                if touch_layout is not None:
                    row_top = max(content_top, y - (row_h // 2))
                    row_w = max(1, content_right - content_left)
                    self._record_touch_target(
                        "row",
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        action_kind="tap_row",
                        index=item_idx + 1,
                        label=self._menu_label(str(row.label)),
                    )
                    pressed = self._touch_pressed(kind="row", index=item_idx + 1)
                    self._draw_touch_list_item_background(
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        current=row.current,
                        pressed=pressed,
                    )
                elif selected and not self.is_tiny_text_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                left = self._menu_label(shorten(str(row.label), left_cols))
                right = shorten(str(row.value), right_cols)
                line = f"{'> ' if selected else '  '}{left:<{left_cols}} {right:>{right_cols}}"[: self.text_cols]
                if self.touch_layout_enabled and self.has_color:
                    row_w = max(1, content_right - content_left)
                    label = self._menu_label(str(row.label))
                    value = str(row.value)
                    self._draw_touch_label_value_row(
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        y,
                        label,
                        value,
                        text_weight=text_weight,
                    )
                else:
                    self._text(line, 6, y, weight=text_weight)

    def draw_param_list(self, params: list[dict], selected_idx: int) -> None:
        if self.is_tft:
            self._draw_param_list_tft(params, selected_idx)
            return
        if self.touch_layout_enabled:
            indices, selected_row, rows = self.list_window(max(0, selected_idx - 1), len(params))
            for row_idx, item_idx in enumerate(indices):
                self.draw_param_value_row(rows[row_idx], row_idx == selected_row, params[item_idx])
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
        if self.is_tiny_text_tft:
            return 9, 5
        right_cols = max(6, min(12, (self.text_cols - 4) // 3))
        left_cols = max(8, self.text_cols - right_cols - 3)
        return left_cols, right_cols

    def _draw_param_list_tft(self, params: list[dict], selected_idx: int) -> None:
        touch_layout = self._touch_list_geometry(visible_rows=4) if self.touch_layout_enabled else None
        if self.touch_layout_enabled:
            items = list(params)
            selected_idx = max(0, selected_idx - 1)
        else:
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

        if touch_layout is not None:
            content_left, content_right, content_top, content_bottom, row_h, _gap, _rows = touch_layout
            page_count = max(1, (max(0, total - 1) + visible - 1) // max(1, visible))
            current_page = (max(0, selected_idx - 1) // max(1, visible)) + 1
            self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)
        else:
            content_left, content_right, content_top, content_bottom, row_h = 0, self.display.width, panel_y, panel_h, 0

        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row and not self.touch_layout_enabled
            pressed = False
            if not self.touch_layout_enabled and item_idx == 0:
                if touch_layout is not None:
                    row_top = max(content_top, y - (row_h // 2))
                    row_w = max(1, content_right - content_left)
                    self._record_touch_target(
                        "row",
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        action_kind="tap_row",
                        index=0,
                        label="..",
                    )
                    pressed = self._touch_pressed(kind="row", index=0)
                    self._draw_touch_row_background(content_left, row_top, row_w, row_h, pressed=pressed)
                if selected and not self.is_full_tft and not self.is_tiny_text_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
                if self.is_full_tft and not self.touch_layout_enabled:
                    self._draw_full_tft_row(y, ">" if selected else " ", "..", selected=selected)
                else:
                    if self.touch_layout_enabled and self.has_color:
                        scale = self._touch_menu_scale()
                        self._text_theme("..", content_left + 16, y - (self._line_height(scale, "medium") // 2), "text", scale, "medium")
                    else:
                        self._text(("> " if selected else "  ") + "..", 6, y)
            else:
                param = items[item_idx]
                prefix = "> " if selected else "  "
                left_cols, right_cols = self._tft_value_columns()
                if touch_layout is not None:
                    row_top = max(content_top, y - (row_h // 2))
                    row_w = max(1, content_right - content_left)
                    tap_index = item_idx + (1 if self.touch_layout_enabled else 0)
                    self._record_touch_target(
                        "row",
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        action_kind="tap_row",
                        index=tap_index,
                        label=self._menu_label(shorten_param_name(param.get("name", ""))),
                    )
                    pressed = self._touch_pressed(kind="row", index=tap_index)
                    self._draw_touch_list_item_background(content_left, row_top, row_w, row_h, pressed=pressed)
                if selected and not self.is_full_tft and not self.is_tiny_text_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 12 if self.is_full_tft else 8, True, False)
                full_left = self._menu_label(shorten_param_name(param.get("name", "")))
                full_right = format_param_value_with_midi(param, param.get("value"))
                midi_marker = param_midi_mapping_marker(param)
                left = shorten(full_left, left_cols)
                right = shorten(full_right, right_cols)
                row = f"{prefix}{left:<{left_cols}} {right:>{right_cols}}"[: self.text_cols]
                if self.is_full_tft and not self.touch_layout_enabled:
                    self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected)
                else:
                    if self.touch_layout_enabled and self.has_color:
                        self._draw_touch_label_value_row(
                            content_left,
                            row_top,
                            row_w,
                            row_h,
                            y,
                            full_left,
                            full_right,
                            text_weight="regular",
                            value_prefix=midi_marker,
                        )
                    else:
                        self._text(row, 6, y)

    def draw_preset_list(self, ui, presets: list[dict], selected_idx: int) -> None:
        current_indices = {
            idx + 1 for idx, item in enumerate(presets) if str(item.get("name", "")) == ui.current_preset_name
        }
        self.draw_string_list([".."] + [str(item.get("name", "")) for item in presets], selected_idx, current_indices=current_indices)

    def draw_instance_list(self, ui) -> None:
        if self.touch_layout_enabled:
            self._draw_instance_list_touch(ui)
            return
        self.draw_menu_rows(ui.instance_rows, ui.state.instance_cursor)

    def _draw_instance_list_touch(self, ui) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        labels = [str(item.get("label", "")) for item in ui.state.instances]
        current_indices = {idx - 1 for idx in ui.instance_current_indices if idx > 0}
        selected_zero = max(0, ui.state.instance_cursor - 1)
        list_items = labels if labels else ["no instances"]
        list_selected = min(selected_zero, max(0, len(list_items) - 1))

        touch_layout = self._touch_list_geometry(visible_rows=4)
        content_left, content_right, content_top, content_bottom, row_h, _gap, all_rows = touch_layout
        rows = all_rows[:3]
        visible = max(1, len(rows))
        page_count = max(1, (max(0, len(labels)) + visible - 1) // visible)
        current_page = (max(0, selected_zero) // visible) + 1 if labels else 1
        self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)

        total_items = len(list_items)
        if total_items <= visible:
            indices = list(range(total_items))
            selected_row = list_selected
        else:
            half = visible // 2
            start = max(0, min(list_selected - half, total_items - visible))
            indices = list(range(start, start + visible))
            selected_row = list_selected - start
        row_positions = rows[: len(indices)]
        for row_idx, item_idx in enumerate(indices):
            y = row_positions[row_idx]
            instance_idx = item_idx
            tap_index = item_idx + 1
            row_top = max(content_top, y - (row_h // 2))
            row_w = max(1, content_right - content_left)
            if not (0 <= instance_idx < len(labels)):
                self._draw_touch_list_item_background(content_left, row_top, row_w, row_h)
                self._text_theme(
                    "no instances",
                    content_left + 30,
                    y - (self._line_height(3, "regular") // 2),
                    "muted",
                    3,
                    "regular",
                )
                continue

            label = self._menu_label(labels[instance_idx])
            self._record_touch_target(
                "row",
                content_left,
                row_top,
                row_w,
                row_h,
                action_kind="tap_row",
                index=tap_index,
                label=label,
            )
            pressed = self._touch_pressed(kind="row", index=tap_index)
            self._draw_touch_list_item_background(
                content_left,
                row_top,
                row_w,
                row_h,
                current=(instance_idx + 1) in ui.instance_current_indices,
                pressed=pressed,
            )
            text_w = self._truncate_to_width(label, max(1, row_w - 96), 3, "regular")
            self._text_theme(text_w, content_left + 30, y - (self._line_height(3, "regular") // 2), "text", 3, "regular")
            self._draw_touch_row_chevron(content_left, row_top, row_w, row_h, 3)

        action_labels = []
        action_indices = {}
        if ui.can_add_instance:
            action_labels.append("Add")
            action_indices["add_instance"] = len(labels) + 1
        if ui.can_remove_instances:
            action_labels.append("Remove")
            action_indices["remove_instance"] = len(labels) + 1 + (1 if ui.can_add_instance else 0)

        if not action_labels:
            return

        self._draw_touch_footer_button_row(
            action_labels,
            content_left,
            content_right,
            all_rows[3] if len(all_rows) > 3 else panel_y + panel_h - (row_h // 2),
            row_h,
        )

    def _draw_instance_list_tft(self, items: list[str], selected_idx: int, action_start: int, current_indices: set[int] | None = None) -> None:
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
            base_weight = "semibold" if item_idx >= action_start else None
            text_weight = self._current_row_weight(base_weight, current=item_idx in (current_indices or set()))
            if self.is_full_tft and not self.touch_layout_enabled:
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
            self._draw_routing_list_tft(ports, selected_idx, current_indices=self._ui.routing_port_current_indices if hasattr(self, "_ui") else None)
            return
        if self.touch_layout_enabled:
            selected_zero = max(0, selected_idx - 1)
            indices, selected_row, rows = self.list_window(selected_zero, len(ports))
            for row_idx, item_idx in enumerate(indices):
                port = ports[item_idx]
                value = port.get("connections", [])
                self.draw_value_row(
                    rows[row_idx],
                    row_idx == selected_row,
                    routing_port_display_name(port),
                    value,
                    current=(item_idx + 1) in (self._ui.routing_port_current_indices if hasattr(self, "_ui") else set()),
                )
            return
        indices, selected_row, rows = self.list_window(selected_idx, len(ports) + 1)
        for row_idx, item_idx in enumerate(indices):
            if item_idx == 0:
                self.draw_menu_row(rows[row_idx], row_idx == selected_row, "..")
            else:
                port = ports[item_idx - 1]
                value = port.get("connections", [])
                self.draw_value_row(
                    rows[row_idx],
                    row_idx == selected_row,
                    routing_port_display_name(port),
                    value,
                    current=item_idx in (self._ui.routing_port_current_indices if hasattr(self, "_ui") else set()),
                )

    def _draw_routing_list_tft(self, ports: list[dict], selected_idx: int, current_indices: set[int] | None = None) -> None:
        touch_layout = self._touch_list_geometry(visible_rows=4) if self.touch_layout_enabled else None
        if self.touch_layout_enabled:
            items = list(ports)
            selected_idx = max(0, selected_idx - 1)
        else:
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

        if touch_layout is not None:
            content_left, content_right, content_top, content_bottom, row_h, _gap, _rows = touch_layout
            page_count = max(1, (max(0, total - 1) + visible - 1) // max(1, visible))
            current_page = (max(0, selected_idx - 1) // max(1, visible)) + 1
            self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)
        else:
            content_left, content_right, content_top, content_bottom, row_h = 0, self.display.width, panel_y, panel_h, 0

        left_cols, right_cols = self._tft_value_columns()
        for row_idx, item_idx in enumerate(indices):
            y = rows[row_idx]
            selected = row_idx == selected_row and not self.touch_layout_enabled
            pressed = False
            if not self.touch_layout_enabled and item_idx == 0:
                if touch_layout is not None:
                    row_top = max(content_top, y - (row_h // 2))
                    row_w = max(1, content_right - content_left)
                    self._record_touch_target(
                        "row",
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        action_kind="tap_row",
                        index=0,
                        label="..",
                    )
                    pressed = self._touch_pressed(kind="row", index=0)
                    self._draw_touch_row_background(content_left, row_top, row_w, row_h, pressed=pressed)
                if selected and not self.is_full_tft and not self.is_tiny_text_tft:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                if self.is_full_tft:
                    self._draw_full_tft_row(y, ">" if selected else " ", "..", selected=selected)
                else:
                    self._text(("> " if selected else "  ") + "..", 6, y)
                continue

            port = items[item_idx]
            if self.touch_layout_enabled:
                left = self._menu_label(shorten_param_name(routing_port_display_name(port)))
                right = format_display_value(port.get("connections", []))
            else:
                left = shorten(shorten_param_name(routing_port_display_name(port)), left_cols)
                right = shorten(format_display_value(port.get("connections", [])), right_cols)
            text_weight = self._current_row_weight(current=item_idx in (current_indices or set()))
            if touch_layout is not None:
                row_top = max(content_top, y - (row_h // 2))
                row_w = max(1, content_right - content_left)
                tap_index = item_idx + (1 if self.touch_layout_enabled else 0)
                self._record_touch_target(
                    "row",
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    action_kind="tap_row",
                    index=tap_index,
                    label=self._menu_label(str(left)),
                )
                pressed = self._touch_pressed(kind="row", index=tap_index)
                self._draw_touch_list_item_background(
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    current=item_idx in (current_indices or set()),
                    pressed=pressed,
                )
            if self.is_full_tft and not self.touch_layout_enabled:
                self._draw_full_tft_row(y, ">" if selected else " ", left, right, selected, text_weight=text_weight)
            else:
                if selected and not self.is_tiny_text_tft and not self.touch_layout_enabled:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                row = f"{'> ' if selected else '  '}{left:<{left_cols}} {right:>{right_cols}}"[: self.text_cols]
                if self.touch_layout_enabled and self.has_color:
                    row_w = max(1, content_right - content_left)
                    self._draw_touch_label_value_row(
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        y,
                        left,
                        right,
                        text_weight=text_weight,
                    )
                else:
                    self._text(row, 6, y, weight=text_weight)

    def draw_routing_targets(self, ui, selected_idx: int) -> None:
        if self.touch_layout_enabled:
            self._draw_routing_assignments_touch(ui, selected_idx)
            return
        self.draw_menu_rows(ui.routing_assignment_rows, selected_idx)

    def _draw_routing_assignments_touch(self, ui, selected_idx: int) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        touch_layout = self._touch_list_geometry(visible_rows=4)
        content_left, content_right, content_top, content_bottom, row_h, _gap, all_rows = touch_layout
        rows = all_rows[:3]
        visible = max(1, len(rows))
        assignments = ui.current_routing_targets
        selected_zero = max(0, selected_idx - 1)
        page_count = max(1, (max(0, len(assignments)) + visible - 1) // visible)
        current_page = (selected_zero // visible) + 1 if assignments else 1
        self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)

        row_w = max(1, content_right - content_left)
        if not assignments:
            y = rows[0]
            row_top = max(content_top, y - (row_h // 2))
            self._draw_touch_list_item_background(content_left, row_top, row_w, row_h)
            self._text_theme(
                "no assignments",
                content_left + 30,
                y - (self._line_height(3, "regular") // 2),
                "muted",
                3,
                "regular",
            )
        else:
            selected_zero = min(selected_zero, len(assignments) - 1)
            if len(assignments) <= visible:
                indices = list(range(len(assignments)))
            else:
                half = visible // 2
                start = max(0, min(selected_zero - half, len(assignments) - visible))
                indices = list(range(start, start + visible))
            for row_idx, item_idx in enumerate(indices):
                y = rows[row_idx]
                row_top = max(content_top, y - (row_h // 2))
                label = self._menu_label(str(assignments[item_idx]))
                tap_index = item_idx + 1
                self._record_touch_target(
                    "row",
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    action_kind="tap_row",
                    index=tap_index,
                    label=label,
                )
                pressed = self._touch_pressed(kind="row", index=tap_index)
                self._draw_touch_list_item_background(content_left, row_top, row_w, row_h, current=True, pressed=pressed)
                fitted = self._truncate_to_width(label, max(1, row_w - 96), 3, "regular")
                self._text_theme(fitted, content_left + 30, y - (self._line_height(3, "regular") // 2), "text", 3, "regular")

        self._draw_touch_footer_button_row(
            ["Add", "Remove"],
            content_left,
            content_right,
            all_rows[3] if len(all_rows) > 3 else panel_y + panel_h - (row_h // 2),
            row_h,
            destructive_idx=1 if assignments else None,
        )

    def draw_routing_target_picker(self, labels: list[str], selected_idx: int, empty_label: str = "no targets") -> None:
        items = [".."] + labels if labels else ["..", empty_label]
        action_indices = set(range(1, len(items))) if labels else None
        self.draw_string_list(items, selected_idx, action_indices=action_indices)

    def draw_legacy_routing_targets(self, ui, selected_idx: int) -> None:
        port = ui.selected_routing_port
        labels = [row.label for row in ui.routing_target_rows]
        current_indices = {idx for idx, row in enumerate(ui.routing_target_rows) if row.current}
        item_weights = {
            idx: weight
            for idx, row in enumerate(ui.routing_target_rows)
            if (weight := self._row_base_weight(row))
        }
        if self.is_tft:
            self._draw_routing_targets_tft(
                port,
                labels,
                selected_idx,
                current_indices=current_indices,
                item_weights=item_weights or None,
            )
            return
        self.draw_string_list(labels, selected_idx, current_indices=current_indices, item_weights=item_weights or None)
        if port and self.is_tall:
            current = port.get("connections", [])
            current_text = "none" if not current else shorten(format_display_value(current), self.title_cols)
            self.text_center(current_text, self.content_rows[-1] + 2 if self.is_tft else 56)

    def _draw_routing_targets_touch(
        self,
        port: dict | None,
        labels: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        touch_layout = self._touch_list_geometry(visible_rows=4)
        content_left, content_right, content_top, content_bottom, row_h, _gap, all_rows = touch_layout
        target_labels = labels[2:]
        target_current_indices = {idx - 2 for idx in (current_indices or set()) if idx >= 2}
        target_weights = {idx - 2: weight for idx, weight in (item_weights or {}).items() if idx >= 2}
        selected_zero = max(0, selected_idx - 2)
        rows = all_rows[:3]
        visible = max(1, len(rows))
        total_targets = len(target_labels)
        page_count = max(1, (max(0, total_targets) + visible - 1) // visible)
        current_page = (max(0, selected_zero) // visible) + 1 if total_targets else 1
        self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)

        if total_targets <= 0:
            indices = [0]
            selected_row = 0
            display_labels = ["no targets"]
        elif total_targets <= visible:
            indices = list(range(total_targets))
            selected_row = min(selected_zero, total_targets - 1)
            display_labels = target_labels
        else:
            half = visible // 2
            start = max(0, min(selected_zero - half, total_targets - visible))
            indices = list(range(start, start + visible))
            selected_row = selected_zero - start
            display_labels = target_labels

        for row_idx, item_idx in enumerate(indices[:visible]):
            y = rows[row_idx]
            row_top = max(content_top, y - (row_h // 2))
            row_w = max(1, content_right - content_left)
            if total_targets <= 0:
                self._draw_touch_list_item_background(content_left, row_top, row_w, row_h)
                self._text_theme(
                    "no targets",
                    content_left + 30,
                    y - (self._line_height(3, "regular") // 2),
                    "muted",
                    3,
                    "regular",
                )
                continue

            label = self._menu_label(str(display_labels[item_idx]))
            tap_index = item_idx + 2
            self._record_touch_target(
                "row",
                content_left,
                row_top,
                row_w,
                row_h,
                action_kind="tap_row",
                index=tap_index,
                label=label,
            )
            pressed = self._touch_pressed(kind="row", index=tap_index)
            current = item_idx in target_current_indices
            weight = self._current_row_weight(target_weights.get(item_idx), current=current)
            self._draw_touch_list_item_background(
                content_left,
                row_top,
                row_w,
                row_h,
                current=current,
                pressed=pressed,
            )
            fitted = self._truncate_to_width(label, max(1, row_w - 96), 3, weight)
            self._text_theme(fitted, content_left + 30, y - (self._line_height(3, weight) // 2), "text", 3, weight)
            self._draw_touch_row_chevron(content_left, row_top, row_w, row_h, 3)

        disconnect_label = self._menu_label(labels[1] if len(labels) > 1 else "DISCONNECT")
        button_h = max(1, row_h - 20)
        button_w = min(320, panel_w - 80)
        button_x = panel_x + max(0, (panel_w - button_w) // 2)
        button_y = max(content_top, all_rows[3] - (row_h // 2) + 10) if len(all_rows) > 3 else panel_y + panel_h - button_h - 10
        self._draw_choice_box(
            button_x,
            button_y,
            button_w,
            button_h,
            disconnect_label,
            selected_idx == 1 or 1 in (current_indices or set()),
            destructive=bool(port and port.get("connections")),
        )

    def _draw_routing_targets_tft(
        self,
        port: dict | None,
        labels: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        if self.touch_layout_enabled:
            self._draw_routing_targets_touch(port, labels, selected_idx, current_indices, item_weights)
            return

        touch_layout = self._touch_list_geometry(visible_rows=4) if self.touch_layout_enabled else None
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)

        rows = self._panel_list_rows(panel_y, panel_h)
        if self.touch_layout_enabled:
            labels = labels[1:]
            current_indices = {idx - 1 for idx in (current_indices or set()) if idx > 0}
            item_weights = {idx - 1: weight for idx, weight in (item_weights or {}).items() if idx > 0}
            selected_idx = max(0, selected_idx - 1)
        elif rows:
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

            if touch_layout is not None:
                content_left, content_right, content_top, content_bottom, row_h, _gap, _rows = touch_layout
                page_count = max(1, (total + visible - 1) // max(1, visible))
                current_page = (selected_idx // max(1, visible)) + 1
                self._draw_touch_page_rail(content_top, content_bottom, current_page, page_count)
            else:
                content_left, content_right, content_top, content_bottom, row_h = 0, self.display.width, panel_y, panel_h, 0

            for row_idx, item_idx in enumerate(indices):
                y = rows[row_idx]
                selected = row_idx == selected_row and not self.touch_layout_enabled
                pressed = False
                if touch_layout is not None:
                    row_top = max(content_top, y - (row_h // 2))
                    row_w = max(1, content_right - content_left)
                    tap_index = item_idx + (1 if self.touch_layout_enabled else 0)
                    self._record_touch_target(
                        "row",
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        action_kind="tap_row",
                        index=tap_index,
                        label=self._menu_label(str(labels[item_idx])),
                    )
                    pressed = self._touch_pressed(kind="row", index=tap_index)
                    self._draw_touch_list_item_background(
                        content_left,
                        row_top,
                        row_w,
                        row_h,
                        current=item_idx in (current_indices or set()),
                        pressed=pressed,
                    )
                if selected and not self.is_full_tft and not self.touch_layout_enabled:
                    self.display.rect(2, y - 2, max(0, self.display.width - 4), 8, True, False)
                current = item_idx in (current_indices or set())
                prefix = ">" if selected else " "
                line_limit = self.text_cols - 3 if self.is_full_tft else 50
                weight = self._current_row_weight((item_weights or {}).get(item_idx), current=current)
                if self.is_full_tft and not self.touch_layout_enabled:
                    self._draw_full_tft_row(y, prefix, shorten(self._menu_label(str(labels[item_idx])), line_limit), selected=selected, text_weight=weight)
                else:
                    label = self._menu_label(str(labels[item_idx]))
                    if self.touch_layout_enabled and self.has_color:
                        scale = self._touch_menu_scale()
                        row_w = max(1, content_right - content_left)
                        fitted = self._truncate_to_width(label, max(1, row_w - 96), scale, weight)
                        self._text_theme(fitted, content_left + 30, y - (self._line_height(scale, weight) // 2), "text", scale, weight)
                        self._draw_touch_row_chevron(content_left, row_top, row_w, row_h, scale)
                    else:
                        self._text(f"{prefix} {shorten(label, line_limit)}"[: self.text_cols], 6, y, weight=weight)

        if not port:
            return
        if self.touch_layout_enabled:
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

    def _midi_mapping_label(self, ui, param: dict | None) -> str:
        if not isinstance(param, dict):
            return "MIDI unmapped"
        path = str(param.get("path", "") or "")
        if (
            path
            and str(getattr(ui.state, "midi_learn_param_path", "") or "") == path
            and str(getattr(ui.state, "midi_learn_instance_id", "") or "") == str(ui.state.active_instance_id)
        ):
            return "MIDI learn: move a control"
        metadata = param.get("metadata", {})
        midi = metadata.get("midi") if isinstance(metadata, dict) else None
        if not isinstance(midi, dict):
            return "MIDI unmapped"
        chan = midi.get("chan")
        ctrl = midi.get("ctrl")
        if chan is None or ctrl is None:
            return "MIDI unmapped"
        try:
            chan = int(float(chan))
            ctrl = int(float(ctrl))
        except (TypeError, ValueError):
            return "MIDI unmapped"
        return f"MIDI ch {chan} CC {ctrl}"

    def _draw_edit_midi_controls(self, ui, param: dict | None) -> None:
        label = self._midi_mapping_label(ui, param)
        if self.touch_layout_enabled and self.has_color:
            panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
            text_scale = 2 if self.is_five_inch_touch else 1
            weight = "medium"
            label = self._truncate_to_width(label, max(1, panel_w - 64), text_scale, weight)
            text_w, text_h = self._measure_text(label, text_scale, weight)
            text_x = panel_x + max(0, (panel_w - text_w) // 2)
            button_y = panel_y + panel_h - 68
            text_y = max(panel_y + 4, button_y - text_h - 14)
            self._text_theme(label, text_x, text_y, "muted", text_scale, weight)
            self._draw_modal_button_row(["LEARN", "CLEAR"], y=button_y, destructive_idx=1)
            return

        if self.is_full_tft:
            self.text_center_scaled(shorten(label, 30), self.content_bottom - 56, 1)
            return
        if self.is_tft:
            self.text_center(shorten(label, self.title_cols), self.content_bottom - 28)
            return
        self._text(shorten(label, self.text_cols), 0, max(0, self.display.height - 8))

    def _draw_touch_edit_value_readout(self, param: dict | None, value: Any, slider_y: int) -> bool:
        if not self.touch_layout_enabled:
            return False

        text = format_param_value(param, value)
        if text in ("", "-"):
            return False

        right_edge = self.display.width - 24
        left_edge = 24
        top = self.content_top + 12
        bottom = max(top + 1, slider_y - 10)
        max_w = max(1, right_edge - left_edge)
        max_h = max(1, bottom - top)
        weight = "semibold"
        scale = 5 if self.is_five_inch_touch else 2

        while scale > 1:
            text_w, text_h = self._measure_text(text, scale, weight)
            if text_w <= max_w and text_h <= max_h:
                break
            scale -= 1

        text = self._truncate_to_width(text, max_w, scale, weight)
        text_w, text_h = self._measure_text(text, scale, weight)

        if "." in text:
            dot_idx = text.find(".")
            left_text = text[:dot_idx]
            right_text = text[dot_idx:]
            right_w, _ = self._measure_text(right_text, scale, weight)
            left_w, _ = self._measure_text(left_text, scale, weight)
            decimal_x = right_edge - right_w
            x = decimal_x - left_w
        else:
            x = right_edge - text_w
        x = max(left_edge, min(x, right_edge - text_w))
        y = top + max(0, (max_h - text_h) // 2)

        if self.has_color:
            self._text_theme(text, x, y, "text", scale, weight)
        else:
            self._text(text, x, y, scale, weight)
        return True

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

    def _fill_rect_level(self, x: int, y: int, w: int, h: int, level: int) -> None:
        fill_rect_level = getattr(self.display, "fill_rect_level", None)
        if callable(fill_rect_level):
            fill_rect_level(x, y, w, h, level)
            return
        self._fill_rect(x, y, w, h, level >= 128)

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

    def _draw_polyline(self, points: list[tuple[int, int]], on: bool = True) -> None:
        if len(points) < 2:
            return
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            dx = abs(x1 - x0)
            dy = -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            x = x0
            y = y0
            while True:
                self.display.pixel(x, y, on)
                if x == x1 and y == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x += sx
                if e2 <= dx:
                    err += dx
                    y += sy

    def _scope_time_label(self, sample_count: int, sample_rate: Any) -> str:
        seconds = scope_time_seconds(sample_count, sample_rate)
        if seconds is None:
            return "--"
        if seconds < 1.0:
            return f"{seconds * 1000:.1f}ms"
        return f"{seconds:.3f}s"

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

    def _draw_choice_box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        active: bool,
        *,
        destructive: bool = False,
    ) -> None:
        label = self._menu_label(str(label))
        if self.touch_layout_enabled:
            button_id = re.sub(r"\s+", "_", label.strip().lower())
            pressed = self._touch_pressed(kind="modal_button", button_id=button_id)
            self._record_touch_target(
                "modal_button",
                x,
                y,
                max(1, w),
                max(1, h),
                action_kind="tap_button",
                button_id=button_id,
                label=str(label),
            )
            if pressed and not self.has_color:
                self.display.rect(x, y, max(1, w), max(1, h), True, True)
        text_scale = 3 if self.touch_layout_enabled else 1
        if self.touch_layout_enabled:
            active = False
        weight = "semibold" if active else "medium"
        if self.touch_layout_enabled and self.has_color:
            pressed = self._touch_pressed(kind="modal_button", button_id=button_id)
            if pressed:
                fill_color = "panel_pressed"
                border_color = "danger" if destructive else "accent"
                text_color = "text"
                weight = "semibold"
            elif active:
                fill_color = "danger" if destructive else "accent"
                border_color = fill_color
                text_color = "bg"
            else:
                fill_color = "panel_alt"
                border_color = "danger" if destructive else "line"
                text_color = "danger" if destructive else "text"
            self._rounded_theme(x, y, max(1, w), max(1, h), 10, fill_color, fill=True)
            self._rounded_theme(x, y, max(1, w), max(1, h), 10, border_color, fill=False)
            text_w, text_h = self._measure_text(label, text_scale, weight)
            tx = x + max(0, (w - text_w) // 2)
            ty = y + max(0, (h - text_h) // 2)
            self._text_theme(label, tx, ty, text_color, text_scale, weight)
            return
        if self.is_full_tft:
            self.display.rect(x, y, max(1, w), max(1, h), True, False)
            prefix = "> " if active else "  "
            self._text(prefix + label, x, y, 2, "medium" if active else "regular")
            return
        self.display.rect(x, y, w, h, True, active)
        text_w, text_h = self._measure_text(label, text_scale, weight)
        tx = x + max(0, (w - text_w) // 2)
        ty = y + max(0, (h - text_h) // 2)
        self._text(label, tx, ty, text_scale, weight)

    def _draw_modal_button_row(
        self,
        labels: list[str],
        selected_idx: int = 0,
        *,
        y: int | None = None,
        destructive_idx: int | None = None,
    ) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        if y is None:
            button_h = 56 if self.touch_layout_enabled else 44 if self.is_full_tft else 24
            y = panel_y + panel_h - button_h - (24 if self.touch_layout_enabled else 30 if self.is_full_tft else 16)
        else:
            button_h = 56 if self.touch_layout_enabled else 44 if self.is_full_tft else 24

        count = max(1, len(labels))
        if count == 1:
            if self.touch_layout_enabled:
                button_w = min(panel_w - 80, 320)
            else:
                button_w = min(panel_w - 32, 260 if self.is_full_tft else 96)
            x_positions = [panel_x + max(0, (panel_w - button_w) // 2)]
        else:
            gap = 18 if self.touch_layout_enabled else 20 if self.is_full_tft else 10
            if self.touch_layout_enabled:
                button_w = min((panel_w - 72 - gap * (count - 1)) // count, 220)
            else:
                button_w = min(
                    (panel_w - 32 - gap * (count - 1)) // count,
                    180 if self.is_full_tft else 76,
                )
            total_w = button_w * count + gap * (count - 1)
            start_x = panel_x + max(16, (panel_w - total_w) // 2)
            x_positions = [start_x + idx * (button_w + gap) for idx in range(count)]

        for idx, label in enumerate(labels):
            self._draw_choice_box(
                x_positions[idx],
                y,
                button_w,
                button_h,
                label,
                idx == selected_idx,
                destructive=(destructive_idx is not None and idx == destructive_idx),
            )

    def _draw_modal_screen(
        self,
        ui,
        title: str,
        buttons: list[str],
        selected_idx: int,
        *,
        body_lines: list[str] | None = None,
        destructive_idx: int | None = None,
    ) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
        title = self._menu_label(title)
        if self.is_five_inch_touch and self.has_color:
            card_x = panel_x + 28
            card_y = panel_y + 24
            card_w = panel_w - 56
            card_h = min(panel_h - 48, 332)
            self._rounded_theme(card_x, card_y, card_w, card_h, 18, "panel", fill=True)
            self._rounded_theme(card_x, card_y, card_w, card_h, 18, "line", fill=False)
            if title:
                title_scale = 3
                title_w, title_h = self._measure_text(title, title_scale, "semibold")
                title_x = card_x + max(0, (card_w - title_w) // 2)
                self._text_theme(title, title_x, card_y + 22, "text", title_scale, "semibold")
            if body_lines:
                body_scale = 2
                body_y = card_y + 92
                for idx, line in enumerate(body_lines):
                    line = self._truncate_to_width(str(line), max(0, card_w - 56), body_scale, "medium")
                    weight = "semibold" if idx == len(body_lines) - 1 and len(body_lines) > 1 else "medium"
                    color = "text" if idx == len(body_lines) - 1 and len(body_lines) > 1 else "muted"
                    line_w, _line_h = self._measure_text(line, body_scale, weight)
                    line_x = card_x + max(0, (card_w - line_w) // 2)
                    self._text_theme(line, line_x, body_y + idx * 30, color, body_scale, weight)
            self._draw_modal_button_row(buttons, selected_idx, y=card_y + card_h - (56 + 24), destructive_idx=destructive_idx)
            return
        if title:
            if self.is_full_tft:
                self.text_center_scaled(shorten(title, 28), panel_y + 20, 2)
            else:
                self.text_center(shorten(title, self.title_cols), panel_y + 12)
        if body_lines:
            line_y = panel_y + (58 if self.is_full_tft else 28)
            for idx, line in enumerate(body_lines):
                if self.is_full_tft:
                    self.text_center_scaled(shorten(line, 30), line_y + idx * 24, 1)
                else:
                    self.text_center(shorten(line, self.title_cols), line_y + idx * 12)
        self._draw_modal_button_row(buttons, selected_idx)

    def draw_name_overwrite_confirm(self, ui) -> None:
        draft = ui.state.name_editor_draft or "(empty)"
        self._draw_modal_screen(
            ui,
            "OVERWRITE?",
            NAME_OVERWRITE_CONFIRM_BUTTONS,
            ui.state.name_overwrite_cursor,
            body_lines=["Replace the saved name with", f"{draft}"],
            destructive_idx=1,
        )

    def draw_name_error(self, ui) -> None:
        self._draw_modal_screen(
            ui,
            ui.name_error_title,
            NAME_ERROR_BUTTONS,
            0,
            body_lines=["Tap to edit the name"],
        )

    def draw_remove_instance_confirm(self, ui) -> None:
        target = ui.remove_instance_target
        label = str(target.get("label", "") or target.get("name", "") or target.get("id", "")) if target else "instance"
        self._draw_modal_screen(
            ui,
            "REMOVE?",
            REMOVE_INSTANCE_CONFIRM_BUTTONS,
            ui.state.remove_instance_confirm_cursor,
            body_lines=["Remove this instance?", f"{label}"],
            destructive_idx=1,
        )

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

        if 0 <= selected_pc < 12:
            if selected_pc in black_rects:
                bx, by, bw, _ = black_rects[selected_pc]
                self._fill_rect(bx, max(0, by - 4), bw, 3, True)
            else:
                white_index = white_pcs.index(selected_pc)
                wx = x + white_index * white_w
                self._fill_rect(wx + 2, max(0, y - 4), max(3, white_w - 4), 3, True)

    def _record_ttid_keyboard_targets(self, x: int, y: int, w: int, h: int) -> None:
        if not self.touch_layout_enabled:
            return
        white_h = h
        black_h = max(8, int(h * 0.58))
        white_w = w // 7
        black_w = max(4, white_w // 2)
        white_pcs = [0, 2, 4, 5, 7, 9, 11]
        black_positions = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}

        for i, pc in enumerate(white_pcs):
            wx = x + i * white_w
            ww = white_w if i < 6 else (x + w) - wx
            self._record_touch_target("ttid_key", wx, y, ww, white_h, action_kind="set_ttid_pc", index=pc, label=note_name(pc))
        for pc, white_index in black_positions.items():
            bx = x + ((white_index + 1) * white_w) - (black_w // 2)
            self._record_touch_target("ttid_key", bx, y, black_w, black_h, action_kind="set_ttid_pc", index=pc, label=note_name(pc))

    def _draw_touch_ttid_choice_grid(self, labels: list[str], selected_idx: int, x: int, y: int, w: int, h: int, *, action_kind: str, target_kind: str) -> None:
        if not labels:
            return
        cols = 4
        rows = max(1, (len(labels) + cols - 1) // cols)
        gap = 10 if self.is_five_inch_touch else 6
        cell_w = max(1, (w - (gap * (cols - 1))) // cols)
        cell_h = max(1, (h - (gap * (rows - 1))) // rows)
        for idx, label in enumerate(labels):
            col = idx % cols
            row = idx // cols
            cx = x + col * (cell_w + gap)
            cy = y + row * (cell_h + gap)
            selected = idx == selected_idx
            pressed = self._touch_pressed(kind=target_kind, index=idx)
            if self.touch_layout_enabled and self.has_color:
                self._rounded_theme(cx, cy, cell_w, cell_h, 8, "panel_pressed" if pressed else "panel_alt" if selected else "panel", True)
                self._rect_theme(cx, cy, cell_w, cell_h, "accent" if selected else "line", False)
                scale = 2 if self.is_five_inch_touch else 1
                weight = "semibold" if selected else "medium"
                fitted = self._truncate_to_width(label, max(1, cell_w - 12), scale, weight)
                text_w, text_h = self._measure_text(fitted, scale, weight)
                self._text_theme(fitted, cx + max(0, (cell_w - text_w) // 2), cy + max(0, (cell_h - text_h) // 2), "text", scale, weight)
            self._record_touch_target(target_kind, cx, cy, cell_w, cell_h, action_kind=action_kind, index=idx, label=str(label))

    def _draw_touch_ttid_controls(self, state, x: int, y: int, w: int, h: int) -> None:
        roots = get_root_names()
        names = state.edit_ttid_scale_names or ["major"]
        scale_idx = max(0, min(len(names) - 1, int(state.edit_ttid_scale_index))) if names else 0
        root_idx = int(state.edit_ttid_load_root) % 12

        root_h = 44
        gap = 6
        root_w = max(1, (w - (gap * 11)) // 12)
        for idx, root in enumerate(roots):
            rx = x + idx * (root_w + gap)
            selected = idx == root_idx
            pressed = self._touch_pressed(kind="ttid_root", index=idx)
            if self.has_color:
                self._rounded_theme(rx, y, root_w, root_h, 6, "panel_pressed" if pressed else "panel_alt" if selected else "panel", True)
                self._rect_theme(rx, y, root_w, root_h, "accent" if selected else "line", False)
                text_w, text_h = self._measure_text(root, 1, "semibold" if selected else "medium")
                self._text_theme(root, rx + max(0, (root_w - text_w) // 2), y + max(0, (root_h - text_h) // 2), "text", 1, "semibold" if selected else "medium")
            else:
                self.display.rect(rx, y, root_w, root_h, True, pressed or selected)
                self._text(root, rx + 6, y + 14, 1, "medium")
            self._record_touch_target("ttid_root", rx, y, root_w, root_h, action_kind="set_ttid_root", index=idx, label=root)

        control_y = y + root_h + 14
        control_h = max(48, h - root_h - 14)
        step_w = 58
        load_w = 128
        scale_x = x + step_w + 8
        scale_w = max(1, w - (step_w * 2) - load_w - 32)
        right_x = scale_x + scale_w + 8
        load_x = right_x + step_w + 16
        scale_name = shorten(names[scale_idx] if names else "major", 22)

        controls = [
            ("ttid_scale_step", x, control_y, step_w, control_h, "step_ttid_scale", -1, "<"),
            ("ttid_scale_name", scale_x, control_y, scale_w, control_h, "set_ttid_scale", scale_idx, scale_name),
            ("ttid_scale_step", right_x, control_y, step_w, control_h, "step_ttid_scale", 1, ">"),
            ("ttid_load", load_x, control_y, load_w, control_h, "load_ttid_scale", 12, "Load"),
        ]
        for kind, cx, cy, cw, ch, action, index, label in controls:
            pressed = self._touch_pressed(kind=kind, index=index)
            if self.has_color:
                self._rounded_theme(cx, cy, cw, ch, 8, "panel_pressed" if pressed else "panel_alt" if kind == "ttid_scale_name" else "panel", True)
                self._rect_theme(cx, cy, cw, ch, "accent" if kind == "ttid_load" else "line", False)
                scale = 2 if kind in {"ttid_scale_name", "ttid_load"} else 2
                weight = "semibold" if kind == "ttid_load" else "medium"
                fitted = self._truncate_to_width(label, max(1, cw - 16), scale, weight)
                text_w, text_h = self._measure_text(fitted, scale, weight)
                self._text_theme(fitted, cx + max(0, (cw - text_w) // 2), cy + max(0, (ch - text_h) // 2), "text", scale, weight)
            else:
                self.display.rect(cx, cy, cw, ch, True, pressed)
                self._text(label, cx + 8, cy + 16, 2 if kind != "ttid_scale_step" else 1, "medium")
            self._record_touch_target(kind, cx, cy, cw, ch, action_kind=action, index=index, label=label)

    def draw_edit_ttid(self, state, param) -> None:
        mask = int(state.edit_value or 0)
        mode = state.edit_ttid_mode
        if self.is_tall:
            if mode == "keyboard":
                if self.is_five_inch_touch:
                    block_h = 366
                    top = self.edit_content_top(block_h)
                    key_x, key_y, key_w, key_h = 52, top, 696, 188
                    self._draw_ttid_keyboard(mask, -1, key_x, key_y, key_w, key_h)
                    self._record_ttid_keyboard_targets(key_x, key_y, key_w, key_h)
                    self._draw_touch_ttid_controls(state, key_x, key_y + key_h + 24, key_w, 134)
                elif self.is_full_tft:
                    block_h = 134
                    top = self.edit_content_top(block_h)
                    self._draw_ttid_keyboard(mask, state.edit_ttid_selected_pc, 20, top, 280, 104)
                    self._record_ttid_keyboard_targets(20, top, 280, 104)
                else:
                    block_h = 48
                    top = self.edit_content_top(block_h)
                    self._draw_ttid_keyboard(mask, state.edit_ttid_selected_pc, 4, top, 120, 32)
                    self._record_ttid_keyboard_targets(4, top, 120, 32)
                if self.is_five_inch_touch:
                    return
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
                if self.is_five_inch_touch:
                    block_h = 310
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load root", top)
                    self._draw_touch_ttid_choice_grid(roots, state.edit_ttid_load_root % 12, 52, top + 44, 704, 230, action_kind="set_ttid_root", target_kind="ttid_root")
                elif self.is_full_tft:
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
                if self.is_five_inch_touch:
                    block_h = 310
                    top = self.edit_content_top(block_h)
                    self._draw_edit_caption("load scale", top)
                    self._draw_touch_ttid_choice_grid([shorten(name, 14) for name in names[:12]], min(idx, 11), 52, top + 44, 704, 230, action_kind="set_ttid_scale", target_kind="ttid_scale")
                elif self.is_full_tft:
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

        if self.touch_layout_enabled:
            self._draw_edit_step16_touch(cells, state, ui.active_step16_playhead)
            return

        self._draw_edit_step16_encoder(cells, state, ui.active_step16_playhead)

    def _draw_edit_step16_touch(self, cells, state, playhead: int | None) -> None:
        top = self.edit_content_top(360)
        cols = 4
        cell_w = 142
        cell_h = 68
        gap = 14
        grid_w = cols * cell_w + (cols - 1) * gap
        origin_x = max(24, (self.display.width - grid_w) // 2)
        origin_y = top + 10
        text_y = top + 326

        for cell in cells:
            col = cell.index % cols
            row = cell.index // cols
            x = origin_x + col * (cell_w + gap)
            y = origin_y + row * (cell_h + gap)
            pressed = self._touch_pressed(kind="step16_cell", index=cell.index)
            self._record_touch_target("step16_cell", x, y, cell_w, cell_h, action_kind="tap_step16", index=cell.index, label=str(cell.index + 1))

            if self.has_color:
                fill = "panel_pressed" if pressed else "panel_alt" if cell.focused else "panel"
                self._rounded_theme(x, y, cell_w, cell_h, 10, fill, True)
                self._rect_theme(x, y, cell_w, cell_h, "accent" if cell.playing else "line", False)
                if cell.active:
                    self._fill_theme(x + 8, y + 8, max(1, cell_w - 16), max(1, cell_h - 16), "accent_soft")
                    self._fill_theme(x + 10, y + 10, max(1, cell_w - 20), max(1, cell_h - 20), "accent")
                if cell.playing:
                    self._fill_theme(x + 10, y + 10, max(1, cell_w - 20), 8, "text")
                label = f"{cell.index + 1:02d}"
                label_w, label_h = self._measure_text(label, 2, "semibold")
                self._text_theme(label, x + max(0, (cell_w - label_w) // 2), y + max(0, (cell_h - label_h) // 2), "text", 2, "semibold")
            else:
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
        play_label = "--" if playhead is None else f"{playhead + 1:02d}"
        self._text_theme(f"F{focus_label} P{play_label}", 48, text_y, "muted", 2, "medium")

    def _draw_edit_step16_encoder(self, cells, state, playhead: int | None) -> None:
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

            if self.is_tft:
                self.display.rect(x, y, cell_w, cell_h, True, False)
                if cell.active:
                    self._fill_rect_level(x + 1, y + 1, max(0, cell_w - 2), max(0, cell_h - 2), STEP16_ENABLED_FILL_LEVEL)
            else:
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

        if self.touch_layout_enabled:
            pitch_scale = 6
            cents_scale = 2
            status_scale = 2
            meter_w = min(self.display.width - 96, 620)
            meter_h = 24
            pitch_segments = self._pitch_display_segments(pitch_value, pitch_scale)
            pitch_h = max(self._measure_text(text, scale, weight)[1] for text, scale, weight in pitch_segments)
            cents_h = self._measure_text(cents_text, cents_scale, "medium")[1]
            status_h = self._measure_text("IN TUNE", status_scale, "medium")[1]
            total_h = pitch_h + 24 + meter_h + 18 + cents_h + 12 + status_h
            panel_w = min(self.display.width - 56, 720)
            panel_h = total_h + 48
            panel_x = max(28, (self.display.width - panel_w) // 2)
            panel_y = self.edit_content_top(panel_h)
            pitch_y = panel_y + 24
            meter_y = pitch_y + pitch_h + 24
            cents_y = meter_y + meter_h + 18
            status_y = cents_y + cents_h + 12
            meter_x = max(0, (self.display.width - meter_w) // 2)

            if self.has_color:
                self._rounded_theme(panel_x, panel_y, panel_w, panel_h, 14, "panel", True)
                self._rect_theme(panel_x, panel_y, panel_w, panel_h, "line", False)
                self._text_theme("TUNER", panel_x + 24, panel_y + 18, "muted", 2, "medium")
                self._hline_theme(panel_x + 24, panel_y + 52, panel_w - 48, "line")
                self._fill_theme(panel_x + 24, panel_y + 54, 72, 4, "accent")
            else:
                self.display.rect(panel_x, panel_y, panel_w, panel_h, True, False)
            self._draw_centered_segments(pitch_segments, pitch_y)
            self._draw_pitch_meter(cents_float, meter_x, meter_y, meter_w, meter_h)
            self.text_center_scaled(cents_text, cents_y, cents_scale)
            if cents_float is None:
                status_text = "LISTENING"
            elif abs(cents_float) <= 3:
                status_text = "IN TUNE"
            elif cents_float < 0:
                status_text = "FLAT"
            else:
                status_text = "SHARP"
            self.text_center_scaled(status_text, status_y, status_scale)
            return

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

    def draw_edit_scope(self, ui, param, state) -> None:
        samples = list(getattr(state, "edit_scope_samples", []) or [])
        if self.touch_layout_enabled:
            panel_w = 720
            panel_h = 306
            panel_x = max(40, (self.display.width - panel_w) // 2)
            panel_y = self.edit_content_top(panel_h)
            x, y, w, h = panel_x + 24, panel_y + 58, panel_w - 48, 178
            label_scale = 2
            value_y = panel_y + panel_h - 36
            time_label_y = value_y - 2

            if self.has_color:
                self._rounded_theme(panel_x, panel_y, panel_w, panel_h, 14, "panel", True)
                self._rect_theme(panel_x, panel_y, panel_w, panel_h, "line", False)
                self._text_theme("TIME DOMAIN", panel_x + 24, panel_y + 18, "muted", 2, "medium")
                self._hline_theme(panel_x + 24, panel_y + 52, panel_w - 48, "line")
                self._fill_theme(panel_x + 24, panel_y + 54, 96, 4, "accent")
            else:
                self.display.rect(panel_x, panel_y, panel_w, panel_h, True, False)
            self.display.rect(x, y, w, h, True, False)
            mid_y = y + h // 2
            self.display.hline(x + 1, mid_y, max(0, w - 2), True)

            if samples and w > 2 and h > 2:
                visible = samples[-max(1, w - 2):]
                if len(visible) == 1:
                    visible = visible * 2
                points: list[tuple[int, int]] = []
                denom = max(1, len(visible) - 1)
                for idx, sample in enumerate(visible):
                    sx = x + 1 + int(round(idx * (w - 3) / denom))
                    sy = mid_y - int(round(max(-1.0, min(1.0, float(sample))) * ((h - 3) / 2)))
                    points.append((sx, max(y + 1, min(y + h - 2, sy))))
                self._draw_polyline(points, True)
            else:
                self._text_theme("waiting", panel_x + 24, y + 6, "muted", 2, "medium")

            sample_rate = getattr(state, "edit_value", None)
            time_label = self._scope_time_label(min(len(samples), max(0, w - 2)), sample_rate)
            value_text = format_param_value(param, sample_rate)
            footer = f"{value_text}  {time_label}"
            self._text_theme(shorten(footer, 30), panel_x + 24, value_y, "text", label_scale, "medium")
            return

        if self.is_full_tft:
            x, y, w, h = 16, 48, self.display.width - 32, 126
            label_scale = 2
            value_y = y + h + 18
        elif self.is_tall:
            x, y, w, h = 6, 30, self.display.width - 12, 62 if self.is_tft else 54
            label_scale = 1
            value_y = y + h + 8
        else:
            x, y, w, h = 4, 13, self.display.width - 8, 14
            label_scale = 1
            value_y = y + h + 1

        self.display.rect(x, y, w, h, True, False)
        mid_y = y + h // 2
        self.display.hline(x + 1, mid_y, max(0, w - 2), True)

        if samples and w > 2 and h > 2:
            visible = samples[-max(1, w - 2):]
            if len(visible) == 1:
                visible = visible * 2
            points: list[tuple[int, int]] = []
            denom = max(1, len(visible) - 1)
            for idx, sample in enumerate(visible):
                sx = x + 1 + int(round(idx * (w - 3) / denom))
                sy = mid_y - int(round(max(-1.0, min(1.0, float(sample))) * ((h - 3) / 2)))
                points.append((sx, max(y + 1, min(y + h - 2, sy))))
            self._draw_polyline(points, True)
        else:
            self.text_center("waiting", mid_y - 4)

        sample_rate = getattr(state, "edit_value", None)
        time_label = self._scope_time_label(min(len(samples), max(0, w - 2)), sample_rate)
        value_text = format_param_value(param, sample_rate)
        footer = f"{value_text}  {time_label}"
        self.text_center_scaled(shorten(footer, 28 if self.is_full_tft else 20), value_y, label_scale)

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
        if is_scope_param(selected_param):
            self.draw_edit_scope(ui, selected_param, state)
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
            if self.touch_layout_enabled:
                touch_pad_y = 28 if self.is_five_inch_touch else 8
                self._record_touch_target(
                    "edit_slider",
                    gfx_x,
                    max(self.content_top, gfx_y - touch_pad_y),
                    gfx_w,
                    gfx_h + (touch_pad_y * 2),
                    action_kind="set_edit_value",
                    button_id="value_slider",
                )
            if not self._draw_touch_edit_value_readout(selected_param, value, gfx_y):
                self.text_center(shorten(format_param_value(selected_param, value), 21), value_y)
        else:
            norm = 0.0
            if isinstance(value, (int, float)) and pmin is not None and pmax is not None and (pmax - pmin) > 0:
                norm = (value - pmin) / (pmax - pmin)
            self._draw_continuous_bar(norm, gfx_x, gfx_y, gfx_w, gfx_h)
            if self.touch_layout_enabled:
                touch_pad_y = 28 if self.is_five_inch_touch else 8
                self._record_touch_target(
                    "edit_slider",
                    gfx_x,
                    max(self.content_top, gfx_y - touch_pad_y),
                    gfx_w,
                    gfx_h + (touch_pad_y * 2),
                    action_kind="set_edit_value",
                    button_id="value_slider",
                )
            if not self._draw_touch_edit_value_readout(selected_param, value, gfx_y):
                self.text_center(shorten(format_param_value(selected_param, value), 21), value_y)
        self._draw_edit_midi_controls(ui, selected_param)

    def draw_splash(self, title: str = "SHADOWBOX") -> None:
        self.display.clear()
        if self.is_tft:
            scale = self._hero_scale(3 if self.is_full_tft else 2)
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

    def _draw_startup_activity_bar(self, x: int, y: int, w: int, h: int, phase: float) -> None:
        if w <= 8 or h <= 3:
            return
        phase = max(0.0, min(1.0, float(phase) % 1.0))
        segment_w = max(4, min(w - 2, w // 3))
        travel_w = max(1, w - 2 - segment_w)
        segment_x = x + 1 + int(round(travel_w * phase))
        if self.has_color:
            radius = max(1, h // 2)
            self._rounded_theme(x, y, w, h, radius, "line", fill=False)
            self._rounded_theme(segment_x, y + 1, segment_w, max(1, h - 2), radius, "accent", fill=True)
            return
        self.display.rect(x, y, w, h, True, False)
        self.display.rect(segment_x, y + 1, segment_w, max(1, h - 2), True, True)

    def draw_startup_status(
        self,
        title: str,
        status_line: str = "",
        hint_line: str = "",
        activity_phase: float | None = None,
    ) -> None:
        self.display.clear()
        if self.is_tft:
            if self.is_tiny_text_tft:
                self.draw_splash(title)
                return
            title_scale = self._hero_scale(4 if self.is_full_tft else 3)
            status_scale = self._hero_scale(2)
            hint_scale = self._hero_scale(2)
            text_width = max(0, self.display.width - (24 if self.is_full_tft else 16))
            status_weight = "medium" if self.is_full_tft else "regular"
            hint_weight = "medium" if self.is_full_tft else "regular"
            status_lines = self._wrap_text_to_width(status_line, text_width, status_scale, status_weight)
            hint_lines = self._wrap_text_to_width(hint_line, text_width, hint_scale, hint_weight)
            if title == "SHADOWBOX":
                _, title_h, _ = self._measure_shadowbox_logo(title_scale)
            else:
                title_h = self._measure_text(title, title_scale, "medium")[1]
            status_line_h = self._line_height(status_scale, status_weight) if status_lines else 0
            hint_line_h = self._line_height(hint_scale, hint_weight) if hint_lines else 0
            status_block_h = len(status_lines) * status_line_h
            hint_block_h = len(hint_lines) * hint_line_h
            gap_scale = 2 if self.is_five_inch_touch else 1
            status_gap = (20 if self.is_full_tft else 14) * gap_scale
            hint_gap = (14 if self.is_full_tft else 10) * gap_scale
            activity_gap = (18 if self.is_full_tft else 12) * gap_scale
            activity_h = (8 if self.is_full_tft else 5) * gap_scale if activity_phase is not None else 0
            block_h = title_h
            if status_block_h:
                block_h += status_gap + status_block_h
            if hint_block_h:
                block_h += hint_gap + hint_block_h
            if activity_h:
                block_h += activity_gap + activity_h
            title_y = max(0, (self.display.height - block_h) // 2)

            if title == "SHADOWBOX":
                self._draw_shadowbox_logo(title_y, title_scale)
            else:
                self.text_center_scaled(title, title_y, title_scale)

            status_y = title_y + title_h + status_gap
            for idx, line in enumerate(status_lines):
                self.text_center_scaled(line, status_y + (idx * status_line_h), status_scale)
            hint_y = status_y + status_block_h + hint_gap
            for idx, line in enumerate(hint_lines):
                self.text_center_scaled(line, hint_y + (idx * hint_line_h), hint_scale)
            if activity_h:
                bar_w = min(max(48, self.display.width // 2), self.display.width - (64 if self.is_full_tft else 32))
                bar_x = max(0, (self.display.width - bar_w) // 2)
                bar_y = hint_y + hint_block_h + activity_gap
                self._draw_startup_activity_bar(bar_x, bar_y, bar_w, activity_h, activity_phase)
        else:
            self.text_center(title, 28 if self.is_tall else 12)
            if status_line:
                self.text_center(shorten(status_line, self.text_cols), 44 if self.is_tall else 22)
            if hint_line and self.is_tall:
                self.text_center(shorten(hint_line, self.text_cols), 56)
            if activity_phase is not None and self.is_tall:
                self._draw_startup_activity_bar(16, self.display.height - 8, max(1, self.display.width - 32), 5, activity_phase)
        self.display.show()

    def draw_status(self, ui) -> None:
        if self.touch_layout_enabled and self.has_color:
            panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
            self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
            content_left, content_right, content_top, _content_bottom, row_h, _gap, rows = self._touch_list_geometry(visible_rows=4)
            row_w = max(1, content_right - content_left)
            for y, row in zip(rows, ui.status_value_rows):
                row_top = max(content_top, y - (row_h // 2))
                label = {
                    "inst": "Instances",
                    "cpu": "CPU",
                    "xruns": "XRUNS",
                    "rnbo": "RNBO",
                }.get(str(row.label).lower(), self._menu_label(str(row.label)))
                self._draw_touch_list_item_background(
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    current=row.current,
                )
                self._draw_touch_label_value_row(
                    content_left,
                    row_top,
                    row_w,
                    row_h,
                    y,
                    label,
                    format_display_value(row.value),
                    text_weight=self._current_row_weight(row.emphasis or None, current=row.current),
                    show_chevron=False,
                )
            return
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
        self.draw_value_rows(ui.status_value_rows)

    def draw_system_audio(self, ui) -> None:
        self.draw_string_list([".."] + SYSTEM_AUDIO_ITEMS, ui.state.system_audio_cursor)

    def draw_graph_status(self, ui) -> None:
        dirty_text = "YES" if ui.current_set_dirty else "NO"
        if self.is_tft:
            self._draw_info_rows(
                [
                    ("SET", ui.current_set_name),
                    ("DIRTY", dirty_text),
                    ("SAVED", len(ui.available_set_names)),
                ]
            )
            return
        self.draw_value_rows(ui.graph_status_value_rows)

    def draw_graph_startup(self, ui) -> None:
        sets = ui.state.system.get("sets", {})
        auto_last = "ON" if sets.get("auto_start_last") is True else "OFF"
        initial = str(sets.get("initial_value", "") or "-")
        if self.is_tft:
            self._draw_info_rows(
                [
                    ("STARTUP", ui.startup_graph_label),
                    ("AUTO LAST", auto_last),
                    ("INITIAL", initial),
                ]
            )
            return
        self.draw_value_rows(ui.graph_startup_value_rows)

    def draw_system_audio_device(self, ui) -> None:
        self.draw_menu_rows(ui.audio_device_rows, ui.state.audio_device_cursor)

    def draw_system_audio_rate(self, ui) -> None:
        self.draw_menu_rows(ui.sample_rate_rows, ui.state.sample_rate_cursor)

    def draw_system_audio_buffer(self, ui) -> None:
        self.draw_menu_rows(ui.buffer_size_rows, ui.state.buffer_size_cursor)

    def draw_network(self, ui) -> None:
        self.draw_selectable_value_rows(ui.network_value_rows, ui.state.network_cursor)

    def _name_key_index(self, char: str) -> int:
        try:
            return NAME_TOUCH_KEY_VALUES.index(char)
        except ValueError:
            return 0

    def _draw_name_keyboard_key(
        self,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        action_kind: str,
        index: int | None = None,
        button_id: str = "",
        kind: str = "name_key",
        accent: bool = False,
        destructive: bool = False,
        active: bool = False,
    ) -> None:
        button_id = button_id or re.sub(r"\s+", "_", str(label).strip().lower())
        pressed = self._touch_pressed(kind=kind, index=index, button_id=button_id)
        self._record_touch_target(
            kind,
            x,
            y,
            max(1, w),
            max(1, h),
            action_kind=action_kind,
            index=index,
            button_id=button_id,
            label=str(label),
        )
        if self.touch_layout_enabled and self.has_color:
            fill = "panel_pressed" if pressed else "accent" if accent or active else "panel_alt"
            border = "danger" if destructive else "accent" if accent or active or pressed else "line"
            text_color = "bg" if accent or active else "danger" if destructive else "text"
            if pressed:
                text_color = "text"
            self._rounded_theme(x, y, max(1, w), max(1, h), 10, fill, True)
            self._rounded_theme(x, y, max(1, w), max(1, h), 10, border, False)
            scale = 3 if len(str(label)) <= 2 else 2
            weight = "semibold" if accent or active else "medium"
            text_w, text_h = self._measure_text(label, scale, weight)
            self._text_theme(label, x + max(0, (w - text_w) // 2), y + max(0, (h - text_h) // 2), text_color, scale, weight)
            return
        if pressed:
            self.display.rect(x, y, max(1, w), max(1, h), True, True)
        else:
            self.display.rect(x, y, max(1, w), max(1, h), True, False)
        scale = 3 if self.touch_layout_enabled and len(str(label)) <= 2 else 2 if self.touch_layout_enabled else 1
        weight = "semibold" if accent or active else "medium"
        text_w, text_h = self._measure_text(label, scale, weight)
        self._text(str(label), x + max(0, (w - text_w) // 2), y + max(0, (h - text_h) // 2), scale, weight)

    def _draw_name_keyboard_row(self, row: list[str], x: int, y: int, w: int, h: int, gap: int, *, shift: bool = False) -> None:
        count = max(1, len(row))
        key_w = max(1, (w - gap * (count - 1)) // count)
        total_w = key_w * count + gap * (count - 1)
        row_x = x + max(0, (w - total_w) // 2)
        for idx, char in enumerate(row):
            label = char.upper() if shift and char.isalpha() else char
            self._draw_name_keyboard_key(
                label,
                row_x + idx * (key_w + gap),
                y,
                key_w,
                h,
                action_kind="tap_name_key",
                index=self._name_key_index(char),
                button_id=f"key_{char}",
            )

    def draw_name_keyboard_editor(self, ui) -> None:
        panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
        self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
        self._record_touch_target("keyboard_surface", panel_x, panel_y, panel_w, panel_h, action_kind="noop")
        margin = 24
        content_x = panel_x + margin
        content_w = max(1, panel_w - margin * 2)
        draft_h = 62
        draft_y = panel_y + 14
        key_h = 46
        gap = 8
        row_gap = 9
        key_y = draft_y + draft_h + 18

        draft = ui.state.name_editor_draft or ""
        draft_text = draft if draft else "Name"
        text_scale = 3
        text_weight = "semibold"
        line_h = self.display.line_height(text_scale, text_weight) if callable(getattr(self.display, "line_height", None)) else self._line_height(text_scale, text_weight)
        text_y = draft_y + max(0, (draft_h - line_h) // 2)
        if self.has_color:
            self._rounded_theme(content_x, draft_y, content_w, draft_h, 12, "panel", True)
            self._rounded_theme(content_x, draft_y, content_w, draft_h, 12, "line", False)
            color = "text" if draft else "muted"
            shown = self._truncate_to_width(draft_text, max(0, content_w - 36), text_scale, text_weight)
            self._text_line_theme(shown, content_x + 18, text_y, color, text_scale, text_weight)
        else:
            self.display.rect(content_x, draft_y, content_w, draft_h, True, False)
            shown = self._truncate_to_width(draft_text, max(0, content_w - 36), text_scale, text_weight)
            self._text(shown, content_x + 18, text_y, text_scale, text_weight)

        mode = ui.state.name_keyboard_mode if ui.state.name_keyboard_mode in {"letters", "numbers"} else "letters"
        if mode == "numbers":
            rows = NAME_TOUCH_NUMBER_ROWS
            self._draw_name_keyboard_row(rows[0], content_x, key_y, content_w, key_h, gap)
            self._draw_name_keyboard_row(rows[1], content_x + 190, key_y + key_h + row_gap, content_w - 380, key_h, gap)
            third_y = key_y + (key_h + row_gap) * 2
        else:
            self._draw_name_keyboard_row(NAME_TOUCH_LETTER_ROWS[0], content_x, key_y, content_w, key_h, gap, shift=ui.state.name_keyboard_shift)
            self._draw_name_keyboard_row(NAME_TOUCH_LETTER_ROWS[1], content_x + 34, key_y + key_h + row_gap, content_w - 68, key_h, gap, shift=ui.state.name_keyboard_shift)
            third_y = key_y + (key_h + row_gap) * 2
            side_w = 76
            letters_w = max(1, content_w - side_w * 2 - gap * 2)
            self._draw_name_keyboard_key(
                "shift",
                content_x,
                third_y,
                side_w,
                key_h,
                action_kind="name_shift",
                kind="name_control",
                button_id="shift",
                active=ui.state.name_keyboard_shift,
            )
            self._draw_name_keyboard_row(NAME_TOUCH_LETTER_ROWS[2], content_x + side_w + gap, third_y, letters_w, key_h, gap, shift=ui.state.name_keyboard_shift)
            self._draw_name_keyboard_key(
                "<",
                content_x + content_w - side_w,
                third_y,
                side_w,
                key_h,
                action_kind="name_backspace",
                kind="name_control",
                button_id="backspace",
            )

        control_y = key_y + (key_h + row_gap) * 3
        mode_label = "ABC" if mode == "numbers" else "123"
        mode_w = 82
        small_w = 82
        save_w = 126
        clear_w = 96
        space_w = max(1, content_w - mode_w - small_w * 3 - clear_w - save_w - gap * 6)
        x = content_x
        self._draw_name_keyboard_key(mode_label, x, control_y, mode_w, key_h, action_kind="name_keyboard_mode", kind="name_control", button_id="mode")
        x += mode_w + gap
        self._draw_name_keyboard_key("space", x, control_y, space_w, key_h, action_kind="name_space", kind="name_control", button_id="space")
        x += space_w + gap
        self._draw_name_keyboard_key("del", x, control_y, small_w, key_h, action_kind="name_backspace", kind="name_control", button_id="backspace")
        x += small_w + gap
        self._draw_name_keyboard_key("date", x, control_y, small_w, key_h, action_kind="tap_button", kind="modal_button", button_id="date")
        x += small_w + gap
        self._draw_name_keyboard_key("gen", x, control_y, small_w, key_h, action_kind="tap_button", kind="modal_button", button_id="generate")
        x += small_w + gap
        self._draw_name_keyboard_key("clear", x, control_y, clear_w, key_h, action_kind="tap_button", kind="modal_button", button_id="clear", destructive=True)
        x += clear_w + gap
        self._draw_name_keyboard_key(ui.name_editor_confirm_label.lower(), x, control_y, save_w, key_h, action_kind="tap_button", kind="modal_button", button_id=ui.name_editor_confirm_label.lower(), accent=True)

    def draw_name_inline_editor(self, ui) -> None:
        if self.is_tft:
            panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
            self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
            if self.is_full_tft:
                name_y = panel_y + 12
                mode_y = name_y + self._line_height(2, "semibold") + 10
                strip_y = mode_y + self._line_height(2, "bold") + 12
                hint_y = panel_y + panel_h - self._line_height(1, "regular") - 10
                name_text = self._inline_name_window(ui, 18)
                self._draw_centered_text(name_text, name_y, 2, "semibold")
                self._draw_centered_segments(self._inline_mode_segments(ui.state.name_inline_edit_mode), mode_y)
                if ui.state.name_inline_edit_mode:
                    char_strip = self._inline_char_strip_text(ui, 9)
                    self._draw_centered_text(self._truncate_to_width(char_strip, max(0, panel_w - 16), 1, "medium"), strip_y, 1, "medium")
                    hint_text = "Rotate to choose character  PRESS=SET  HOLD=BACK"
                else:
                    hint_text = "Rotate to move cursor  PRESS=EDIT  HOLD=BACK"
                self._draw_centered_text(self._truncate_to_width(hint_text, max(0, panel_w - 16), 1), hint_y, 1, "regular")
                return
            rows = self._panel_list_rows(panel_y, panel_h)
            if rows:
                name_text = self._inline_name_window(ui, 14)
                self._draw_centered_text(name_text, rows[0], 2, "medium")
            if len(rows) > 2:
                self._draw_centered_segments(self._inline_mode_segments(ui.state.name_inline_edit_mode), rows[2])
            if ui.state.name_inline_edit_mode and len(rows) > 4:
                char_strip = self._inline_char_strip_text(ui, 7)
                self._draw_centered_text(self._truncate_to_width(char_strip, max(0, panel_w - 12), 1, "medium"), rows[4], 1, "medium")
            if len(rows) > 6:
                hint_text = "Step chooses char" if ui.state.name_inline_edit_mode else "Step moves cursor"
                action_text = "PRESS=SET  HOLD=BACK" if ui.state.name_inline_edit_mode else "PRESS=EDIT  HOLD=BACK"
                self._draw_centered_text(hint_text, rows[6], 1, "regular")
                if len(rows) > 7:
                    self._draw_centered_text(action_text, rows[7], 1, "regular")
            return
        rows = self.content_rows
        name_text = self._inline_name_window(ui, self.text_cols - 1)
        self._draw_centered_text(name_text, rows[0], 1, "medium")
        if len(rows) > 1:
            self._draw_centered_segments(self._inline_mode_segments(ui.state.name_inline_edit_mode), rows[1])
        if ui.state.name_inline_edit_mode and len(rows) > 2:
            char_strip = self._inline_char_strip_text(ui, 7)
            self._draw_centered_text(shorten(char_strip, self.text_cols), rows[2], 1, "regular")
        elif len(rows) > 2:
            self._draw_centered_text(shorten("step moves cursor", self.text_cols), rows[2], 1, "regular")
        if self.is_tall and len(rows) > 3:
            hint = "press=set hold=back" if ui.state.name_inline_edit_mode else "press=edit hold=back"
            self._draw_centered_text(shorten(hint, self.text_cols), rows[3], 1, "regular")

    def draw_about(self) -> None:
        version_text = SHADOWBOX_VERSION
        build_text = f"build {SHADOWBOX_BUILD_INFO}"
        if self.is_tft:
            panel_x, panel_y, panel_w, panel_h = self._content_panel_box()
            self._draw_panel(panel_x, panel_y, panel_w, panel_h, None)
            logo_scale = self._hero_scale(3 if self.is_full_tft else 2)
            line_scale = self._hero_scale(1)
            text_lines = [
                version_text,
                build_text,
                "stretta.com",
                "github.com/stretta/Shadowbox",
            ]
            logo_h = self._measure_shadowbox_logo(logo_scale)[1]
            line_h = max(self._measure_text(line, line_scale, "regular")[1] for line in text_lines)
            gap_scale = 2 if self.is_five_inch_touch else 1
            logo_gap = (14 if self.is_full_tft else 10) * gap_scale
            line_gap = (8 if self.is_full_tft else 4) * gap_scale
            block_h = logo_h + logo_gap + (line_h * len(text_lines)) + (line_gap * (len(text_lines) - 1))
            y = panel_y + max(0, (panel_h - block_h) // 2)
            y += self._draw_shadowbox_logo(y, logo_scale) + logo_gap
            for idx, line in enumerate(text_lines):
                self.text_center_scaled(line, y, line_scale)
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
        items = [".."] + ui.maint_menu_items
        action_indices = set(range(1, len(items))) if ui.maint_menu_items else None
        self.draw_string_list(items, ui.state.maint_cursor, action_indices=action_indices)

    def _draw_graphs_icon(self, x: int, y: int, on: bool = True, scale: int = 1) -> None:
        s = max(1, int(scale))
        self.display.rect(x + (18 * s), y + (10 * s), 24 * s, 18 * s, on, False)
        self.display.rect(x + (10 * s), y + (20 * s), 24 * s, 18 * s, on, False)
        self.display.rect(x + (26 * s), y + (20 * s), 24 * s, 18 * s, on, False)
        self.display.rect(x + (18 * s), y + (30 * s), 24 * s, 18 * s, on, False)

        for dot_x, dot_y in ((22, 14), (30, 14), (26, 24), (34, 24), (42, 24), (26, 34), (34, 34)):
            self.display.rect(x + (dot_x * s), y + (dot_y * s), 4 * s, 4 * s, on, True)

    def _draw_instances_icon(self, x: int, y: int, on: bool = True, scale: int = 1) -> None:
        s = max(1, int(scale))
        for offset_y in (10, 24, 38):
            self.display.rect(x + (14 * s), y + (offset_y * s), 32 * s, 10 * s, on, False)
            self.display.rect(x + (18 * s), y + (offset_y * s) + (3 * s), 4 * s, 4 * s, on, True)
            self.display.rect(x + (26 * s), y + (offset_y * s) + (3 * s), 12 * s, 4 * s, on, True)

    def _draw_system_icon(self, x: int, y: int, on: bool = True, scale: int = 1) -> None:
        s = max(1, int(scale))
        self.display.rect(x + (18 * s), y + (18 * s), 24 * s, 24 * s, on, False)
        self.display.rect(x + (24 * s), y + (24 * s), 12 * s, 12 * s, on, False)

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
            self.display.rect(x + (dx * s), y + (dy * s), w * s, h * s, on, True)

    def _draw_tft_home_card(self, x: int, y: int, w: int, h: int, label: str, index: int, selected: bool) -> None:
        if self.touch_layout_enabled and self.has_color:
            fill = "panel_pressed" if self._touch_pressed(kind="card", index=index) else "panel"
            self._rounded_theme(x, y, w, h, 12, fill, True)
            self._rect_theme(x, y, w, h, "line", False)
            self._fill_theme(x + 18, y + h - 10, max(24, w - 36), 4, "line")
        if selected and not self.touch_layout_enabled:
            underline_y = y + h - (14 if self.is_full_tft else 8)
            underline_x = x + (10 if self.is_full_tft else 6)
            underline_w = max(12, w - ((20 if self.is_full_tft else 12)))
            self.display.hline(underline_x, underline_y, underline_w, True)
            if self.is_full_tft:
                self.display.hline(underline_x, underline_y + 1, underline_w, True)

        icon_scale = 2 if self.touch_layout_enabled else 1
        icon_size = 120 if self.touch_layout_enabled else 60 if self.is_full_tft else 40
        icon_x = x + max(8, (w - icon_size) // 2)
        icon_y = y + (18 if self.is_full_tft else 12)
        if self.touch_layout_enabled:
            # Give the icon and the label their own hit areas so either visual
            # element can be tapped directly on the home screen.
            self._record_touch_target(
                "home_card_icon",
                icon_x - 6,
                icon_y - 6,
                icon_size + 12,
                icon_size + 12,
                action_kind="tap_row",
                index=index,
                label=str(label),
            )
        if label == "SYSTEM":
            self._draw_system_icon(icon_x, icon_y, on=True, scale=icon_scale)
        elif label == "SETS":
            self._draw_graphs_icon(icon_x, icon_y, on=True, scale=icon_scale)
        else:
            self._draw_instances_icon(icon_x, icon_y, on=True, scale=icon_scale)

        text_scale = 4 if self.touch_layout_enabled else 2 if self.is_full_tft else 1
        effective_selected = selected and not self.touch_layout_enabled
        text_weight = "semibold" if effective_selected and self.is_full_tft else "medium" if effective_selected else "regular"
        display_label = self._menu_label(label)
        text_w, text_h = self._measure_text(display_label, text_scale, text_weight)
        text_x = x + max(0, (w - text_w) // 2)
        if self.touch_layout_enabled:
            _ref_w, reference_h = self._measure_text("Sets", text_scale, "semibold")
            text_y = y + h - reference_h - 30
        else:
            text_y = y + h - text_h - (24 if self.is_full_tft else 14)
        if self.touch_layout_enabled:
            self._record_touch_target(
                "home_card_label",
                max(x, text_x - 4),
                max(y, text_y - 2),
                min(w, text_w + 8),
                min(h, text_h + 6),
                action_kind="tap_row",
                index=index,
                label=display_label,
            )
        if self.touch_layout_enabled and self.has_color:
            self._text_theme(display_label, text_x, text_y, "text", text_scale, "semibold")
        else:
            self._text(display_label, text_x, text_y, text_scale, text_weight, on=True)

    def draw_top_menu_tft(self, items: list[str], selected_idx: int) -> None:
        total = len(items)
        if total <= 0:
            return
        selected_idx = max(0, min(selected_idx, total - 1))

        avail_top = 0 if self.touch_layout_enabled else self.content_top
        avail_h = max(0, self.display.height - avail_top)
        gap = 18 if self.is_full_tft else 10
        max_card_w = (self.display.width - (gap * max(0, total - 1)) - 8) // max(1, total)
        if self.touch_layout_enabled:
            gap = 24
            max_card_w = (self.display.width - (gap * max(0, total - 1)) - 64) // max(1, total)
            card_w = min(210, max(150, max_card_w))
            card_h = min(250, max(170, avail_h - 160))
        else:
            card_w = min(136 if self.is_full_tft else 70, max(56, max_card_w))
            card_h = min(146 if self.is_full_tft else 82, max(56, avail_h - (24 if self.is_full_tft else 12)))
        total_w = (card_w * total) + (gap * (total - 1))
        start_x = max(4, (self.display.width - total_w) // 2)
        start_y = max(avail_top + 6, avail_top + ((avail_h - card_h) // 2) - (8 if self.is_full_tft and not self.touch_layout_enabled else 0))

        for idx, label in enumerate(items):
            x = start_x + idx * (card_w + gap)
            if self.touch_layout_enabled:
                self._record_touch_target(
                    "card",
                    x,
                    start_y,
                    card_w,
                    card_h,
                    action_kind="tap_row",
                    index=idx,
                    label=str(label),
                )
                if self._touch_pressed(kind="card", index=idx) and not self.has_color:
                    self.display.rect(x + 2, start_y + 2, max(1, card_w - 4), max(1, card_h - 4), True, True)
            self._draw_tft_home_card(x, start_y, card_w, card_h, str(label), idx, idx == selected_idx)

    def draw(self, ui, touch_state: TouchSample | None = None) -> None:
        state = ui.state
        self._ui = ui
        self._touch_state = touch_state
        self._begin_touch_layout(state.ui_mode)
        self.display.clear()

        header = {
            "TOP": "SHADOWBOX",
            "GRAPH_MENU": ui.current_set_name,
            "GRAPH_STATUS": "CURRENT SET",
            "GRAPH_SET_LIST": "SETS",
            "GRAPH_LOAD_SET_LIST": "LOAD SET",
            "GRAPH_STARTUP": "STARTUP",
            "GRAPH_STARTUP_SET_LIST": "STARTUP SET",
            "NAME_EDITOR": ui.name_editor_title,
            "NAME_OVERWRITE_CONFIRM": "OVERWRITE?",
            "NAME_ERROR": ui.name_error_title,
            "NAME_INLINE_EDITOR": "EDIT NAME",
            "INSTANCE_LIST": "INSTANCES",
            "PATCHER_PICKER": "ADD INSTANCE" if state.patcher_picker_context == "add" else "REPLACE",
            "INSTANCE_MENU": ui.active_instance.get("label", "INSTANCE") if ui.active_instance else "INSTANCE",
            "REMOVE_INSTANCE_PICKER": "REMOVE",
            "REMOVE_INSTANCE_CONFIRM": "REMOVE",
            "PRESET_LIST": "PRESETS",
            "PARAM_LIST": "PARAMETERS",
            "AUDIO_ROUTING_OVERVIEW": "AUDIO I/O",
            "MIDI_ROUTING_OVERVIEW": "MIDI I/O",
            "ENUM_LIST": shorten(shorten_param_name(ui.selected_param.get("name", "")), 19) if ui.selected_param else "ENUM",
            "ROUTING_GROUP": state.active_transport.upper(),
            "ROUTING_PORTS": f"{state.active_transport[:1].upper()}{state.active_transport[1:]} {state.active_routing_direction[:1].upper()}{state.active_routing_direction[1:]}",
            "ROUTING_TARGETS": routing_port_display_name(ui.selected_routing_port) or "TARGET",
            "ROUTING_ADD_PICKER": "ADD",
            "ROUTING_DISCONNECT_PICKER": "REMOVE",
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
            "GRAPH_PRESET_LIST": "SET PRESETS",
        }.get(state.ui_mode, state.ui_mode)
        if state.status_message:
            header = state.status_message
        if state.ui_mode == "EDIT":
            header = self.edit_header_title(ui.selected_param)
        self._show_back_button = self.touch_layout_enabled and state.ui_mode != "TOP"
        if not (self.touch_layout_enabled and state.ui_mode == "TOP"):
            self.draw_header(
                header,
                busy=state.busy,
                ticks=state.activity_ticks,
            )

        if state.ui_mode == "EDIT":
            self.draw_edit(ui, ui.selected_param, state)
        elif state.ui_mode == "TOP":
            if self.is_tft and not self.is_tiny_text_tft:
                self.draw_top_menu_tft(ui.top_level_items, state.top_index)
            else:
                self.draw_string_list(ui.top_level_items, state.top_index)
        elif state.ui_mode == "GRAPH_MENU":
            self.draw_string_list([".."] + ui.graph_menu_items, state.graph_menu_cursor)
        elif state.ui_mode == "GRAPH_STATUS":
            self.draw_graph_status(ui)
        elif state.ui_mode == "GRAPH_SET_LIST":
            self.draw_menu_rows(ui.graph_set_rows, state.graph_set_cursor)
        elif state.ui_mode == "GRAPH_LOAD_SET_LIST":
            self.draw_menu_rows(ui.graph_load_set_rows, state.graph_load_set_cursor)
        elif state.ui_mode == "GRAPH_PRESET_LIST":
            if self.touch_layout_enabled:
                self.draw_preset_list_with_footer(
                    ui.available_graph_preset_names,
                    state.graph_preset_cursor - len(ui.graph_preset_action_items),
                    ui.current_graph_preset_name,
                    ui.graph_preset_action_items,
                )
            else:
                self.draw_menu_rows(ui.graph_preset_rows, state.graph_preset_cursor)
        elif state.ui_mode == "GRAPH_PRESET_REMOVE_PICKER":
            items = [".."] + ui.available_graph_preset_names if ui.available_graph_preset_names else ["..", "no set presets"]
            action_indices = set(range(1, len(items))) if ui.available_graph_preset_names else None
            self.draw_string_list(items, state.graph_preset_remove_cursor, action_indices=action_indices)
        elif state.ui_mode == "GRAPH_STARTUP":
            self.draw_menu_rows(ui.graph_startup_rows, state.graph_startup_cursor)
        elif state.ui_mode == "GRAPH_STARTUP_SET_LIST":
            self.draw_string_list([".."] + ui.available_set_names if ui.available_set_names else ["..", "no saved sets"], state.graph_startup_set_cursor)
        elif state.ui_mode == "NAME_EDITOR":
            if self.touch_layout_enabled:
                self.draw_name_keyboard_editor(ui)
            else:
                self.draw_string_list(ui.name_editor_items, state.name_editor_cursor)
        elif state.ui_mode == "NAME_OVERWRITE_CONFIRM":
            if self.touch_layout_enabled:
                self.draw_name_overwrite_confirm(ui)
            else:
                self.draw_string_list(ui.overwrite_confirm_items, state.name_overwrite_cursor)
        elif state.ui_mode == "NAME_ERROR":
            if self.touch_layout_enabled:
                self.draw_name_error(ui)
            else:
                self.draw_string_list(ui.name_error_items, state.name_overwrite_cursor)
        elif state.ui_mode == "NAME_INLINE_EDITOR":
            self.draw_name_inline_editor(ui)
        elif state.ui_mode == "INSTANCE_LIST":
            self.draw_instance_list(ui)
        elif state.ui_mode == "REMOVE_INSTANCE_PICKER":
            remove_items = [".."] + [str(item.get("label", "")) for item in state.instances] if state.instances else ["..", "no instances"]
            remove_action_indices = set(range(1, len(remove_items))) if state.instances else None
            self.draw_string_list(remove_items, state.remove_instance_picker_cursor, action_indices=remove_action_indices)
        elif state.ui_mode == "PATCHER_PICKER":
            patcher_items = [".."] + state.patchers if state.patchers else ["..", "no patchers"]
            patcher_action_indices = set(range(1, len(patcher_items))) if state.patchers else None
            self.draw_string_list(patcher_items, state.patcher_cursor, action_indices=patcher_action_indices)
        elif state.ui_mode == "INSTANCE_MENU":
            instance_menu_items = [".."] + ui.instance_menu_items
            instance_action_indices = {
                idx for idx, item in enumerate(instance_menu_items)
                if item in {"REPLACE INSTANCE", "REMOVE INSTANCE"}
            }
            self.draw_string_list(instance_menu_items, state.instance_menu_cursor, action_indices=instance_action_indices)
        elif state.ui_mode == "REMOVE_INSTANCE_CONFIRM":
            if self.touch_layout_enabled:
                self.draw_remove_instance_confirm(ui)
            else:
                self.draw_string_list(REMOVE_INSTANCE_CONFIRM_ITEMS, state.remove_instance_confirm_cursor)
        elif state.ui_mode == "PRESET_LIST":
            if self.touch_layout_enabled:
                self.draw_preset_list_with_footer(
                    [str(item.get("name", "")) for item in ui.active_presets],
                    state.preset_cursor - len(ui.preset_action_items),
                    ui.current_preset_name,
                    ui.preset_action_items,
                )
            else:
                self.draw_menu_rows(ui.preset_rows, state.preset_cursor)
        elif state.ui_mode == "PRESET_REMOVE_PICKER":
            preset_items = [".."] + [str(item.get("name", "")) for item in ui.active_presets] if ui.active_presets else ["..", "no presets"]
            preset_action_indices = set(range(1, len(preset_items))) if ui.active_presets else None
            self.draw_string_list(preset_items, state.preset_remove_cursor, action_indices=preset_action_indices)
        elif state.ui_mode == "PARAM_LIST":
            self.draw_param_list(ui.active_params, state.param_cursor) if ui.active_params else self.draw_string_list(["..", "no params"], state.param_cursor)
        elif state.ui_mode == "ENUM_LIST":
            self.draw_enum_list(ui, state.enum_cursor)
        elif state.ui_mode in {"AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"}:
            self.draw_selectable_value_rows(ui.routing_overview_rows, state.routing_overview_cursor)
        elif state.ui_mode == "ROUTING_GROUP":
            self.draw_string_list([".."] + ROUTING_GROUP_ITEMS, state.routing_group_cursor)
        elif state.ui_mode == "ROUTING_PORTS":
            self.draw_routing_list(ui.active_routing_ports, state.routing_port_cursor) if ui.active_routing_ports else self.draw_string_list(["..", "no ports"], state.routing_port_cursor)
        elif state.ui_mode == "ROUTING_TARGETS":
            self.draw_routing_targets(ui, state.routing_target_cursor)
        elif state.ui_mode == "ROUTING_ADD_PICKER":
            self.draw_routing_target_picker(ui.available_routing_add_targets, state.routing_add_cursor)
        elif state.ui_mode == "ROUTING_DISCONNECT_PICKER":
            disconnect_items = [".."] + ui.current_routing_targets if ui.current_routing_targets else ["..", "no connections"]
            disconnect_action_indices = set(range(1, len(disconnect_items))) if ui.current_routing_targets else None
            self.draw_string_list(disconnect_items, state.routing_disconnect_cursor, action_indices=disconnect_action_indices)
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
            self.draw_network(ui)
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
    def draw_header(self, title: str, busy: bool = False, ticks: int = 0, show_back_button: bool = False) -> None:
        banner_h = self.header_height
        pad_x = 4
        text_scale = 2 if self.is_full_tft else 1
        text_weight = "semibold" if self.is_full_tft else "regular"
        show_back_button = show_back_button or bool(getattr(self, "_show_back_button", False))
        title = title if title == "SHADOWBOX" else self._menu_label(title)
        back_w = 112 if (self.touch_layout_enabled and show_back_button) else 0
        fitted = self._truncate_to_width(title, self.display.width - (pad_x * 2) - 20 - back_w, text_scale, text_weight)
        _, text_h = self._measure_text(fitted, text_scale, text_weight)
        text_y = max(1, (banner_h - text_h) // 2)
        if self.is_five_inch_touch and self.has_color:
            pad_x = 24
            text_scale = self._touch_menu_scale()
            text_weight = "regular"
            back_w = 96 if (self.touch_layout_enabled and show_back_button) else 0
            fitted = self._truncate_to_width(title, self.display.width - (pad_x * 2) - back_w - 48, text_scale, text_weight)
            _, text_h = self._measure_text(fitted, text_scale, text_weight)
            text_y = max(2, (banner_h - text_h) // 2)
            self._fill_theme(0, 0, self.display.width, banner_h, "panel")
            if self.touch_layout_enabled and show_back_button:
                self._record_touch_target("header", 0, 0, self.display.width, banner_h)
                self._record_touch_target("back_button", 0, 0, back_w, banner_h, action_kind="tap_back", button_id="back")
                self._text_theme("<", 30, max(1, (banner_h - self._measure_text("<", text_scale, "regular")[1]) // 2), "text", text_scale, "regular")
            else:
                self._record_touch_target("header", 0, 0, self.display.width, banner_h)
            title_x = 88 if (self.touch_layout_enabled and show_back_button) else pad_x
            self._text_theme(fitted, title_x, text_y, "text", text_scale, text_weight)
            if busy:
                spinner = activity_frame(ticks)
                spinner_w, spinner_h = self._measure_text(spinner, text_scale, "medium")
                self._text_theme(spinner, max(pad_x, self.display.width - pad_x - spinner_w), max(1, (banner_h - spinner_h) // 2), "accent", text_scale, "medium")
            return
        self.display.rect(0, 0, self.display.width, banner_h, True, True)
        if self.touch_layout_enabled and show_back_button:
            self._record_touch_target("header", 0, 0, self.display.width, banner_h)
            self._record_touch_target("back_button", 0, 0, back_w, banner_h, action_kind="tap_back", button_id="back")
            arrow_x = 20
            arrow_y = max(1, (banner_h - self._measure_text("<", text_scale, text_weight)[1]) // 2)
            self._text("<", arrow_x, arrow_y, text_scale, text_weight, on=False)
        else:
            self._record_touch_target("header", 0, 0, self.display.width, banner_h)
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


def should_enable_touch_layout(input_kind: str) -> bool:
    return str(input_kind).strip().lower() in {"touch_zones", "touch_direct"}
