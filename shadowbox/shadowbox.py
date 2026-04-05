#!/usr/bin/env python3

from __future__ import annotations

import os
import re
from queue import Empty, SimpleQueue
from threading import Thread
from time import monotonic, sleep

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from shadowbox.display import load_display_from_env
from shadowbox.encoder import EncoderInput
from shadowbox.rnbo import RNBOClient
from shadowbox.ui import ShadowboxUI
from shadowbox.renderer import create_renderer


FPS = 20
FRAME_DT = 1.0 / FPS
TURBO_FPS = 40
TURBO_FRAME_DT = 1.0 / TURBO_FPS
REFRESH_SECONDS = 3.0
STARTUP_MIN_SECONDS = 1.2
STARTUP_DISCOVERY_TIMEOUT = 15.0
STARTUP_DISCOVERY_POLL_SECONDS = 0.4
STARTUP_STABLE_PASSES = 2
STARTUP_FOUND_HOLD_SECONDS = 1.0

DIM_TIMEOUT = 120.0
SLEEP_TIMEOUT = 600.0
BRIGHTNESS_NORMAL = 0x7F
BRIGHTNESS_DIM = 0x10
OSC_LISTEN_HOST = "127.0.0.1"
OSC_LISTEN_PORT = 13333
POST_LOAD_VIEW_DEFAULT = "instance"


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value, 0)
    except ValueError:
        return default


DIM_TIMEOUT = max(0.0, _env_float("SHADOWBOX_DIM_TIMEOUT", DIM_TIMEOUT))
SLEEP_TIMEOUT = max(DIM_TIMEOUT, _env_float("SHADOWBOX_SLEEP_TIMEOUT", SLEEP_TIMEOUT))
BRIGHTNESS_NORMAL = max(0, min(255, _env_int("SHADOWBOX_BRIGHTNESS_NORMAL", BRIGHTNESS_NORMAL)))
BRIGHTNESS_DIM = max(0, min(BRIGHTNESS_NORMAL, _env_int("SHADOWBOX_BRIGHTNESS_DIM", BRIGHTNESS_DIM)))
TURBO_FPS = max(1, _env_int("SHADOWBOX_TURBO_FPS", _env_int("SHADOWBOX_BRICK_PANEL_FPS", TURBO_FPS)))
TURBO_FRAME_DT = 1.0 / TURBO_FPS


def _is_tft_display(display) -> bool:
    module = type(display).__module__
    return module.startswith("shadowbox.display.st7789") or module.startswith("shadowbox.display.waveshare_2inch")


class RunnerOSCListener:
    def __init__(self, host: str = OSC_LISTEN_HOST, port: int = OSC_LISTEN_PORT):
        self.host = host
        self.port = port
        self.queue: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._dispatcher = Dispatcher()
        self._dispatcher.set_default_handler(self._handle_message, needs_reply_address=False)
        self._server = ThreadingOSCUDPServer((self.host, self.port), self._dispatcher)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def listener_spec(self) -> str:
        return f"{self.host}:{self.port}"

    def _handle_message(self, address: str, *args) -> None:
        value: object
        if len(args) == 0:
            value = None
        elif len(args) == 1:
            value = args[0]
        else:
            value = list(args)
        self.queue.put((str(address), value))

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1.0)

    def drain(self) -> list[tuple[str, object]]:
        items: list[tuple[str, object]] = []
        while True:
            try:
                items.append(self.queue.get_nowait())
            except Empty:
                return items


def _parse_instance_state_path(path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"(/rnbo/inst/(\d+)/(?:state/.+|messages/out/.+))", str(path))
    if not match:
        return None
    return match.group(2), match.group(1)


def _playback_index(name: str) -> int:
    match = re.fullmatch(r"system:playback_(\d+)", str(name))
    return int(match.group(1)) if match else 10**9


def _capture_index(name: str) -> int:
    match = re.fullmatch(r"system:capture_(\d+)", str(name))
    return int(match.group(1)) if match else 10**9


def _snapshot_ready(snapshot) -> bool:
    if snapshot is None:
        return False
    audio = snapshot.system.get("audio", {})
    status = snapshot.system.get("status", {})
    maint = snapshot.system.get("maint", {})
    return bool(
        snapshot.instances
        or snapshot.patchers
        or snapshot.add_instance_path
        or snapshot.remove_instance_path
        or status.get("runner_version")
        or audio.get("current_card")
        or audio.get("card_options")
        or audio.get("sample_rate_options")
        or maint.get("jack_restart_path")
    )


def _snapshot_signature(snapshot) -> tuple:
    if snapshot is None:
        return ()
    audio = snapshot.system.get("audio", {})
    status = snapshot.system.get("status", {})
    maint = snapshot.system.get("maint", {})
    return (
        tuple((str(item.get("id", "")), str(item.get("label", ""))) for item in snapshot.instances),
        tuple(str(item) for item in snapshot.patchers),
        str(snapshot.add_instance_path),
        str(snapshot.remove_instance_path),
        str(status.get("runner_version", "")),
        str(audio.get("current_card", "")),
        tuple(str(item) for item in audio.get("card_options", [])),
        tuple(str(item) for item in audio.get("sample_rate_options", [])),
        str(maint.get("jack_restart_path", "")),
    )


def _post_load_view() -> str:
    value = os.environ.get("SHADOWBOX_POST_LOAD_VIEW", POST_LOAD_VIEW_DEFAULT).strip().lower()
    if value in {"instance", "parameters", "presets"}:
        return value
    return POST_LOAD_VIEW_DEFAULT


def _apply_post_load_view(ui) -> None:
    view = _post_load_view()
    if view == "parameters":
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.param_cursor = 1 if ui.active_params else 0
        return
    if view == "presets":
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 1 if ui.active_presets else 0
        return
    ui.state.ui_mode = "INSTANCE_MENU"
    ui.state.instance_menu_cursor = 1


def _find_dummy_audio_device(ui) -> str:
    for option in ui.state.system.get("audio", {}).get("card_options", []):
        name = str(option).strip()
        if name and "dummy" in name.lower():
            return name
    return ""


def _try_dummy_audio_fallback(ui, rnbo) -> bool:
    audio = ui.state.system.get("audio", {})
    if audio.get("input_targets") or audio.get("output_targets"):
        return False

    dummy_device = _find_dummy_audio_device(ui)
    if not dummy_device:
        return False

    current_card = str(audio.get("current_card", "")).strip()
    if current_card == dummy_device:
        return False

    rnbo.set_audio_device(dummy_device)
    rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
    sleep(0.6)
    ui.apply_runner_snapshot(rnbo.discover())
    return True


def _discover_new_instance_ids(ui, rnbo, before_ids: list[str], attempts: int = 5, delay: float = 0.2) -> tuple[list[str], list[str]]:
    after_ids: list[str] = [str(inst.get("id", "")) for inst in ui.state.instances]
    new_ids = [item for item in after_ids if item not in before_ids]
    if new_ids:
        return after_ids, new_ids

    for attempt in range(1, max(0, attempts) + 1):
        sleep(delay)
        ui.apply_runner_snapshot(rnbo.discover())
        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
        new_ids = [item for item in after_ids if item not in before_ids]
        if new_ids:
            return after_ids, new_ids

    return after_ids, []


def _startup_status_lines(snapshot) -> tuple[str, str]:
    if _snapshot_ready(snapshot):
        return "OSCQuery Runner found!", "Launching..."
    return "waiting for OSCQuery Runner", "(this is normal) press encoder to enter"


def _assign_next_unused_inputs(ui, rnbo, instance_id: str) -> bool:
    instance = next((item for item in ui.state.instances if str(item.get("id", "")) == str(instance_id)), None)
    if not instance:
        return False

    inputs = list(instance.get("routing", {}).get("audio", {}).get("inputs", []))
    if not inputs:
        return False

    targets = ui.state.system.get("audio", {}).get("input_targets", [])
    capture_targets = sorted(
        [str(target) for target in targets if str(target).startswith("system:capture_")],
        key=_capture_index,
    )
    if not capture_targets:
        return False

    used_targets: set[str] = set()
    for other in ui.state.instances:
        if str(other.get("id", "")) == str(instance_id):
            continue
        other_inputs = other.get("routing", {}).get("audio", {}).get("inputs", [])
        for port in other_inputs:
            for connection in port.get("connections", []):
                if connection in capture_targets:
                    used_targets.add(str(connection))

    available_targets = [target for target in capture_targets if target not in used_targets]
    if not available_targets:
        return False

    changed = False
    for port, target in zip(inputs, available_targets):
        if not port.get("path"):
            continue
        current = [str(item) for item in port.get("connections", []) if str(item)]
        if current == [target]:
            continue
        rnbo.send_value(port.get("path"), [target])
        changed = True

    return changed


def _assign_next_unused_outputs(ui, rnbo, instance_id: str) -> bool:
    instance = next((item for item in ui.state.instances if str(item.get("id", "")) == str(instance_id)), None)
    if not instance:
        return False

    outputs = list(instance.get("routing", {}).get("audio", {}).get("outputs", []))
    if not outputs:
        return False

    targets = ui.state.system.get("audio", {}).get("output_targets", [])
    playback_targets = sorted(
        [str(target) for target in targets if str(target).startswith("system:playback_")],
        key=_playback_index,
    )
    if not playback_targets:
        return False

    used_targets: set[str] = set()
    for other in ui.state.instances:
        if str(other.get("id", "")) == str(instance_id):
            continue
        other_outputs = other.get("routing", {}).get("audio", {}).get("outputs", [])
        for port in other_outputs:
            for connection in port.get("connections", []):
                if connection in playback_targets:
                    used_targets.add(str(connection))

    available_targets = [target for target in playback_targets if target not in used_targets]
    if not available_targets:
        return False

    changed = False
    for port, target in zip(outputs, available_targets):
        if not port.get("path"):
            continue
        current = [str(item) for item in port.get("connections", []) if str(item)]
        if current == [target]:
            continue
        rnbo.send_value(port.get("path"), [target])
        changed = True

    return changed


def main():
    display = load_display_from_env(default_kind="st7789_raw")
    brightness_normal = BRIGHTNESS_NORMAL
    brightness_dim = BRIGHTNESS_DIM
    if _is_tft_display(display) and "SHADOWBOX_BRIGHTNESS_NORMAL" not in os.environ:
        brightness_normal = 0xFF
    if _is_tft_display(display) and "SHADOWBOX_BRIGHTNESS_DIM" not in os.environ:
        brightness_dim = min(brightness_normal, 0x40)
    display.init()
    display.set_contrast(brightness_normal)

    rnbo = RNBOClient()
    osc_listener = RunnerOSCListener()
    encoder = EncoderInput()
    ui = ShadowboxUI(rnbo=rnbo)
    renderer = create_renderer(display=display)
    ui.restore_from_saved_state()
    osc_listener.start()
    rnbo.send_value("/rnbo/listeners/add", osc_listener.listener_spec)

    # Startup discovery
    startup_started = monotonic()
    startup_last_poll = 0.0
    startup_stable_passes = 0
    startup_signature = None
    startup_found_at = None

    current_snapshot = None
    proceed_from_startup = False

    while True:
        now = monotonic()

        for event in encoder.get_events():
            if event.kind in {"short_press", "long_press"}:
                proceed_from_startup = True
                break
        if proceed_from_startup:
            break
        else:
            if (now - startup_last_poll) >= STARTUP_DISCOVERY_POLL_SECONDS:
                startup_last_poll = now
                ui.set_busy(True, "refresh")
                current_snapshot = rnbo.discover()
                ui.apply_runner_snapshot(current_snapshot)
                ui.set_busy(False)

                if _snapshot_ready(current_snapshot):
                    signature = _snapshot_signature(current_snapshot)
                    if signature == startup_signature:
                        startup_stable_passes += 1
                    else:
                        startup_signature = signature
                        startup_stable_passes = 1

                    if (
                        startup_stable_passes >= STARTUP_STABLE_PASSES
                        and (now - startup_started) >= STARTUP_MIN_SECONDS
                    ):
                        if startup_found_at is None:
                            startup_found_at = now
                else:
                    startup_signature = None
                    startup_stable_passes = 0
                    startup_found_at = None

            if startup_found_at is not None and (now - startup_found_at) >= STARTUP_FOUND_HOLD_SECONDS:
                break
            status_line, hint_line = _startup_status_lines(current_snapshot)
            renderer.draw_startup_status(
                "SHADOWBOX",
                status_line,
                hint_line,
            )
            sleep(0.05)
            continue
        break

    # Always start clean at TOP level
    ui.reset_to_top()

    last_frame = 0.0
    last_refresh = monotonic()
    last_activity = monotonic()

    is_dimmed = False
    is_sleeping = False

    def mark_activity() -> None:
        nonlocal last_activity, is_dimmed, is_sleeping
        last_activity = monotonic()

        if is_sleeping:
            display.wake()
            is_sleeping = False

        if is_dimmed:
            display.set_contrast(brightness_normal)
            is_dimmed = False

    try:
        while True:
            now = monotonic()

            # Pull pending hardware events
            events = encoder.get_events()
            if events:
                mark_activity()

            for event in events:
                ui.handle_event(event)

            for path, value in osc_listener.drain():
                parsed = _parse_instance_state_path(path)
                if parsed is None:
                    continue
                instance_id, full_path = parsed
                if ui.apply_instance_state_update(instance_id, full_path, value):
                    ui.state.activity_ticks += 1

            # Pull pending RNBO actions requested by UI
            for action in ui.pop_actions():
                if action.kind == "set_param":
                    if action.path is not None:
                        rnbo.set_param(action.path, action.value)

                elif action.kind == "send_osc":
                    if action.path is not None:
                        rnbo.send_value(action.path, action.value)

                elif action.kind == "load_preset":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.set_busy(False)

                elif action.kind == "load_set":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.state.ui_mode = "GRAPH_STATUS"
                        ui.state.graph_menu_cursor = 1
                        ui.set_busy(False)

                elif action.kind == "save_set":
                    if action.path is not None:
                        ui.set_busy(True, "save")
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.state.ui_mode = "GRAPH_STATUS"
                        ui.state.graph_menu_cursor = 1
                        ui.set_busy(False)

                elif action.kind == "set_graph_startup":
                    updates = action.value if isinstance(action.value, list) else []
                    if updates:
                        ui.set_busy(True, "startup")
                        for update in updates:
                            if not isinstance(update, (list, tuple)) or len(update) != 2:
                                continue
                            path, value = update
                            if path is None or str(path) == "":
                                continue
                            rnbo.send_value(str(path), value)
                        sleep(0.1)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.state.ui_mode = "GRAPH_STARTUP"
                        ui.set_busy(False)

                elif action.kind == "set_routing":
                    if action.path is not None:
                        ui.set_busy(True, "routing")
                        rnbo.send_value(action.path, action.value)
                        sleep(0.1)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.set_busy(False)

                elif action.kind == "add_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        rnbo.send_value(action.path, action.value)
                        after_ids, new_ids = _discover_new_instance_ids(ui, rnbo, before_ids)
                        if not new_ids and _try_dummy_audio_fallback(ui, rnbo):
                            rnbo.send_value(action.path, action.value)
                            after_ids, new_ids = _discover_new_instance_ids(ui, rnbo, before_ids)
                        if new_ids:
                            changed = _assign_next_unused_inputs(ui, rnbo, new_ids[-1])
                            changed = _assign_next_unused_outputs(ui, rnbo, new_ids[-1]) or changed
                            if changed:
                                sleep(0.1)
                                ui.apply_runner_snapshot(rnbo.discover())
                                after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                            ui.state.active_instance_id = str(new_ids[-1])
                            ui.state.instance_cursor = after_ids.index(new_ids[-1]) + 1
                            _apply_post_load_view(ui)
                        ui.set_busy(False)

                elif action.kind == "replace_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        target_id = str(ui.state.active_instance_id)
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        target_index = before_ids.index(target_id) if target_id in before_ids else max(ui.state.instance_cursor - 1, 0)
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        if target_id in after_ids:
                            ui.state.active_instance_id = str(target_id)
                            ui.state.instance_cursor = after_ids.index(target_id) + 1
                        else:
                            new_ids = [item for item in after_ids if item not in before_ids]
                            if new_ids:
                                replacement_id = new_ids[-1]
                                ui.state.active_instance_id = str(replacement_id)
                                ui.state.instance_cursor = after_ids.index(replacement_id) + 1
                            elif after_ids:
                                fallback_index = min(target_index, len(after_ids) - 1)
                                ui.state.active_instance_id = str(after_ids[fallback_index])
                                ui.state.instance_cursor = fallback_index + 1
                            else:
                                ui.state.active_instance_id = ""
                                ui.state.instance_cursor = 0
                        _apply_post_load_view(ui)
                        ui.set_busy(False)

                elif action.kind == "remove_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        removed_id = str(action.value)
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        removed_index = before_ids.index(removed_id) if removed_id in before_ids else max(ui.state.instance_cursor - 1, 0)
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        if after_ids:
                            new_index = min(removed_index, len(after_ids) - 1)
                            ui.state.active_instance_id = str(after_ids[new_index])
                            ui.state.instance_cursor = after_ids.index(ui.state.active_instance_id) + 1
                        else:
                            ui.state.active_instance_id = ""
                            ui.state.instance_cursor = 0
                        ui.state.pending_remove_instance_id = ""
                        ui.state.remove_instance_origin = ""
                        ui.state.ui_mode = "INSTANCE_LIST"
                        ui.set_busy(False)

                elif action.kind == "set_audio_device":
                    ui.set_busy(True, "audio")
                    rnbo.set_audio_device(action.device_name)
                    rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                    sleep(0.6)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "set_jack_config":
                    if action.path is not None:
                        ui.set_busy(True, "audio")
                        rnbo.send_value(action.path, action.value)
                        rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                        sleep(0.6)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.set_busy(False)

                elif action.kind == "restart_jack":
                    ui.set_busy(True, "audio")
                    rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                    sleep(0.6)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "refresh_snapshot":
                    ui.set_busy(True, "refresh")
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "save_state":
                    ui.save_state()

            # Periodic discovery refresh
            if (now - last_refresh) >= REFRESH_SECONDS:
                last_refresh = now
                if not ui.should_pause_refresh():
                    ui.set_busy(True, "refresh")
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

            # OLED dim / sleep policy
            idle = now - last_activity

            if (not is_sleeping) and idle >= SLEEP_TIMEOUT:
                display.sleep()
                is_sleeping = True

            elif (not is_dimmed) and idle >= DIM_TIMEOUT:
                display.set_contrast(brightness_dim)
                is_dimmed = True

            # Draw at fixed-ish frame rate, but allow selected screens to opt into a faster animation cadence.
            is_turbo_frame = ui.uses_turbo_rendering
            target_frame_dt = TURBO_FRAME_DT if is_turbo_frame else FRAME_DT
            frame_scale = target_frame_dt / FRAME_DT if is_turbo_frame else 1.0
            if (not is_sleeping) and (now - last_frame) >= target_frame_dt:
                last_frame = now
                ui.advance_frame(frame_scale=frame_scale)
                renderer.draw(ui)

            sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            rnbo.send_value("/rnbo/listeners/del", osc_listener.listener_spec)
        except Exception:
            pass
        osc_listener.stop()
        encoder.close()
        display.wake()
        display.set_contrast(brightness_normal)
        display.clear()
        display.show()


if __name__ == "__main__":
    main()
