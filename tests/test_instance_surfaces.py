import sys
import types
import unittest
from types import SimpleNamespace


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.render_scheduler import RenderScheduler
from shadowbox.renderer import ShadowboxRenderer
from shadowbox.surfaces import resolve_instance_surface
from shadowbox.surfaces.list_sequencer import FIELD_KEYS
from shadowbox.surfaces.organ import FOOTAGES
from shadowbox.touch import TouchLayout
from shadowbox.ui import ShadowboxUI, UIEvent


def _param(name, *, value=0.0, minimum=0.0, maximum=1.0, metadata=None):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/params/{name}",
        "value": value,
        "min": minimum,
        "max": maximum,
        "metadata": dict(metadata or {}),
    }


def _state(name, value=0.0):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/messages/out/{name}",
        "value": value,
        "metadata": {},
    }


def _scope_instance():
    return {
        "id": "7",
        "name": "TimeDomainScope",
        "label": "MY SCOPE",
        "params": [_param("SamplingRate", value=48.0, minimum=10.0, maximum=100.0, metadata={"editor": "Scope Display"})],
        "state": [_state("scope", [0.1, -0.1])],
    }


def _analog_instance():
    params = []
    for stage in range(1, 17):
        params.append(_param(f"{stage:02d}StageValue", value=60.0, minimum=0.0, maximum=127.0))
        params.append(_param(f"{stage:02d}StageStep", value=1.0, minimum=0.0, maximum=1.0))
    params.extend([_param("MaxCnt", value="16"), _param("Clock", value=1.0)])
    return {
        "id": "7",
        "name": "AnalogSequencer",
        "label": "RENAMED",
        "params": params,
        "state": [_state("current_stage", [3.0])],
    }


def _organ_instance():
    names = ["Bass", "Quint", "Neutral", "Octave", "Nazard", "Block-flute", "Tierce", "Larigot", "Sifflute"]
    return {
        "id": "7",
        "name": "Organ",
        "label": "DRAWBARS",
        "params": [_param(name, value=-96.0, minimum=-96.0, maximum=0.0) for name in names],
        "state": [],
    }


def _tuner_instance():
    return {
        "id": "7",
        "name": "Tuner",
        "label": "Tuner",
        "params": [
            _param("Tuner", value=0.0, minimum=0.0, maximum=1.0, metadata={"editor": "pitch_display"}),
            _param("Smooth", value=0.0, minimum=0.0, maximum=100.0),
            _param("NoiseThreshold", value=0.0, minimum=0.0, maximum=100.0),
        ],
        "state": [_state("pitch_name", []), _state("pitch_cents", [])],
    }


def _live_organ_instance():
    instance = _organ_instance()
    for param in instance["params"]:
        param["name"] = f"Tonewheel/{param['name']}"
        param["path"] = f"/rnbo/inst/7/params/{param['name']}"
    return instance


def _list_input(name):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/messages/in/{name}",
        "metadata": {},
    }


def _list_sequencer_instance():
    names = ["Steps", "StepsSecondary", "PrimaryRotation", "SecondaryRotation", "Oct", "Velocity", "Duration"]
    return {
        "id": "7",
        "name": "ListSequencer",
        "label": "LISTS",
        "params": [],
        "inputs": [_list_input(name) for name in names],
        "state": [_state(f"{name}Ack", [0.0, 1.0] if name == "Steps" else [1.0, 2.0]) for name in names],
    }


def _snapshot(instances):
    return SimpleNamespace(
        instances=instances,
        patchers=[],
        add_instance_path="",
        remove_instance_path="",
        system={},
    )


class _SurfaceDisplay:
    width = 800
    height = 480

    def __init__(self):
        self.ops = []

    def clear(self):
        pass

    def show(self):
        pass

    def measure_text(self, text, scale=1, weight="regular"):
        return len(str(text)) * 8 * scale, 12 * scale

    def line_height(self, scale=1, weight="regular"):
        return 12 * scale

    def text_with_style(self, *args, **kwargs):
        self.ops.append(("text", *args))

    def text_color(self, *args, **kwargs):
        self.ops.append(("text_color", *args))

    def text_line_color(self, *args, **kwargs):
        self.ops.append(("text_line_color", *args))

    def rect(self, *args, **kwargs):
        self.ops.append(("rect", *args))

    def hline(self, *args, **kwargs):
        self.ops.append(("hline", *args))

    def vline(self, *args, **kwargs):
        self.ops.append(("vline", *args))

    def fill_rect_color(self, *args, **kwargs):
        self.ops.append(("fill_rect_color", *args))

    def rect_color(self, *args, **kwargs):
        self.ops.append(("rect_color", *args))

    def rounded_rect_color(self, *args, **kwargs):
        self.ops.append(("rounded_rect_color", *args))

    def hline_color(self, *args, **kwargs):
        self.ops.append(("hline_color", *args))


class InstanceSurfaceTests(unittest.TestCase):
    def test_resolution_uses_export_name_not_label(self):
        instance = _scope_instance()
        instance["label"] = "Tuner"
        resolved = resolve_instance_surface(instance)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "time_domain_scope")

    def test_missing_scope_state_rejects_surface(self):
        instance = _scope_instance()
        instance["state"] = []
        self.assertIsNone(resolve_instance_surface(instance))

    def test_live_tuner_contract_resolves_pitch_and_cents(self):
        resolved = resolve_instance_surface(_tuner_instance())
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "tuner")
        self.assertEqual(resolved[1].params["anchor"]["name"], "Tuner")
        self.assertEqual(resolved[1].state["pitch"]["name"], "pitch_name")
        self.assertEqual(resolved[1].state["cents"]["name"], "pitch_cents")

    def test_current_wren_organ_db_contract_resolves_canonically(self):
        resolved = resolve_instance_surface(_live_organ_instance())
        self.assertIsNotNone(resolved)
        self.assertEqual(tuple(resolved[1].params), FOOTAGES)
        self.assertEqual(resolved[1].params["16"]["name"], "Tonewheel/Bass")
        self.assertEqual(resolved[1].params["1"]["name"], "Tonewheel/Sifflute")

    def test_planned_organ_contract_resolves_in_canonical_order(self):
        names = ["Drawbar1", "Drawbar1_1_3", "Drawbar16", "Drawbar2", "Drawbar8", "Drawbar5_1_3", "Drawbar4", "Drawbar2_2_3", "Drawbar1_3_5"]
        instance = {
            "id": "7",
            "name": "Organ",
            "params": [_param(name, minimum=0, maximum=8) for name in names],
            "state": [],
        }
        resolved = resolve_instance_surface(instance)
        self.assertEqual(tuple(resolved[1].params), FOOTAGES)

    def test_surface_menu_opens_without_modifying_param_cursor(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.state.param_cursor = 9
        self.assertEqual(ui.instance_menu_items[0], "TIME DOMAIN SCOPE")

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_SURFACE")
        self.assertEqual(ui.state.active_surface_key, "time_domain_scope")
        self.assertEqual(ui.state.param_cursor, 9)
        self.assertEqual(ui.state.edit_scope_samples, [0.1, -0.1])

    def test_back_returns_to_instance_menu(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("long_press"))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")
        self.assertEqual(ui.state.active_surface_key, "")

    def test_incompatible_refresh_closes_surface(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        incompatible = _scope_instance()
        incompatible["state"] = []

        ui.apply_runner_snapshot(_snapshot([incompatible]))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")

    def test_scope_surface_refresh_preserves_history(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.state.edit_scope_samples = [0.5, 0.25]

        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))

        self.assertEqual(ui.state.edit_scope_samples, [0.5, 0.25])

    def test_surface_frame_rates(self):
        ui = ShadowboxUI()
        for instance, expected in ((_scope_instance(), 15.0), (_analog_instance(), 20.0)):
            ui.apply_runner_snapshot(_snapshot([instance]))
            ui.state.ui_mode = "INSTANCE_MENU"
            ui.state.instance_menu_cursor = 1
            ui.handle_event(UIEvent("short_press"))
            self.assertEqual(RenderScheduler.frame_rate(ui), expected)
            ui._exit_instance_surface()

    def test_list_sequencer_resolves_ordered_osc_inports(self):
        resolved = resolve_instance_surface(_list_sequencer_instance())

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "list_sequencer")
        self.assertEqual(tuple(resolved[1].inputs), FIELD_KEYS)
        self.assertEqual(resolved[1].inputs["steps_secondary"]["name"], "StepsSecondary")
        self.assertEqual(resolved[1].state["duration_ack"]["name"], "DurationAck")

    def test_list_sequencer_rejects_missing_required_inport(self):
        instance = _list_sequencer_instance()
        instance["inputs"] = [item for item in instance["inputs"] if item["name"] != "Duration"]

        self.assertIsNone(resolve_instance_surface(instance))

    def test_list_sequencer_open_reads_ack_fields_and_hydrates_drafts(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.active_surface_key, "list_sequencer")
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "0 1")
        reads = [action for action in ui.pop_actions() if action.kind == "send_osc"]
        self.assertEqual(len(reads), len(FIELD_KEYS))
        self.assertTrue(all(action.value == [-999] for action in reads))

    def test_list_sequencer_keypad_sends_complete_numeric_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["steps"] = ""

        for key in ("1", "space", "0", "space", "1"):
            ui.handle_event(UIEvent("edit_list_key", button_id=key))
        ui.handle_event(UIEvent("send_list_field"))

        writes = [action for action in ui.pop_actions() if action.kind == "send_osc"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].path, "/rnbo/inst/7/messages/in/Steps")
        self.assertEqual(writes[0].value, [1, 0, 1])

    def test_list_sequencer_signed_field_uses_contextual_sign(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.handle_event(UIEvent("select_list_field", index=2))
        ui.state.surface_state["drafts"]["primary_rotation"] = ""

        ui.handle_event(UIEvent("toggle_list_sign"))
        ui.handle_event(UIEvent("edit_list_key", button_id="6"))
        ui.handle_event(UIEvent("edit_list_key", button_id="0"))
        ui.handle_event(UIEvent("send_list_field"))

        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.value, [-60])

    def test_list_sequencer_keypad_field_steps_are_surface_scoped(self):
        ui = ShadowboxUI()
        ui.handle_event(UIEvent("step_list_field", delta=1))
        self.assertEqual(ui.state.surface_focus, 0)

        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.handle_event(UIEvent("step_list_field", delta=1))
        self.assertEqual(ui.state.surface_focus, 1)
        ui.handle_event(UIEvent("step_list_field", delta=-1))
        self.assertEqual(ui.state.surface_focus, 0)

    def test_context_neutral_keypad_events_retain_list_sequencer_behavior(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui._list_surface_drafts()["steps"] = ""

        ui.handle_event(UIEvent("keypad_digit", button_id="1"))
        ui.handle_event(UIEvent("keypad_space"))
        ui.handle_event(UIEvent("keypad_digit", button_id="0"))
        ui.handle_event(UIEvent("keypad_decimal"))
        ui.handle_event(UIEvent("keypad_digit", button_id="1"))
        ui.handle_event(UIEvent("keypad_enter"))

        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.value, [1, 1])

    def test_list_sequencer_steps_reject_non_binary_values(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["steps"] = "0 2"

        ui.handle_event(UIEvent("send_list_field"))

        self.assertEqual([action for action in ui.pop_actions() if action.kind == "send_osc"], [])
        self.assertEqual(ui.state.status_message, "INVALID LIST")

    def test_list_sequencer_ack_updates_clean_but_not_dirty_draft(self):
        ui = ShadowboxUI()
        instance = _list_sequencer_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        steps_ack = next(item for item in instance["state"] if item["name"] == "StepsAck")

        self.assertTrue(ui.apply_instance_state_update("7", steps_ack["path"], [1, 1, 0]))
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "1 1 0")
        ui.handle_event(UIEvent("edit_list_key", button_id="1"))
        self.assertTrue(ui.apply_instance_state_update("7", steps_ack["path"], [0]))
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "1 1 01")

    def test_list_sequencer_surface_renders_seven_fields_and_twelve_keys(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        fields = [target for target in renderer.touch_layout.targets if target.kind == "list_field"]
        keys = [target for target in renderer.touch_layout.targets if target.kind == "list_key"]
        sends = [target for target in renderer.touch_layout.targets if target.kind == "list_send"]
        self.assertEqual(len(fields), 7)
        self.assertEqual(len(keys), 12)
        self.assertEqual(len(sends), 1)
        self.assertEqual([target.label for target in fields], [
            "Stp",
            "Stp2",
            "Rot",
            "Rot2",
            "Oct",
            "Vel",
            "Dur",
        ])
        self.assertFalse(any(target.kind == "list_sign" for target in renderer.touch_layout.targets))

        ui.handle_event(UIEvent("select_list_field", index=2))
        renderer.draw(ui)

        signs = [target for target in renderer.touch_layout.targets if target.kind == "list_sign"]
        self.assertEqual(len(signs), 1)
        self.assertEqual(signs[0].action_kind, "toggle_list_sign")

    def test_analog_touch_updates_stage_and_toggle(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_analog_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("set_surface_value", index=2, value=0.5, pressed=True))
        ui.handle_event(UIEvent("toggle_surface_value", index=2))

        self.assertAlmostEqual(ui.surface_param_binding("stage_03_value")["value"], 63.5)
        self.assertEqual(ui.surface_param_binding("stage_03_enabled")["value"], 0)
        writes = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(writes), 2)

    def test_analog_surface_renders_sixteen_touch_targets(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_analog_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        targets = [target for target in renderer.touch_layout.targets if target.kind == "analog_stage_value"]
        toggles = [target for target in renderer.touch_layout.targets if target.kind == "analog_stage_toggle"]
        self.assertEqual(len(targets), 16)
        self.assertEqual(len(toggles), 16)
        self.assertTrue(all(not target.label for target in targets + toggles))
        rendered_text = [op[1] for op in renderer.display.ops if op[0] in {"text", "text_color"}]
        self.assertNotIn("STAGES", rendered_text)
        self.assertFalse(any(text in {str(index) for index in range(1, 17)} for text in rendered_text))
        self.assertTrue(all(toggle.h <= 34 for toggle in toggles))

    def test_organ_touch_maps_top_to_minus_96_and_bottom_to_zero(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_organ_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("set_surface_value", index=0, value=0.0, pressed=True))
        self.assertEqual(ui.surface_param_binding("16")["value"], -96.0)
        ui.handle_event(UIEvent("set_surface_value", index=0, value=1.0, pressed=False))
        self.assertEqual(ui.surface_param_binding("16")["value"], 0.0)

    def test_organ_encoder_selects_then_adjusts_in_one_db_steps(self):
        ui = ShadowboxUI()
        instance = _organ_instance()
        instance["params"][0]["value"] = -48.0
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("step", 1))
        self.assertEqual(ui.state.surface_focus, 1)
        ui.handle_event(UIEvent("short_press"))
        ui.handle_event(UIEvent("step", 1))

        self.assertEqual(ui.surface_param_binding("5_1_3")["value"], -95.0)

    def test_organ_surface_renders_nine_vertical_touch_targets(self):
        ui = ShadowboxUI()
        instance = _organ_instance()
        next(param for param in instance["params"] if param["name"] == "Nazard")["value"] = 0.0
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        targets = [target for target in renderer.touch_layout.targets if target.kind == "organ_drawbar"]
        self.assertEqual(len(targets), 9)
        self.assertTrue(all(target.button_id == "organ_drawbar" for target in targets))
        self.assertLess(targets[0].x, 50)
        self.assertTrue(
            any(op[0] == "fill_rect_color" and op[-1] == (128, 128, 128) for op in renderer.display.ops)
        )

    def test_vertical_surface_target_maps_top_to_one(self):
        layout = TouchLayout(800, 480)
        layout.add_target("stage", 100, 100, 40, 200, action_kind="set_surface_value", index=3)
        top = layout.action_for_point(120 / 799, 100 / 479)
        bottom = layout.action_for_point(120 / 799, 299 / 479)
        self.assertAlmostEqual(top.value, 1.0)
        self.assertAlmostEqual(bottom.value, 0.0)

    def test_organ_vertical_target_maps_top_to_zero(self):
        layout = TouchLayout(800, 480)
        layout.add_target(
            "drawbar",
            100,
            100,
            40,
            200,
            action_kind="set_surface_value",
            index=3,
            button_id="organ_drawbar",
        )
        top = layout.action_for_point(120 / 799, 100 / 479)
        bottom = layout.action_for_point(120 / 799, 299 / 479)
        self.assertAlmostEqual(top.value, 0.0)
        self.assertAlmostEqual(bottom.value, 1.0)

    def test_step16_metadata_remains_parameter_scoped(self):
        instance = {
            "id": "7",
            "name": "SimpleSequencer",
            "params": [_param("steps", metadata={"editor": "step16"})],
            "state": [],
        }
        self.assertIsNone(resolve_instance_surface(instance))

    def test_scope_metadata_no_longer_dispatches_from_parameter_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "EDIT")
        self.assertEqual(ui.state.edit_value, 48.0)
        self.assertEqual(ui.state.edit_scope_samples, [])
        self.assertIsNone(RenderScheduler.frame_rate(ui))

    def test_tuner_metadata_no_longer_dispatches_from_parameter_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_tuner_instance()]))
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "EDIT")
        self.assertEqual(ui.state.edit_value, 0.0)
        self.assertIsNone(RenderScheduler.frame_rate(ui))


if __name__ == "__main__":
    unittest.main()
