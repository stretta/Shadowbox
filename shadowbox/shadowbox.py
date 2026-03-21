#!/usr/bin/env python3

from __future__ import annotations

import re
from queue import Empty, SimpleQueue
from threading import Thread
from time import monotonic, sleep

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from shadowbox.display import create_display
from shadowbox.encoder import EncoderInput
from shadowbox.rnbo import RNBOClient
from shadowbox.ui import ShadowboxUI
from shadowbox.renderer import ShadowboxRenderer


FPS = 20
FRAME_DT = 1.0 / FPS
REFRESH_SECONDS = 3.0

DIM_TIMEOUT = 120.0
SLEEP_TIMEOUT = 600.0
BRIGHTNESS_NORMAL = 0x7F
BRIGHTNESS_DIM = 0x10
OSC_LISTEN_HOST = "127.0.0.1"
OSC_LISTEN_PORT = 13333


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


def _assign_next_unused_inputs(ui, rnbo, instance_id: str) -> bool:
    instance = next((item for item in ui.state.instances if item.get("id") == instance_id), None)
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
        if other.get("id") == instance_id:
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
    instance = next((item for item in ui.state.instances if item.get("id") == instance_id), None)
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
        if other.get("id") == instance_id:
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
    display = create_display("ssd1309")
    display.init()
    display.set_contrast(BRIGHTNESS_NORMAL)

    rnbo = RNBOClient()
    osc_listener = RunnerOSCListener()
    encoder = EncoderInput()
    ui = ShadowboxUI(rnbo=rnbo)
    renderer = ShadowboxRenderer(display=display)
    ui.restore_from_saved_state()
    osc_listener.start()
    rnbo.send_value("/rnbo/listeners/add", osc_listener.listener_spec)

    # Startup splash
    renderer.draw_splash("SHADOWBOX")
    sleep(1.2)

    # Initial discovery
    ui.set_busy(True, "refresh")
    ui.apply_runner_snapshot(rnbo.discover())
    ui.set_busy(False)

    # Always start clean at TOP level
    ui.reset_to_top()

    last_frame = 0.0
    last_refresh = 0.0
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
            display.set_contrast(BRIGHTNESS_NORMAL)
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
                        before_ids = [inst.get("id") for inst in ui.state.instances]
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        after_ids = [inst.get("id") for inst in ui.state.instances]
                        new_ids = [item for item in after_ids if item not in before_ids]
                        if new_ids:
                            changed = _assign_next_unused_inputs(ui, rnbo, new_ids[-1])
                            changed = _assign_next_unused_outputs(ui, rnbo, new_ids[-1]) or changed
                            if changed:
                                sleep(0.1)
                                ui.apply_runner_snapshot(rnbo.discover())
                                after_ids = [inst.get("id") for inst in ui.state.instances]
                            ui.state.active_instance_id = new_ids[-1]
                            ui.state.instance_cursor = after_ids.index(new_ids[-1]) + 1
                            ui.state.ui_mode = "INSTANCE_MENU"
                            ui.state.instance_menu_cursor = 1
                        ui.set_busy(False)

                elif action.kind == "replace_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        target_id = ui.state.active_instance_id
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        after_ids = [inst.get("id") for inst in ui.state.instances]
                        if target_id in after_ids:
                            ui.state.active_instance_id = target_id
                            ui.state.instance_cursor = after_ids.index(target_id) + 1
                        ui.state.ui_mode = "INSTANCE_MENU"
                        ui.state.instance_menu_cursor = 1
                        ui.set_busy(False)

                elif action.kind == "remove_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        removed_id = str(action.value)
                        before_ids = [inst.get("id") for inst in ui.state.instances]
                        removed_index = before_ids.index(removed_id) if removed_id in before_ids else max(ui.state.instance_cursor - 1, 0)
                        rnbo.send_value(action.path, action.value)
                        sleep(0.2)
                        ui.apply_runner_snapshot(rnbo.discover())
                        after_ids = [inst.get("id") for inst in ui.state.instances]
                        if after_ids:
                            new_index = min(removed_index, len(after_ids) - 1)
                            ui.state.active_instance_id = after_ids[new_index]
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
                    rnbo.restart_jack()
                    sleep(0.6)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "set_jack_config":
                    if action.path is not None:
                        ui.set_busy(True, "audio")
                        rnbo.send_value(action.path, action.value)
                        rnbo.restart_jack()
                        sleep(0.6)
                        ui.apply_runner_snapshot(rnbo.discover())
                        ui.set_busy(False)

                elif action.kind == "restart_jack":
                    ui.set_busy(True, "audio")
                    rnbo.restart_jack()
                    sleep(0.6)
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
                display.set_contrast(BRIGHTNESS_DIM)
                is_dimmed = True

            # Draw at fixed-ish frame rate, but skip while sleeping
            if (not is_sleeping) and (now - last_frame) >= FRAME_DT:
                last_frame = now
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
        display.set_contrast(BRIGHTNESS_NORMAL)
        display.clear()
        display.show()


if __name__ == "__main__":
    main()
