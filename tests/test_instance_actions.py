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

from shadowbox.renderer import ShadowboxRenderer
from shadowbox.rnbo import RNBO_PORT, RNBOSnapshot
from shadowbox.ui import ShadowboxUI


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
        self.last_value_rows: list[tuple[str, object]] | None = None
        self.last_value_weights: list[str | None] | None = None
        self.last_header: str | None = None
        self.last_selectable_value_rows: list[tuple[str, object, bool]] | None = None

    def draw_header(self, title: str, busy: bool = False, ticks: int = 0) -> None:
        self.last_header = title

    def draw_string_list(
        self,
        items: list[str],
        selected_idx: int,
        current_indices: set[int] | None = None,
        item_weights: dict[int, str] | None = None,
    ) -> None:
        self.last_items = items
        self.last_selected_idx = selected_idx
        self.last_current_indices = current_indices
        self.last_item_weights = item_weights

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


class InstanceActionTests(unittest.TestCase):
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
        self.assertTrue(ui.can_remove_instances)
        self.assertEqual(ui.state.instance_cursor, 1)

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

    def test_routing_target_list_marks_used_destinations_italic(self) -> None:
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
        ui.state.routing_target_cursor = 2

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "DISCONNECT", "system:capture_1", "system:capture_2"])
        self.assertEqual(renderer.last_current_indices, {2})
        self.assertEqual(renderer.last_item_weights, {3: "italic"})

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

    def test_graph_menu_shows_audio_and_midi_overview_entries(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertIn("AUDIO OVERVIEW", renderer.last_items or [])
        self.assertIn("MIDI OVERVIEW", renderer.last_items or [])

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

        ui.handle_event(type("Evt", (), {"kind": "rotate", "delta": 1})())

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

    def test_overview_long_press_returns_to_instance_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_routing_overview())
        ui.state.ui_mode = "MIDI_ROUTING_OVERVIEW"

        ui.handle_event(type("Evt", (), {"kind": "long_press"})())

        self.assertEqual(ui.state.ui_mode, "GRAPH_MENU")

    def test_top_level_graphs_enters_graph_menu(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.top_index = 0

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "GRAPH_MENU")
        self.assertEqual(ui.state.graph_menu_cursor, 1)

    def test_graph_menu_renders_expected_items(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "CURRENT GRAPH", "LOAD GRAPH", "AUDIO OVERVIEW", "MIDI OVERVIEW", "SAVE GRAPH", "STARTUP"],
        )
        self.assertEqual(renderer.last_selected_idx, 1)

    def test_graph_menu_shows_new_graph_when_published_as_loadable_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_new_graph_set())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "CURRENT GRAPH", "NEW GRAPH", "LOAD GRAPH", "AUDIO OVERVIEW", "MIDI OVERVIEW", "SAVE GRAPH", "STARTUP"],
        )

    def test_network_properties_use_discovered_ip_and_rnbo_port(self) -> None:
        ui = ShadowboxUI()
        fake_socket = mock.Mock()
        fake_socket.getsockname.return_value = ("10.0.0.24", 54321)

        with mock.patch("shadowbox.ui.socket.socket", return_value=fake_socket) as socket_ctor:
            self.assertEqual(ui.network_ip_address, "10.0.0.24")

        socket_ctor.assert_called_once()
        fake_socket.connect.assert_called_once_with(("1.1.1.1", 80))
        fake_socket.close.assert_called_once()
        self.assertEqual(ui.network_osc_port, RNBO_PORT)

    def test_network_ip_address_falls_back_when_probe_fails(self) -> None:
        ui = ShadowboxUI()

        with mock.patch("shadowbox.ui.socket.socket", side_effect=OSError("offline")):
            self.assertEqual(ui.network_ip_address, "?")

    def test_graph_set_list_renders_published_saved_sets(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "StudioA", "StudioB"])
        self.assertEqual(renderer.last_selected_idx, 1)
        self.assertEqual(renderer.last_current_indices, {1})
        self.assertEqual(renderer.last_item_weights, {1: "italic"})

    def test_graph_menu_shows_rename_set_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "CURRENT GRAPH", "LOAD GRAPH", "AUDIO OVERVIEW", "MIDI OVERVIEW", "SAVE GRAPH", "RENAME GRAPH", "STARTUP"],
        )

    def test_graph_menu_shows_presets_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "CURRENT GRAPH", "LOAD GRAPH", "AUDIO OVERVIEW", "MIDI OVERVIEW", "GRAPH PRESETS", "SAVE GRAPH", "STARTUP"],
        )

    def test_graph_status_marks_current_set_and_dirty_state_in_value_rows(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STATUS"

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_value_rows, [("graph", "StudioA"), ("dirty", "YES"), ("graphs", 2)])
        self.assertEqual(renderer.last_current_indices, {1, 2})
        self.assertEqual(renderer.last_value_weights, ["italic", None, None])

    def test_graph_status_shows_loaded_graph_preset_when_published(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        self.assertEqual(
            [(row.label, row.value, row.current) for row in ui.graph_status_value_rows],
            [("graph", "StudioA", True), ("dirty", "YES", True), ("graphs", 2, False), ("preset", "linke synce", True)],
        )

    def test_graph_set_selection_queues_load_set_action(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "load_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/load")
        self.assertEqual(actions[0].value, "StudioB")

    def test_new_graph_action_queues_load_new_graph_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_new_graph_set())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "load_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/load")
        self.assertEqual(actions[0].value, "New Graph")

    def test_graph_save_set_opens_name_editor_with_generated_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 5

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260401-120000"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_set")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/control/sets/save")
        self.assertEqual(ui.state.name_editor_draft, "studioa-20260401-120000")
        self.assertEqual(ui.state.name_editor_cursor, 1)

    def test_graph_preset_list_shows_actions_and_current_selection(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = ui.graph_preset_initial_cursor()

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(
            renderer.last_items,
            ["..", "SAVE PRESET", "RENAME PRESET", "DELETE PRESET", "Unipolar Positive", "linke synce"],
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

    def test_save_graph_preset_action_opens_name_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 1

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260404-111500"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_graph_preset")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/control/sets/presets/save")
        self.assertEqual(ui.state.name_editor_draft, "linke-synce-20260404-111")

    def test_rename_graph_preset_action_opens_name_editor_and_submits_pair(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "rename_graph_preset")
        self.assertEqual(ui.state.name_editor_draft, "linke synce")
        self.assertEqual(ui.state.name_editor_target_name, "linke synce")

        ui.state.name_editor_draft = "linke synce 2"
        ui.state.name_editor_cursor = 1
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "rename_graph_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/presets/rename")
        self.assertEqual(actions[0].value, ["linke synce", "linke synce 2"])

    def test_delete_graph_preset_action_queues_delete(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_graph_preset_capabilities())
        ui.state.ui_mode = "GRAPH_PRESET_LIST"
        ui.state.graph_preset_cursor = 3

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

        self.assertEqual(renderer.last_header, "SAVE GRAPH")
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

        ui.handle_event(type("Evt", (), {"kind": "rotate", "delta": 1})())
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

    def test_graph_rename_set_opens_name_editor_with_current_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 6

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "rename_set")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/control/sets/rename")
        self.assertEqual(ui.state.name_editor_draft, "StudioA")
        self.assertEqual(ui.state.name_editor_target_name, "StudioA")

    def test_name_editor_rename_label_and_action_for_rename_set(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_set_rename())
        ui._begin_rename_name_editor("rename_set", "/rnbo/inst/control/sets/rename", "StudioA", "GRAPH_MENU")
        ui.state.name_editor_cursor = 1
        ui.state.name_editor_draft = "StudioC"

        renderer = _CaptureRenderer()
        renderer.draw(ui)
        self.assertEqual(renderer.last_header, "RENAME GRAPH")
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
            ["..", "SAVE PRESET", "RENAME PRESET", "Init", "Bass"],
        )
        self.assertEqual(renderer.last_current_indices, {4})
        self.assertEqual(renderer.last_selected_idx, 3)

    def test_save_preset_action_opens_name_editor(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 1

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260404-111500"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "save_preset")
        self.assertEqual(ui.state.name_editor_path, "/rnbo/inst/1/presets/save")
        self.assertEqual(ui.state.name_editor_draft, "bass-20260404-111500")

    def test_rename_preset_action_opens_name_editor_and_submits(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_preset_capabilities())
        ui.state.active_instance_id = "1"
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.preset_cursor = 2

        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        self.assertEqual(ui.state.ui_mode, "NAME_EDITOR")
        self.assertEqual(ui.state.name_editor_context, "rename_preset")
        self.assertEqual(ui.state.name_editor_draft, "Bass")
        self.assertEqual(ui.state.name_editor_target_name, "Bass")

        ui.state.name_editor_draft = "Bass 2"
        ui.state.name_editor_cursor = 1
        ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "rename_preset")
        self.assertEqual(actions[0].path, "/rnbo/inst/1/presets/rename")
        self.assertEqual(actions[0].value, "Bass 2")

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

        self.assertEqual(renderer.last_items, ["..", "RESTORE LAST", "LOAD NAMED GRAPH", "OFF"])
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


if __name__ == "__main__":
    unittest.main()
