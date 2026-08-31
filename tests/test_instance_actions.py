import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import ShadowboxRenderer
from shadowbox.rnbo import RNBO_PORT, RNBOSnapshot
from shadowbox.ui import MenuRow, ShadowboxUI, UIEvent
from shadowbox.transpose_control import MidiInputPort, ROLE_CHROMATIC, ROLE_SCALAR


class _FakeDisplay:
    width = 128
    height = 32

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, int, str, bool]] = []

    def clear(self) -> None:
        pass

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        self.calls.append((text, x, y, scale, weight, on))

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 6 * max(1, scale), 8 * max(1, scale))

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * max(1, scale)

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        pass

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        pass

    def show(self) -> None:
        pass


class _CaptureRenderer(ShadowboxRenderer):
    def __init__(self) -> None:
        super().__init__(_FakeDisplay())
        self.last_items: list[str] | None = None
        self.last_selected_idx: int | None = None
        self.last_current_indices: set[int] | None = None
        self.last_item_weights: dict[int, str] | None = None
        self.last_action_indices: set[int] | None = None
        self.last_value_rows: list[tuple[str, object]] | None = None
        self.last_value_weights: list[str | None] | None = None
        self.last_header: str | None = None
        self.last_selectable_value_rows: list[tuple[str, object, bool]] | None = None

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0, show_back_button: bool = False) -> None:
        self.last_header = title

    def draw_string_list(
        self,
        items: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
        action_indices: set[int] | None = None,
    ) -> None:
        self.last_items = items
        self.last_selected_idx = selected_idx
        self.last_current_indices = current_indices
        self.last_item_weights = item_weights
        self.last_action_indices = action_indices

    def draw_value_row(
        self,
        y: int,
        selected: bool,
        label: str,
        value: object,
        current: bool = False,
        emphasis: str | None = None,
        invert: bool = False,
    ) -> None:
        if self.last_value_rows is None:
            self.last_value_rows = []
        if self.last_value_weights is None:
            self.last_value_weights = []
        self.last_value_rows.append((label, value))
        self.last_value_weights.append(emphasis)
        if current:
            current_indices = self.last_current_indices or set()
            current_indices.add(len(self.last_value_rows))
            self.last_current_indices = current_indices

    def draw_selectable_value_rows(self, rows, selected_idx: int) -> None:
        self.last_selectable_value_rows = [(row.label, row.value, row.current) for row in rows]
        self.last_selected_idx = selected_idx

    def draw_menu_rows(self, rows: list[MenuRow], selected_idx: int) -> None:
        self.last_items = [str(row.label) for row in rows]
        self.last_selected_idx = selected_idx
        self.last_current_indices = {idx for idx, row in enumerate(rows) if row.current}
        self.last_action_indices = {idx for idx, row in enumerate(rows) if row.action}


class InstanceActionTests(unittest.TestCase):
    def test_audio_device_selection_immediately_shows_restart_feedback(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "audio": {
                "current_card": "hw:Dummy",
                "card_options": ["hw:Dummy", "hw:USB"],
            }
        }
        ui.state.ui_mode = "SYSTEM_AUDIO_DEVICE"
        ui.state.audio_device_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "SYSTEM_AUDIO_RESTART")
        self.assertTrue(ui.state.busy)
        self.assertEqual(ui.state.audio_restart_device, "hw:USB")
        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "set_audio_device")
        self.assertEqual(actions[0].device_name, "hw:USB")

    def test_audio_restart_completion_returns_to_picker_with_ready_feedback(self) -> None:
        ui = ShadowboxUI()
        ui.begin_audio_restart("hw:USB", "SYSTEM_AUDIO_DEVICE")

        ui.finish_audio_restart()

        self.assertEqual(ui.state.ui_mode, "SYSTEM_AUDIO_DEVICE")
        self.assertFalse(ui.state.busy)
        self.assertEqual(ui.state.status_message, "hw:USB ready")

    def _snapshot_with_direct_network(self) -> RNBOSnapshot:
        return RNBOSnapshot(
            instances=[],
            patchers=[],
            add_instance_path="",
            remove_instance_path="",
            system={
                "network": {
                    "hostname": "shadowbox",
                    "hostname_local": "shadowbox.local",
                    "wired_name": "eth0",
                    "wired_link": True,
                    "wired_ipv4": "169.254.12.34",
                    "wired_link_local": "169.254.12.34",
                    "wifi_name": "wlan0",
                    "wifi_connected": False,
                    "wifi_ssid": "",
                    "wifi_networks": [
                        {"id": "studio-profile", "ssid": "studio", "saved": True, "connected": False, "signal": "80", "security": "WPA2"},
                        {"id": "stage-profile", "ssid": "stage", "saved": True, "connected": False, "signal": "55", "security": "WPA2"},
                        {"id": "", "ssid": "guest", "saved": False, "connected": False, "signal": "35", "security": "WPA2"},
                        {"id": "", "ssid": "open", "saved": False, "connected": False, "signal": "25", "security": ""},
                    ],
                    "wifi_ipv4": "",
                    "primary_ipv4": "",
                    "direct_setup_available": True,
                    "direct_setup_active": False,
                    "direct_setup_ip": "",
                    "direct_setup_ready": True,
                }
            },
        )

    def _snapshot_with_active_direct_setup(self) -> RNBOSnapshot:
        snapshot = self._snapshot_with_direct_network()
        snapshot.system["network"]["wired_ipv4"] = "10.42.0.1"
        snapshot.system["network"]["primary_ipv4"] = "10.42.0.1"
        snapshot.system["network"]["direct_setup_active"] = True
        snapshot.system["network"]["direct_setup_ip"] = "10.42.0.1"
        snapshot.system["network"]["direct_setup_ready"] = True
        return snapshot

    def _snapshot_with_sets(self) -> RNBOSnapshot:
        return RNBOSnapshot(
            instances=[],
            patchers=[],
            add_instance_path="/rnbo/inst/control/load",
            remove_instance_path="/rnbo/inst/control/unload",
            system={
                "set_name": "StudioA",
                "sets": {
                    "current_name": "StudioA",
                    "dirty": True,
                    "available_sets": ["StudioA", "StudioB"],
                    "load_path": "/rnbo/inst/control/sets/load",
                    "save_path": "/rnbo/inst/control/sets/save",
                    "auto_start_last_path": "/rnbo/inst/config/auto_start_last",
                    "initial_path": "/rnbo/inst/control/sets/initial",
                    "auto_start_last": True,
                    "initial_value": "",
                },
            },
        )

    def _snapshot_with_set_rename(self) -> RNBOSnapshot:
        snapshot = self._snapshot_with_sets()
        snapshot.system["sets"]["rename_path"] = "/rnbo/inst/control/sets/rename"
        return snapshot

    def _snapshot_with_preset_capabilities(self) -> RNBOSnapshot:
        return RNBOSnapshot(
            instances=[
                {
                    "id": "1",
                    "label": "Synth A",
                    "presets": [
                        {"name": "Init", "path": "/rnbo/inst/1/presets/load", "value": "Init"},
                        {"name": "Bass", "path": "/rnbo/inst/1/presets/load", "value": "Bass"},
                    ],
                    "preset_save_path": "/rnbo/inst/1/presets/save",
                    "preset_rename_path": "/rnbo/inst/1/presets/rename",
                    "preset_destroy_path": "/rnbo/inst/1/presets/destroy",
                    "current_preset_name": "Bass",
                    "params": [],
                    "routing": {"audio": {"inputs": [], "outputs": []}, "midi": {"inputs": [], "outputs": []}},
                }
            ],
            patchers=[],
            add_instance_path="",
            remove_instance_path="",
            system={},
        )

    def _snapshot_with_graph_preset_capabilities(self) -> RNBOSnapshot:
        snapshot = self._snapshot_with_sets()
        snapshot.system["set_presets"] = {
            "save_path": "/rnbo/inst/control/sets/presets/save",
            "load_path": "/rnbo/inst/control/sets/presets/load",
            "rename_path": "/rnbo/inst/control/sets/presets/rename",
            "destroy_path": "/rnbo/inst/control/sets/presets/destroy",
            "loaded_name": "linke synce",
            "count": 2,
            "available_presets": ["Unipolar Positive", "linke synce"],
        }
        return snapshot

    def _snapshot_with_new_graph_set(self) -> RNBOSnapshot:
        snapshot = self._snapshot_with_sets()
        snapshot.system["sets"]["available_sets"] = ["New Graph", "StudioA", "StudioB"]
        return snapshot

    def _apply_empty_snapshot(self) -> ShadowboxUI:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[],
                patchers=[],
                add_instance_path="/rnbo/inst/control/load",
                remove_instance_path="/rnbo/inst/control/unload",
                system={},
            )
        )
        return ui

    def _snapshot_with_routing_overview(self) -> RNBOSnapshot:
        return RNBOSnapshot(
            instances=[
                {
                    "id": "1",
                    "label": "Synth A",
                    "params": [],
                    "presets": [],
                    "routing": {
                        "audio": {
                            "inputs": [
                                {"connections": ["system:capture_1"]},
                                {"connections": ["system:capture_2"]},
                            ],
                            "outputs": [
                                {"connections": ["system:playback_1"]},
                                {"connections": ["system:playback_2"]},
                            ],
                        },
                        "midi": {
                            "inputs": [{"connections": ["system:midi_from_keys"]}],
                            "outputs": [{"connections": ["system:midi_to_synth"]}],
                        },
                    },
                },
                {
                    "id": "2",
                    "label": "Looper",
                    "params": [],
                    "presets": [],
                    "routing": {
                        "audio": {
                            "inputs": [{"connections": ["system:capture_3"]}],
                            "outputs": [],
                        },
                        "midi": {
                            "inputs": [],
                            "outputs": [],
                        },
                    },
                },
            ],
            patchers=[],
            add_instance_path="",
            remove_instance_path="",
            system={},
        )

    def _snapshot_with_many_routing_instances(self, count: int = 8) -> RNBOSnapshot:
        instances = []
        for idx in range(1, count + 1):
            instances.append(
                {
                    "id": str(idx),
                    "label": f"Inst {idx}",
                    "params": [],
                    "presets": [],
                    "routing": {
                        "audio": {
                            "inputs": [{"connections": [f"system:capture_{idx}"]}],
                            "outputs": [{"connections": [f"system:playback_{idx}"]}],
                        },
                        "midi": {"inputs": [], "outputs": []},
                    },
                }
            )
        return RNBOSnapshot(
            instances=instances,
            patchers=[],
            add_instance_path="",
            remove_instance_path="",
            system={},
        )

    def test_empty_install_keeps_instance_actions_available(self) -> None:
        ui = self._apply_empty_snapshot()

        self.assertTrue(ui.can_add_instance)

    def test_network_rows_surface_direct_ethernet_setup_state(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())

        rows = [(row.label, row.value, row.current) for row in ui.network_value_rows]

        self.assertEqual(
            rows,
            [
                ("setup", "ENABLE", False),
                ("state", "OFF", False),
                ("wired", "LINK", True),
                ("eth ip", "169.254.12.34", False),
                ("wifi", "CHOOSE", False),
                ("wifi ip", "-", False),
                ("hint", "DIRECT READY", True),
                ("host", "shadowbox.local", False),
                ("osc", RNBO_PORT, False),
            ],
        )
        self.assertTrue(ui.network_value_rows[0].toggle)
        self.assertFalse(ui.network_value_rows[0].toggle_on)
        self.assertEqual(ui.network_ip_address, "169.254.12.34")

    def test_network_rows_show_active_direct_setup_state(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_active_direct_setup())

        rows = [(row.label, row.value, row.current) for row in ui.network_value_rows[:4]]

        self.assertEqual(
            rows,
            [
                ("setup", "DISABLE", True),
                ("state", "ACTIVE", True),
                ("wired", "LINK", True),
                ("eth ip", "10.42.0.1", False),
            ],
        )
        self.assertTrue(ui.network_value_rows[0].toggle)
        self.assertTrue(ui.network_value_rows[0].toggle_on)
        self.assertEqual(ui.network_ip_address, "10.42.0.1")

    def test_network_press_queues_enable_direct_ethernet(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "NETWORK"
        ui.state.network_cursor = 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.pop_actions()[0].kind, "enable_direct_ethernet")

    def test_network_press_queues_disable_direct_ethernet_when_active(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_active_direct_setup())
        ui.state.ui_mode = "NETWORK"
        ui.state.network_cursor = 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.pop_actions()[0].kind, "disable_direct_ethernet")

    def test_network_press_opens_wifi_network_picker(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "NETWORK"
        ui.state.network_cursor = 5

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "WIFI_NETWORKS")
        self.assertEqual(ui.state.wifi_network_cursor, 1)

    def test_system_menu_includes_update_screen(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = ui.system_menu_items.index("UPDATE") + 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "SOFTWARE_UPDATE")
        self.assertEqual(ui.state.software_update_cursor, ui.software_update_check_cursor)

    def test_hdmi_menu_is_only_available_on_supported_display(self) -> None:
        self.assertNotIn("HDMI", ShadowboxUI().system_menu_items)
        self.assertIn("HDMI", ShadowboxUI(hdmi_mirror_available=True).system_menu_items)

    def test_hdmi_setting_queues_persistent_change_and_marks_reboot_required(self) -> None:
        ui = ShadowboxUI(hdmi_mirror_available=True, hdmi_mirror_enabled=False)
        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = ui.system_menu_items.index("HDMI") + 1
        ui.handle_event(types.SimpleNamespace(kind="short_press"))
        self.assertEqual(ui.state.ui_mode, "SYSTEM_HDMI_MIRROR")

        ui.handle_event(types.SimpleNamespace(kind="short_press"))
        action = next(action for action in ui.pop_actions() if action.kind != "save_state")
        self.assertEqual((action.kind, action.value), ("set_hdmi_mirror", True))

        ui.finish_hdmi_mirror_change(True)
        self.assertTrue(ui.state.hdmi_mirror_enabled)
        self.assertTrue(ui.state.hdmi_mirror_restart_required)
        self.assertTrue(ui.hdmi_mirror_rows[0].toggle)
        self.assertTrue(ui.hdmi_mirror_rows[0].toggle_on)
        self.assertEqual(ui.hdmi_mirror_rows[1].label, "touch feedback")
        self.assertEqual(ui.hdmi_mirror_rows[1].value, "OFF")
        self.assertEqual(ui.hdmi_mirror_rows[2].value, "REBOOT REQUIRED")

    def test_hdmi_touch_feedback_is_optional_immediate_and_defaults_off(self) -> None:
        ui = ShadowboxUI(hdmi_mirror_available=True)
        ui.state.ui_mode = "SYSTEM_HDMI_MIRROR"
        ui.state.hdmi_mirror_cursor = 2

        self.assertFalse(ui.state.touch_feedback_enabled)
        self.assertEqual(ui.hdmi_mirror_rows[1].value, "OFF")
        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertTrue(ui.state.touch_feedback_enabled)
        self.assertEqual(ui.hdmi_mirror_rows[1].value, "ON")
        self.assertTrue(ui.hdmi_mirror_rows[1].toggle_on)
        self.assertIn("save_state", [action.kind for action in ui.pop_actions()])

    def test_hdmi_touch_feedback_setting_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            with mock.patch("shadowbox.ui.STATE_PATH", state_path):
                ui = ShadowboxUI(hdmi_mirror_available=True)
                ui.state.touch_feedback_enabled = True
                ui.save_state()

                restored = ShadowboxUI(hdmi_mirror_available=True)
                restored.restore_from_saved_state()

        self.assertTrue(restored.state.touch_feedback_enabled)

    def test_hdmi_reboot_required_row_opens_safe_confirmation(self) -> None:
        ui = ShadowboxUI(hdmi_mirror_available=True, hdmi_mirror_enabled=False)
        ui.finish_hdmi_mirror_change(True)
        ui.state.ui_mode = "SYSTEM_HDMI_MIRROR"
        ui.state.hdmi_mirror_cursor = 3

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "SYSTEM_REBOOT_CONFIRM")
        self.assertEqual(ui.state.reboot_confirm_cursor, 0)

    def test_reboot_confirmation_defaults_to_cancel(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = ui.system_menu_items.index("REBOOT") + 1
        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "SYSTEM_REBOOT_CONFIRM")
        self.assertEqual(ui.state.reboot_confirm_cursor, 0)

        ui.handle_event(types.SimpleNamespace(kind="short_press"))
        self.assertEqual(ui.state.ui_mode, "SYSTEM_MENU")
        self.assertEqual([action for action in ui.pop_actions() if action.kind != "save_state"], [])

    def test_confirmed_reboot_queues_system_action(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "SYSTEM_REBOOT_CONFIRM"
        ui.state.reboot_confirm_cursor = 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.pop_actions()[0].kind, "reboot_system")
        self.assertTrue(ui.state.busy)

    def test_update_check_action_is_queued(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "SOFTWARE_UPDATE"
        ui.state.software_update_cursor = ui.software_update_check_cursor

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.pop_actions()[0].kind, "check_software_update")

    def test_update_apply_prompts_for_sudo_password_when_available(self) -> None:
        ui = ShadowboxUI()
        ui.set_software_update_status({"available": True, "message": "1 update"})
        ui.state.ui_mode = "SOFTWARE_UPDATE"
        ui.state.software_update_cursor = ui.software_update_check_cursor + 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.software_update_menu_items, ["CHECK", "UPDATE BOX"])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "software_update_password")
        self.assertEqual(ui.name_editor_title, "SUDO PASSWORD")
        self.assertEqual(ui.name_editor_confirm_label, "UPDATE")

    def test_update_password_submit_queues_apply_action(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor(
            context="software_update_password",
            path="",
            initial_draft="c74rnbo",
            return_mode="SOFTWARE_UPDATE",
        )
        ui.state.name_editor_cursor = 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        action = ui.pop_actions()[0]
        self.assertEqual(action.kind, "apply_software_update")
        self.assertEqual(action.value, "c74rnbo")
        self.assertEqual(ui.state.ui_mode, "SOFTWARE_UPDATE")
        self.assertEqual(ui.state.name_editor_draft, "")

    def test_update_screen_includes_shadowscore_install_action_when_missing(self) -> None:
        ui = ShadowboxUI()
        ui.set_software_update_status(
            {
                "targets": {
                    "shadowbox": {"state": "current", "message": "up to date", "available": False},
                    "shadowscore": {"state": "missing", "message": "not installed", "installed": False},
                }
            }
        )

        self.assertIn("INSTALL SCORE", ui.software_update_menu_items)
        self.assertTrue(any(row.label == "score" and row.value == "NOT INSTALLED" for row in ui.software_update_value_rows))

    def test_update_score_prompts_for_sudo_password_with_shadowscore_target(self) -> None:
        ui = ShadowboxUI()
        ui.set_software_update_status(
            {
                "targets": {
                    "shadowbox": {"state": "current", "message": "up to date", "available": False},
                    "shadowscore": {"state": "available", "message": "1 update", "available": True},
                }
            }
        )
        ui.state.ui_mode = "SOFTWARE_UPDATE"
        ui.state.software_update_cursor = len(ui.software_update_rows) - 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))
        ui.pop_actions()
        ui.state.name_editor_draft = "c74rnbo"
        ui.state.name_editor_cursor = 1
        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        action = ui.pop_actions()[0]
        self.assertEqual(action.kind, "apply_software_update")
        self.assertEqual(action.path, "shadowscore")
        self.assertEqual(action.value, "c74rnbo")
        self.assertEqual(ui.state.ui_mode, "SOFTWARE_UPDATE")
        self.assertEqual(ui.state.name_editor_draft, "")

    def test_update_applying_row_queues_cancel_action(self) -> None:
        ui = ShadowboxUI()
        ui.set_software_update_status({"state": "applying", "message": "python deps"})
        ui.state.ui_mode = "SOFTWARE_UPDATE"
        ui.state.software_update_cursor = ui.software_update_check_cursor

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.software_update_menu_items, ["CANCEL UPDATE"])
        self.assertEqual(ui.pop_actions()[0].kind, "cancel_software_update")

    def test_network_touch_wifi_row_opens_wifi_network_picker(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "NETWORK"

        ui.handle_event(types.SimpleNamespace(kind="tap_row", index=5))

        self.assertEqual(ui.state.network_cursor, 5)
        self.assertEqual(ui.state.ui_mode, "WIFI_NETWORKS")
        self.assertEqual(ui.state.wifi_network_cursor, 1)

    def test_wifi_network_picker_rescan_queues_rescan_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "WIFI_NETWORKS"
        ui.state.wifi_network_cursor = len(ui.wifi_network_rows) - 1

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.pop_actions()[0].kind, "rescan_wifi")

    def test_wifi_network_picker_queues_connect_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "WIFI_NETWORKS"
        ui.state.wifi_network_cursor = 2

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        action = ui.pop_actions()[0]
        self.assertEqual(action.kind, "connect_wifi")
        self.assertEqual(action.ssid, "stage-profile")

    def test_wifi_network_picker_opens_password_editor_for_unsaved_secured_network(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "WIFI_NETWORKS"
        ui.state.wifi_network_cursor = 3

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "wifi_password")
        self.assertEqual(ui.state.pending_wifi_ssid, "guest")
        self.assertEqual(ui.name_editor_title, "WIFI PASSWORD")
        self.assertEqual(ui.name_editor_confirm_label, "CONNECT")

    def test_wifi_password_submit_queues_new_network_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui._begin_wifi_password_editor("guest")
        ui.state.name_editor_draft = "secretpass"

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        action = ui.pop_actions()[0]
        self.assertEqual(action.kind, "connect_wifi_new")
        self.assertEqual(action.ssid, "guest")
        self.assertEqual(action.value, "secretpass")
        self.assertEqual(ui.state.ui_mode, "WIFI_NETWORKS")
        self.assertEqual(ui.state.name_editor_draft, "")

    def test_failed_saved_wifi_can_reopen_password_editor_by_connection_id(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())

        retry_started = ui.begin_wifi_password_retry("stage-profile")

        self.assertTrue(retry_started)
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "wifi_password")
        self.assertEqual(ui.state.pending_wifi_ssid, "stage")
        self.assertEqual(ui.state.name_editor_draft, "")

    def test_wifi_network_picker_queues_open_network_without_password(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "WIFI_NETWORKS"
        ui.state.wifi_network_cursor = 4

        ui.handle_event(types.SimpleNamespace(kind="short_press"))

        action = ui.pop_actions()[0]
        self.assertEqual(action.kind, "connect_wifi_new")
        self.assertEqual(action.ssid, "open")
        self.assertEqual(action.value, "")

    def test_wifi_network_rows_mark_current_ssid(self) -> None:
        ui = ShadowboxUI()
        snapshot = self._snapshot_with_direct_network()
        snapshot.system["network"]["wifi_connected"] = True
        snapshot.system["network"]["wifi_ssid"] = "stage"
        snapshot.system["network"]["wifi_ipv4"] = "10.0.0.44"
        ui.apply_runner_snapshot(snapshot)

        rows = ui.wifi_network_rows

        self.assertEqual([row.label for row in rows], ["..", "studio", "stage", "guest", "open", "RESCAN"])
        self.assertFalse(rows[1].current)
        self.assertTrue(rows[2].current)
        self.assertTrue(rows[-1].action)

    def test_renderer_draw_network_uses_network_value_rows_on_oled(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_direct_network())
        ui.state.ui_mode = "NETWORK"
        ui.state.network_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_header, "NETWORK")
        self.assertEqual(
            renderer.last_selectable_value_rows[:3],
            [
                ("setup", "ENABLE", False),
                ("state", "OFF", False),
                ("wired", "LINK", True),
            ],
        )

    def test_renderer_draw_wifi_network_picker_marks_current(self) -> None:
        ui = ShadowboxUI()
        snapshot = self._snapshot_with_direct_network()
        snapshot.system["network"]["wifi_ssid"] = "studio"
        ui.apply_runner_snapshot(snapshot)
        ui.state.ui_mode = "WIFI_NETWORKS"
        ui.state.wifi_network_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_header, "WIFI NETWORKS")
        self.assertEqual(renderer.last_items, ["..", "studio", "stage", "guest", "open", "RESCAN"])
        self.assertEqual(renderer.last_current_indices, {1})
        self.assertEqual(renderer.last_action_indices, {5})

    def test_instance_list_shows_add_and_remove_actions_without_patchers_or_instances(self) -> None:
        ui = self._apply_empty_snapshot()
        ui.state.ui_mode = "INSTANCE_LIST"

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "ADD INSTANCE", "REMOVE INSTANCE"])
        self.assertEqual(renderer.last_selected_idx, 1)

    def test_instance_list_marks_active_instance_current(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {"id": "1", "label": "Synth A", "params": [], "presets": [], "routing": {"audio": {"inputs": [], "outputs": []}, "midi": {"inputs": [], "outputs": []}}},
                    {"id": "2", "label": "Synth B", "params": [], "presets": [], "routing": {"audio": {"inputs": [], "outputs": []}, "midi": {"inputs": [], "outputs": []}}},
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "2"
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instance_cursor = 2

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_current_indices, {2})

    def test_empty_pickers_show_placeholder_rows(self) -> None:
        ui = self._apply_empty_snapshot()
        renderer = _CaptureRenderer()

        ui.state.ui_mode = "PATCHER_PICKER"
        ui.state.patcher_cursor = 0
        renderer.draw(ui)
        self.assertEqual(renderer.last_items, ["..", "no patchers"])
        self.assertEqual(renderer.last_selected_idx, 0)

        ui.state.ui_mode = "REMOVE_INSTANCE_PICKER"
        ui.state.remove_instance_picker_cursor = 0
        renderer.draw(ui)
        self.assertEqual(renderer.last_items, ["..", "no instances"])
        self.assertEqual(renderer.last_selected_idx, 0)

    def test_used_routing_targets_excludes_selected_port_connections(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {
                        "id": "1",
                        "label": "Synth A",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "In 1",
                                        "path": "/inst/1/in1",
                                        "targets": ["system:capture_1", "system:capture_2"],
                                        "connections": ["system:capture_1"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    },
                    {
                        "id": "2",
                        "label": "Synth B",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "In 1",
                                        "path": "/inst/2/in1",
                                        "targets": ["system:capture_1", "system:capture_2"],
                                        "connections": ["system:capture_2"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    },
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        self.assertEqual(ui.current_routing_targets, ["system:capture_1"])
        self.assertEqual(ui.used_routing_targets, {"system:capture_2"})

    def test_routing_assignment_list_shows_current_assignments_and_actions(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {
                        "id": "1",
                        "label": "Synth A",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "In 1",
                                        "path": "/inst/1/in1",
                                        "targets": ["system:capture_1", "system:capture_2"],
                                        "connections": ["system:capture_1"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    },
                    {
                        "id": "2",
                        "label": "Synth B",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "In 1",
                                        "path": "/inst/2/in1",
                                        "targets": ["system:capture_1", "system:capture_2"],
                                        "connections": ["system:capture_2"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    },
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "ROUTING_TARGETS"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1
        ui.state.routing_target_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "system:capture_1", "ADD", "REMOVE"])
        self.assertEqual(renderer.last_current_indices, {1})
        self.assertEqual(renderer.last_action_indices, {2, 3})

    def test_routing_add_picker_excludes_targets_already_assigned_to_instance(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {
                        "id": "1",
                        "label": "Synth A",
                        "routing": {
                            "midi": {
                                "inputs": [
                                    {
                                        "name": "Midi In 1",
                                        "path": "/inst/1/midi/in1",
                                        "targets": ["system:midi_a", "system:midi_b", "system:midi_c"],
                                        "connections": ["system:midi_a"],
                                    },
                                    {
                                        "name": "Midi In 2",
                                        "path": "/inst/1/midi/in2",
                                        "targets": ["system:midi_a", "system:midi_b", "system:midi_c"],
                                        "connections": ["system:midi_b"],
                                    },
                                ],
                                "outputs": [],
                            }
                        },
                    }
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "midi"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1
        ui.state.ui_mode = "ROUTING_ADD_PICKER"

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(ui.available_routing_add_targets, ["system:midi_c"])
        self.assertEqual(renderer.last_items, ["..", "system:midi_c"])
        self.assertEqual(renderer.last_action_indices, {1})

    def test_routing_add_picker_appends_selected_assignment(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {
                        "id": "1",
                        "label": "Synth A",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "In 1",
                                        "path": "/inst/1/in1",
                                        "targets": ["system:capture_1", "system:capture_2"],
                                        "connections": ["system:capture_1"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    }
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1
        ui.state.ui_mode = "ROUTING_ADD_PICKER"
        ui.state.routing_add_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind == "set_routing"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].path, "/inst/1/in1")
        self.assertEqual(actions[0].value, ["system:capture_1", "system:capture_2"])
        self.assertEqual(ui.state.ui_mode, "ROUTING_TARGETS")

    def test_routing_views_prefer_port_display_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[
                    {
                        "id": "1",
                        "label": "Synth A",
                        "routing": {
                            "audio": {
                                "inputs": [
                                    {
                                        "name": "in1",
                                        "display_name": "Main Input",
                                        "path": "/inst/1/in1",
                                        "targets": ["system:capture_1"],
                                        "connections": ["system:capture_1"],
                                    }
                                ],
                                "outputs": [],
                            }
                        },
                    }
                ],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "ROUTING_PORTS"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)
        self.assertIn(("Main Input", ["system:capture_1"]), renderer.last_value_rows or [])
        self.assertEqual(renderer.last_current_indices, {1})

        ui.state.ui_mode = "ROUTING_TARGETS"
        renderer.draw(ui)
        self.assertEqual(renderer.last_header, "Main Input")

    def test_instance_menu_does_not_show_graph_level_overview_entries(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "PARAMETERS", "PRESETS", "AUDIO", "MIDI"],
        )

    def test_audio_overview_rows_summarize_instance_routing(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"

        self.assertEqual(
            [(row.label, row.value, row.current) for row in ui.routing_overview_rows],
            [
                ("Synth A", "I:C1-2 O:P1-2", True),
                ("Looper", "I:C3 O:-", False),
            ],
        )

    def test_midi_overview_rows_summarize_instance_routing(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "midi"

        self.assertEqual(
            [(row.label, row.value, row.current) for row in ui.routing_overview_rows],
            [
                ("Synth A", "I:midi_from_keys O:midi_to_synth", True),
                ("Looper", "I:- O:-", False),
            ],
        )

    def test_audio_overview_renders_as_selectable_value_rows(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_transport = "audio"
        ui.state.ui_mode = "AUDIO_ROUTING_OVERVIEW"
        ui.state.routing_overview_cursor = 2

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_header, "AUDIO I/O")
        self.assertEqual(
            renderer.last_selectable_value_rows,
            [
                ("Synth A", "I:C1-2 O:P1-2", True),
                ("Looper", "I:C3 O:-", False),
            ],
        )
        self.assertEqual(renderer.last_selected_idx, 2)

    def test_system_menu_keeps_startup_but_not_graph_detail_entries(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertIn("STARTUP", renderer.last_items or [])
        self.assertNotIn("AUDIO OVERVIEW", renderer.last_items or [])
        self.assertNotIn("MIDI OVERVIEW", renderer.last_items or [])
        self.assertNotIn("SET PRESETS", renderer.last_items or [])

    def test_graph_menu_audio_overview_selects_active_instance_row(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_instance_id = "2"
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = ui.graph_menu_items.index("AUDIO OVERVIEW") + 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "AUDIO_ROUTING_OVERVIEW")
        self.assertEqual(ui.state.active_transport, "audio")
        self.assertEqual(ui.state.routing_overview_cursor, 2)

    def test_overview_rotation_reaches_eighth_item_without_wrapping(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_many_routing_instances(8))
        ui.state.active_transport = "audio"
        ui.state.ui_mode = "AUDIO_ROUTING_OVERVIEW"
        ui.state.routing_overview_cursor = 7
        ui.state.active_instance_id = "7"

        ui.handle_event(type("Evt", (), {"kind": "step", "delta": 1})())

        self.assertEqual(ui.state.routing_overview_cursor, 8)
        self.assertEqual(ui.state.active_instance_id, "8")

    def test_overview_press_opens_selected_instance_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.active_transport = "audio"
        ui.state.ui_mode = "AUDIO_ROUTING_OVERVIEW"
        ui.state.routing_overview_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.active_instance_id, "2")
        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")
        self.assertEqual(ui.state.instance_menu_cursor, 1)

    def test_overview_long_press_returns_to_graph_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.ui_mode = "MIDI_ROUTING_OVERVIEW"

        ui.handle_event(type("Evt", (), {"kind": "long_press"})())

        self.assertEqual(ui.state.ui_mode, "GRAPH_MENU")

    def test_top_level_graphs_enters_graph_list(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.top_index = 0

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "GRAPH_SET_LIST")
        self.assertEqual(ui.state.graph_set_cursor, ui.graph_set_initial_cursor())

    def test_graph_menu_renders_expected_items(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "AUDIO OVERVIEW", "MIDI OVERVIEW"],
        )
        self.assertEqual(renderer.last_selected_idx, 1)

    def test_instance_inventory_refreshes_while_action_flows_remain_protected(self) -> None:
        ui = ShadowboxUI()

        ui.state.ui_mode = "INSTANCE_LIST"
        self.assertFalse(ui.should_pause_refresh())

        for mode in ("INSTANCE_MENU", "PATCHER_PICKER", "REMOVE_INSTANCE_CONFIRM", "GRAPH_MENU", "EDIT"):
            ui.state.ui_mode = mode
            self.assertTrue(ui.should_pause_refresh(), mode)

    def test_identical_runner_snapshot_does_not_request_another_render(self) -> None:
        ui = ShadowboxUI()
        snapshot = self._snapshot_with_sets()
        self.assertTrue(ui.apply_runner_snapshot(snapshot))
        ui.render_revision = 0

        self.assertFalse(ui.apply_runner_snapshot(self._snapshot_with_sets()))

        self.assertEqual(ui.render_revision, 0)

    def test_changed_runner_snapshot_still_requests_a_render(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.render_revision = 0
        changed = self._snapshot_with_sets()
        changed.system["sets"]["dirty"] = False

        self.assertTrue(ui.apply_runner_snapshot(changed))

        self.assertEqual(ui.render_revision, 1)
        self.assertEqual(ui.last_render_reason, "runner_snapshot")

    def test_live_state_churn_updates_cache_without_redrawing_instance_inventory(self) -> None:
        ui = ShadowboxUI()
        snapshot = self._snapshot_with_preset_capabilities()
        snapshot.instances[0]["state"] = [
            {"name": "note", "path": "/rnbo/inst/1/messages/out/note", "value": [60.0], "metadata": {}}
        ]
        ui.apply_runner_snapshot(snapshot)
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.render_revision = 0
        changed = self._snapshot_with_preset_capabilities()
        changed.instances[0]["state"] = [
            {"name": "note", "path": "/rnbo/inst/1/messages/out/note", "value": [64.0], "metadata": {}}
        ]

        self.assertFalse(ui.apply_runner_snapshot(changed))

        self.assertEqual(ui.state.instances[0]["state"][0]["value"], [64.0])
        self.assertEqual(ui.render_revision, 0)

    def test_instance_inventory_change_still_redraws_instance_list(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.render_revision = 0
        changed = self._snapshot_with_preset_capabilities()
        changed.instances[0]["label"] = "Renamed instance"

        self.assertTrue(ui.apply_runner_snapshot(changed))

        self.assertEqual(ui.render_revision, 1)

    def test_graph_menu_shows_new_graph_when_published_as_loadable_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_new_graph_set())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "AUDIO OVERVIEW", "MIDI OVERVIEW"],
        )

    def test_network_properties_use_snapshot_network_info_and_rnbo_port(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[],
                patchers=[],
                add_instance_path="",
                remove_instance_path="",
                system={
                    "network": {
                        "primary_ipv4": "10.0.0.24",
                        "hostname": "shadowbox",
                        "hostname_local": "shadowbox.local",
                    }
                },
            )
        )

        self.assertEqual(ui.network_ip_address, "10.0.0.24")
        self.assertEqual(ui.network_host_display, "shadowbox.local")
        self.assertEqual(ui.network_osc_port, RNBO_PORT)

    def test_network_ip_address_falls_back_when_probe_fails(self) -> None:
        ui = ShadowboxUI()
        self.assertEqual(ui.network_ip_address, "?")

    def test_graph_set_list_renders_current_and_load_entries(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "CURRENT SET", "LOAD SET"])
        self.assertEqual(renderer.last_selected_idx, 1)
        self.assertEqual(renderer.last_current_indices, {1})

    def test_graph_menu_shows_current_set_actions_without_rename(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "AUDIO OVERVIEW", "MIDI OVERVIEW"],
        )

    def test_sets_menu_shows_current_set_and_load_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = ui.graph_set_initial_cursor()

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "CURRENT SET", "LOAD SET"],
        )
        self.assertEqual(renderer.last_current_indices, {1})

    def test_graph_status_marks_current_set_and_dirty_state_in_value_rows(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STATUS"

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_value_rows, [("set", "StudioA"), ("dirty", "YES"), ("sets", 2)])
        self.assertEqual(renderer.last_current_indices, {1, 2})
        self.assertEqual(renderer.last_value_weights, ["italic", None, None])

    def test_graph_status_shows_loaded_graph_preset_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        self.assertEqual(
            [(row.label, row.value, row.current) for row in ui.graph_status_value_rows],
            [("set", "StudioA", True), ("dirty", "YES", True), ("sets", 2, False), ("preset", "linke synce", True)],
        )

    def test_sets_menu_current_set_opens_current_set_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "GRAPH_MENU")
        self.assertEqual(ui.state.graph_menu_cursor, 1)

    def test_sets_menu_load_set_opens_graph_preset_list(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "GRAPH_LOAD_SET_LIST")
        self.assertEqual(ui.state.graph_load_set_cursor, ui.graph_load_set_initial_cursor())

    def test_load_set_list_selection_queues_load_set_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_LOAD_SET_LIST"
        ui.state.graph_load_set_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "load_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/load")
        self.assertEqual(actions[0].value, "StudioB")

    def test_current_set_menu_shows_set_presets_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "SET PRESETS", "AUDIO OVERVIEW", "MIDI OVERVIEW"],
        )

    def test_current_set_menu_set_presets_opens_graph_preset_list(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = ui.graph_menu_items.index("SET PRESETS") + 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "GRAPH_PRESET_LIST")
        self.assertEqual(ui.state.graph_preset_cursor, ui.graph_preset_initial_cursor())

    def test_graph_save_as_set_opens_name_editor_with_generated_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = ui.graph_menu_items.index("SAVE AS...") + 1

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260401-120000"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_set")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/control/sets/save")
        self.assertEqual(ui.state.name_editor_draft, "studioa-20260401-120000")
        self.assertEqual(ui.state.name_editor_return_mode, "GRAPH_MENU")
        self.assertEqual(ui.state.name_editor_cursor, 1)

    def test_graph_save_action_overwrites_current_graph(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = ui.graph_menu_items.index("SAVE") + 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/save")
        self.assertEqual(actions[0].value, "StudioA")

    def test_current_set_menu_hides_save_for_untitled_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.system["set_name"] = ""
        ui.state.system["sets"]["current_name"] = ""

        self.assertEqual(ui.graph_menu_items, ["SAVE AS...", "AUDIO OVERVIEW", "MIDI OVERVIEW"])

    def test_graph_preset_list_shows_actions_and_current_selection(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "REMOVE", "Unipolar Positive", "linke synce"],
        )
        self.assertEqual(renderer.last_current_indices, {5})
        self.assertEqual(renderer.last_selected_idx, 4)

    def test_graph_preset_selection_queues_load_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 4

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "load_graph_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/presets/load")
        self.assertEqual(actions[0].value, "Unipolar Positive")

    def test_save_graph_preset_action_overwrites_current_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_graph_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/presets/save")
        self.assertEqual(actions[0].value, "linke synce")

    def test_save_as_graph_preset_action_opens_name_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 2

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260404-111500"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_graph_preset")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/control/sets/presets/save")
        self.assertEqual(ui.state.name_editor_draft, "linke-synce-20260404-111")

    def test_remove_graph_preset_action_opens_picker_and_queues_selected_delete(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 3

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        self.assertEqual(ui.state.ui_mode, "GRAPH_PRESET_REMOVE_PICKER")
        ui.state.graph_preset_remove_cursor = 2
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "delete_graph_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/presets/destroy")
        self.assertEqual(actions[0].value, "linke synce")

    def test_name_editor_generate_name_replaces_draft(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")
        ui.state.name_editor_cursor = 2

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260402-101500"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.name_editor_draft, "studioa-20260402-101500")

    def test_name_editor_add_date_appends_date_token(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")
        ui.state.name_editor_cursor = 3

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260403"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.name_editor_draft, "custom-name-20260403")

    def test_name_editor_clear_name_removes_entire_draft(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")
        ui.state.name_editor_cursor = 5

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.name_editor_draft, "")

    def test_name_editor_empty_submit_shows_error(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_ERROR")
        self.assertEqual(ui.state.name_error_message, "ENTER NAME")

    def test_name_error_edit_name_button_returns_to_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_MENU")
        ui.state.ui_mode = "NAME_ERROR"

        ui.handle_event(type("Evt", (), {"kind": "tap_button", "button_id": "edit_name"})())

        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")

    def test_name_editor_save_queues_save_set_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/save")
        self.assertEqual(actions[0].value, "custom-name")

    def test_name_editor_duplicate_save_shows_overwrite_confirm(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "StudioB", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_OVERWRITE_CONFIRM")
        self.assertEqual(ui.state.name_editor_draft, "StudioB")

    def test_name_overwrite_cancel_button_returns_to_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "StudioB", "GRAPH_MENU")
        ui.state.ui_mode = "NAME_OVERWRITE_CONFIRM"

        ui.handle_event(type("Evt", (), {"kind": "tap_button", "button_id": "cancel"})())

        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")

    def test_name_overwrite_confirm_queues_save_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "StudioB", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        ui.pop_actions()

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_set")
        self.assertEqual(actions[0].value, "StudioB")

    def test_remove_instance_confirm_remove_button_queues_remove_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[{"id": "1", "label": "Synth A", "params": [], "presets": [], "routing": {"audio": {"inputs": [], "outputs": []}, "midi": {"inputs": [], "outputs": []}}}],
                patchers=[],
                add_instance_path="",
                remove_instance_path="/rnbo/inst/control/unload",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "REMOVE_INSTANCE_CONFIRM"
        ui.state.pending_remove_instance_id = "1"
        ui.state.remove_instance_origin = "instance_menu"

        ui.handle_event(type("Evt", (), {"kind": "tap_button", "button_id": "remove"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "remove_instance")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/unload")
        self.assertEqual(actions[0].value, 1)
        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")
        self.assertEqual(ui.state.pending_remove_instance_id, "")

    def test_remove_instance_confirm_cancel_button_returns_to_parent(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(
            RNBOSnapshot(
                instances=[{"id": "1", "label": "Synth A", "params": [], "presets": [], "routing": {"audio": {"inputs": [], "outputs": []}, "midi": {"inputs": [], "outputs": []}}}],
                patchers=[],
                add_instance_path="",
                remove_instance_path="/rnbo/inst/control/unload",
                system={},
            )
        )
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "REMOVE_INSTANCE_CONFIRM"
        ui.state.pending_remove_instance_id = "1"
        ui.state.remove_instance_origin = "instance_list"

        ui.handle_event(type("Evt", (), {"kind": "tap_button", "button_id": "cancel"})())

        self.assertEqual(ui.state.ui_mode, "REMOVE_INSTANCE_PICKER")
        self.assertEqual(ui.state.pending_remove_instance_id, "")

    def test_name_editor_long_press_cancels_to_graph_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")

        ui.handle_event(type("Evt", (), {"kind": "long_press"})())

        self.assertEqual(ui.state.ui_mode, "GRAPH_MENU")

    def test_name_editor_renderer_shows_draft_and_actions(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "custom-name", "GRAPH_MENU")

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_header, "SAVE SET")
        self.assertEqual(
            renderer.last_items,
            [
                "NAME: custom-name",
                "SAVE",
                "GENERATE NAME",
                "ADD DATE",
                "EDIT NAME",
                "CLEAR NAME",
                "DELETE CHAR",
                "CANCEL",
            ],
        )
        self.assertEqual(renderer.last_selected_idx, 1)

    def test_inline_name_editor_updates_character_and_returns_to_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "Ab", "GRAPH_MENU")
        ui.state.name_editor_cursor = 4

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        self.assertEqual(ui.state.ui_mode, "NAME_INLINE_EDITOR")
        self.assertTrue(ui.state.name_inline_edit_mode)

        ui.handle_event(type("Evt", (), {"kind": "step", "delta": 1})())
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertFalse(ui.state.name_inline_edit_mode)
        self.assertNotEqual(ui.state.name_editor_draft, "Ab")

        ui.handle_event(type("Evt", (), {"kind": "long_press"})())
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")

    def test_inline_name_editor_tft_shows_mode_tabs_and_character_strip(self) -> None:
        display = _FakeDisplay()
        display.width = 160
        display.height = 80
        renderer = ShadowboxRenderer(display)
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "Ab", "GRAPH_MENU")
        ui.state.name_editor_cursor = 4
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        ui.state.name_inline_preview_index = ui.inline_name_option_count - 1

        renderer.draw(ui)

        rendered_text = [call[0] for call in display.calls]
        rendered_scales = [call[3] for call in display.calls]

        self.assertIn("[EDIT]", rendered_text)
        self.assertTrue(any("|" in text and "[DE" in text for text in rendered_text))
        self.assertTrue(any(scale >= 2 for scale in rendered_scales))

    def test_inline_name_editor_delete_slot_removes_character(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "Ab", "GRAPH_MENU")
        ui.state.name_editor_cursor = 4
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        ui.state.name_inline_preview_index = ui.inline_name_option_count - 1
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.name_editor_draft, "A")
        self.assertEqual(ui.state.name_inline_cursor, 1)
        self.assertFalse(ui.state.name_inline_edit_mode)

    def test_sets_menu_load_set_opens_load_set_list_from_legacy_position(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = ui.graph_set_menu_items.index("LOAD SET")

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "GRAPH_LOAD_SET_LIST")
        self.assertEqual(ui.state.graph_load_set_cursor, ui.graph_load_set_initial_cursor())

    def test_name_editor_rename_label_and_action_for_rename_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui._begin_rename_name_editor("rename_set", "/rnbo/inst/control/sets/rename", "StudioA", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1
        ui.state.name_editor_draft = "StudioC"

        renderer = _CaptureRenderer()
        renderer.draw(ui)
        self.assertEqual(renderer.last_header, "RENAME SET")
        self.assertEqual(renderer.last_items[1], "RENAME")

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "rename_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/rename")
        self.assertEqual(actions[0].value, "StudioC")

    def test_rename_set_duplicate_name_shows_error(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui._begin_rename_name_editor("rename_set", "/rnbo/inst/control/sets/rename", "StudioA", "GRAPH_MENU")
        ui.state.name_editor_draft = "StudioB"
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_ERROR")
        self.assertEqual(ui.state.name_error_message, "NAME EXISTS")

    def test_preset_list_shows_save_and_rename_actions_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = ui.preset_initial_cursor()

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE", "SAVE AS...", "REMOVE", "Init", "Bass"],
        )
        self.assertEqual(renderer.last_current_indices, {5})
        self.assertEqual(renderer.last_selected_idx, 4)

    def test_save_preset_action_overwrites_current_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/1/presets/save")
        self.assertEqual(actions[0].value, "Bass")

    def test_save_as_preset_action_opens_name_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 2

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260404-111500"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_preset")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/1/presets/save")
        self.assertEqual(ui.state.name_editor_draft, "bass-20260404-111500")

    def test_remove_preset_action_opens_picker_and_queues_selected_delete(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 3

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        self.assertEqual(ui.state.ui_mode, "PRESET_REMOVE_PICKER")
        ui.state.preset_remove_cursor = 2
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "delete_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/1/presets/destroy")
        self.assertEqual(actions[0].value, "Bass")

    def test_duplicate_preset_save_shows_overwrite_confirm(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui._begin_name_editor("save_preset", "/rnbo/inst/1/presets/save", "Bass", "PRESET_LIST")
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_OVERWRITE_CONFIRM")

    def test_duplicate_preset_rename_shows_error(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui._begin_rename_name_editor("rename_preset", "/rnbo/inst/1/presets/rename", "Bass", "PRESET_LIST")
        ui.state.name_editor_draft = "Init"
        ui.state.name_editor_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_ERROR")
        self.assertEqual(ui.state.name_error_message, "NAME EXISTS")

    def test_graph_startup_menu_renders_expected_items(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STARTUP"
        ui.state.graph_startup_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "RESTORE LAST", "LOAD NAMED SET", "OFF"])
        self.assertEqual(renderer.last_current_indices, {1})

    def test_graph_startup_value_rows_mark_current_startup_state(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())

        renderer = _CaptureRenderer()
        renderer.draw_graph_startup(ui)

        self.assertEqual(renderer.last_value_rows, [("startup", "LAST"), ("auto", "on"), ("initial", "-")])
        self.assertEqual(renderer.last_current_indices, {1, 2})

    def test_graph_startup_restore_last_queues_updates(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STARTUP"
        ui.state.graph_startup_cursor = 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "set_graph_startup")
        self.assertEqual(
            actions[0].value,
            [
                ("/rnbo/inst/config/auto_start_last", True),
                ("/rnbo/inst/control/sets/initial", ""),
            ],
        )

    def test_graph_startup_named_set_queues_updates(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STARTUP_SET_LIST"
        ui.state.graph_startup_set_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "set_graph_startup")
        self.assertEqual(
            actions[0].value,
            [
                ("/rnbo/inst/config/auto_start_last", False),
                ("/rnbo/inst/control/sets/initial", "StudioB"),
            ],
        )

    def test_graph_startup_off_queues_updates(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STARTUP"
        ui.state.graph_startup_cursor = 3

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "set_graph_startup")
        self.assertEqual(
            actions[0].value,
            [
                ("/rnbo/inst/config/auto_start_last", False),
                ("/rnbo/inst/control/sets/initial", ""),
            ],
        )

    def test_system_transpose_menu_opens_local_control_screen(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = ui.system_menu_items.index("TRANSPOSE") + 1

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPOSE")
        self.assertEqual(ui.state.transpose_cursor, 2)
        self.assertEqual(ui.transpose_rows[0].value, "UNCONFIGURED")

    def test_system_transport_controls_global_runner_state_and_tempo(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 90.0,
            }
        }
        self.assertIn("TRANSPORT", ui.system_menu_items)

        ui.state.ui_mode = "SYSTEM_MENU"
        ui.state.system_cursor = ui.system_menu_items.index("TRANSPORT") + 1
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT")
        self.assertEqual([(row.label, row.value) for row in ui.transport_rows], [("state", "STOPPED · LOCAL"), ("tempo", "90.0 BPM")])

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        actions = [action for action in ui.pop_actions() if action.kind == "set_transport"]
        self.assertEqual([(action.path, action.value) for action in actions], [("/rnbo/jack/transport/rolling", True)])
        self.assertEqual(ui.transport_rows[0].value, "RUNNING · LOCAL")

        ui.state.transport_cursor = 2
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT_TEMPO_EDIT")
        ui.handle_event(type("Evt", (), {"kind": "step", "delta": 1})())
        actions = [action for action in ui.pop_actions() if action.kind == "set_transport"]
        self.assertEqual([(action.path, action.value) for action in actions], [("/rnbo/jack/transport/bpm", 91.0)])

        ui.handle_event(type("Evt", (), {"kind": "long_press"})())
        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT")

    def test_list_sequencer_set_defaults_to_local_transport_when_server_is_connected(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [{"id": "14", "name": "ListSequencer", "params": []}]
        ui.state.system = {
            "set_name": "Local Lists",
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 100.0,
            },
        }
        ui.apply_shadowscore_transport_snapshot({
            "revision": 1,
            "is_playing": False,
            "tempo": 90.0,
            "active_section": "F",
            "sync": {"state": "unavailable"},
        })

        self.assertEqual(ui.transport_authority, "local")
        self.assertEqual(ui.home_transport_tempo_label, "100 BPM · LOCAL")
        ui.state.ui_mode = "SYSTEM_TRANSPORT"
        ui.handle_event(UIEvent(kind="tap_button", button_id="transport_play_stop"))

        actions = ui.pop_actions()
        self.assertEqual(
            [(action.kind, action.path, action.value) for action in actions],
            [("set_transport", "/rnbo/jack/transport/rolling", True)],
        )

    def test_live_remote_shadowscore_cohort_keeps_score_authority_without_local_client(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [{"id": "14", "name": "ListSequencer", "params": []}]
        ui.state.system = {
            "set_name": "Ensemble",
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 100.0,
            },
        }
        ui.apply_shadowscore_transport_snapshot({
            "revision": 1,
            "is_playing": False,
            "tempo": 90.0,
            "sync": {"online_players": 3, "fresh_players": 3},
        })

        self.assertEqual(ui.transport_authority, "shadowscore")
        self.assertEqual(ui.transport_authority_label, "SHADOWSCORE")

    def test_transport_authority_choice_persists_per_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            with mock.patch("shadowbox.ui.STATE_PATH", state_path):
                ui = ShadowboxUI()
                ui.state.transport_authority_by_set = {"Local Lists": "local", "Ensemble": "shadowscore"}
                ui.save_state()

                restored = ShadowboxUI()
                restored.restore_from_saved_state()

        self.assertEqual(
            restored.state.transport_authority_by_set,
            {"Local Lists": "local", "Ensemble": "shadowscore"},
        )

    def test_server_transport_is_acknowledged_and_exposes_arrangement_actions(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 90.0,
            }
        }
        snapshot = {
            "revision": 4,
            "is_playing": False,
            "tempo": 108.0,
            "active_section": "B",
            "position_bbt": "3.1.000",
            "sync": {"state": "slipped", "re_sync_recommended": True},
            "capabilities": {"can_re_sync": True},
        }
        self.assertTrue(ui.apply_shadowscore_transport_snapshot(snapshot, base_url="http://wren:8790"))
        self.assertEqual(ui.top_level_items[-1], "PLAY")
        self.assertEqual(ui.home_transport_tempo_label, "108 BPM · B · SLIPPED")
        self.assertEqual(
            [(row.label, row.value) for row in ui.transport_rows],
            [
                ("authority", "SHADOWSCORE"),
                ("state", "STOPPED · SHADOWSCORE"),
                ("tempo", "108.0 BPM"),
                ("section", "B"),
                ("position", "3.1.000"),
                ("sync", "SLIPPED"),
                ("previous", "SECTION"),
                ("next", "SECTION"),
                ("return", "TO START"),
                ("re-sync", "RECOMMENDED"),
            ],
        )

        ui.state.ui_mode = "TOP"
        ui.state.top_index = 3
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        actions = [action for action in ui.pop_actions() if action.kind == "transport_command"]
        self.assertEqual(actions[0].value, {"operation": "play", "args": {}})
        self.assertEqual(ui.home_transport_label, "STARTING")
        self.assertFalse(ui.state.system["transport"]["rolling"])

        acknowledged = dict(snapshot, revision=5, is_playing=True)
        ui.apply_shadowscore_transport_snapshot(acknowledged, operation="play")
        self.assertEqual(ui.home_transport_label, "STOP")
        self.assertEqual(ui.state.shadowscore_transport_pending, "")

    def test_server_transport_rejects_older_snapshots_and_reports_command_errors(self) -> None:
        ui = ShadowboxUI()
        self.assertTrue(ui.apply_shadowscore_transport_snapshot({"revision": 8, "is_playing": False, "tempo": 120}))
        self.assertFalse(ui.apply_shadowscore_transport_snapshot({"revision": 7, "is_playing": True, "tempo": 90}))
        self.assertFalse(ui.transport_rolling)
        ui._queue_transport_command("play")
        ui.apply_shadowscore_transport_command_error("play", "timed out; verifying state")
        self.assertEqual(ui.state.shadowscore_transport_pending, "")
        self.assertEqual(ui.state.shadowscore_transport_error, "timed out; verifying state")

    def test_encoder_transport_blocks_view_preserves_block_ids_and_launch_state(self) -> None:
        ui = ShadowboxUI()
        ui.apply_shadowscore_transport_snapshot({
            "revision": 1,
            "is_playing": True,
            "tempo": 120,
            "active_section": "VerseA",
            "arrangement": {"requested_mode": "hold", "running": False},
            "block_launcher": {
                "active_block_id": "VerseA",
                "requested_block_id": "ChorusB",
                "request_state": "armed",
                "blocks": [
                    {"id": "VerseA", "launchable": True, "occurrence_indices": [0]},
                    {"id": "ChorusB", "launchable": True, "occurrence_indices": [1]},
                ],
            },
            "capabilities": {"can_launch_meso_blocks": True},
        })
        ui.state.ui_mode = "SYSTEM_TRANSPORT"
        self.assertEqual(ui.state.transport_view, "blocks")

        self.assertEqual(
            [(row.label, row.value) for row in ui.transport_rows[-2:]],
            [("block:VerseA", "ACTIVE"), ("block:ChorusB", "ARMED")],
        )
        ui.state.transport_cursor = next(index for index, row in enumerate(ui.transport_rows, start=1) if row.label == "block:ChorusB")
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        commands = [action for action in ui.pop_actions() if action.kind == "transport_command"]
        self.assertEqual(commands[0].value, {"operation": "launch_meso_block", "args": {"block_id": "ChorusB", "macro_index": 1}})

    def test_touch_transport_locate_previews_until_release_and_waits_for_ack(self) -> None:
        ui = ShadowboxUI(touch_locate_available=True)
        snapshot = {
            "revision": 10,
            "is_playing": False,
            "tempo": 120,
            "position_fraction": 0.25,
            "position_bbt": "3.1.000",
            "duration_beats": 32,
            "time_signature_numerator": 4,
            "active_section": "B",
            "arrangement": {
                "sections": [
                    {"id": "A", "start_beat": 0, "end_beat": 8},
                    {"id": "B", "start_beat": 8, "end_beat": 16},
                    {"id": "C", "start_beat": 16, "end_beat": 24},
                    {"id": "D", "start_beat": 24, "end_beat": 32},
                ]
            },
            "sync": {"state": "aligned"},
            "capabilities": {"can_locate": True},
        }
        ui.apply_shadowscore_transport_snapshot(snapshot)
        ui.state.ui_mode = "SYSTEM_TRANSPORT"
        ui.state.transport_cursor = next(
            index for index, row in enumerate(ui.transport_rows, start=1) if row.label == "position"
        )

        ui.handle_event(UIEvent(kind="short_press"))
        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT_LOCATE")
        self.assertEqual(ui.transport_locate_fraction, 0.25)

        ui.handle_event(UIEvent(kind="set_transport_position", value=0.625, pressed=True))
        self.assertEqual(ui.transport_locate_position_label, "6.1.000")
        self.assertEqual(ui.transport_locate_section_label, "C")
        self.assertEqual([a for a in ui.pop_actions() if a.kind == "transport_command"], [])

        ui.handle_event(UIEvent(kind="set_transport_position", value=0.625, pressed=False))
        actions = [a for a in ui.pop_actions() if a.kind == "transport_command"]
        self.assertEqual(actions[0].value, {"operation": "locate_fraction", "args": {"fraction": 0.625}})
        self.assertEqual(ui.state.shadowscore_transport_pending, "locate_fraction")
        self.assertIn("LOCATING 62%", [row.value for row in ui.transport_rows if row.label == "position"])

        acknowledged = dict(snapshot, revision=11, position_fraction=0.625, position_bbt="6.1.000", active_section="C")
        ui.apply_shadowscore_transport_snapshot(acknowledged, operation="locate_fraction")
        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT")
        self.assertEqual(ui.state.shadowscore_transport_pending, "")

    def test_touch_transport_locate_failure_stays_authoritative(self) -> None:
        ui = ShadowboxUI(touch_locate_available=True)
        ui.apply_shadowscore_transport_snapshot({
            "revision": 2,
            "is_playing": True,
            "position_fraction": 0.1,
            "position_bbt": "1.4.192",
            "capabilities": {"can_locate": True},
        })
        self.assertTrue(ui._begin_transport_locate())
        ui.handle_event(UIEvent(kind="set_transport_position", value=0.8, pressed=False))
        ui.pop_actions()

        ui.apply_shadowscore_transport_command_error("locate_fraction", "LOCATE FAILED · CLIENTS NOT ACTIVE")

        self.assertEqual(ui.state.ui_mode, "SYSTEM_TRANSPORT_LOCATE")
        self.assertEqual(ui.state.shadowscore_transport_pending, "")
        self.assertEqual(ui.transport_locate_fraction, 0.1)
        self.assertEqual(ui.state.shadowscore_transport_error, "LOCATE FAILED · CLIENTS NOT ACTIVE")

    def test_home_transport_card_toggles_global_runner_state(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 90.0,
            }
        }

        self.assertEqual(ui.top_level_items, ["SETS", "INSTANCES", "SYSTEM", "PLAY"])
        ui.state.top_index = 3
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind == "set_transport"]
        self.assertEqual([(action.path, action.value) for action in actions], [("/rnbo/jack/transport/rolling", True)])
        self.assertEqual(ui.state.ui_mode, "TOP")
        self.assertEqual(ui.top_level_items[-1], "STOP")

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        actions = [action for action in ui.pop_actions() if action.kind == "set_transport"]
        self.assertEqual([(action.path, action.value) for action in actions], [("/rnbo/jack/transport/rolling", False)])
        self.assertEqual(ui.top_level_items[-1], "PLAY")

    def test_home_keypad_enter_plays_and_zero_stops_transport(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 90.0,
            }
        }

        ui.handle_event(type("Evt", (), {"kind": "keypad_enter"})())
        ui.handle_event(type("Evt", (), {"kind": "keypad_digit", "button_id": "7"})())
        ui.handle_event(type("Evt", (), {"kind": "keypad_digit", "button_id": "0"})())

        actions = [action for action in ui.pop_actions() if action.kind == "set_transport"]
        self.assertEqual(
            [(action.path, action.value) for action in actions],
            [
                ("/rnbo/jack/transport/rolling", True),
                ("/rnbo/jack/transport/rolling", False),
            ],
        )
        self.assertEqual(ui.state.ui_mode, "TOP")

    def test_home_transport_card_is_disabled_when_transport_is_unavailable(self) -> None:
        ui = ShadowboxUI()
        self.assertEqual(ui.top_level_items[-1], "TRANSPORT")
        ui.state.top_index = 3

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        ui.handle_event(type("Evt", (), {"kind": "keypad_enter"})())
        ui.handle_event(type("Evt", (), {"kind": "keypad_digit", "button_id": "0"})())

        self.assertEqual([action for action in ui.pop_actions() if action.kind == "set_transport"], [])
        self.assertEqual(ui.state.ui_mode, "TOP")

    def test_transport_live_updates_refresh_screen_and_renderer(self) -> None:
        ui = ShadowboxUI()
        ui.state.system = {
            "transport": {
                "rolling_path": "/rnbo/jack/transport/rolling",
                "rolling": False,
                "bpm_path": "/rnbo/jack/transport/bpm",
                "bpm": 90.0,
            }
        }
        ui.state.ui_mode = "SYSTEM_TRANSPORT"
        ui.state.transport_cursor = 1

        self.assertTrue(ui.apply_transport_update("/rnbo/jack/transport/rolling", True))
        self.assertTrue(ui.apply_transport_update("/rnbo/jack/transport/bpm", 123.5))

        renderer = _CaptureRenderer()
        renderer.draw(ui)
        self.assertEqual(renderer.last_header, "TRANSPORT")
        self.assertEqual(
            renderer.last_selectable_value_rows,
            [("state", "RUNNING · LOCAL", True), ("tempo", "123.5 BPM", False)],
        )

    def test_designated_midi_note_sets_absolute_offset_and_source(self) -> None:
        ui = ShadowboxUI()
        ui.state.transpose_authority = "standalone"
        ui.state.transpose_controller_role = ROLE_CHROMATIC

        self.assertTrue(ui.apply_transpose_midi_note(60, "KeyStep 37"))
        self.assertEqual(ui.state.transpose_chromatic, 0)
        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual([(action.kind, action.path, action.value) for action in actions], [("set_transpose", ROLE_CHROMATIC, 0)])
        self.assertEqual(ui.state.transpose_last_source, "MIDI KeyStep 37")

        self.assertTrue(ui.apply_transpose_midi_note(57, "KeyStep 37"))
        self.assertEqual(ui.state.transpose_chromatic, -3)

    def test_controller_and_role_pickers_store_stable_device_identity(self) -> None:
        ui = ShadowboxUI()
        device = MidiInputPort("KeyStep 37", "KeyStep 37 MIDI 1", "24:0")
        ui.set_transpose_devices([device], "")
        ui.state.ui_mode = "SYSTEM_TRANSPOSE_CONTROLLER"
        ui.state.transpose_controller_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.transpose_controller_identity, device.identity)
        actions = ui.pop_actions()
        self.assertTrue(any(action.kind == "configure_transpose_midi" and action.value == device.identity for action in actions))

        ui.state.ui_mode = "SYSTEM_TRANSPOSE_ROLE"
        ui.state.transpose_role_cursor = 3
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())
        self.assertEqual(ui.state.transpose_controller_role, ROLE_SCALAR)

    def test_transpose_edit_uses_common_published_target_range(self) -> None:
        ui = ShadowboxUI()
        ui.state.transpose_authority = "standalone"
        ui.state.instances = [
            {"id": "1", "params": [{"name": "ChromaticTranspose", "path": "/a", "value": 0, "min": -12, "max": 12}]},
            {"id": "2", "params": [{"name": "ChromaticTranspose", "path": "/b", "value": 0, "min": -7, "max": 7}]},
        ]
        ui.state.ui_mode = "SYSTEM_TRANSPOSE_EDIT"
        ui.state.transpose_edit_role = ROLE_CHROMATIC
        ui.state.edit_value = 7

        ui.handle_event(type("Evt", (), {"kind": "step", "delta": 1})())

        self.assertEqual(ui.state.transpose_chromatic, 7)
        self.assertEqual(ui.state.edit_value, 7)

    def test_transpose_requires_explicit_local_authority(self) -> None:
        ui = ShadowboxUI()
        ui.state.transpose_controller_role = ROLE_CHROMATIC

        self.assertFalse(ui.apply_transpose_midi_note(64, "KeyStep 37"))
        self.assertEqual(ui.state.transpose_chromatic, 0)
        self.assertFalse(any(action.kind == "set_transpose" for action in ui.pop_actions()))

        self.assertTrue(ui.set_transpose_authority("standalone"))
        self.assertTrue(ui.apply_transpose_midi_note(64, "KeyStep 37"))
        self.assertEqual(ui.state.transpose_chromatic, 4)


if __name__ == "__main__":
    unittest.main()
