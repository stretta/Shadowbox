from __future__ import annotations

from time import monotonic
from typing import Callable

MODE_FPS = {
    "BRICK_PANEL": 30.0,
}


class RenderScheduler:
    def __init__(self, *, clock: Callable[[], float] = monotonic, mode: str = "dirty"):
        self.clock = clock
        self.mode = mode if mode in {"legacy", "dirty"} else "dirty"
        self.dirty = True
        self.reason = "startup"
        self.last_render = float("-inf")
        self.last_animation = float("-inf")
        self.last_input_render = float("-inf")
        self.input_requested_at: float | None = None

    def request(self, reason: str = "state", *, input_event: bool = False) -> None:
        self.dirty = True
        self.reason = str(reason)
        if input_event:
            self.input_requested_at = self.clock()

    @staticmethod
    def frame_rate(ui) -> float | None:
        state = ui.state
        if state.busy or state.status_message:
            return 10.0
        if state.ui_mode == "BRICK_PANEL":
            return 30.0
        if state.ui_mode == "INSTANCE_SURFACE":
            return ui.active_surface_frame_rate
        if state.ui_mode == "EDIT" and ui.selected_param:
            from shadowbox.editors.pitch_display import is_pitch_display_param
            from shadowbox.editors.scope import is_scope_param
            from shadowbox.editors.step16 import is_step16_param
            if is_scope_param(ui.selected_param):
                return 15.0
            if is_pitch_display_param(ui.selected_param) or is_step16_param(ui.selected_param):
                return 20.0
        return None

    @property
    def input_pending(self) -> bool:
        return self.input_requested_at is not None

    def animation_due(self, ui, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        fps = self.frame_rate(ui)
        if fps is None:
            return False
        return now - self.last_animation >= 1.0 / fps

    def should_render(self, ui, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        fps = self.frame_rate(ui)
        if self.mode == "legacy":
            fps = fps or 20.0
            return now - self.last_render >= 1.0 / fps
        # Human input is event-driven.  The framebuffer path is fast enough to
        # present each coalesced input sample, and static/data-only redraws are
        # still controlled by dirty invalidation and mode-specific caps.
        if self.input_pending:
            return True
        if not self.dirty and fps is None:
            return False
        if not self.dirty and fps is not None and (ui.state.ui_mode == "BRICK_PANEL" or ui.state.busy or ui.state.status_message):
            self.dirty = True
        if not self.dirty:
            return False
        return fps is None or now - self.last_render >= 1.0 / fps

    def rendered(self, now: float | None = None, *, animation_advanced: bool = False) -> float | None:
        now = self.clock() if now is None else now
        latency = None if self.input_requested_at is None else max(0.0, now - self.input_requested_at)
        self.last_render = now
        if self.input_pending:
            self.last_input_render = now
        if animation_advanced:
            self.last_animation = now
        self.dirty = False
        self.input_requested_at = None
        return latency
