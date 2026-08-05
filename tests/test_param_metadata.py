import json
import sys
import types
import unittest
from unittest import mock


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import ShadowboxRenderer, format_param_value, param_midi_mapping_marker, param_unit, routing_port_display_name
from shadowbox.rnbo import (
    _discover_wifi_networks,
    _wifi_scan_lines,
    discover_host_network,
    discover_instances,
    discover_set_presets,
    discover_sets,
    discover_system,
    extract_meta_info,
)
from shadowbox.ui import (
    UIEvent,
    ShadowboxUI,
    apply_edit_delta,
    edit_as_int,
    is_boolish,
    normalize_current_value_for_edit,
    numeric_step,
    quantize_edit_value,
    rnbo_integer_step_grid,
    rnbo_step,
)


class _DummyDisplay:
    width = 128
    height = 32

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (max(1, len(str(text))) * 6 * scale, 8 * scale)

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * scale

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        return None

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        return None

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        return None

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        return None


class _RecordingDisplay(_DummyDisplay):
    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        self.ops.append(("text", str(text), x, y, scale, weight, on))


class ParamMetadataTests(unittest.TestCase):
    def test_discover_host_network_prefers_wifi_primary_and_marks_direct_setup_when_wired_is_link_local(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = (
            "2: eth0    inet 169.254.12.34/16 brd 169.254.255.255 scope global noprefixroute eth0\n"
            "3: wlan0   inet 10.0.0.55/24 brd 10.0.0.255 scope global dynamic wlan0\n"
        )

        with (
            mock.patch("shadowbox.rnbo.os.listdir", return_value=["lo", "eth0", "wlan0"]),
            mock.patch(
                "shadowbox.rnbo.os.path.isdir",
                side_effect=lambda path: path == "/sys/class/net/wlan0/wireless",
            ),
            mock.patch(
                "shadowbox.rnbo._read_text",
                side_effect=lambda path: {
                    "/sys/class/net/eth0/carrier": "1",
                    "/sys/class/net/eth0/operstate": "up",
                    "/sys/class/net/wlan0/carrier": "",
                    "/sys/class/net/wlan0/operstate": "up",
                }.get(path, ""),
            ),
            mock.patch("shadowbox.rnbo.subprocess.run", return_value=completed),
            mock.patch(
                "shadowbox.rnbo._discover_wifi_networks",
                return_value=[{"ssid": "studio", "saved": True, "connected": True, "signal": "80"}],
            ),
            mock.patch("shadowbox.rnbo.socket.gethostname", return_value="shadowbox"),
        ):
            info = discover_host_network()

        self.assertEqual(info["wired_name"], "eth0")
        self.assertTrue(info["wired_link"])
        self.assertEqual(info["wired_ipv4"], "169.254.12.34")
        self.assertEqual(info["wired_link_local"], "169.254.12.34")
        self.assertEqual(info["wifi_name"], "wlan0")
        self.assertTrue(info["wifi_connected"])
        self.assertEqual(info["wifi_ssid"], "studio")
        self.assertEqual(info["wifi_ipv4"], "10.0.0.55")
        self.assertEqual(info["primary_ipv4"], "10.0.0.55")
        self.assertTrue(info["direct_setup_available"])
        self.assertFalse(info["direct_setup_active"])
        self.assertEqual(info["direct_setup_ip"], "")
        self.assertTrue(info["direct_setup_ready"])
        self.assertEqual(info["hostname_local"], "shadowbox.local")

    def test_discover_host_network_marks_direct_setup_active_when_fallback_ip_present(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = "2: eth0    inet 10.42.0.1/24 brd 10.42.0.255 scope global eth0\n"

        with (
            mock.patch("shadowbox.rnbo.os.listdir", return_value=["lo", "eth0"]),
            mock.patch("shadowbox.rnbo.os.path.isdir", return_value=False),
            mock.patch(
                "shadowbox.rnbo._read_text",
                side_effect=lambda path: {
                    "/sys/class/net/eth0/carrier": "1",
                    "/sys/class/net/eth0/operstate": "up",
                }.get(path, ""),
            ),
            mock.patch("shadowbox.rnbo.subprocess.run", return_value=completed),
            mock.patch("shadowbox.rnbo._discover_wifi_networks", return_value=[]),
            mock.patch("shadowbox.rnbo.socket.gethostname", return_value="shadowbox"),
            mock.patch("shadowbox.rnbo.DIRECT_ETHERNET_IP", "10.42.0.1"),
            mock.patch("shadowbox.rnbo.DIRECT_ETHERNET_IFACE", "eth0"),
        ):
            info = discover_host_network()

        self.assertTrue(info["direct_setup_available"])
        self.assertTrue(info["direct_setup_active"])
        self.assertEqual(info["direct_setup_ip"], "10.42.0.1")
        self.assertTrue(info["direct_setup_ready"])

    def test_discover_host_network_returns_empty_defaults_when_ip_command_fails(self) -> None:
        with (
            mock.patch("shadowbox.rnbo.os.listdir", return_value=[]),
            mock.patch("shadowbox.rnbo.subprocess.run", side_effect=OSError("missing ip")),
            mock.patch("shadowbox.rnbo._discover_wifi_networks", return_value=[]),
            mock.patch("shadowbox.rnbo.socket.gethostname", return_value="shadowbox"),
        ):
            info = discover_host_network()

        self.assertEqual(info["primary_ipv4"], "")
        self.assertFalse(info["wired_link"])
        self.assertFalse(info["wifi_connected"])
        self.assertFalse(info["direct_setup_available"])
        self.assertFalse(info["direct_setup_active"])
        self.assertEqual(info["direct_setup_ip"], "")
        self.assertFalse(info["direct_setup_ready"])
        self.assertEqual(info["hostname_local"], "shadowbox.local")

    def test_discover_wifi_networks_merges_saved_and_scanned_nmcli_rows(self) -> None:
        def fake_nmcli(args, timeout=3.0):
            if args[:2] == ["--fields", "NAME,TYPE,ACTIVE"]:
                return ["studio-profile:802-11-wireless:yes", "wired:802-3-ethernet:no", "stage-profile:802-11-wireless:no"]
            if args[:2] == ["--fields", "IN-USE,SSID,SIGNAL,SECURITY"]:
                return ["*:studio:80:WPA2", ":guest:40:WPA1 WPA2"]
            return []

        def fake_connection_ssid(connection_id):
            return {"studio-profile": "studio", "stage-profile": "stage"}.get(connection_id, "")

        with (
            mock.patch("shadowbox.rnbo._nmcli_lines", side_effect=fake_nmcli),
            mock.patch("shadowbox.rnbo._nmcli_connection_ssid", side_effect=fake_connection_ssid),
            mock.patch("shadowbox.rnbo._wifi_scan_lines", return_value=["*:studio:80:WPA2", ":guest:40:WPA1 WPA2"]),
        ):
            networks = _discover_wifi_networks()

        self.assertEqual(
            networks,
            [
                {"id": "studio-profile", "ssid": "studio", "saved": True, "connected": True, "signal": "80", "security": "WPA2"},
                {"id": "stage-profile", "ssid": "stage", "saved": True, "connected": False, "signal": "", "security": ""},
                {"id": "", "ssid": "guest", "saved": False, "connected": False, "signal": "40", "security": "WPA1 WPA2"},
            ],
        )

    def test_wifi_scan_lines_prefers_sudo_helper_when_available(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = " :Wefie:50:WPA2\n*:studio:80:WPA2\n"

        with (
            mock.patch("shadowbox.rnbo._wifi_network_helper_path", return_value="/tmp/wifi_network.sh"),
            mock.patch("shadowbox.rnbo.os.path.exists", return_value=True),
            mock.patch("shadowbox.rnbo.subprocess.run", return_value=completed) as run,
        ):
            lines = _wifi_scan_lines()

        self.assertEqual(lines, [" :Wefie:50:WPA2", "*:studio:80:WPA2"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["sudo", "-n", "/tmp/wifi_network.sh", "list"])

    def test_numeric_step_prefers_metadata_edit_step(self) -> None:
        param = {"type": "f", "min": 0, "max": 100, "metadata": {"edit_step": 2.5}}
        self.assertEqual(numeric_step(param), 2.5)

    def test_numeric_step_uses_rnbo_endpoint_inclusive_steps(self) -> None:
        note = {"type": "f", "min": 0, "max": 127, "metadata": {"steps": 128}}
        sample = {"type": "f", "min": 0, "max": 102, "metadata": {"steps": 103}}

        self.assertEqual(rnbo_step(note), 1)
        self.assertEqual(numeric_step(note), 1)
        self.assertEqual(numeric_step(sample), 1)

    def test_edit_step_overrides_rnbo_steps(self) -> None:
        param = {"type": "f", "min": 0, "max": 100, "metadata": {"steps": 101, "edit_step": 5}}
        self.assertEqual(numeric_step(param), 5)

    def test_rnbo_steps_quantize_to_grid_anchored_at_minimum(self) -> None:
        param = {"type": "f", "min": 0, "max": 64, "metadata": {"steps": 4}}

        self.assertAlmostEqual(numeric_step(param), 64 / 3)
        self.assertAlmostEqual(quantize_edit_value(param, 20), 64 / 3)
        self.assertAlmostEqual(apply_edit_delta(param, 20, 1), 128 / 3)

    def test_rnbo_integer_step_grid_is_detected_without_misclassifying_fractional_grid(self) -> None:
        note = {"min": 0, "max": 127, "metadata": {"steps": 128}}
        fractional = {"min": 0, "max": 64, "metadata": {"steps": 4}}

        self.assertTrue(rnbo_integer_step_grid(note))
        self.assertFalse(rnbo_integer_step_grid(fractional))

    def test_rnbo_steps_disable_float_encoder_acceleration(self) -> None:
        param = {"name": "Sample1/Note", "type": "f", "value": 38.0, "min": 0, "max": 127, "metadata": {"steps": 128}}
        ui = ShadowboxUI()
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 38.0

        ui.handle_event(UIEvent(kind="step", delta=1))
        ui.handle_event(UIEvent(kind="step", delta=1))

        self.assertEqual(ui.state.edit_value, 40.0)

    def test_normalize_current_value_for_edit_coerces_integer_style(self) -> None:
        param = {"type": "f", "value": 7.6, "metadata": {"edit_as": "int"}}
        self.assertEqual(normalize_current_value_for_edit(param), 8)

    def test_apply_edit_delta_uses_integer_style_and_edit_step(self) -> None:
        param = {"type": "f", "min": 0, "max": 10, "metadata": {"edit_as": "int", "edit_step": 1}}
        self.assertEqual(apply_edit_delta(param, 2.2, 1), 3)
        self.assertEqual(apply_edit_delta(param, 2.2, -1), 1)

    def test_edit_step_quantizes_to_grid_anchored_at_minimum(self) -> None:
        param = {
            "type": "f",
            "min": 30,
            "max": 3840,
            "metadata": {"edit_as": "int", "edit_step": "30"},
        }

        self.assertEqual(quantize_edit_value(param, 30), 30)
        self.assertEqual(quantize_edit_value(param, 411), 420)
        self.assertEqual(quantize_edit_value(param, 3840), 3840)
        self.assertEqual(apply_edit_delta(param, 411, 1), 450)

    def test_touch_edit_honors_explicit_step_grid(self) -> None:
        param = {
            "name": "Clock/ClockInterval",
            "value": 30.0,
            "path": "/rnbo/inst/1/params/Clock/ClockInterval",
            "min": 30.0,
            "max": 3840.0,
            "metadata": {"edit_as": "int", "edit_step": "30"},
        }
        ui = ShadowboxUI()
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 30

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.1, pressed=True))

        self.assertEqual(ui.state.edit_value, 420)
        action = next(action for action in ui.pop_actions() if action.kind == "set_param")
        self.assertEqual(action.value, 420)

    def test_numeric_keypad_commit_honors_explicit_step_grid(self) -> None:
        param = {
            "name": "Clock/ClockInterval",
            "value": 30.0,
            "path": "/rnbo/inst/1/params/Clock/ClockInterval",
            "min": 30.0,
            "max": 3840.0,
            "metadata": {"edit_as": "int", "edit_step": "30"},
        }
        ui = ShadowboxUI()
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 30
        ui.state.edit_numeric_draft = "46"

        ui.handle_event(UIEvent(kind="keypad_enter"))

        self.assertEqual(ui.state.edit_value, 60)
        action = next(action for action in ui.pop_actions() if action.kind == "set_param")
        self.assertEqual(action.value, 60)

    def test_float_editor_acceleration_applies_only_to_float_style_numeric_editing(self) -> None:
        ui = ShadowboxUI()
        ui.float_edit_accel_fast_seconds = 0.05
        ui.float_edit_accel_fast_multiplier = 2
        ui.float_edit_accel_turbo_seconds = 0.02
        ui.float_edit_accel_turbo_multiplier = 3
        float_param = {"type": "f", "min": 0, "max": 10, "metadata": {}}

        with mock.patch("shadowbox.ui.time.monotonic", side_effect=[100.0, 100.03, 100.045]):
            self.assertEqual(ui._accelerate_float_edit_delta(float_param, 1), 1)
            self.assertEqual(ui._accelerate_float_edit_delta(float_param, 1), 2)
            self.assertEqual(ui._accelerate_float_edit_delta(float_param, 1), 3)

    def test_float_editor_acceleration_does_not_apply_to_integer_style_editing(self) -> None:
        ui = ShadowboxUI()
        ui.float_edit_accel_fast_seconds = 1.0
        ui.float_edit_accel_fast_multiplier = 4
        int_style_param = {"type": "f", "min": 0, "max": 10, "metadata": {"edit_as": "int"}}

        with mock.patch("shadowbox.ui.time.monotonic", return_value=100.0):
            self.assertEqual(ui._accelerate_float_edit_delta(int_style_param, 1), 1)

    def test_integer_editing_is_not_inferred_from_param_type(self) -> None:
        param = {"type": "i", "value": 7.6, "metadata": {}}
        self.assertFalse(edit_as_int(param))
        self.assertEqual(normalize_current_value_for_edit(param), 7.6)

    def test_bool_editor_is_not_inferred_from_range(self) -> None:
        param = {"type": "f", "min": 0, "max": 1, "metadata": {}}
        self.assertFalse(is_boolish(param))

    def test_bool_editor_requires_explicit_metadata(self) -> None:
        renderer = ShadowboxRenderer(_DummyDisplay())
        self.assertFalse(renderer._is_bool_param({"type": "f", "min": 0, "max": 1, "metadata": {}}, 1))
        self.assertTrue(renderer._is_bool_param({"type": "f", "min": 0, "max": 1, "metadata": {"bool": True}}, 1))

    def test_bool_params_toggle_directly_from_parameter_list(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "enabled", "value": 0, "path": "/params/enabled", "metadata": {"bool": True}},
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(ui.selected_param.get("value"), 1)
        queued_kinds = [action.kind for action in ui.pop_actions()]
        self.assertIn("set_param", queued_kinds)
        self.assertIn("save_state", queued_kinds)

    def test_enum_params_still_open_the_enum_list(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "mode", "value": "A", "path": "/params/mode", "vals": ["A", "B", "C"]},
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "ENUM_LIST")
        self.assertEqual(ui.state.edit_value, "A")

    def test_enum_renderer_distinguishes_cursor_from_current_choice(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "mode", "value": "A", "path": "/params/mode", "vals": ["A", "B", "C"]},
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        display = _RecordingDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.draw_enum_list(ui, selected_idx=1)

        rows = [op[1] for op in display.ops if op[0] == "text"]
        self.assertIn("  (*) A", rows)
        self.assertIn("> ( ) B", rows)

    def test_live_param_update_refreshes_matching_param(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "cutoff", "value": 10.0, "path": "/rnbo/inst/1/params/cutoff"},
                    {"name": "resonance", "value": 0.0, "path": "/rnbo/inst/1/params/resonance"},
                ],
            }
        ]

        self.assertTrue(ui.apply_instance_param_update("1", "/rnbo/inst/1/params/cutoff", 42.0))

        self.assertEqual(ui.state.instances[0]["params"][0]["value"], 42.0)
        self.assertEqual(ui.state.instances[0]["params"][1]["value"], 0.0)

    def test_live_param_update_refreshes_open_edit_value(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {
                        "name": "WavetableA",
                        "value": 3.0,
                        "path": "/rnbo/inst/1/params/WavetableA",
                        "metadata": {"edit_as": "int"},
                    },
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 3

        self.assertTrue(ui.apply_instance_param_update("1", "/rnbo/inst/1/params/WavetableA", 11.7))

        self.assertEqual(ui.selected_param.get("value"), 11.7)
        self.assertEqual(ui.state.edit_value, 12)

    def test_numeric_keypad_commits_typed_float_from_general_editor(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "offset", "value": 3.0, "path": "/params/offset", "min": -100.0, "max": 100.0}
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 3.0

        for event in (
            UIEvent(kind="keypad_sign"),
            UIEvent(kind="keypad_digit", button_id="1"),
            UIEvent(kind="keypad_digit", button_id="2"),
            UIEvent(kind="keypad_decimal"),
            UIEvent(kind="keypad_digit", button_id="5"),
        ):
            ui.handle_event(event)

        self.assertEqual(ui.state.edit_numeric_draft, "-12.5")
        self.assertEqual(param["value"], 3.0)
        self.assertEqual(ui.pop_actions(), [])

        ui.handle_event(UIEvent(kind="keypad_enter"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(param["value"], -12.5)
        actions = ui.pop_actions()
        self.assertTrue(any(action.kind == "set_param" and action.value == -12.5 for action in actions))
        self.assertTrue(any(action.kind == "save_state" for action in actions))

    def test_numeric_keypad_clamps_integer_style_value_and_ignores_decimal(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "count",
            "value": 2,
            "path": "/params/count",
            "min": 0,
            "max": 16,
            "metadata": {"edit_as": "int"},
        }
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 2

        ui.handle_event(UIEvent(kind="keypad_sign"))
        ui.handle_event(UIEvent(kind="keypad_digit", button_id="9"))
        ui.handle_event(UIEvent(kind="keypad_decimal"))
        ui.handle_event(UIEvent(kind="keypad_digit", button_id="9"))
        ui.handle_event(UIEvent(kind="keypad_enter"))

        self.assertEqual(param["value"], 16)

    def test_numeric_keypad_backspace_and_encoder_cancel_typed_draft(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 1.0, "path": "/params/gain", "min": 0.0, "max": 10.0}
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 1.0

        ui.handle_event(UIEvent(kind="keypad_digit", button_id="4"))
        ui.handle_event(UIEvent(kind="keypad_digit", button_id="2"))
        ui.handle_event(UIEvent(kind="keypad_space"))
        self.assertEqual(ui.state.edit_numeric_draft, "4")

        ui.handle_event(UIEvent(kind="step", delta=1))

        self.assertEqual(ui.state.edit_numeric_draft, "")
        self.assertEqual(param["value"], 1.05)

    def test_midi_learn_button_enables_last_message_reporting(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "WaveBiasA", "value": 0, "path": "/rnbo/inst/5/params/WaveBiasA", "metadata": {}}
        ui.state.instances = [{"id": "5", "params": [param]}]
        ui.state.active_instance_id = "5"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"

        ui.handle_event(UIEvent(kind="tap_button", button_id="learn"))

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "send_osc")
        self.assertEqual(actions[0].path, "/rnbo/inst/5/midi/last/report")
        self.assertTrue(actions[0].value)
        self.assertEqual(ui.state.midi_learn_param_path, "/rnbo/inst/5/params/WaveBiasA")

    def test_midi_learn_update_writes_selected_param_metadata(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "WaveBiasA", "value": 0, "path": "/rnbo/inst/5/params/WaveBiasA", "metadata": {"edit_as": "int"}}
        ui.state.instances = [{"id": "5", "params": [param]}]
        ui.state.active_instance_id = "5"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.midi_learn_instance_id = "5"
        ui.state.midi_learn_param_path = "/rnbo/inst/5/params/WaveBiasA"

        self.assertTrue(ui.apply_instance_midi_learn_update("5", "/rnbo/inst/5/midi/last/value", '{"chan":4,"ctrl":16}'))

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions[0].kind, "send_osc")
        self.assertEqual(actions[0].path, "/rnbo/inst/5/params/WaveBiasA/meta")
        self.assertEqual(json.loads(actions[0].value), {"edit_as": "int", "midi": {"chan": 4, "ctrl": 16}})
        self.assertEqual(actions[1].kind, "save_midi_profile")
        self.assertEqual(actions[2].path, "/rnbo/inst/5/midi/last/report")
        self.assertFalse(actions[2].value)
        self.assertEqual(param["metadata"]["midi"], {"chan": 4, "ctrl": 16})
        self.assertEqual(ui.state.midi_learn_param_path, "")

    def test_midi_clear_button_removes_mapping_metadata(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "WaveBiasA",
            "value": 0,
            "path": "/rnbo/inst/5/params/WaveBiasA",
            "metadata": {"edit_as": "int", "midi": {"chan": 4, "ctrl": 16}},
        }
        ui.state.instances = [{"id": "5", "params": [param]}]
        ui.state.active_instance_id = "5"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"

        ui.handle_event(UIEvent(kind="tap_button", button_id="clear"))

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions[0].path, "/rnbo/inst/5/params/WaveBiasA/meta")
        self.assertEqual(json.loads(actions[0].value), {"edit_as": "int"})
        self.assertNotIn("midi", param["metadata"])

    def test_format_param_value_uses_display_precision(self) -> None:
        param = {"metadata": {"display_precision": 2}}
        self.assertEqual(format_param_value(param, 1.234), "1.23")

    def test_format_param_value_uses_integer_display_hint(self) -> None:
        param = {"metadata": {"display_as": "int"}}
        self.assertEqual(format_param_value(param, 3.7), "4")

    def test_format_param_value_uses_integer_rnbo_step_grid(self) -> None:
        param = {"min": 0, "max": 127, "metadata": {"steps": 128}}
        self.assertEqual(format_param_value(param, 38.0), "38")

    def test_format_param_value_preserves_fractional_rnbo_step_grid(self) -> None:
        param = {"min": 0, "max": 64, "metadata": {"steps": 4}}
        self.assertEqual(format_param_value(param, 64 / 3), "21.33")

    def test_format_param_value_appends_units_after_precision_formatting(self) -> None:
        param = {"metadata": {"display_precision": 1, "unit": "Hz"}}
        self.assertEqual(format_param_value(param, 42.34), "42.3Hz")

    def test_format_param_value_truncates_long_unit_labels(self) -> None:
        param = {"metadata": {"display_precision": 1, "unit": "semitones"}}
        self.assertEqual(param_unit(param), "se")
        self.assertEqual(format_param_value(param, 42.34), "42.3se")

    def test_param_midi_mapping_marker_formats_channel_and_cc(self) -> None:
        param = {"metadata": {"midi": {"chan": 4.0, "ctrl": 28.0}}}
        self.assertEqual(param_midi_mapping_marker(param), "4:28")

    def test_extract_meta_info_parses_editor_and_precision_from_tag_list(self) -> None:
        node = {
            "CONTENTS": {
                "meta": {
                    "VALUE": '["ttid", "display_precision:0", "display_as:int", "edit_as:int"]'
                }
            }
        }

        self.assertEqual(
            extract_meta_info(node),
            {
                "tags": ["ttid", "display_precision:0", "display_as:int", "edit_as:int"],
                "editor": "ttid",
                "display_precision": 0,
                "display_as": "int",
                "edit_as": "int",
            },
        )

    def test_extract_meta_info_keeps_explicit_editor_when_tags_include_bare_editor_name(self) -> None:
        node = {
            "CONTENTS": {
                "meta": {"VALUE": '["ttid"]'},
                "editor": {"VALUE": "step16"},
            }
        }

        self.assertEqual(extract_meta_info(node).get("editor"), "step16")

    def test_extract_meta_info_promotes_trigger_sequencer_tag_to_editor(self) -> None:
        node = {
            "CONTENTS": {
                "meta": {"VALUE": '["trigger sequencer"]'},
            }
        }

        self.assertEqual(extract_meta_info(node).get("editor"), "trigger sequencer")

    def test_extract_meta_info_preserves_direct_unit_children(self) -> None:
        node = {
            "CONTENTS": {
                "meta": {"VALUE": '{"display_precision": 1}'},
                "unit": {"VALUE": "Hz"},
                "units": {"VALUE": "ignored once unit is present"},
                "steps": {"VALUE": 128},
            }
        }

        self.assertEqual(
            extract_meta_info(node),
            {
                "display_precision": 1,
                "unit": "Hz",
                "units": "ignored once unit is present",
                "steps": 128,
            },
        )

    def test_discover_instances_uses_routing_label_metadata_for_display_name(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "info": {
                                    "CONTENTS": {
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {
                                                    "CONTENTS": {
                                                        "sources": {"VALUE": ["system:capture_1"]},
                                                        "sinks": {"VALUE": ["system:playback_1"]},
                                                    }
                                                },
                                                "midi": {
                                                    "CONTENTS": {
                                                        "sources": {"VALUE": []},
                                                        "sinks": {"VALUE": []},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "inst": {
                            "CONTENTS": {
                                "1": {
                                    "CONTENTS": {
                                        "name": {"VALUE": "My Synth"},
                                        "jack": {
                                            "CONTENTS": {
                                                "connections": {
                                                    "CONTENTS": {
                                                        "audio": {
                                                            "CONTENTS": {
                                                                "sinks": {
                                                                    "CONTENTS": {
                                                                        "in1": {
                                                                            "FULL_PATH": "/rnbo/inst/1/jack/connections/audio/sinks/in1",
                                                                            "VALUE": ["system:capture_1"],
                                                                            "CONTENTS": {
                                                                                "meta": {"VALUE": '["label:Main Input"]'},
                                                                            },
                                                                        }
                                                                    }
                                                                },
                                                                "sources": {
                                                                    "CONTENTS": {
                                                                        "out1": {
                                                                            "FULL_PATH": "/rnbo/inst/1/jack/connections/audio/sources/out1",
                                                                            "VALUE": ["system:playback_1"],
                                                                            "CONTENTS": {
                                                                                "display_name": {"VALUE": "Main Output"},
                                                                            },
                                                                        }
                                                                    }
                                                                },
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        instances = discover_instances(tree)

        self.assertEqual(instances[0]["routing"]["audio"]["inputs"][0]["name"], "in1")
        self.assertEqual(instances[0]["routing"]["audio"]["inputs"][0]["display_name"], "Main Input")
        self.assertEqual(instances[0]["routing"]["audio"]["outputs"][0]["display_name"], "Main Output")

    def test_discover_set_presets_reads_published_graph_preset_branch(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "presets": {
                                                    "CONTENTS": {
                                                        "save": {"FULL_PATH": "/rnbo/inst/control/sets/presets/save"},
                                                        "load": {
                                                            "FULL_PATH": "/rnbo/inst/control/sets/presets/load",
                                                            "RANGE": [{"VALS": ["Unipolar Positive", "linke synce"]}],
                                                        },
                                                        "loaded": {"VALUE": "linke synce"},
                                                        "count": {"VALUE": 2},
                                                        "destroy": {"FULL_PATH": "/rnbo/inst/control/sets/presets/destroy"},
                                                        "rename": {"FULL_PATH": "/rnbo/inst/control/sets/presets/rename"},
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        presets = discover_set_presets(tree)

        self.assertEqual(presets["save_path"], "/rnbo/inst/control/sets/presets/save")
        self.assertEqual(presets["load_path"], "/rnbo/inst/control/sets/presets/load")
        self.assertEqual(presets["rename_path"], "/rnbo/inst/control/sets/presets/rename")
        self.assertEqual(presets["destroy_path"], "/rnbo/inst/control/sets/presets/destroy")
        self.assertEqual(presets["loaded_name"], "linke synce")
        self.assertEqual(presets["count"], 2)
        self.assertEqual(presets["available_presets"], ["Unipolar Positive", "linke synce"])

    def test_discover_sets_reads_published_set_capabilities(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "save": {"FULL_PATH": "/rnbo/inst/control/sets/save"},
                                                "rename": {"FULL_PATH": "/rnbo/inst/control/sets/rename"},
                                                "load": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/load",
                                                    "RANGE": [{"VALS": ["Alpha", "Bravo"]}],
                                                },
                                                "reload": {"FULL_PATH": "/rnbo/inst/control/sets/reload"},
                                                "initial": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/initial",
                                                    "VALUE": "Alpha",
                                                },
                                                "current": {
                                                    "CONTENTS": {
                                                        "name": {"VALUE": "Bravo"},
                                                        "dirty": {"VALUE": True},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                },
                                "config": {
                                    "CONTENTS": {
                                        "auto_start_last": {
                                            "FULL_PATH": "/rnbo/inst/config/auto_start_last",
                                            "VALUE": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }

        sets = discover_sets(tree)

        self.assertEqual(sets["current_name"], "Bravo")
        self.assertTrue(sets["dirty"])
        self.assertEqual(sets["save_path"], "/rnbo/inst/control/sets/save")
        self.assertEqual(sets["rename_path"], "/rnbo/inst/control/sets/rename")
        self.assertEqual(sets["load_path"], "/rnbo/inst/control/sets/load")
        self.assertEqual(sets["reload_path"], "/rnbo/inst/control/sets/reload")
        self.assertEqual(sets["initial_path"], "/rnbo/inst/control/sets/initial")
        self.assertEqual(sets["initial_value"], "Alpha")
        self.assertEqual(sets["available_sets"], ["Alpha", "Bravo"])
        self.assertEqual(sets["auto_start_last_path"], "/rnbo/inst/config/auto_start_last")
        self.assertTrue(sets["auto_start_last"])

    def test_discover_instances_reads_preset_save_and_rename_capabilities(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "info": {
                                    "CONTENTS": {
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                                "midi": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "inst": {
                            "CONTENTS": {
                                "1": {
                                    "CONTENTS": {
                                        "name": {"VALUE": "Synth A"},
                                        "presets": {
                                            "CONTENTS": {
                                                "entries": {"VALUE": ["Init", "Bass"]},
                                                "load": {"FULL_PATH": "/rnbo/inst/1/presets/load"},
                                                "save": {"FULL_PATH": "/rnbo/inst/1/presets/save"},
                                                "rename": {"FULL_PATH": "/rnbo/inst/1/presets/rename"},
                                                "destroy": {"FULL_PATH": "/rnbo/inst/1/presets/destroy"},
                                                "current": {"CONTENTS": {"name": {"VALUE": "Bass"}}},
                                            }
                                        },
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        instances = discover_instances(tree)

        self.assertEqual(instances[0]["preset_save_path"], "/rnbo/inst/1/presets/save")
        self.assertEqual(instances[0]["preset_rename_path"], "/rnbo/inst/1/presets/rename")
        self.assertEqual(instances[0]["preset_destroy_path"], "/rnbo/inst/1/presets/destroy")
        self.assertEqual(instances[0]["current_preset_name"], "Bass")

    def test_discover_instances_includes_message_inports(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "7": {
                                    "CONTENTS": {
                                        "name": {"VALUE": "ListSequencer"},
                                        "messages": {
                                            "CONTENTS": {
                                                "in": {
                                                    "CONTENTS": {
                                                        "Steps": {
                                                            "FULL_PATH": "/rnbo/inst/7/messages/in/Steps",
                                                            "TYPE": "N",
                                                        },
                                                        "Velocity": {
                                                            "FULL_PATH": "/rnbo/inst/7/messages/in/Velocity",
                                                            "CONTENTS": {
                                                                "meta": {"VALUE": '["label:Velocity"]'},
                                                            },
                                                        },
                                                    }
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        instances = discover_instances(tree)

        self.assertEqual(
            [(item["name"], item["path"]) for item in instances[0]["inputs"]],
            [
                ("Steps", "/rnbo/inst/7/messages/in/Steps"),
                ("Velocity", "/rnbo/inst/7/messages/in/Velocity"),
            ],
        )
        self.assertEqual(instances[0]["inputs"][1]["metadata"]["label"], "Velocity")

    def test_discover_params_include_normalized_child_path(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "1": {
                                    "CONTENTS": {
                                        "params": {
                                            "CONTENTS": {
                                                "SamplingRate": {
                                                    "FULL_PATH": "/rnbo/inst/1/params/SamplingRate",
                                                    "VALUE": 10.0,
                                                    "TYPE": "f",
                                                    "ACCESS": 3,
                                                    "RANGE": [{"MIN": 10.0, "MAX": 100.0}],
                                                    "CONTENTS": {
                                                        "normalized": {
                                                            "FULL_PATH": "/rnbo/inst/1/params/SamplingRate/normalized",
                                                            "VALUE": 0.0,
                                                            "TYPE": "f",
                                                        }
                                                    },
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        instances = discover_instances(tree)

        param = instances[0]["params"][0]
        self.assertEqual(param["path"], "/rnbo/inst/1/params/SamplingRate")
        self.assertEqual(param["normalized_path"], "/rnbo/inst/1/params/SamplingRate/normalized")
        self.assertEqual(param["max"], 100.0)

    def test_discover_system_includes_set_name_and_sets_section(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "config": {
                                    "CONTENTS": {
                                        "card": {"FULL_PATH": "/rnbo/jack/config/card", "VALUE": "hw:ES8"},
                                        "period_frames": {"FULL_PATH": "/rnbo/jack/config/period_frames", "VALUE": 256},
                                        "sample_rate": {"FULL_PATH": "/rnbo/jack/config/sample_rate", "VALUE": 48000.0},
                                    }
                                },
                                "info": {
                                    "CONTENTS": {
                                        "cpu_load": {"VALUE": 1.5},
                                        "xrun_count": {"VALUE": 0},
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                                "midi": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                            }
                                        },
                                    }
                                },
                                "restart": {"FULL_PATH": "/rnbo/jack/restart"},
                                "transport": {
                                    "CONTENTS": {
                                        "bpm": {
                                            "FULL_PATH": "/rnbo/jack/transport/bpm",
                                            "TYPE": "f",
                                            "VALUE": 89.99995422363281,
                                        },
                                        "rolling": {
                                            "FULL_PATH": "/rnbo/jack/transport/rolling",
                                            "TYPE": "F",
                                            "VALUE": None,
                                        },
                                    }
                                },
                            }
                        },
                        "info": {"CONTENTS": {"runner_version": {"VALUE": "1.4.3"}}},
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "load": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/load",
                                                    "RANGE": [{"VALS": ["StudioA"]}],
                                                },
                                                "current": {
                                                    "CONTENTS": {
                                                        "name": {"VALUE": "StudioA"},
                                                        "dirty": {"VALUE": False},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        system = discover_system(tree)

        self.assertEqual(system["set_name"], "StudioA")
        self.assertEqual(system["sets"]["current_name"], "StudioA")
        self.assertEqual(system["sets"]["available_sets"], ["StudioA"])
        self.assertEqual(
            system["transport"],
            {
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 89.99995422363281,
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
            },
        )
        self.assertNotIn("network", system)


if __name__ == "__main__":
    unittest.main()
