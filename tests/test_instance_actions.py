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
from shadowbox.rnbo import RNBOSnapshot
from shadowbox.ui import ShadowboxUI


class _FakeDisplay:
    width = 128
    height = 32

    def clear(self) -> None:
        pass

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        pass

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 6 * max(1, scale), 8 * max(1, scale))

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * max(1, scale)

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
        self.last_header: str | None = None

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

    def draw_value_row(self, y: int, selected: bool, label: str, value: object, invert: bool = False) -> None:
        if self.last_value_rows is None:
            self.last_value_rows = []
        self.last_value_rows.append((label, value))


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

        ui.state.ui_mode = "ROUTING_TARGETS"
        renderer.draw(ui)
        self.assertEqual(renderer.last_header, "Main Input")

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

        self.assertEqual(renderer.last_items, ["..", "CURRENT GRAPH", "LOAD SET", "SAVE SET", "STARTUP"])
        self.assertEqual(renderer.last_selected_idx, 1)

    def test_graph_set_list_renders_published_saved_sets(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.graph_set_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "StudioA", "StudioB"])
        self.assertEqual(renderer.last_selected_idx, 1)

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

    def test_graph_save_set_queues_generated_name(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.graph_menu_cursor = 3

        with mock.patch("shadowbox.ui.time.strftime", return_value="20260401-120000"):
            ui.handle_event(type("Evt", (), {"kind": "short_press"})())

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_set")
        self.assertEqual(actions[0].path, "/rnbo/inst/control/sets/save")
        self.assertEqual(actions[0].value, "studioa-20260401-120000")

    def test_graph_startup_menu_renders_expected_items(self) -> None:
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(self._snapshot_with_sets())
        ui.state.ui_mode = "GRAPH_STARTUP"
        ui.state.graph_startup_cursor = 1

        renderer = _CaptureRenderer()
        renderer.draw(ui)

        self.assertEqual(renderer.last_items, ["..", "RESTORE LAST", "LOAD NAMED SET", "OFF"])
        self.assertEqual(renderer.last_current_indices, {1})

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
