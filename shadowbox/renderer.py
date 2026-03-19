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
from shadowbox.ttid import (
    BLACK_PCS,
    WHITE_PCS,
    get_root_names,
    is_pc_on,
    is_ttid_param,
    note_name,
)


TOP_LEVEL_ITEMS = ["PATCH", "PARAM", "SYSTEM"]
SYSTEM_ITEMS = ["STATUS", "AUDIO", "NETWORK", "STARTUP", "MAINT"]


def shorten(text: str, max_chars: int) -> str:
    text = str(text)
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def shorten_param_name(name: str) -> str:
    name = str(name)
    if "/" not in name:
        return name

    parts = [p for p in name.split("/") if p]
    if len(parts) < 2:
        return name

    parents = parts[:-1]
    leaf = parts[-1]
    short_parents = "/".join(p[0] for p in parents if p)

    if short_parents:
        return f"{short_parents}/{leaf}"
    return leaf


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


def activity_frame(ticks: int) -> str:
    frames = ["-", "\\", "|", "/"]
    return frames[ticks % len(frames)]


class ShadowboxRenderer:
    def __init__(self, display):
        self.display = display

    @property
    def is_tall(self) -> bool:
        return getattr(self.display, "height", 32) >= 64

    @property
    def content_rows(self) -> list[int]:
        if self.is_tall:
            return [10, 20, 30, 40, 50]
        return [8, 16, 24]

    @property
    def header_y(self) -> int:
        return 0

    @property
    def content_max_chars(self) -> int:
        return 21

    def text_center(self, text: str, y: int) -> None:
        text = str(text)
        x = max(0, (self.display.width - (len(text) * 6)) // 2)
        self.display.text(text, x, y)

    def list_window(self, selected_idx: int, total: int):
        rows = self.content_rows
        visible = len(rows)

        if total <= 0:
            return [], 0, rows

        selected_idx = max(0, min(selected_idx, total - 1))

        if total <= visible:
            indices = list(range(total))
            selected_row = selected_idx
            return indices, selected_row, rows[: len(indices)]

        half = visible // 2
        start = selected_idx - half
        end = start + visible

        if start < 0:
            start = 0
            end = visible
        elif end > total:
            end = total
            start = total - visible

        indices = list(range(start, end))
        selected_row = selected_idx - start
        return indices, selected_row, rows

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        self.display.text(shorten(title, 19), 0, self.header_y)
        if busy:
            self.display.text(activity_frame(ticks), 120, self.header_y)

    def draw_menu_row(self, y: int, selected: bool, label: str) -> None:
        prefix = "> " if selected else "  "
        self.display.text((prefix + shorten(label, 19))[: self.content_max_chars], 0, y)

    def draw_value_row(self, y: int, selected: bool, name: str, value: Any) -> None:
        prefix = "> " if selected else "  "

        left_width = 9
        right_width = 9

        left = shorten(shorten_param_name(name), left_width)
        right = shorten(format_display_value(value), right_width)

        line = f"{prefix}{left:<{left_width}} {right:>{right_width}}"
        self.display.text(line[: self.content_max_chars], 0, y)

    def _is_bool_param(self, param: dict, value: Any) -> bool:
        vals = param.get("vals")
        ptype = param.get("type", "")
        pmin = param.get("min")
        pmax = param.get("max")

        if ptype in ("T", "F"):
            return True

        if vals and len(vals) == 2:
            return True

        if pmin == 0 and pmax == 1:
            return True

        return isinstance(value, bool)

    def _is_enum_param(self, param: dict) -> bool:
        vals = param.get("vals")
        return isinstance(vals, list) and len(vals) > 0

    def _is_small_int_param(self, param: dict, value: Any) -> bool:
        ptype = param.get("type", "")
        pmin = param.get("min")
        pmax = param.get("max")

        if ptype not in ("i", "h", "I", "c"):
            return False

        if pmin is None or pmax is None:
            return False

        span = pmax - pmin
        return span <= 16

    def _draw_continuous_bar(self, norm: float, x: int, y: int, w: int, h: int) -> None:
        norm = max(0.0, min(1.0, norm))
        fill_w = int(norm * (w - 2))

        self.display.rect(x, y, w, h, True, False)
        if fill_w > 0:
            self.display.rect(x + 1, y + 1, fill_w, h - 2, True, True)

    def _draw_steps(self, active_idx: int, steps: int, x: int, y: int, w: int, h: int) -> None:
        if steps <= 0:
            return

        gap = 2
        step_w = max(1, (w - (gap * (steps - 1))) // steps)

        for i in range(steps):
            sx = x + i * (step_w + gap)
            filled = i <= active_idx
            self.display.rect(sx, y, step_w, h, True, filled)

    def _draw_bool_block(self, on: bool, x: int, y: int, w: int, h: int) -> None:
        self.display.rect(x, y, w, h, True, on)

    def _draw_enum_slots(self, vals: list[Any], value: Any, x: int, y: int, w: int, h: int) -> None:
        if not vals:
            return

        try:
            idx = vals.index(value)
        except ValueError:
            idx = 0

        self._draw_steps(idx, len(vals), x, y, w, h)

    def _fill_rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        if w <= 0 or h <= 0:
            return
        for yy in range(y, y + h):
            self.display.hline(x, yy, w, on)

    # --------------------------------------------------------
    # TTID keyboard helpers
    # --------------------------------------------------------

    def _ttid_white_segments(self, x: int, y: int, w: int, h: int, kind: str, black_h: int):
        """
        Return two rectangles describing the legal white-key shape:
        upper visible neck + lower full body.

        kind:
            left-notch  = C/F
            middle      = D/G/A
            right-notch = E/B
        """
        body_y = y + black_h
        body_h = max(0, h - black_h)

        # Upper visible neck dimensions
        neck_h = black_h
        neck_w = max(4, (w * 9) // 16)

        if kind in ("C", "F"):
            neck_x = x
        elif kind in ("E", "B"):
            neck_x = x + w - neck_w
        else:
            neck_x = x + (w - neck_w) // 2

        return {
            "neck": (neck_x, y, neck_w, neck_h),
            "body": (x, body_y, w, body_h),
        }

    def _draw_ttid_white_key(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        on: bool,
        selected: bool,
        key_kind: str,
        black_h: int,
    ) -> None:
        segs = self._ttid_white_segments(x, y, w, h, key_kind, black_h)
        nx, ny, nw, nh = segs["neck"]
        bx, by, bw, bh = segs["body"]

        # Fill only legal white-key shape, never into black-key area.
        if on:
            self._fill_rect(nx, ny, nw, nh, True)
            self._fill_rect(bx, by, bw, bh, True)

        # Outline the full white-key shape.
        self.display.rect(nx, ny, nw, nh, True, False)
        self.display.rect(bx, by, bw, bh, True, False)

        # Connect neck and body with side walls where needed.
        if key_kind in ("C", "F"):
            # Full left side.
            self.display.vline(x, y, h, True)
        if key_kind in ("E", "B"):
            # Full right side.
            self.display.vline(x + w - 1, y, h, True)

        # Selected state: show the whole key shape, not just lower body.
        # Use an inset outline over both neck and body.
        if selected:
            if nw > 4 and nh > 4:
                self.display.rect(nx + 1, ny + 1, nw - 2, nh - 2, True, False)
            if bw > 4 and bh > 4:
                self.display.rect(bx + 1, by + 1, bw - 2, bh - 2, True, False)

            # Bridge marker line so the whole key reads as selected.
            if by > ny + nh:
                self.display.vline(x + w // 2, ny + nh - 1, by - (ny + nh) + 1, True)

    def _draw_ttid_black_key(self, x: int, y: int, w: int, h: int, on: bool, selected: bool) -> None:
        self.display.rect(x, y, w, h, True, on)
        if selected:
            # Strong marker above black key.
            marker_w = max(5, w)
            marker_x = x + (w - marker_w) // 2
            self.display.rect(marker_x, max(0, y - 4), marker_w, 3, True, True)

    def draw_splash(self, title: str = "SHADOWBOX") -> None:
        self.display.clear()
        y = 28 if self.is_tall else 12
        self.text_center(title, y)
        self.display.show()

    def draw_top(self, state) -> None:
        indices, selected_row, rows = self.list_window(state.top_index, len(TOP_LEVEL_ITEMS))
        for row_idx, item_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, TOP_LEVEL_ITEMS[item_idx])

    def draw_patch_list(self, state) -> None:
        indices, selected_row, rows = self.list_window(state.patch_index, len(state.patches))
        for row_idx, patch_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, state.patches[patch_idx])

    def draw_param_list(self, state) -> None:
        if not state.params:
            if self.is_tall:
                self.text_center("no params", 22)
                self.text_center("long press <", 40)
            else:
                self.display.text("  no params", 0, 16)
                self.display.text("  long press <", 0, 24)
            return

        indices, selected_row, rows = self.list_window(state.param_index, len(state.params))
        for row_idx, p_idx in enumerate(indices):
            p = state.params[p_idx]
            self.draw_value_row(
                rows[row_idx],
                row_idx == selected_row,
                p.get("name", ""),
                p.get("value"),
            )

    def _fill_rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        if w <= 0 or h <= 0:
            return
        for yy in range(y, y + h):
            self.display.hline(x, yy, w, on)

    def _draw_ttid_keyboard(self, mask: int, selected_pc: int, x: int, y: int, w: int, h: int) -> None:
        """
        Draw a clean one-octave keyboard using shared boundaries.
        White-key divisions are drawn once.
        Black keys are drawn once.
        Selection is an overlay marker, not a redraw of the whole key.
        """

        # Geometry
        white_h = h
        black_h = max(8, int(h * 0.58))
        white_w = w // 7
        black_w = max(4, white_w // 2)

        # White key pitch classes in order
        white_pcs = [0, 2, 4, 5, 7, 9, 11]
        white_names = ["C", "D", "E", "F", "G", "A", "B"]

        # Black keys positioned between white keys
        black_positions = {
            1: 0,   # C#
            3: 1,   # Eb
            6: 3,   # F#
            8: 4,   # Ab
            10: 5,  # Bb
        }

        # ---- fill white key bodies first, respecting keyboard geometry ----
        for i, pc in enumerate(white_pcs):
            wx = x + i * white_w
            ww = white_w if i < 6 else (x + w) - wx

            on = is_pc_on(mask, pc)

            # shape model:
            # C/F : upper-left neck
            # D/G/A : centered neck
            # E/B : upper-right neck
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
                # Fill only legal white-key regions
                self._fill_rect(neck_x + 1, y + 1, max(0, neck_w - 2), max(0, neck_h - 1), True)
                self._fill_rect(wx + 1, body_y, max(0, ww - 2), max(0, body_h - 1), True)

        # ---- draw white-key borders once ----
        # outer frame
        self.display.rect(x, y, w, h, True, False)

        # vertical divisions between white keys
        for i in range(1, 7):
            vx = x + i * white_w
            self.display.vline(vx, y, h, True)

        # ---- draw black keys on top ----
        black_rects = {}
        for pc, white_index in black_positions.items():
            bx = x + ((white_index + 1) * white_w) - (black_w // 2)
            by = y
            bw = black_w
            bh = black_h

            black_rects[pc] = (bx, by, bw, bh)

            on = is_pc_on(mask, pc)

            # clear/cover the area first so white borders do not show through
            self._fill_rect(bx, by, bw, bh, False)

            # draw black key border once
            self.display.rect(bx, by, bw, bh, True, False)

            # if enabled, fill inside it
            if on and bw > 2 and bh > 2:
                self._fill_rect(bx + 1, by + 1, bw - 2, bh - 2, True)

        # ---- selection overlay only ----
        if selected_pc < 12:
            if selected_pc in black_rects:
                bx, by, bw, bh = black_rects[selected_pc]
                # black key selection marker above key
                marker_w = max(3, bw)
                marker_x = bx + (bw - marker_w) // 2
                self._fill_rect(marker_x, max(0, by - 4), marker_w, 3, True)
            else:
                white_index = white_pcs.index(selected_pc)
                wx = x + white_index * white_w
                ww = white_w if white_index < 6 else (x + w) - wx

                # white key selection marker at top for consistency
                kind = ["C", "D", "E", "F", "G", "A", "B"][white_index]
                neck_w = max(3, (ww * 6) // 16)

                if kind in ("C", "F"):
                    neck_x = wx
                elif kind in ("E", "B"):
                    neck_x = wx + ww - neck_w
                else:
                    neck_x = wx + (ww - neck_w) // 2

                marker_w = max(3, neck_w)
                marker_x = neck_x + (neck_w - marker_w) // 2
                self._fill_rect(marker_x, max(0, y - 4), marker_w, 3, True)

    def draw_edit_ttid(self, state, param) -> None:
        title = shorten(shorten_param_name(param.get("name", "")), 21)
        mask = int(state.edit_value or 0)
        mode = state.edit_ttid_mode

        if self.is_tall:
            self.text_center(title, 2)

            if mode == "keyboard":
                kb_x = 4
                kb_y = 16
                kb_w = 120
                kb_h = 32

                self._draw_ttid_keyboard(
                    mask,
                    state.edit_ttid_selected_pc,
                    kb_x,
                    kb_y,
                    kb_w,
                    kb_h,
                )

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
                root = state.edit_ttid_load_root % 12
                self.text_center("load root", 16)
                self.text_center(roots[root], 32)
                self.text_center("press -> scale", 54)

            elif mode == "load_scale":
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                scale_name = names[idx]
                self.text_center("load scale", 14)
                self.text_center(shorten(scale_name, 18), 30)
                self.text_center("press -> apply", 54)

        else:
            self.text_center(title, 0)

            if mode == "keyboard":
                if state.edit_ttid_selected_pc == 12:
                    self.text_center("LOAD", 12)
                else:
                    pc = state.edit_ttid_selected_pc
                    line = f"{note_name(pc)} {'ON' if is_pc_on(mask, pc) else 'OFF'}"
                    self.text_center(line, 12)
                self.text_center(str(mask), 24)

            elif mode == "load_root":
                roots = get_root_names()
                root = state.edit_ttid_load_root % 12
                self.text_center("root", 12)
                self.text_center(roots[root], 24)

            elif mode == "load_scale":
                names = state.edit_ttid_scale_names or ["major"]
                idx = max(0, min(len(names) - 1, state.edit_ttid_scale_index))
                self.text_center(shorten(names[idx], 21), 18)

    def draw_edit(self, state) -> None:
        param = None
        if state.params and 0 <= state.param_index < len(state.params):
            param = state.params[state.param_index]

        if param is None:
            self.text_center("no param", 28 if self.is_tall else 16)
            return

        name = shorten_param_name(param.get("name", ""))
        value = state.edit_value

        if is_ttid_param(param):
            self.draw_edit_ttid(state, param)
            return

        if self.is_tall:
            title_y = 4
            gfx_x = 4
            gfx_y = 20
            gfx_w = 120
            gfx_h = 24
            value_y = 52
        else:
            title_y = 0
            gfx_x = 4
            gfx_y = 12
            gfx_w = 120
            gfx_h = 12
            value_y = 26

        self.text_center(shorten(name, 21), title_y)

        vals = param.get("vals")
        pmin = param.get("min")
        pmax = param.get("max")

        if self._is_bool_param(param, value):
            on = bool(value)
            self._draw_bool_block(on, gfx_x, gfx_y, gfx_w, gfx_h)
            self.text_center("ON" if on else "OFF", value_y)

        elif self._is_enum_param(param):
            self._draw_enum_slots(vals, value, gfx_x, gfx_y, gfx_w, gfx_h)
            self.text_center(shorten(format_display_value(value), 21), value_y)

        elif self._is_small_int_param(param, value):
            active_idx = 0
            if pmin is not None and pmax is not None and isinstance(value, (int, float)):
                active_idx = int(round(value - pmin))
                active_idx = max(0, min(int(pmax - pmin), active_idx))
                self._draw_steps(active_idx, int(pmax - pmin) + 1, gfx_x, gfx_y, gfx_w, gfx_h)
            else:
                self.display.rect(gfx_x, gfx_y, gfx_w, gfx_h, True, False)

            self.text_center(shorten(format_display_value(value), 21), value_y)

        else:
            norm = 0.0
            if isinstance(value, (int, float)) and pmin is not None and pmax is not None:
                span = pmax - pmin
                if span > 0:
                    norm = (value - pmin) / span

            self._draw_continuous_bar(norm, gfx_x, gfx_y, gfx_w, gfx_h)
            self.text_center(shorten(format_display_value(value), 21), value_y)

    def draw_system_menu(self, state) -> None:
        indices, selected_row, rows = self.list_window(state.system_index, len(SYSTEM_ITEMS))
        for row_idx, item_idx in enumerate(indices):
            self.draw_menu_row(rows[row_idx], row_idx == selected_row, SYSTEM_ITEMS[item_idx])

    def draw_status(self, state) -> None:
        patch = state.current_patch or "-"
        cpu = state.system.get("status", {}).get("cpu_load", None)
        xr = state.system.get("status", {}).get("xruns", None)

        rows = self.content_rows
        self.draw_value_row(rows[0], False, "patch", patch)
        self.draw_value_row(rows[1], False, "cpu", "-" if cpu is None else f"{cpu:.1f}")
        self.draw_value_row(rows[2], False, "xruns", "-" if xr is None else xr)

    def draw_audio(self, state) -> None:
        audio = state.system.get("audio", {})
        options = audio.get("card_options", [])

        if options and 0 <= state.audio_card_index < len(options):
            device = options[state.audio_card_index]
        else:
            device = audio.get("current_card", "-")

        rate = audio.get("sample_rate", None)
        buf = audio.get("period_frames", None)

        rows = self.content_rows
        self.draw_value_row(rows[0], False, "device", device or "-")
        self.draw_value_row(rows[1], False, "rate", "-" if rate is None else int(rate))
        self.draw_value_row(rows[2], False, "buffer", "-" if buf is None else buf)

        if self.is_tall:
            self.text_center("press = apply", 56)

    def draw_network(self, state) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "?"

        rows = self.content_rows
        self.draw_value_row(rows[0], False, "ip", ip)
        self.draw_value_row(rows[1], False, "osc", RNBO_PORT)

        if self.is_tall:
            self.text_center("long press <", 56)
        else:
            self.display.text("long press <", 0, 24)

    def draw_startup(self, state) -> None:
        rows = self.content_rows
        self.draw_value_row(rows[1], False, "autoload", "ON" if state.auto_load_last_patch else "OFF")

        if self.is_tall:
            self.text_center("press = toggle", 56)
        else:
            self.display.text("short press tog", 0, 24)

    def draw_maint(self, state) -> None:
        if self.is_tall:
            self.text_center("jack restart", 20)
            self.text_center("press to run", 40)
        else:
            self.display.text("jack restart", 0, 10)
            self.display.text("short press", 0, 22)

    def draw(self, state) -> None:
        self.display.clear()

        if state.ui_mode == "EDIT":
            self.draw_edit(state)
            self.display.show()
            return

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
