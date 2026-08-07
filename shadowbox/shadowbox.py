#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic, sleep

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from shadowbox.display import load_display_from_env
from shadowbox.discovery import DiscoveryCoordinator, NetworkOperationCoordinator
from shadowbox.encoder import EncoderInput
from shadowbox.midi_mappings import apply_midi_profile_to_instance, save_instance_midi_profile
from shadowbox.rnbo import RNBOClient
from shadowbox.software_update import (
    read_all_software_update_status,
    start_shadowscore_update_install,
    start_software_update_install,
)
from shadowbox.ui import ShadowboxUI
from shadowbox.renderer import create_renderer, should_enable_touch_layout
from shadowbox.performance import PerformanceProbe, Timer
from shadowbox.render_scheduler import RenderScheduler
from shadowbox.transpose_control import (
    ROLE_CHROMATIC,
    ROLE_SCALAR,
    AlsaMidiControllerMonitor,
    normalize_role,
    transpose_targets,
)


FPS = 20
FRAME_DT = 1.0 / FPS
TURBO_FPS = 40
TURBO_FRAME_DT = 1.0 / TURBO_FPS
REFRESH_SECONDS = 3.0
STARTUP_MIN_SECONDS = 1.2
STARTUP_DISCOVERY_TIMEOUT = 60.0
STARTUP_DISCOVERY_POLL_SECONDS = 0.4
STARTUP_STABLE_PASSES = 2
STARTUP_FOUND_HOLD_SECONDS = 1.0
STARTUP_EMPTY_SET_GRACE_SECONDS = 8.0
STARTUP_AUDIO_DEVICE_PRIORITY_DEFAULT = (
    "hw:ES8",
    "hw:sndrpihifiberry",
    "hw:Dummy",
)
JACK_CARD_PATH_DEFAULT = "/rnbo/jack/config/card"
JACK_RESTART_PATH_DEFAULT = "/rnbo/jack/restart"
JACK_RESTART_TIMEOUT_SECONDS = 30.0
JACK_RESTART_POLL_SECONDS = 0.75

DIM_TIMEOUT = 120.0
SLEEP_TIMEOUT = 600.0
BRIGHTNESS_NORMAL = 0x7F
BRIGHTNESS_DIM = 0x10
OSC_LISTEN_HOST = "127.0.0.1"
OSC_LISTEN_PORT = 13333
POST_LOAD_VIEW_DEFAULT = "instance"
DIRECT_ETHERNET_HELPER_DEFAULT = str(Path(__file__).resolve().parent.parent / "tools" / "direct_ethernet.sh")
WIFI_NETWORK_HELPER_DEFAULT = str(Path(__file__).resolve().parent.parent / "tools" / "wifi_network.sh")
HDMI_MIRROR_HELPER_DEFAULT = str(Path(__file__).resolve().parent.parent / "tools" / "hdmi_mirror_config.py")
SYSTEM_POWER_HELPER_DEFAULT = str(Path(__file__).resolve().parent.parent / "tools" / "system_power.py")


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


def _env_text(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _parse_audio_device_priority(value: str | None) -> tuple[str, ...]:
    if value is None:
        return STARTUP_AUDIO_DEVICE_PRIORITY_DEFAULT
    devices = []
    for item in str(value).split(","):
        device = item.strip()
        if device and device not in devices:
            devices.append(device)
    return tuple(devices)


def _audio_device_priority_from_env() -> tuple[str, ...]:
    value = os.environ.get("SHADOWBOX_AUDIO_DEVICE_PRIORITY")
    if value is None:
        value = os.environ.get("SHADOWBOX_STARTUP_AUDIO_RECOVERY_DEVICE")
    return _parse_audio_device_priority(value)


DIM_TIMEOUT = max(0.0, _env_float("SHADOWBOX_DIM_TIMEOUT", DIM_TIMEOUT))
SLEEP_TIMEOUT = max(DIM_TIMEOUT, _env_float("SHADOWBOX_SLEEP_TIMEOUT", SLEEP_TIMEOUT))
BRIGHTNESS_NORMAL = max(0, min(255, _env_int("SHADOWBOX_BRIGHTNESS_NORMAL", BRIGHTNESS_NORMAL)))
BRIGHTNESS_DIM = max(0, min(BRIGHTNESS_NORMAL, _env_int("SHADOWBOX_BRIGHTNESS_DIM", BRIGHTNESS_DIM)))
STARTUP_DISCOVERY_TIMEOUT = max(0.0, _env_float("SHADOWBOX_STARTUP_DISCOVERY_TIMEOUT", STARTUP_DISCOVERY_TIMEOUT))
STARTUP_EMPTY_SET_GRACE_SECONDS = max(
    0.0,
    _env_float("SHADOWBOX_STARTUP_EMPTY_SET_GRACE_SECONDS", STARTUP_EMPTY_SET_GRACE_SECONDS),
)
STARTUP_AUDIO_DEVICE_PRIORITY = _audio_device_priority_from_env()
JACK_RESTART_TIMEOUT_SECONDS = max(
    1.0,
    _env_float("SHADOWBOX_JACK_RESTART_TIMEOUT", JACK_RESTART_TIMEOUT_SECONDS),
)
TURBO_FPS = max(1, _env_int("SHADOWBOX_TURBO_FPS", _env_int("SHADOWBOX_BRICK_PANEL_FPS", TURBO_FPS)))
TURBO_FRAME_DT = 1.0 / TURBO_FPS


def _is_tft_display(display) -> bool:
    module = type(display).__module__
    return (
        module.startswith("shadowbox.display.st7789")
        or module.startswith("shadowbox.display.waveshare_2inch")
        or module.startswith("shadowbox.display.waveshare_5inch_dsi")
    )


def _is_five_inch_dsi_display(display) -> bool:
    return type(display).__module__.startswith("shadowbox.display.waveshare_5inch_dsi")


def _direct_ethernet_helper_path() -> str:
    return _env_text("SHADOWBOX_DIRECT_ETHERNET_HELPER", DIRECT_ETHERNET_HELPER_DEFAULT)


def _wifi_network_helper_path() -> str:
    return _env_text("SHADOWBOX_WIFI_NETWORK_HELPER", WIFI_NETWORK_HELPER_DEFAULT)


def _hdmi_mirror_helper_path() -> str:
    return _env_text("SHADOWBOX_HDMI_MIRROR_HELPER", HDMI_MIRROR_HELPER_DEFAULT)


def _system_power_helper_path() -> str:
    return _env_text("SHADOWBOX_SYSTEM_POWER_HELPER", SYSTEM_POWER_HELPER_DEFAULT)


def _short_error_text(message: str, limit: int = 48) -> str:
    text = " ".join(str(message or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _run_direct_ethernet_helper(command: str) -> tuple[bool, str]:
    helper_path = _direct_ethernet_helper_path()
    if not helper_path or not os.path.exists(helper_path):
        return False, "helper missing"

    try:
        result = subprocess.run(
            ["sudo", "-n", helper_path, command],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return False, "sudo unavailable"
    except subprocess.TimeoutExpired:
        return False, "network timeout"
    except Exception as exc:
        return False, _short_error_text(str(exc))

    if result.returncode == 0:
        return True, ""

    detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
    lowered = detail.lower()
    if "password" in lowered and "sudo" in lowered:
        return False, "sudo not configured"
    return False, _short_error_text(detail)


def _run_wifi_network_helper(command: str, ssid: str = "", password: str = "") -> tuple[bool, str]:
    helper_path = _wifi_network_helper_path()
    if not helper_path or not os.path.exists(helper_path):
        return False, "helper missing"

    args = ["sudo", "-n", helper_path, command]
    if ssid:
        args.append(ssid)
    if password:
        args.append(password)

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return False, "sudo unavailable"
    except subprocess.TimeoutExpired:
        return False, "wifi timeout"
    except Exception as exc:
        return False, _short_error_text(str(exc))

    if result.returncode == 0:
        return True, ""

    detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
    lowered = detail.lower()
    if "password" in lowered and "sudo" in lowered:
        return False, "sudo not configured"
    return False, _short_error_text(detail)


def _run_fixed_privileged_helper(helper_path: str, command: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    if not helper_path or not os.path.exists(helper_path):
        return False, "helper missing"
    try:
        result = subprocess.run(
            ["sudo", "-n", helper_path, command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "sudo unavailable"
    except subprocess.TimeoutExpired:
        return False, "helper timeout"
    except Exception as exc:
        return False, _short_error_text(str(exc))
    if result.returncode == 0:
        return True, ""
    detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
    if "password" in detail.lower() and "sudo" in detail.lower():
        return False, "sudo not configured"
    return False, _short_error_text(detail)


def _run_hdmi_mirror_helper(enabled: bool) -> tuple[bool, str]:
    return _run_fixed_privileged_helper(_hdmi_mirror_helper_path(), "enable" if enabled else "disable")


def _run_system_reboot_helper() -> tuple[bool, str]:
    return _run_fixed_privileged_helper(_system_power_helper_path(), "reboot")


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
    match = re.fullmatch(r"(/rnbo/inst/(\d+)/(?:midi/last/value|params/.+|state/.+|messages/out/.+))", str(path))
    if not match:
        return None
    return match.group(2), match.group(1)


def _transport_event_key(path: str, system: dict) -> str:
    transport = system.get("transport", {}) if isinstance(system, dict) else {}
    for key in ("bpm", "rolling"):
        if str(path) == str(transport.get(f"{key}_path", "")):
            return key
    return ""


def _playback_index(name: str) -> int:
    match = re.fullmatch(r"system:playback_(\d+)", str(name))
    return int(match.group(1)) if match else 10**9


def _capture_index(name: str) -> int:
    match = re.fullmatch(r"system:capture_(\d+)", str(name))
    return int(match.group(1)) if match else 10**9


def _snapshot_ready(snapshot, *, allow_empty_set: bool = False) -> bool:
    if snapshot is None:
        return False
    if _snapshot_waiting_for_instances(snapshot) and not allow_empty_set:
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


def _snapshot_waiting_for_instances(snapshot) -> bool:
    if snapshot is None or snapshot.instances:
        return False
    system = snapshot.system if isinstance(snapshot.system, dict) else {}
    sets = system.get("sets", {})
    if not isinstance(sets, dict):
        return False

    current_name = str(sets.get("current_name", "") or system.get("set_name", "") or "").strip()
    initial_value = str(sets.get("initial_value", "") or "").strip()
    auto_start_last = sets.get("auto_start_last") is True
    return bool(current_name or initial_value or auto_start_last)


def _snapshot_loading_set_label(snapshot) -> str:
    if snapshot is None:
        return ""
    system = snapshot.system if isinstance(snapshot.system, dict) else {}
    sets = system.get("sets", {})
    if not isinstance(sets, dict):
        sets = {}
    for value in (
        sets.get("current_name", ""),
        system.get("set_name", ""),
        sets.get("initial_value", ""),
    ):
        text = str(value or "").strip()
        if text:
            return text
    if sets.get("auto_start_last") is True:
        return "last set"
    return ""


def _snapshot_signature(snapshot) -> tuple:
    if snapshot is None:
        return ()
    audio = snapshot.system.get("audio", {})
    status = snapshot.system.get("status", {})
    maint = snapshot.system.get("maint", {})
    transport = snapshot.system.get("transport", {})
    sets = snapshot.system.get("sets", {})
    if not isinstance(sets, dict):
        sets = {}
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
        str(transport.get("bpm_path", "")),
        transport.get("bpm"),
        str(transport.get("rolling_path", "")),
        transport.get("rolling"),
        str(sets.get("current_name", "") or snapshot.system.get("set_name", "")),
        str(sets.get("initial_value", "")),
        sets.get("auto_start_last") is True,
    )


def _empty_set_settling_signature(snapshot) -> tuple:
    """Track readiness inputs without volatile transport values.

    RNBO publishes a set name before its instances and does not expose a set-loading
    flag. A stable signature therefore provides the bounded settling signal for a
    set that may intentionally contain no instances.
    """
    audio = snapshot.system.get("audio", {})
    status = snapshot.system.get("status", {})
    maint = snapshot.system.get("maint", {})
    sets = snapshot.system.get("sets", {})
    if not isinstance(sets, dict):
        sets = {}
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
        str(sets.get("current_name", "") or snapshot.system.get("set_name", "")),
        str(sets.get("initial_value", "")),
        sets.get("auto_start_last") is True,
    )


def _update_empty_set_settling(
    snapshot,
    previous_signature: tuple | None,
    settled_since: float | None,
    now: float,
) -> tuple[tuple | None, float | None, bool]:
    if not _snapshot_waiting_for_instances(snapshot):
        return None, None, False

    signature = _empty_set_settling_signature(snapshot)
    if signature != previous_signature or settled_since is None:
        settled_since = now

    settled = (now - settled_since) >= STARTUP_EMPTY_SET_GRACE_SECONDS
    return signature, settled_since, settled


def _startup_discovery_timed_out(
    startup_started: float,
    now: float,
    startup_audio_attempted_device: str,
    snapshot,
    *,
    allow_empty_set: bool = False,
) -> bool:
    return bool(
        STARTUP_DISCOVERY_TIMEOUT > 0.0
        and (now - startup_started) >= STARTUP_DISCOVERY_TIMEOUT
        and not startup_audio_attempted_device
        and not _snapshot_ready(snapshot, allow_empty_set=allow_empty_set)
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


def _audio_needs_recovery(audio: dict) -> bool:
    if not audio.get("input_targets") and not audio.get("output_targets"):
        return True

    current_card = str(audio.get("current_card", "")).strip()
    card_options = {str(option).strip() for option in audio.get("card_options", []) if str(option).strip()}
    return bool(current_card and card_options and current_card not in card_options)


def _preferred_audio_device(
    audio: dict,
    priority: tuple[str, ...] = STARTUP_AUDIO_DEVICE_PRIORITY,
    excluded: set[str] | None = None,
) -> str:
    card_options = {str(option).strip() for option in audio.get("card_options", []) if str(option).strip()}
    excluded = excluded or set()
    for device in priority:
        if device in card_options and device not in excluded:
            return device
    return ""


def _try_startup_audio_device(ui, rnbo, device_name: str) -> bool:
    device_name = str(device_name or "").strip()
    if not device_name:
        return False
    try:
        rnbo.set_audio_device(device_name)
        restart_path = ui.state.system.get("maint", {}).get("jack_restart_path", "") or JACK_RESTART_PATH_DEFAULT
        rnbo.restart_jack(restart_path)
        return True
    except Exception as exc:
        print(f"Startup audio selection failed for {device_name!r}:", exc)
        return False


def _startup_audio_attempt_timed_out(started_at: float | None, now: float) -> bool:
    return started_at is not None and (now - started_at) >= JACK_RESTART_TIMEOUT_SECONDS


def _jack_restart_ready(snapshot, expected_card: str = "") -> bool:
    system = getattr(snapshot, "system", {})
    if not isinstance(system, dict):
        return False
    audio = system.get("audio", {})
    status = system.get("status", {})
    if not isinstance(audio, dict) or not isinstance(status, dict):
        return False
    current_card = str(audio.get("current_card", "") or "").strip()
    expected_card = str(expected_card or "").strip()
    if expected_card and current_card != expected_card:
        return False
    # cpu_load is published by JACK's live info tree. A card configuration can
    # reappear before the audio server itself is ready, so the config alone is
    # not a sufficient completion callback.
    return bool(current_card and status.get("cpu_load") is not None)

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


def _instance_by_id(ui, instance_id: str) -> dict | None:
    for instance in ui.state.instances:
        if str(instance.get("id", "")) == str(instance_id):
            return instance
    return None


def _apply_saved_midi_profile(ui, rnbo, instance_id: str) -> int:
    applied = apply_midi_profile_to_instance(_instance_by_id(ui, instance_id), rnbo)
    if applied:
        sleep(0.1)
        ui.apply_runner_snapshot(rnbo.discover())
    return applied


def _startup_status_lines(
    snapshot,
    stable_passes: int = 0,
    *,
    allow_empty_set: bool = False,
) -> tuple[str, str]:
    if _snapshot_waiting_for_instances(snapshot) and not allow_empty_set:
        label = _snapshot_loading_set_label(snapshot)
        if label:
            return "loading set", label
        return "loading instances", "waiting for RNBO"
    if _snapshot_ready(snapshot, allow_empty_set=allow_empty_set):
        if stable_passes < STARTUP_STABLE_PASSES:
            return "RNBO found", "stabilizing..."
        return "OSCQuery Runner found!", "Launching..."
    return "waiting for OSCQuery Runner", "(this is normal) press to enter"


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


def _fanout_transpose(
    ui,
    rnbo,
    role: str,
    value: int,
    delivered: dict[tuple[str, str], int],
    *,
    force_instance_ids: set[str] | None = None,
) -> tuple[int, int]:
    role = normalize_role(role)
    sent = 0
    unsupported = 0
    for target in transpose_targets(ui.state.instances, role):
        if not target.accepts(int(value)):
            unsupported += 1
            continue
        key = (role, target.path)
        forced = force_instance_ids is not None and target.instance_id in force_instance_ids
        if not forced and delivered.get(key) == int(value):
            continue
        rnbo.set_param(target.path, int(value))
        delivered[key] = int(value)
        sent += 1
    return sent, unsupported


def _report_transpose_delivery(ui, unsupported: int) -> None:
    """Report actionable target failures; having no target is a valid synth setup."""
    if unsupported:
        ui.set_status_message(f"{unsupported} transpose target out of range")


def _sync_new_transpose_targets(
    ui,
    rnbo,
    delivered: dict[tuple[str, str], int],
    *,
    force_instance_ids: set[str] | None = None,
) -> None:
    if str(ui.state.transpose_authority) != "standalone":
        return
    for role, value in (
        (ROLE_CHROMATIC, ui.state.transpose_chromatic),
        (ROLE_SCALAR, ui.state.transpose_scalar),
    ):
        _fanout_transpose(
            ui,
            rnbo,
            role,
            int(value),
            delivered,
            force_instance_ids=force_instance_ids,
        )


def _transpose_osc_command(path: str, value: object) -> tuple[str, int, str] | None:
    role = {
        "/shadowbox/transpose/chromatic": ROLE_CHROMATIC,
        "/shadowbox/transpose/scalar": ROLE_SCALAR,
    }.get(str(path))
    if role is None:
        return None
    values = value if isinstance(value, list) else [value]
    if not values or isinstance(values[0], bool) or not isinstance(values[0], (int, float)):
        return None
    source = str(values[1]).strip() if len(values) > 1 and str(values[1]).strip() else "External OSC"
    return role, int(round(float(values[0]))), source


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

    # Paint the first application-owned frame before constructing input,
    # network, MIDI, or UI subsystems. The boot helper may already have drawn
    # the same status screen; this replaces it without a visible transition.
    perf = PerformanceProbe()
    display.performance_probe = perf
    renderer = create_renderer(display=display)
    renderer.draw_startup_status("SHADOWBOX", "starting Shadowbox", "please wait", activity_phase=0.0)

    rnbo = RNBOClient()
    osc_listener = RunnerOSCListener()
    encoder = EncoderInput()
    ui = ShadowboxUI(
        rnbo=rnbo,
        hdmi_mirror_available=_is_five_inch_dsi_display(display),
        hdmi_mirror_enabled=_env_bool("SHADOWBOX_DSI_HDMI_MIRROR", False),
    )
    transpose_midi = AlsaMidiControllerMonitor()
    scheduler = RenderScheduler(mode=os.environ.get("SHADOWBOX_RENDER_SCHEDULER", "dirty").strip().lower())
    renderer.set_touch_mode(should_enable_touch_layout(encoder.input_kind))
    ui.restore_from_saved_state()
    transpose_midi.configure(ui.state.transpose_controller_identity)
    transpose_midi.start()
    osc_listener.start()
    rnbo.send_value("/rnbo/listeners/add", osc_listener.listener_spec)

    # Startup discovery
    startup_started = monotonic()
    startup_last_poll = 0.0
    startup_stable_passes = 0
    startup_signature = None
    startup_found_at = None
    startup_audio_failed_devices: set[str] = set()
    startup_audio_attempted_device = ""
    startup_audio_attempt_started = None
    startup_empty_set_signature = None
    startup_empty_set_since = None
    startup_allow_empty_set = False

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

                audio = ui.state.system.get("audio", {})
                if startup_audio_attempted_device:
                    if _jack_restart_ready(current_snapshot, startup_audio_attempted_device) and not _audio_needs_recovery(audio):
                        startup_audio_attempted_device = ""
                        startup_audio_attempt_started = None
                    elif _startup_audio_attempt_timed_out(startup_audio_attempt_started, now):
                        startup_audio_failed_devices.add(startup_audio_attempted_device)
                        startup_audio_attempted_device = ""
                        startup_audio_attempt_started = None

                preferred_device = _preferred_audio_device(audio, excluded=startup_audio_failed_devices)
                current_card = str(audio.get("current_card", "")).strip()
                if (
                    not startup_audio_attempted_device
                    and preferred_device
                    and (current_card != preferred_device or _audio_needs_recovery(audio))
                ):
                    print(f"Selecting startup audio device {preferred_device!r}")
                    if _try_startup_audio_device(ui, rnbo, preferred_device):
                        startup_audio_attempted_device = preferred_device
                        startup_audio_attempt_started = now
                    else:
                        startup_audio_failed_devices.add(preferred_device)
                    startup_signature = None
                    startup_stable_passes = 0
                    startup_found_at = None
                    startup_empty_set_signature = None
                    startup_empty_set_since = None
                    startup_allow_empty_set = False
                    continue

                was_allowing_empty_set = startup_allow_empty_set
                if startup_audio_attempted_device or _audio_needs_recovery(audio):
                    startup_empty_set_signature = None
                    startup_empty_set_since = None
                    startup_allow_empty_set = False
                else:
                    (
                        startup_empty_set_signature,
                        startup_empty_set_since,
                        startup_allow_empty_set,
                    ) = _update_empty_set_settling(
                        current_snapshot,
                        startup_empty_set_signature,
                        startup_empty_set_since,
                        now,
                    )
                if startup_allow_empty_set and not was_allowing_empty_set:
                    label = _snapshot_loading_set_label(current_snapshot) or "unnamed set"
                    print(f"RNBO set {label!r} remained empty; continuing startup")

                if not startup_audio_attempted_device and _snapshot_ready(
                    current_snapshot,
                    allow_empty_set=startup_allow_empty_set,
                ):
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

            if _startup_discovery_timed_out(
                startup_started,
                now,
                startup_audio_attempted_device,
                current_snapshot,
                allow_empty_set=startup_allow_empty_set,
            ):
                print("Startup discovery timed out; leaving the configured audio device unchanged")
                break

            status_line, hint_line = _startup_status_lines(
                current_snapshot,
                startup_stable_passes,
                allow_empty_set=startup_allow_empty_set,
            )
            renderer.draw_startup_status(
                "SHADOWBOX",
                status_line,
                hint_line,
                activity_phase=(now - startup_started) * 0.65,
            )
            sleep(0.05)
            continue
        break

    # Always start clean at TOP level
    ui.reset_to_top()
    transpose_delivered: dict[tuple[str, str], int] = {}
    _sync_new_transpose_targets(ui, rnbo, transpose_delivered)
    ui.set_software_update_status(read_all_software_update_status(fetch=False))
    update_status_queue: SimpleQueue[dict] = SimpleQueue()
    if _env_bool("SHADOWBOX_UPDATE_CHECK_ON_STARTUP", True):
        Thread(
            target=lambda: update_status_queue.put(read_all_software_update_status(fetch=True)),
            daemon=True,
        ).start()

    last_frame = 0.0
    last_refresh = monotonic()
    last_activity = monotonic()

    is_dimmed = False
    is_sleeping = False
    update_cancel_event: Event | None = None

    def mark_activity() -> None:
        nonlocal last_activity, is_dimmed, is_sleeping
        last_activity = monotonic()

        if is_sleeping:
            display.wake()
            is_sleeping = False

        if is_dimmed:
            display.set_contrast(brightness_normal)
            is_dimmed = False

    discovery = DiscoveryCoordinator(rnbo, metrics=perf)
    discovery.start()
    network_operations = NetworkOperationCoordinator(rnbo, _run_direct_ethernet_helper, _run_wifi_network_helper)
    network_operations.start()
    previous_mode = ui.state.ui_mode
    lifecycle_context: dict[str, dict] = {}
    jack_restart_context: dict[str, object] = {}

    try:
        while True:
            loop_started = monotonic()
            now = monotonic()

            # Pull pending hardware events
            events = encoder.get_events()
            if events:
                mark_activity()
                scheduler.request("input", input_event=True)
                perf.increment("input_batches")
                perf.increment("input_events", len(events))

            for event in events:
                ui.handle_event(event)

            ui.set_transpose_devices(transpose_midi.devices, transpose_midi.connected_identity)
            for midi_event in transpose_midi.drain():
                if ui.apply_transpose_midi_note(midi_event.note, midi_event.device_name):
                    mark_activity()
                    scheduler.request("transpose_midi", input_event=True)

            for path, value in osc_listener.drain():
                transpose_command = _transpose_osc_command(path, value)
                if transpose_command is not None:
                    role, offset, source = transpose_command
                    ui.set_transpose_value(role, offset, source)
                    continue
                transport_key = _transport_event_key(path, ui.state.system)
                if transport_key:
                    # OSC True/False typetags carry no arguments, so python-osc
                    # reports both as None. Re-read the advertised tree instead
                    # of mistaking a True notification for False.
                    if transport_key == "rolling" and value is None:
                        discovery.request("runner", "transport listener", delay=0.05)
                    elif ui.apply_transport_update(path, value):
                        ui.state.activity_ticks += 1
                    continue
                parsed = _parse_instance_state_path(path)
                if parsed is None:
                    continue
                instance_id, full_path = parsed
                if (
                    ui.apply_instance_state_update(instance_id, full_path, value)
                    or ui.apply_instance_param_update(instance_id, full_path, value)
                    or ui.apply_instance_midi_learn_update(instance_id, full_path, value)
                ):
                    ui.state.activity_ticks += 1

            for result in discovery.drain():
                perf.observe(f"discovery_{result.kind}", result.duration)
                if discovery.is_stale(result):
                    perf.increment("discovery_stale")
                    continue
                is_jack_restart = result.kind == "runner" and result.reason == "jack restart" and bool(jack_restart_context)
                if result.error:
                    if is_jack_restart:
                        elapsed = now - float(jack_restart_context.get("started_at", now))
                        if elapsed < JACK_RESTART_TIMEOUT_SECONDS:
                            discovery.request("runner", "jack restart", delay=JACK_RESTART_POLL_SECONDS)
                        else:
                            ui.fail_audio_restart("JACK did not restart")
                            jack_restart_context.clear()
                        scheduler.request("jack_restart")
                        continue
                    ui.set_status_message(f"Refresh failed: {_short_error_text(result.error)}")
                    if (result.kind == "runner" and ui.state.busy_reason not in {"network", "update"}) or (
                        result.kind != "runner" and ui.state.busy_reason == "network"
                    ):
                        ui.set_busy(False)
                    scheduler.request("discovery_error")
                    continue
                if result.kind == "runner":
                    ui.apply_runner_snapshot(result.value)
                    forced_transpose_ids: set[str] = set()
                    if is_jack_restart:
                        expected_card = str(jack_restart_context.get("expected_card", "") or "")
                        elapsed = now - float(jack_restart_context.get("started_at", now))
                        if _jack_restart_ready(result.value, expected_card):
                            ui.finish_audio_restart()
                            jack_restart_context.clear()
                        elif elapsed < JACK_RESTART_TIMEOUT_SECONDS:
                            discovery.request("runner", "jack restart", delay=JACK_RESTART_POLL_SECONDS)
                            scheduler.request("jack_restart")
                            continue
                        else:
                            ui.fail_audio_restart("JACK did not restart")
                            jack_restart_context.clear()
                    context = lifecycle_context.pop(result.reason, {})
                    if result.reason == "add instance":
                        before_ids = context.get("before_ids", [])
                        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        new_ids = [item for item in after_ids if item not in before_ids]
                        if new_ids:
                            new_id = new_ids[-1]
                            changed = _assign_next_unused_inputs(ui, rnbo, new_id)
                            changed = _assign_next_unused_outputs(ui, rnbo, new_id) or changed
                            applied = apply_midi_profile_to_instance(_instance_by_id(ui, new_id), rnbo)
                            if changed or applied:
                                discovery.request("runner", "finish add instance", delay=0.1)
                            ui.state.active_instance_id = new_id
                            ui.state.instance_cursor = after_ids.index(new_id) + 1
                            _apply_post_load_view(ui)
                            forced_transpose_ids.update(new_ids)
                    elif result.reason == "replace instance":
                        before_ids = context.get("before_ids", [])
                        target_id = context.get("target_id", "")
                        target_index = context.get("target_index", 0)
                        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        new_ids = [item for item in after_ids if item not in before_ids]
                        replacement_id = target_id if target_id in after_ids else (new_ids[-1] if new_ids else (after_ids[min(target_index, len(after_ids) - 1)] if after_ids else ""))
                        if replacement_id:
                            apply_midi_profile_to_instance(_instance_by_id(ui, replacement_id), rnbo)
                            ui.state.active_instance_id = replacement_id
                            ui.state.instance_cursor = after_ids.index(replacement_id) + 1
                            forced_transpose_ids.add(replacement_id)
                        _apply_post_load_view(ui)
                    elif result.reason == "remove instance":
                        after_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        if after_ids:
                            new_index = min(context.get("removed_index", 0), len(after_ids) - 1)
                            ui.state.active_instance_id = after_ids[new_index]
                            ui.state.instance_cursor = new_index + 1
                        ui.state.pending_remove_instance_id = ""
                        ui.state.remove_instance_origin = ""
                        ui.state.ui_mode = "INSTANCE_LIST"
                    _sync_new_transpose_targets(
                        ui,
                        rnbo,
                        transpose_delivered,
                        force_instance_ids=forced_transpose_ids or None,
                    )
                else:
                    ui.apply_network_snapshot(result.value)
                    if result.kind in {"wifi_list", "wifi_rescan"}:
                        ui.state.ui_mode = "WIFI_NETWORKS" if ui.network_wifi_available else "NETWORK"
                        ui.state.wifi_network_cursor = ui.wifi_network_initial_cursor()
                if (result.kind == "runner" and ui.state.busy_reason not in {"network", "update"}) or (
                    result.kind != "runner" and ui.state.busy_reason == "network"
                ):
                    ui.set_busy(False)
                scheduler.request("discovery")

            for result in network_operations.drain():
                ui.apply_network_snapshot(result.network)
                if result.ok:
                    ui.clear_network_error()
                else:
                    ui.set_network_error(_short_error_text(result.error))
                ui.state.ui_mode = "NETWORK"
                ui.state.network_cursor = 5 if result.kind.startswith("connect_wifi") and len(ui.network_value_rows) >= 5 else 1
                ui.set_busy(False)
                scheduler.request("network_operation")

            while True:
                try:
                    ui.set_software_update_status(update_status_queue.get_nowait())
                    if ui.state.busy_reason == "update":
                        ui.state.ui_mode = "SOFTWARE_UPDATE"
                        ui.set_busy(False)
                    scheduler.request("update_status")
                except Empty:
                    break

            # Pull pending RNBO actions requested by UI
            for action in ui.pop_actions():
                if action.kind == "set_param":
                    if action.path is not None:
                        rnbo.set_param(action.path, action.value)

                elif action.kind == "send_osc":
                    if action.path is not None:
                        rnbo.send_value(action.path, action.value)

                elif action.kind == "set_transport":
                    if action.path is not None:
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "transport", delay=0.15)

                elif action.kind == "set_transpose":
                    if action.path is not None and ui.state.transpose_authority == "standalone":
                        _sent, unsupported = _fanout_transpose(
                            ui,
                            rnbo,
                            action.path,
                            int(action.value),
                            transpose_delivered,
                        )
                        _report_transpose_delivery(ui, unsupported)

                elif action.kind == "configure_transpose_midi":
                    transpose_midi.configure(str(action.value or ""))

                elif action.kind == "set_transpose_authority":
                    transpose_delivered.clear()
                    if str(action.value or "") == "standalone":
                        _sync_new_transpose_targets(ui, rnbo, transpose_delivered)

                elif action.kind == "save_midi_profile":
                    instance = _instance_by_id(ui, str(action.value or ui.state.active_instance_id))
                    save_instance_midi_profile(instance, allow_empty=True)

                elif action.kind == "load_preset":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "load preset", delay=0.2)
                        ui.set_status_message(f"Loaded {action.value}")

                elif action.kind == "load_set":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        # Runner set loads currently append, so clear the live graph first
                        # when the published global unload path is available.
                        remove_path = ui.state.remove_instance_path
                        load_path = action.path
                        load_value = action.value

                        def load_set_worker(remove_path=remove_path, load_path=load_path, load_value=load_value):
                            if remove_path:
                                rnbo.send_value(remove_path, -1)
                                sleep(0.1)
                            rnbo.send_value(load_path, load_value)
                            discovery.request("runner", "load set", delay=0.2)

                        Thread(target=load_set_worker, daemon=True).start()
                        ui.state.ui_mode = "GRAPH_MENU"
                        ui.state.graph_menu_cursor = 1 if ui.graph_menu_items else 0
                        ui.set_status_message(f"Loaded {action.value}")

                elif action.kind == "load_graph_preset":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "load graph preset", delay=0.2)
                        ui.state.ui_mode = "GRAPH_PRESET_LIST"
                        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()
                        ui.set_status_message(f"Loaded {action.value}")

                elif action.kind == "save_graph_preset":
                    if action.path is not None:
                        ui.set_busy(True, "save")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "save graph preset", delay=0.2)
                        ui.state.ui_mode = "GRAPH_PRESET_LIST"
                        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()
                        ui.set_status_message(f"Saved {action.value}")

                elif action.kind == "rename_graph_preset":
                    if action.path is not None:
                        ui.set_busy(True, "rename")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "rename graph preset", delay=0.2)
                        ui.state.ui_mode = "GRAPH_PRESET_LIST"
                        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()

                elif action.kind == "delete_graph_preset":
                    if action.path is not None:
                        ui.set_busy(True, "delete")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "delete graph preset", delay=0.2)
                        ui.state.ui_mode = "GRAPH_PRESET_LIST"
                        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()
                        ui.set_status_message(f"Removed {action.value}")

                elif action.kind == "save_set":
                    if action.path is not None:
                        ui.set_busy(True, "save")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "save set", delay=0.2)
                        ui.state.ui_mode = "GRAPH_MENU"
                        ui.state.graph_menu_cursor = 1 if ui.graph_menu_items else 0
                        ui.set_status_message(f"Saved {action.value}")

                elif action.kind == "rename_set":
                    if action.path is not None:
                        ui.set_busy(True, "rename")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "rename set", delay=0.2)
                        ui.state.ui_mode = "GRAPH_STATUS"
                        ui.state.graph_menu_cursor = 1

                elif action.kind == "save_preset":
                    if action.path is not None:
                        ui.set_busy(True, "save")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "save preset", delay=0.2)
                        ui.state.ui_mode = "PRESET_LIST"
                        ui.state.preset_cursor = ui.preset_initial_cursor()
                        ui.set_status_message(f"Saved {action.value}")

                elif action.kind == "rename_preset":
                    if action.path is not None:
                        ui.set_busy(True, "rename")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "rename preset", delay=0.2)
                        ui.state.ui_mode = "PRESET_LIST"
                        ui.state.preset_cursor = ui.preset_initial_cursor()

                elif action.kind == "delete_preset":
                    if action.path is not None:
                        ui.set_busy(True, "delete")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "delete preset", delay=0.2)
                        ui.state.ui_mode = "PRESET_LIST"
                        ui.state.preset_cursor = ui.preset_initial_cursor()
                        ui.set_status_message(f"Removed {action.value}")

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
                        discovery.request("runner", "set graph startup", delay=0.1)
                        ui.state.ui_mode = "GRAPH_STARTUP"

                elif action.kind == "set_routing":
                    if action.path is not None:
                        ui.set_busy(True, "routing")
                        rnbo.send_value(action.path, action.value)
                        discovery.request("runner", "set routing", delay=0.1)

                elif action.kind == "add_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        rnbo.send_value(action.path, action.value)
                        lifecycle_context["add instance"] = {"before_ids": before_ids}
                        discovery.request("runner", "add instance", delay=0.25)

                elif action.kind == "replace_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        target_id = str(ui.state.active_instance_id)
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        target_index = before_ids.index(target_id) if target_id in before_ids else max(ui.state.instance_cursor - 1, 0)
                        rnbo.send_value(action.path, action.value)
                        lifecycle_context["replace instance"] = {"before_ids": before_ids, "target_id": target_id, "target_index": target_index}
                        discovery.request("runner", "replace instance", delay=0.25)

                elif action.kind == "remove_instance":
                    if action.path is not None:
                        ui.set_busy(True, "load")
                        removed_id = str(action.value)
                        before_ids = [str(inst.get("id", "")) for inst in ui.state.instances]
                        removed_index = before_ids.index(removed_id) if removed_id in before_ids else max(ui.state.instance_cursor - 1, 0)
                        rnbo.send_value(action.path, action.value)
                        lifecycle_context["remove instance"] = {"removed_index": removed_index}
                        discovery.request("runner", "remove instance", delay=0.25)

                elif action.kind == "set_audio_device":
                    ui.begin_audio_restart(action.device_name or "", "SYSTEM_AUDIO_DEVICE")
                    jack_restart_context = {"started_at": monotonic(), "expected_card": action.device_name or ""}
                    card_path = ui.state.system.get("audio", {}).get("card_path", JACK_CARD_PATH_DEFAULT)
                    rnbo.send_value(card_path, action.device_name)
                    rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                    discovery.request("runner", "jack restart", delay=0.6)

                elif action.kind == "set_jack_config":
                    if action.path is not None:
                        return_mode = "SYSTEM_AUDIO_RATE" if "sample_rate" in str(action.path) else "SYSTEM_AUDIO_BUFFER"
                        ui.begin_audio_restart(ui.state.audio_restart_device, return_mode)
                        jack_restart_context = {"started_at": monotonic(), "expected_card": ""}
                        rnbo.send_value(action.path, action.value)
                        rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                        discovery.request("runner", "jack restart", delay=0.6)

                elif action.kind == "restart_jack":
                    ui.begin_audio_restart("", "MAINT")
                    jack_restart_context = {"started_at": monotonic(), "expected_card": ""}
                    rnbo.restart_jack(ui.state.system.get("maint", {}).get("jack_restart_path", ""))
                    discovery.request("runner", "jack restart", delay=0.6)

                elif action.kind == "set_hdmi_mirror":
                    enabled = bool(action.value)
                    ok, error = _run_hdmi_mirror_helper(enabled)
                    ui.finish_hdmi_mirror_change(enabled, error="" if ok else error)

                elif action.kind == "reboot_system":
                    ok, error = _run_system_reboot_helper()
                    if not ok:
                        ui.set_busy(False)
                        ui.set_status_message(error or "reboot failed", frames=90)
                        ui.state.ui_mode = "SYSTEM_REBOOT_CONFIRM"
                        ui.state.reboot_confirm_cursor = 0

                elif action.kind == "refresh_snapshot":
                    ui.set_busy(True, "refresh")
                    discovery.request("runner", "manual refresh")

                elif action.kind in {"enable_direct_ethernet", "disable_direct_ethernet"}:
                    ui.set_busy(True, "network")
                    network_operations.request(action.kind)

                elif action.kind == "connect_wifi":
                    ui.set_busy(True, "network")
                    network_operations.request("connect_wifi", action.ssid or "")

                elif action.kind == "connect_wifi_new":
                    ui.set_busy(True, "network")
                    network_operations.request("connect_wifi_new", action.ssid or "", str(action.value or ""))

                elif action.kind == "rescan_wifi":
                    ui.set_busy(True, "network")
                    discovery.request("wifi_rescan", "explicit rescan")

                elif action.kind == "check_software_update":
                    ui.set_busy(True, "update")
                    ui.state.ui_mode = "SOFTWARE_UPDATE"
                    Thread(
                        target=lambda: update_status_queue.put(read_all_software_update_status(fetch=True)),
                        daemon=True,
                    ).start()

                elif action.kind == "apply_software_update":
                    if update_cancel_event is not None and not update_cancel_event.is_set():
                        continue
                    update_cancel_event = Event()
                    update_target = str(action.path or "shadowbox")
                    ui.set_busy(True, "update")
                    applying_statuses = dict(ui.state.software_update or {})
                    applying_targets = dict(applying_statuses.get("targets", {}))
                    applying_targets[update_target] = {
                        "state": "applying",
                        "message": "starting",
                        "available": False,
                    }
                    applying_statuses["targets"] = applying_targets
                    applying_statuses["state"] = "applying"
                    applying_statuses["message"] = "starting"
                    applying_statuses["available"] = False
                    ui.set_software_update_status(applying_statuses)
                    ui.state.ui_mode = "SOFTWARE_UPDATE"

                    def apply_update_worker(target: str, password: str, cancel_event: Event) -> None:
                        nonlocal update_cancel_event

                        def set_progress(message: str) -> None:
                            statuses = dict(ui.state.software_update or {})
                            targets = dict(statuses.get("targets", {}))
                            targets[target] = {
                                "state": "applying",
                                "message": message,
                                "available": False,
                            }
                            statuses["targets"] = targets
                            statuses["state"] = "applying"
                            statuses["message"] = message
                            statuses["available"] = False
                            ui.set_software_update_status(statuses)
                            ui.state.ui_mode = "SOFTWARE_UPDATE"

                        if target == "shadowscore":
                            status = start_shadowscore_update_install(
                                password,
                                status_callback=set_progress,
                                cancel_event=cancel_event,
                            )
                        else:
                            status = start_software_update_install(
                                password,
                                status_callback=set_progress,
                                cancel_event=cancel_event,
                            )
                        statuses = read_all_software_update_status(fetch=False)
                        statuses["targets"][target] = status.to_dict()
                        ui.set_software_update_status(statuses)
                        ui.state.ui_mode = "SOFTWARE_UPDATE"
                        ui.set_busy(False)
                        if update_cancel_event is cancel_event:
                            update_cancel_event = None

                    Thread(
                        target=apply_update_worker,
                        args=(update_target, str(action.value or ""), update_cancel_event),
                        daemon=True,
                    ).start()

                elif action.kind == "cancel_software_update":
                    if update_cancel_event is not None:
                        update_cancel_event.set()
                        ui.set_software_update_status(
                            {
                                "state": "applying",
                                "message": "canceling",
                                "available": False,
                            }
                        )
                    ui.state.ui_mode = "SOFTWARE_UPDATE"

                elif action.kind == "save_state":
                    ui.save_state()

            # Periodic discovery refresh
            if (now - last_refresh) >= REFRESH_SECONDS:
                last_refresh = now
                if not ui.should_pause_refresh():
                    discovery.request("runner", "periodic")

            if ui.state.ui_mode != previous_mode:
                previous_mode = ui.state.ui_mode
                scheduler.request("mode")
                if previous_mode == "NETWORK":
                    discovery.request("network_status", "network screen")
                elif previous_mode == "WIFI_NETWORKS":
                    discovery.request("wifi_list", "wifi screen")

            # OLED dim / sleep policy
            idle = now - last_activity

            if (not is_sleeping) and idle >= SLEEP_TIMEOUT:
                display.sleep()
                is_sleeping = True

            elif (not is_dimmed) and idle >= DIM_TIMEOUT:
                display.set_contrast(brightness_dim)
                is_dimmed = True
                scheduler.request("dim")

            if ui.render_revision:
                scheduler.request(ui.last_render_reason)
                ui.render_revision = 0

            if (not is_sleeping) and scheduler.should_render(ui, now):
                last_frame = now
                frame_rate = scheduler.frame_rate(ui) or FPS
                advance_animation = scheduler.animation_due(ui, now)
                if advance_animation:
                    ui.advance_frame(frame_scale=(1.0 / frame_rate) / FRAME_DT)
                render_timer = Timer(perf, "render")
                renderer.draw(ui, touch_state=encoder.touch_sample())
                render_timer.stop()
                encoder.set_touch_layout(renderer.touch_layout)
                # Use the presentation-complete timestamp.  Reusing ``now``
                # from the top of the loop hid the entire draw/framebuffer
                # duration and made the latency probe report near-zero values.
                presented_at = monotonic()
                input_latency = scheduler.rendered(presented_at, animation_advanced=advance_animation)
                if input_latency is not None:
                    perf.observe("input_to_render", input_latency)
                perf.increment(f"frames_{ui.state.ui_mode.lower()}")

            perf.observe("main_loop", monotonic() - loop_started)
            perf.maybe_log()

            sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        discovery.stop()
        network_operations.stop()
        transpose_midi.stop()
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
