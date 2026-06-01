import unittest
import sys
import types
from types import SimpleNamespace

pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import ShadowboxRenderer, create_renderer, should_enable_touch_layout
from shadowbox.touch import TouchAction
from shadowbox.ui import NAME_TOUCH_KEY_VALUES, ShadowboxUI, UIEvent, ValueRow


class _FiveInchDisplay:
    width = 800
    height = 480

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def clear(self) -> None:
        pass

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        self.ops.append(("text", text, x, y, scale, weight, on))

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 12 * max(1, scale), 16 * max(1, scale))

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 16 * max(1, scale)

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        self.ops.append(("rect", x, y, w, h, on, fill))

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        self.ops.append(("hline", x, y, w, on))

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        self.ops.append(("vline", x, y, h, on))

    def show(self) -> None:
        pass


class _ColorFiveInchDisplay(_FiveInchDisplay):
    def fill_rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        self.ops.append(("fill_rect_color", x, y, w, h, color))

    def rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], fill: bool = False) -> None:
        self.ops.append(("rect_color", x, y, w, h, color, fill))

    def rounded_rect_color(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        radius: int,
        color: tuple[int, int, int],
        fill: bool = False,
    ) -> None:
        self.ops.append(("rounded_rect_color", x, y, w, h, radius, color, fill))

    def hline_color(self, x: int, y: int, w: int, color: tuple[int, int, int]) -> None:
        self.ops.append(("hline_color", x, y, w, color))

    def text_color(
        self,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
        scale: int = 1,
        weight: str = "regular",
    ) -> None:
        self.ops.append(("text_color", text, x, y, color, scale, weight))

    def text_line_color(
        self,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
        scale: int = 1,
        weight: str = "regular",
    ) -> None:
        self.ops.append(("text_line_color", text, x, y, color, scale, weight))


def _render_touch_layout(ui: ShadowboxUI) -> tuple[ShadowboxRenderer, _FiveInchDisplay]:
    display = _FiveInchDisplay()
    renderer = create_renderer(display)
    renderer.set_touch_mode(True)
    renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
    if renderer.touch_layout is None:
        raise AssertionError("touch layout was not created")
    return renderer, display


def _touch_action_for_target(
    renderer: ShadowboxRenderer,
    *,
    kind: str,
    index: int | None = None,
    button_id: str = "",
) -> TouchAction:
    if renderer.touch_layout is None:
        raise AssertionError("touch layout was not created")
    target = next(
        target
        for target in renderer.touch_layout.targets
        if target.kind == kind and (index is None or target.index == index) and (not button_id or target.button_id == button_id)
    )
    x = (target.x + (target.w / 2.0)) / max(1, renderer.touch_layout.width - 1)
    y = (target.y + (target.h / 2.0)) / max(1, renderer.touch_layout.height - 1)
    action = renderer.touch_layout.action_for_point(x, y)
    if action is None:
        raise AssertionError(f"no action resolved for {kind}")
    return action


class TouchDirectUITests(unittest.TestCase):
    def test_touch_direct_enables_shared_touch_layout(self) -> None:
        self.assertTrue(should_enable_touch_layout("touch_direct"))

    def test_touch_zones_still_enables_shared_touch_layout(self) -> None:
        self.assertTrue(should_enable_touch_layout("touch_zones"))

    def test_tap_row_selects_top_menu_row(self) -> None:
        ui = ShadowboxUI()

        ui.handle_event(UIEvent(kind="tap_row", index=1))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_LIST")
        self.assertEqual(ui.state.top_index, 1)

    def test_tap_back_uses_explicit_back_navigation(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "GRAPH_MENU"

        ui.handle_event(UIEvent(kind="tap_back"))

        self.assertEqual(ui.state.ui_mode, "GRAPH_SET_LIST")

    def test_page_down_moves_by_discrete_page(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": 1,
                "params": [{"name": f"p{i}", "value": 0, "path": f"/p/{i}"} for i in range(10)],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.param_cursor, 6)

    def test_page_controls_move_the_window_without_toggling_bool_rows(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "enabled", "value": 0, "path": "/params/enabled", "metadata": {"bool": True}},
                    *[
                        {"name": f"p{i}", "value": 0, "path": f"/p/{i}"}
                        for i in range(1, 10)
                    ],
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        bool_param = ui.active_params[0]
        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(ui.state.param_cursor, 6)
        self.assertEqual(bool_param.get("value"), 0)

    def test_instance_page_controls_scroll_instances_not_action_buttons(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [
            {"id": str(idx), "label": f"Inst {idx}"}
            for idx in range(1, 5)
        ]
        ui.state.active_instance_id = "1"
        ui.state.instance_cursor = 1
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.instance_cursor, 4)
        self.assertEqual(ui.state.active_instance_id, "4")

        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.instance_cursor, 4)
        self.assertEqual(ui.state.active_instance_id, "4")

        ui.handle_event(UIEvent(kind="page_up"))

        self.assertEqual(ui.state.instance_cursor, 1)
        self.assertEqual(ui.state.active_instance_id, "1")

    def test_tap_row_toggles_bool_param_directly(self) -> None:
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

        ui.handle_event(UIEvent(kind="tap_row", index=2))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(ui.selected_param.get("value"), 1)

    def test_tap_menu_rows_transition_into_nested_views(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instances = [
            {
                "id": "1",
                "params": [{"name": "enabled", "value": 0, "path": "/params/enabled"}],
            }
        ]
        ui.state.active_instance_id = "1"

        ui.handle_event(UIEvent(kind="tap_row", index=1))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(ui.state.param_cursor, 1)

    def test_primary_button_uses_current_selection(self) -> None:
        ui = ShadowboxUI()
        ui.state.top_index = 2

        ui.handle_event(UIEvent(kind="tap_button", button_id="primary"))

        self.assertEqual(ui.state.ui_mode, "SYSTEM_MENU")

    def test_top_menu_icon_and_label_are_both_direct_touch_targets(self) -> None:
        ui = ShadowboxUI()

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="home_card_icon", index=0), TouchAction("tap_row", index=0))
        self.assertEqual(_touch_action_for_target(renderer, kind="home_card_label", index=0), TouchAction("tap_row", index=0))

    def test_home_card_icons_scale_up_on_touch_layout(self) -> None:
        ui = ShadowboxUI()
        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer._draw_graphs_icon(0, 0, on=True, scale=2)

        rect_sizes = [(w, h) for kind, _x, _y, w, h, *_rest in display.ops if kind == "rect"]
        self.assertTrue(any(w >= 48 and h >= 36 for w, h in rect_sizes))

    def test_home_card_labels_share_a_baseline_height_on_touch_layout(self) -> None:
        class _DescenderAwareDisplay(_FiveInchDisplay):
            def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
                height = 18 if any(ch in "gjpqy" for ch in str(text).lower()) else 14
                return (len(str(text)) * 12 * max(1, scale), height * max(1, scale))

        ui = ShadowboxUI()
        display = _DescenderAwareDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        label_ops = [op for op in display.ops if op[0] == "text" and op[1] in {"Graphs", "Instances", "System"}]
        self.assertEqual([op[1] for op in label_ops], ["Graphs", "Instances", "System"])
        self.assertEqual(len({op[3] for op in label_ops}), 1)

    def test_header_title_sits_closer_to_back_button_on_touch_layout(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "GRAPH_MENU"
        ui.state.system = {"set_name": "StudioA"}

        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        title_ops = [op for op in display.ops if op[0] == "text" and op[1] == "StudioA"]
        self.assertTrue(title_ops)
        _kind, _text, title_x, title_y, scale, _weight, _on = title_ops[0]
        self.assertLessEqual(title_x, 100)
        self.assertGreaterEqual(title_y, 2)

    def test_touch_menu_distinguishes_drilldown_rows_from_action_buttons(self) -> None:
        class _ColorFiveInchDisplay(_FiveInchDisplay):
            def fill_rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
                self.ops.append(("fill_rect_color", x, y, w, h, color))

            def rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], fill: bool = False) -> None:
                self.ops.append(("rect_color", x, y, w, h, color, fill))

            def rounded_rect_color(
                self,
                x: int,
                y: int,
                w: int,
                h: int,
                radius: int,
                color: tuple[int, int, int],
                fill: bool = False,
            ) -> None:
                self.ops.append(("rounded_rect_color", x, y, w, h, radius, color, fill))

            def hline_color(self, x: int, y: int, w: int, color: tuple[int, int, int]) -> None:
                self.ops.append(("hline_color", x, y, w, color))

            def text_color(
                self,
                text: str,
                x: int,
                y: int,
                color: tuple[int, int, int],
                scale: int = 1,
                weight: str = "regular",
            ) -> None:
                self.ops.append(("text_color", text, x, y, color, scale, weight))

        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [{"id": "1", "label": "Kick"}, {"id": "2", "label": "Pad"}]
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        chevrons = [op for op in display.ops if op[0] == "text_color" and op[1] == ">"]
        self.assertEqual(len(chevrons), 2)

        action_labels = [op for op in display.ops if op[0] == "text_color" and op[1] in {"Add", "Remove"}]
        self.assertEqual([op[1] for op in action_labels], ["Add", "Remove"])
        action_targets = [target for target in renderer.touch_layout.targets if target.kind == "modal_button" and target.button_id in {"add", "remove"}]
        self.assertEqual([target.button_id for target in action_targets], ["add", "remove"])
        self.assertEqual(len({target.y for target in action_targets}), 1)
        button_surfaces = [
            op
            for op in display.ops
            if op[0] == "rounded_rect_color"
            and any(op[1] == target.x and op[2] == target.y and op[3] == target.w and op[4] == target.h for target in action_targets)
        ]
        self.assertEqual(len([op for op in button_surfaces if op[7] is True]), 2)

        ui.state.instance_cursor = len(ui.state.instances) + 1
        focused_display = _ColorFiveInchDisplay()
        focused_renderer = create_renderer(focused_display)
        focused_renderer.set_touch_mode(True)
        focused_renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
        focused_add = [op for op in focused_display.ops if op[0] == "text_color" and op[1] == "Add"]
        self.assertTrue(focused_add)
        self.assertEqual(focused_add[0][4], focused_renderer._theme("text"))

    def test_touch_instance_list_does_not_draw_current_focus_accent(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [{"id": "1", "label": "Kick"}, {"id": "2", "label": "Pad"}]
        ui.state.active_instance_id = "1"
        ui.state.instance_cursor = 1

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        accent = renderer._theme("accent")
        focus_marks = [
            op for op in display.ops
            if op[0] in {"fill_rect_color", "rect_color", "rounded_rect_color"} and accent in op
        ]
        self.assertEqual(focus_marks, [])

    def test_preset_touch_list_uses_three_rows_above_justified_footer_buttons(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PRESET_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "label": "Synth A",
                "presets": [
                    {"name": "Init", "path": "/rnbo/inst/1/presets/load", "value": "Init"},
                    {"name": "Bass", "path": "/rnbo/inst/1/presets/load", "value": "Bass"},
                    {"name": "Lead", "path": "/rnbo/inst/1/presets/load", "value": "Lead"},
                    {"name": "Pad", "path": "/rnbo/inst/1/presets/load", "value": "Pad"},
                ],
                "preset_save_path": "/rnbo/inst/1/presets/save",
                "preset_destroy_path": "/rnbo/inst/1/presets/destroy",
                "current_preset_name": "Bass",
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.preset_cursor = len(ui.preset_action_items) + 1

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertEqual([target.label for target in row_targets], ["Init", "Bass", "Lead"])

        buttons = [target for target in renderer.touch_layout.targets if target.kind == "modal_button"]
        self.assertEqual([target.button_id for target in buttons], ["save", "save_as", "remove"])
        self.assertTrue(all(row.y + row.h <= buttons[0].y for row in row_targets))
        self.assertEqual(buttons[0].x, 12)
        self.assertEqual(buttons[1].x, buttons[0].x + buttons[0].w + 12)
        self.assertEqual(buttons[2].x, buttons[1].x + buttons[1].w + 12)

    def test_graph_touch_list_uses_three_rows_and_save_footer_buttons(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "GRAPH_SET_LIST"
        ui.state.system = {
            "set_name": "StudioA",
            "sets": {
                "current_name": "StudioA",
                "dirty": True,
                "available_sets": ["StudioA", "StudioB", "StudioC", "StudioD"],
                "load_path": "/rnbo/inst/control/sets/load",
                "save_path": "/rnbo/inst/control/sets/save",
            },
        }
        ui.state.graph_set_cursor = ui.graph_set_initial_cursor()

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertEqual([target.label for target in row_targets], ["StudioA", "StudioB", "StudioC"])

        buttons = [target for target in renderer.touch_layout.targets if target.kind == "modal_button"]
        self.assertEqual([target.button_id for target in buttons], ["save", "save_as"])
        self.assertTrue(all(row.y + row.h <= buttons[0].y for row in row_targets))
        self.assertEqual(buttons[0].x, 12)
        self.assertEqual(buttons[1].x, buttons[0].x + buttons[0].w + 12)

    def test_touch_page_controls_do_not_select_back_or_action_rows(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "REMOVE_INSTANCE_PICKER"
        ui.state.instances = [{"id": "1", "label": "Kick"}]
        ui.state.remove_instance_picker_cursor = 1

        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.remove_instance_picker_cursor, 1)
        self.assertEqual(ui.state.ui_mode, "REMOVE_INSTANCE_PICKER")

        ui.state.ui_mode = "PATCHER_PICKER"
        ui.state.patchers = ["Juno2"]
        ui.state.patcher_cursor = 1

        ui.handle_event(UIEvent(kind="page_down"))

        self.assertEqual(ui.state.patcher_cursor, 1)
        self.assertEqual(ui.state.ui_mode, "PATCHER_PICKER")

    def test_instance_list_action_buttons_drive_the_picker_flow(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [{"id": "1", "label": "Kick"}]
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        ui.handle_event(UIEvent(kind="tap_button", button_id="add_instance"))
        self.assertEqual(ui.state.ui_mode, "PATCHER_PICKER")
        self.assertEqual(ui.state.patcher_picker_context, "add")

        ui.state.ui_mode = "INSTANCE_LIST"
        ui.handle_event(UIEvent(kind="tap_button", button_id="remove_instance"))
        self.assertEqual(ui.state.ui_mode, "REMOVE_INSTANCE_PICKER")
        self.assertEqual(ui.state.remove_instance_origin, "instance_list")

    def test_instance_list_short_action_button_labels_are_handled(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [{"id": "1", "label": "Kick"}]
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        ui.handle_event(UIEvent(kind="tap_button", button_id="add"))
        self.assertEqual(ui.state.ui_mode, "PATCHER_PICKER")

        ui.state.ui_mode = "INSTANCE_LIST"
        ui.handle_event(UIEvent(kind="tap_button", button_id="remove"))
        self.assertEqual(ui.state.ui_mode, "REMOVE_INSTANCE_PICKER")

    def test_add_instance_returns_to_instances_and_selects_new_snapshot_item(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PATCHER_PICKER"
        ui.state.patcher_picker_context = "add"
        ui.state.instances = [{"id": "1", "label": "Kick"}]
        ui.state.patchers = ["Juno2", "Quantizer"]
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.patcher_cursor = 2

        ui.handle_event(UIEvent(kind="tap_row", index=2))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_LIST")
        self.assertEqual(ui.state.instance_cursor, 2)
        actions = [action for action in ui.pop_actions() if action.kind == "add_instance"]
        self.assertEqual(actions[0].value, [-1, "Quantizer"])

        ui.apply_runner_snapshot(
            SimpleNamespace(
                instances=[{"id": "1", "label": "Kick"}, {"id": "2", "label": "Quantizer"}],
                patchers=["Juno2", "Quantizer"],
                add_instance_path="/rnbo/inst/control/load",
                remove_instance_path="/rnbo/inst/control/unload",
                system={},
            )
        )

        self.assertEqual(ui.state.ui_mode, "INSTANCE_LIST")
        self.assertEqual(ui.state.active_instance_id, "2")
        self.assertEqual(ui.state.instance_cursor, 2)

    def test_empty_instance_list_touch_layout_does_not_index_placeholder_as_instance(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = []
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        renderer, display = _render_touch_layout(ui)

        labels = [op[1] for op in display.ops if op[0] == "text"]
        self.assertIn("no instances", labels)
        row_labels = [target.label for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertNotIn("no instances", row_labels)
        self.assertNotIn("..", row_labels)

    def test_instance_list_touch_layout_omits_back_row(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "INSTANCE_LIST"
        ui.state.instances = [{"id": "1", "label": "Kick"}]
        ui.state.add_instance_path = "/rnbo/inst/control/load"
        ui.state.remove_instance_path = "/rnbo/inst/control/unload"

        renderer, display = _render_touch_layout(ui)

        labels = [op[1] for op in display.ops if op[0] == "text"]
        row_labels = [target.label for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertNotIn("..", labels)
        self.assertNotIn("..", row_labels)
        self.assertIn("Kick", row_labels)

    def test_value_editor_slider_target_maps_touch_position_to_value(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 0.0, "path": "/params/gain", "min": -1.0, "max": 1.0}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.0

        renderer, _display = _render_touch_layout(ui)

        action = _touch_action_for_target(renderer, kind="edit_slider", button_id="value_slider")
        self.assertEqual(action.kind, "set_edit_value")
        self.assertAlmostEqual(action.value, 0.5, places=2)

    def test_value_editor_touch_readout_is_large_and_right_aligned_above_slider(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 0.5, "path": "/params/gain", "min": -1.0, "max": 1.0}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.5

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
        if renderer.touch_layout is None:
            raise AssertionError("touch layout was not created")

        slider = next(target for target in renderer.touch_layout.targets if target.kind == "edit_slider")
        value_op = next(op for op in display.ops if op[0] == "text_color" and op[1] == "0.500")
        _kind, text, x, y, _color, scale, weight = value_op
        text_w = len(text) * 12 * scale

        self.assertGreater(y, renderer.content_top)
        self.assertLess(y, slider.y)
        self.assertGreaterEqual(scale, 4)
        self.assertEqual(weight, "semibold")
        self.assertGreaterEqual(x + text_w, display.width - 28)
        self.assertGreater(x, display.width // 2)

    def test_value_editor_exposes_midi_learn_and_clear_buttons(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "gain",
            "value": 0.0,
            "path": "/rnbo/inst/1/params/gain",
            "min": -1.0,
            "max": 1.0,
            "metadata": {"midi": {"chan": 4, "ctrl": 28}},
        }
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.0

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
        if renderer.touch_layout is None:
            raise AssertionError("touch layout was not created")

        self.assertEqual(_touch_action_for_target(renderer, kind="modal_button", button_id="learn"), TouchAction("tap_button", button_id="learn"))
        self.assertEqual(_touch_action_for_target(renderer, kind="modal_button", button_id="clear"), TouchAction("tap_button", button_id="clear"))
        labels = [op[1] for op in display.ops if op[0] in {"text", "text_color"}]
        self.assertTrue(any("MIDI ch 4 CC 28" in label for label in labels))

    def test_value_editor_touch_event_sets_numeric_param(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 0.0, "path": "/params/gain", "min": -1.0, "max": 1.0}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.0

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.75))

        self.assertEqual(ui.state.edit_value, 0.5)
        self.assertEqual(param["value"], 0.5)
        actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].path, "/params/gain")
        self.assertEqual(actions[0].value, 0.5)

    def test_value_editor_touch_back_keeps_live_numeric_edit(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 0.0, "path": "/params/gain", "min": -1.0, "max": 1.0}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.0
        ui._edit_original_value = 0.0

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.75))
        ui.handle_event(UIEvent(kind="tap_back"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(param["value"], 0.5)
        set_actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual([action.value for action in set_actions], [0.5])

    def test_value_editor_encoder_long_press_still_cancels_numeric_edit(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "gain", "value": 0.0, "path": "/params/gain", "min": -1.0, "max": 1.0}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0.0
        ui._edit_original_value = 0.0

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.75))
        ui.handle_event(UIEvent(kind="long_press"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(param["value"], 0.0)
        set_actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual([action.value for action in set_actions], [0.5, 0.0])

    def test_small_int_editor_step_bar_is_touchable(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "MaxSteps",
            "value": 16,
            "path": "/params/MaxSteps",
            "min": 1,
            "max": 16,
            "metadata": {"display_precision": "0", "edit_step": "1", "edit_as": "int"},
        }
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 16

        renderer, _display = _render_touch_layout(ui)

        action = _touch_action_for_target(renderer, kind="edit_slider", button_id="value_slider")
        self.assertEqual(action.kind, "set_edit_value")

    def test_small_int_editor_touch_event_sets_integer_param(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "MaxSteps",
            "value": 16,
            "path": "/params/MaxSteps",
            "min": 1,
            "max": 16,
            "metadata": {"display_precision": "0", "edit_step": "1", "edit_as": "int"},
        }
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 16

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.0))

        self.assertEqual(ui.state.edit_value, 1)
        self.assertEqual(param["value"], 1)
        actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].path, "/params/MaxSteps")
        self.assertEqual(actions[0].value, 1)

    def test_small_int_editor_touch_back_keeps_live_numeric_edit(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "MaxSteps",
            "value": 16,
            "path": "/params/MaxSteps",
            "min": 1,
            "max": 16,
            "metadata": {"display_precision": "0", "edit_step": "1", "edit_as": "int"},
        }
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 16
        ui._edit_original_value = 16

        ui.handle_event(UIEvent(kind="set_edit_value", value=0.0))
        ui.handle_event(UIEvent(kind="tap_back"))

        self.assertEqual(ui.state.ui_mode, "PARAM_LIST")
        self.assertEqual(param["value"], 1)
        set_actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual([action.value for action in set_actions], [1])

    def test_ttid_keyboard_records_key_and_load_targets(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "ttid", "value": 0, "path": "/params/ttid", "metadata": {"editor": "ttid"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_ttid_mode = "keyboard"
        ui.state.edit_ttid_selected_pc = 0

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="ttid_key", index=0), TouchAction("set_ttid_pc", index=0))
        self.assertEqual(_touch_action_for_target(renderer, kind="ttid_key", index=1), TouchAction("set_ttid_pc", index=1))
        self.assertEqual(_touch_action_for_target(renderer, kind="ttid_root", index=0), TouchAction("set_ttid_root", index=0))
        self.assertEqual(_touch_action_for_target(renderer, kind="ttid_scale_step", index=1), TouchAction("step_ttid_scale", index=1))
        self.assertEqual(_touch_action_for_target(renderer, kind="ttid_load", index=12), TouchAction("load_ttid_scale", index=12))
        self.assertFalse([op for op in _display.ops if op[0] == "text" and op[1] == "0"])

    def test_ttid_touch_key_toggles_pitch_class(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "ttid", "value": 0, "path": "/params/ttid", "metadata": {"editor": "ttid"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_ttid_mode = "keyboard"

        ui.handle_event(UIEvent(kind="set_ttid_pc", index=4))

        self.assertEqual(ui.state.edit_ttid_selected_pc, 4)
        self.assertEqual(ui.state.edit_value, 1 << 4)
        self.assertEqual(param["value"], 1 << 4)
        actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].value, 1 << 4)

    def test_ttid_touch_load_root_and_scale_apply_mask(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "ttid", "value": 0, "path": "/params/ttid", "metadata": {"editor": "ttid"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_ttid_mode = "keyboard"
        ui.state.edit_ttid_scale_names = ["major"]

        ui.handle_event(UIEvent(kind="set_ttid_root", index=2))
        self.assertEqual(ui.state.edit_ttid_load_root, 2)
        self.assertEqual(ui.state.edit_ttid_mode, "keyboard")

        ui.handle_event(UIEvent(kind="set_ttid_scale", index=0))
        self.assertEqual(ui.state.edit_ttid_mode, "keyboard")

        ui.handle_event(UIEvent(kind="load_ttid_scale"))
        self.assertEqual(ui.state.edit_ttid_selected_pc, 2)
        self.assertEqual(param["value"], ui.state.edit_value)
        actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertTrue(actions)

    def test_ttid_touch_scale_step_stays_on_keyboard_page(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "ttid", "value": 0, "path": "/params/ttid", "metadata": {"editor": "ttid"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_ttid_mode = "keyboard"
        ui.state.edit_ttid_scale_names = ["major", "minor"]

        ui.handle_event(UIEvent(kind="step_ttid_scale", index=1))

        self.assertEqual(ui.state.edit_ttid_mode, "keyboard")
        self.assertEqual(ui.state.edit_ttid_scale_index, 1)

    def test_name_editor_touch_layout_uses_direct_keyboard_targets(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_SET_LIST")

        renderer, display = _render_touch_layout(ui)

        q_index = NAME_TOUCH_KEY_VALUES.index("q")
        self.assertEqual(_touch_action_for_target(renderer, kind="name_key", index=q_index), TouchAction("tap_name_key", index=q_index, button_id="key_q"))
        self.assertEqual(_touch_action_for_target(renderer, kind="name_control", button_id="shift"), TouchAction("name_shift", button_id="shift"))
        self.assertEqual(_touch_action_for_target(renderer, kind="name_control", button_id="space"), TouchAction("name_space", button_id="space"))
        self.assertEqual(_touch_action_for_target(renderer, kind="name_control", button_id="backspace"), TouchAction("name_backspace", button_id="backspace"))
        self.assertEqual(_touch_action_for_target(renderer, kind="name_control", button_id="mode"), TouchAction("name_keyboard_mode", button_id="mode"))
        self.assertEqual(_touch_action_for_target(renderer, kind="modal_button", button_id="save"), TouchAction("tap_button", button_id="save"))
        self.assertTrue([op for op in display.ops if op[0] == "text" and op[1] == "q"])

    def test_name_editor_keyboard_background_does_not_fall_through_to_carousel(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_SET_LIST")

        renderer, _display = _render_touch_layout(ui)

        action = renderer.touch_layout.action_for_point(0.5, 0.98)
        self.assertEqual(action, TouchAction("noop"))

    def test_name_editor_keyboard_keeps_header_back_target(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_SET_LIST")

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="back_button", button_id="back"), TouchAction("tap_back", button_id="back"))

    def test_name_editor_text_field_uses_stable_text_origin(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "cxv", "GRAPH_SET_LIST")
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
        cxv_ops = [op for op in display.ops if op[0] == "text_line_color" and op[1] == "cxv"]
        self.assertTrue(cxv_ops)

        ui.state.name_editor_draft = "LX"
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))
        lx_ops = [op for op in display.ops if op[0] == "text_line_color" and op[1] == "LX"]
        self.assertTrue(lx_ops)
        self.assertEqual(cxv_ops[0][3], lx_ops[0][3])

    def test_name_editor_touch_keyboard_updates_draft_and_submits(self) -> None:
        ui = ShadowboxUI()
        ui._begin_name_editor("save_set", "/rnbo/inst/control/sets/save", "", "GRAPH_SET_LIST")

        ui.handle_event(UIEvent(kind="name_shift"))
        ui.handle_event(UIEvent(kind="tap_name_key", index=NAME_TOUCH_KEY_VALUES.index("a")))
        ui.handle_event(UIEvent(kind="tap_name_key", index=NAME_TOUCH_KEY_VALUES.index("b")))
        ui.handle_event(UIEvent(kind="name_space"))
        ui.handle_event(UIEvent(kind="tap_name_key", index=NAME_TOUCH_KEY_VALUES.index("c")))
        ui.handle_event(UIEvent(kind="name_backspace"))
        ui.handle_event(UIEvent(kind="name_keyboard_mode"))
        ui.handle_event(UIEvent(kind="tap_name_key", index=NAME_TOUCH_KEY_VALUES.index("1")))
        ui.handle_event(UIEvent(kind="name_backspace"))
        ui.handle_event(UIEvent(kind="tap_button", button_id="save"))

        actions = [action for action in ui.pop_actions() if action.kind != "save_state"]
        self.assertEqual(ui.state.name_editor_draft, "Ab")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "save_set")
        self.assertEqual(actions[0].value, "Ab")

    def test_step16_touch_targets_cover_the_grid(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "pattern", "value": 0b101, "path": "/params/pattern", "metadata": {"editor": "step16"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0b101
        ui.state.edit_step16_focus = 0

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="step16_cell", index=0), TouchAction("tap_step16", index=0))
        self.assertEqual(_touch_action_for_target(renderer, kind="step16_cell", index=15), TouchAction("tap_step16", index=15))
        cells = [target for target in renderer.touch_layout.targets if target.kind == "step16_cell"]
        self.assertEqual(len(cells), 16)
        self.assertEqual(len({target.x for target in cells}), 4)
        self.assertEqual(len({target.y for target in cells}), 4)

    def test_trigger_sequencer_alias_uses_step16_touch_editor(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "trigger sequencer", "value": 0, "path": "/params/triggers", "metadata": {"editor": "trigger sequencer"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_step16_focus = 0

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="step16_cell", index=3), TouchAction("tap_step16", index=3))

    def test_step16_touch_toggles_cell_and_moves_focus(self) -> None:
        ui = ShadowboxUI()
        param = {"name": "pattern", "value": 0, "path": "/params/pattern", "metadata": {"editor": "step16"}}
        ui.state.ui_mode = "EDIT"
        ui.state.instances = [{"id": "1", "params": [param]}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.edit_value = 0
        ui.state.edit_step16_focus = 0

        ui.handle_event(UIEvent(kind="tap_step16", index=5))

        self.assertEqual(ui.state.edit_step16_focus, 5)
        self.assertEqual(ui.state.edit_value, 1 << 5)
        self.assertEqual(param["value"], 1 << 5)
        actions = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].value, 1 << 5)

    def test_five_inch_renderer_records_hit_targets_and_page_indicator(self) -> None:
        class _FiveInchDisplay:
            width = 800
            height = 480

            def __init__(self) -> None:
                self.ops: list[tuple] = []

            def clear(self) -> None:
                pass

            def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
                self.ops.append(("text", text, x, y, scale, weight, on))

            def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
                return (len(str(text)) * 12 * max(1, scale), 16 * max(1, scale))

            def line_height(self, scale: int = 1, weight: str = "regular") -> int:
                return 16 * max(1, scale)

            def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
                self.ops.append(("rect", x, y, w, h, on, fill))

            def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
                self.ops.append(("hline", x, y, w, on))

            def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
                self.ops.append(("vline", x, y, h, on))

            def show(self) -> None:
                pass

        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [{"name": f"param/{idx}", "value": idx, "path": f"/p/{idx}"} for idx in range(10)],
            }
        ]
        ui.state.active_instance_id = "1"

        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        self.assertIsNotNone(renderer.touch_layout)
        kinds = [target.kind for target in renderer.touch_layout.targets]
        self.assertIn("header", kinds)
        self.assertIn("back_button", kinds)
        self.assertIn("content_area", kinds)
        self.assertIn("page_up", kinds)
        self.assertIn("page_down", kinds)
        self.assertGreaterEqual(sum(1 for kind in kinds if kind == "row"), 4)
        self.assertTrue(any(text == "1/3" for kind, text, *_rest in display.ops if kind == "text"))

    def test_touch_page_rail_visuals_are_inset_from_header(self) -> None:
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer._begin_touch_layout("PARAM_LIST")

        content_top = renderer.content_top
        renderer._draw_touch_page_rail(content_top, display.height, 1, 3)

        rail_surfaces = [op for op in display.ops if op[0] == "rounded_rect_color"]
        rail_surface = next(op for op in rail_surfaces if op[2] > content_top)
        up_arrow = next(op for op in display.ops if op[0] == "text_color" and op[1] == "^")

        self.assertGreater(rail_surface[2], content_top)
        self.assertGreater(up_arrow[3], content_top)

    def test_status_touch_rows_match_primary_list_layout(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "STATUS"
        ui.state.instances = [{"id": "1"}, {"id": "2"}]
        ui.state.system = {
            "status": {
                "cpu_load": 12.3,
                "xruns": 0,
                "runner_version": "1.2.3",
            }
        }

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        label = next(op for op in text_ops if op[1] == "Instances")
        value = next(op for op in text_ops if op[1] == "2")
        chevrons = [op for op in text_ops if op[1] == ">"]

        self.assertEqual(label[3], value[3])
        self.assertEqual(label[5], 3)
        self.assertEqual(value[5], 3)
        self.assertFalse(chevrons)
        self.assertFalse(any(op[0] == "text" and op[1] == "INSTANCES" for op in display.ops))

    def test_maint_touch_commands_render_as_buttons(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "MAINT"
        ui.state.system = {"maint": {"jack_restart_path": "/restart-jack"}}

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        refresh = next(op for op in text_ops if op[1] == "Refresh")
        restart = next(op for op in text_ops if op[1] == "Restart Jack")
        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        button_surfaces = [
            op
            for op in display.ops
            if op[0] == "rounded_rect_color"
            and op[7] is True
            and op[4] < 120
        ]

        self.assertEqual(refresh[5], 3)
        self.assertEqual(restart[5], 3)
        self.assertTrue(any(target.index == 1 and target.label == "Refresh" for target in row_targets))
        self.assertTrue(any(target.index == 2 and target.label == "Restart Jack" for target in row_targets))
        self.assertGreaterEqual(len(button_surfaces), 2)

    def test_five_inch_startup_hero_scales_typography_from_full_tft(self) -> None:
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)

        renderer.draw_startup_status("SHADOWBOX", "starting audio", "please wait")

        text_ops = [op for op in display.ops if op[0] == "text"]
        logo_ops = [op for op in text_ops if op[1] in {"SHADOW", "BOX"}]
        status = next(op for op in text_ops if op[1] == "starting audio")
        hint = next(op for op in text_ops if op[1] == "please wait")

        self.assertTrue(all(op[4] == 8 for op in logo_ops))
        self.assertEqual(status[4], 4)
        self.assertEqual(hint[4], 4)

    def test_five_inch_about_hero_scales_typography_from_full_tft(self) -> None:
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)

        renderer.draw_about()

        text_ops = [op for op in display.ops if op[0] == "text"]
        logo_ops = [op for op in text_ops if op[1] in {"SHADOW", "BOX"}]
        version = next(op for op in text_ops if op[1] not in {"SHADOW", "BOX"})

        self.assertTrue(all(op[4] == 6 for op in logo_ops))
        self.assertEqual(version[4], 2)

    def test_touch_hit_mapping_resolves_rows_back_and_page_rail(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [{"name": f"param/{idx}", "value": idx, "path": f"/p/{idx}"} for idx in range(10)],
            }
        ]
        ui.state.active_instance_id = "1"

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="row", index=1), TouchAction("tap_row", index=1))
        self.assertEqual(_touch_action_for_target(renderer, kind="back_button", button_id="back"), TouchAction("tap_back", button_id="back"))
        self.assertEqual(_touch_action_for_target(renderer, kind="page_up", button_id="page_up"), TouchAction("page_up", button_id="page_up"))
        self.assertEqual(_touch_action_for_target(renderer, kind="page_down", button_id="page_down"), TouchAction("page_down", button_id="page_down"))

    def test_parameter_list_touch_rows_use_list_style_value_and_chevron(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "gain", "value": 0.75, "path": "/params/gain"},
                    {"name": "mode", "value": "A", "path": "/params/mode"},
                ],
            }
        ]
        ui.state.active_instance_id = "1"

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        row_surfaces = [
            op
            for op in display.ops
            if op[0] == "rounded_rect_color"
            and any(op[1] == target.x and op[2] == target.y and op[3] == target.w and op[4] == target.h for target in row_targets)
        ]
        self.assertEqual(row_surfaces, [])

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        gain = next(op for op in text_ops if op[1] == "gain")
        value = next(op for op in text_ops if op[1] == "0.750")
        chevrons = [op for op in text_ops if op[1] == ">"]
        self.assertGreater(value[2], gain[2])
        self.assertGreaterEqual(len(chevrons), 2)
        self.assertGreater(chevrons[0][2], value[2])

    def test_parameter_list_touch_rows_show_midi_mapping_marker(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {
                        "name": "WaveBiasB",
                        "value": 1,
                        "path": "/params/WaveBiasB",
                        "metadata": {"midi": {"chan": 4, "ctrl": 28}},
                    },
                ],
            }
        ]
        ui.state.active_instance_id = "1"

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        labels = [op[1] for op in display.ops if op[0] == "text_color"]
        self.assertIn("WaveBiasB", labels)
        self.assertIn("4:28 ", labels)
        self.assertIn("1", labels)

        midi_text = next(op for op in display.ops if op[0] == "text_color" and op[1] == "4:28 ")
        value_text = next(op for op in display.ops if op[0] == "text_color" and op[1] == "1")
        self.assertNotEqual(midi_text[4], value_text[4])

    def test_parameter_list_touch_rows_allocate_space_by_measured_text(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {
                        "name": "group/ThisParameterNameIsQuiteLongButValueShort",
                        "value": 1,
                        "path": "/params/long-name",
                    },
                    {
                        "name": "gain",
                        "value": "ABCDEFGHIJKLMNOPQRSTUV",
                        "path": "/params/long-value",
                    },
                ],
            }
        ]
        ui.state.active_instance_id = "1"

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        long_label = next(op for op in text_ops if str(op[1]).startswith("g/ThisParam"))
        long_value = next(op for op in text_ops if str(op[1]).startswith("ABCDEFGH"))
        short_value = next(op for op in text_ops if op[1] == "1")
        short_label = next(op for op in text_ops if op[1] == "gain")

        self.assertLess(long_label[2], short_value[2])
        self.assertLess(short_label[2], long_value[2])

    def test_audio_and_midi_io_touch_rows_match_parameter_list_style(self) -> None:
        for mode in ("AUDIO_ROUTING_OVERVIEW", "MIDI_ROUTING_OVERVIEW"):
            display = _ColorFiveInchDisplay()
            renderer = create_renderer(display)
            renderer.set_touch_mode(True)
            renderer._begin_touch_layout(mode)

            renderer.draw_selectable_value_rows(
                [
                    ValueRow("Synth A", "I:C1-2 O:P1-2"),
                    ValueRow("Drums", "I:- O:P1-2"),
                ],
                1,
            )

            text_ops = [op for op in display.ops if op[0] == "text_color"]
            label = next(op for op in text_ops if op[1] == "Synth A")
            value = next(op for op in text_ops if str(op[1]).startswith("I:C1"))
            chevrons = [op for op in text_ops if op[1] == ">"]

            self.assertEqual(label[3], value[3])
            self.assertEqual(label[5], 3)
            self.assertEqual(value[5], 3)
            self.assertGreater(value[2], label[2])
            self.assertGreaterEqual(len(chevrons), 2)
            self.assertGreater(chevrons[0][2], value[2])

    def test_audio_and_midi_port_rows_match_parameter_list_style(self) -> None:
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer._begin_touch_layout("ROUTING_PORTS")

        renderer._draw_routing_list_tft(
            [
                {"name": "Main Input", "connections": ["system:capture_1"]},
                {"name": "Main Output", "connections": []},
            ],
            1,
        )

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        label = next(op for op in text_ops if op[1] == "Main Input")
        value = next(op for op in text_ops if str(op[1]).startswith("sy"))
        chevrons = [op for op in text_ops if op[1] == ">"]

        self.assertEqual(label[3], value[3])
        self.assertEqual(label[5], 3)
        self.assertEqual(value[5], 3)
        self.assertGreater(value[2], label[2])
        self.assertGreaterEqual(len(chevrons), 2)
        self.assertGreater(chevrons[0][2], value[2])

    def test_routing_targets_use_full_height_touch_rows_without_footer(self) -> None:
        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer._begin_touch_layout("ROUTING_TARGETS")

        renderer._draw_routing_targets_tft(
            {"connections": ["system:capture_1"]},
            ["..", "DISCONNECT", "system:capture_1", "system:capture_2"],
            1,
            current_indices={1},
        )

        text_ops = [op for op in display.ops if op[0] == "text_color"]
        target = next(op for op in text_ops if op[1] == "system:capture_1")
        disconnect = next(op for op in text_ops if op[1] == "Disconnect")
        chevrons = [op for op in text_ops if op[1] == ">"]
        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        buttons = [target for target in renderer.touch_layout.targets if target.kind == "modal_button"]

        self.assertEqual(target[5], 3)
        self.assertEqual(disconnect[5], 3)
        self.assertGreaterEqual(len(chevrons), 2)
        self.assertTrue(any(target.index == 2 and target.label == "system:capture_1" for target in row_targets))
        self.assertFalse(any(target.label == "Disconnect" for target in row_targets))
        self.assertTrue(any(target.button_id == "disconnect" for target in buttons))
        self.assertFalse(any(str(op[1]).startswith("CURRENT:") for op in display.ops if op[0] in {"text", "text_color"}))

    def test_routing_targets_remove_button_opens_remove_picker(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "ROUTING_TARGETS"
        ui.state.instances = [
            {
                "id": "1",
                "label": "Synth",
                "routing": {
                    "audio": {
                        "inputs": [
                            {
                                "name": "Main Input",
                                "path": "/rnbo/inst/1/audio/in/0",
                                "connections": ["system:capture_1"],
                                "targets": ["system:capture_1", "system:capture_2"],
                            }
                        ],
                        "outputs": [],
                    },
                    "midi": {"inputs": [], "outputs": []},
                },
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        ui.handle_event(UIEvent(kind="tap_button", button_id="remove"))

        actions = [action for action in ui.pop_actions() if action.kind == "set_routing"]
        self.assertEqual(actions, [])
        self.assertEqual(ui.state.ui_mode, "ROUTING_DISCONNECT_PICKER")
        self.assertEqual(ui.state.routing_disconnect_cursor, 1)

    def test_routing_assignment_touch_screen_shows_assignments_and_add_remove_buttons(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "ROUTING_TARGETS"
        ui.state.instances = [
            {
                "id": "1",
                "label": "Synth",
                "routing": {
                    "midi": {
                        "inputs": [
                            {
                                "name": "Midi Input",
                                "path": "/rnbo/inst/1/midi/in/0",
                                "connections": ["system:midi_a"],
                                "targets": ["system:midi_a", "system:midi_b"],
                            }
                        ],
                        "outputs": [],
                    },
                    "audio": {"inputs": [], "outputs": []},
                },
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "midi"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        labels = [op[1] for op in display.ops if op[0] == "text_color"]
        buttons = [target.button_id for target in renderer.touch_layout.targets if target.kind == "modal_button"]

        self.assertIn("system:midi_a", labels)
        self.assertIn("Add", labels)
        self.assertIn("Remove", labels)
        self.assertEqual(buttons, ["add", "remove"])

    def test_routing_disconnect_picker_removes_selected_connection(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "ROUTING_DISCONNECT_PICKER"
        ui.state.instances = [
            {
                "id": "1",
                "label": "Synth",
                "routing": {
                    "audio": {
                        "inputs": [
                            {
                                "name": "Main Input",
                                "path": "/rnbo/inst/1/audio/in/0",
                                "connections": ["system:capture_1", "system:capture_2"],
                                "targets": ["system:capture_1", "system:capture_2"],
                            }
                        ],
                        "outputs": [],
                    },
                    "midi": {"inputs": [], "outputs": []},
                },
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        ui.handle_event(UIEvent(kind="tap_row", index=1))

        actions = [action for action in ui.pop_actions() if action.kind == "set_routing"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].path, "/rnbo/inst/1/audio/in/0")
        self.assertEqual(actions[0].value, ["system:capture_2"])
        self.assertEqual(ui.state.ui_mode, "ROUTING_TARGETS")

    def test_routing_disconnect_picker_renders_connected_targets_as_actions(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "ROUTING_DISCONNECT_PICKER"
        ui.state.instances = [
            {
                "id": "1",
                "label": "Synth",
                "routing": {
                    "audio": {
                        "inputs": [
                            {
                                "name": "Main Input",
                                "path": "/rnbo/inst/1/audio/in/0",
                                "connections": ["system:capture_1", "system:capture_2"],
                                "targets": ["system:capture_1", "system:capture_2"],
                            }
                        ],
                        "outputs": [],
                    },
                    "midi": {"inputs": [], "outputs": []},
                },
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.active_transport = "audio"
        ui.state.active_routing_direction = "inputs"
        ui.state.routing_port_cursor = 1

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        row_targets = [target for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertTrue(any(target.index == 1 and target.label == "system:capture_1" for target in row_targets))
        self.assertTrue(any(target.index == 2 and target.label == "system:capture_2" for target in row_targets))
        self.assertTrue(any(op[0] == "rounded_rect_color" for op in display.ops))

    def test_modal_buttons_resolve_correctly(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "NAME_OVERWRITE_CONFIRM"
        ui.state.name_editor_draft = "StudioB"

        renderer, _display = _render_touch_layout(ui)

        self.assertEqual(_touch_action_for_target(renderer, kind="modal_button", button_id="cancel"), TouchAction("tap_button", button_id="cancel"))
        self.assertEqual(_touch_action_for_target(renderer, kind="modal_button", button_id="overwrite"), TouchAction("tap_button", button_id="overwrite"))

    def test_parameter_list_row_targets_carry_visible_labels(self) -> None:
        class _FiveInchDisplay:
            width = 800
            height = 480

            def __init__(self) -> None:
                self.ops: list[tuple] = []

            def clear(self) -> None:
                pass

            def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
                self.ops.append(("text", text, x, y, scale, weight, on))

            def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
                return (len(str(text)) * 12 * max(1, scale), 16 * max(1, scale))

            def line_height(self, scale: int = 1, weight: str = "regular") -> int:
                return 16 * max(1, scale)

            def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
                self.ops.append(("rect", x, y, w, h, on, fill))

            def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
                self.ops.append(("hline", x, y, w, on))

            def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
                self.ops.append(("vline", x, y, h, on))

            def show(self) -> None:
                pass

        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {"name": "enabled", "value": 0, "path": "/params/enabled", "metadata": {"bool": True}},
                    {"name": "mode", "value": "A", "path": "/params/mode", "vals": ["A", "B", "C"]},
                ],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1

        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        self.assertIsNotNone(renderer.touch_layout)
        row_labels = [target.label for target in renderer.touch_layout.targets if target.kind == "row"]
        self.assertIn("enabled", row_labels)
        self.assertIn("mode", row_labels)

    def test_pressed_touch_highlights_the_tapped_row_only_while_pressed(self) -> None:
        class _FiveInchDisplay:
            width = 800
            height = 480

            def __init__(self) -> None:
                self.ops: list[tuple] = []

            def clear(self) -> None:
                pass

            def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
                self.ops.append(("text", text, x, y, scale, weight, on))

            def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
                return (len(str(text)) * 12 * max(1, scale), 16 * max(1, scale))

            def line_height(self, scale: int = 1, weight: str = "regular") -> int:
                return 16 * max(1, scale)

            def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
                self.ops.append(("rect", x, y, w, h, on, fill))

            def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
                self.ops.append(("hline", x, y, w, on))

            def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
                self.ops.append(("vline", x, y, h, on))

            def show(self) -> None:
                pass

        ui = ShadowboxUI()
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.instances = [
            {
                "id": "1",
                "params": [{"name": f"param/{idx}", "value": idx, "path": f"/p/{idx}"} for idx in range(10)],
            }
        ]
        ui.state.active_instance_id = "1"

        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        layout_hint = renderer._touch_list_geometry(visible_rows=4)
        _, _, content_top, _, row_h, _, rows = layout_hint
        touch_y = (rows[0] / (display.height - 1))
        renderer.draw(
            ui,
            touch_state=SimpleNamespace(
                pressed=True,
                normalized_x=0.5,
                normalized_y=touch_y,
            ),
        )

        filled_rects = [op for op in display.ops if op[0] == "rect" and len(op) > 6 and op[6] is True]
        self.assertTrue(any(rect[1] >= 0 and rect[2] >= content_top for rect in filled_rects))

    def test_modal_confirm_screens_record_direct_button_targets(self) -> None:
        class _FiveInchDisplay:
            width = 800
            height = 480

            def __init__(self) -> None:
                self.ops: list[tuple] = []

            def clear(self) -> None:
                pass

            def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
                self.ops.append(("text", text, x, y, scale, weight, on))

            def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
                return (len(str(text)) * 12 * max(1, scale), 16 * max(1, scale))

            def line_height(self, scale: int = 1, weight: str = "regular") -> int:
                return 16 * max(1, scale)

            def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
                self.ops.append(("rect", x, y, w, h, on, fill))

            def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
                self.ops.append(("hline", x, y, w, on))

            def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
                self.ops.append(("vline", x, y, h, on))

            def show(self) -> None:
                pass

        ui = ShadowboxUI()
        ui.state.ui_mode = "NAME_OVERWRITE_CONFIRM"
        ui.state.name_editor_draft = "StudioB"

        display = _FiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        self.assertIsNotNone(renderer.touch_layout)
        modal_buttons = [target.button_id for target in renderer.touch_layout.targets if target.kind == "modal_button"]
        self.assertEqual(modal_buttons, ["cancel", "overwrite"])

    def test_modal_confirm_screen_uses_touch_card_and_large_buttons(self) -> None:
        class _ColorFiveInchDisplay(_FiveInchDisplay):
            def fill_rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
                self.ops.append(("fill_rect_color", x, y, w, h, color))

            def rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], fill: bool = False) -> None:
                self.ops.append(("rect_color", x, y, w, h, color, fill))

            def rounded_rect_color(
                self,
                x: int,
                y: int,
                w: int,
                h: int,
                radius: int,
                color: tuple[int, int, int],
                fill: bool = False,
            ) -> None:
                self.ops.append(("rounded_rect_color", x, y, w, h, radius, color, fill))

            def hline_color(self, x: int, y: int, w: int, color: tuple[int, int, int]) -> None:
                self.ops.append(("hline_color", x, y, w, color))

            def text_color(
                self,
                text: str,
                x: int,
                y: int,
                color: tuple[int, int, int],
                scale: int = 1,
                weight: str = "regular",
            ) -> None:
                self.ops.append(("text_color", text, x, y, color, scale, weight))

        ui = ShadowboxUI()
        ui.state.ui_mode = "NAME_OVERWRITE_CONFIRM"
        ui.state.name_editor_draft = "StudioB"

        display = _ColorFiveInchDisplay()
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui, touch_state=SimpleNamespace(pressed=False, normalized_x=0.0, normalized_y=0.0))

        card_ops = [
            op for op in display.ops if op[0] == "rounded_rect_color" and op[3] >= 700 and op[4] >= 260
        ]
        self.assertTrue(card_ops)
        button_ops = [
            op for op in display.ops if op[0] == "rounded_rect_color" and op[3] >= 180 and op[4] >= 48
        ]
        self.assertGreaterEqual(len(button_ops), 2)
        title_ops = [op for op in display.ops if op[0] == "text_color" and op[1] == "Overwrite?" and op[3] >= 80]
        self.assertTrue(title_ops)
        self.assertEqual(title_ops[0][5], 3)
        self.assertEqual(title_ops[0][6], "semibold")


if __name__ == "__main__":
    unittest.main()
