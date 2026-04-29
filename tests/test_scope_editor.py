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

from shadowbox.editors.scope import append_scope_samples, is_scope_param, normalize_scope_samples, scope_time_seconds
from shadowbox.renderer import ShadowboxRenderer
from shadowbox.rnbo import extract_meta_info
from shadowbox.ui import ShadowboxUI, UIEvent


class _ScopeDisplay:
    width = 128
    height = 64

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def text_with_style(self, text: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        self.ops.append(("text", text, x, y, scale, weight, on))

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 6 * scale, 8 * scale)

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * scale

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        self.ops.append(("pixel", x, y, on))

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        self.ops.append(("hline", x, y, w, on))

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        self.ops.append(("vline", x, y, h, on))

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        self.ops.append(("rect", x, y, w, h, on, fill))


class ScopeEditorTests(unittest.TestCase):
    def test_normalize_scope_samples_clips_numeric_inputs(self) -> None:
        self.assertEqual(normalize_scope_samples([-2, "-0.5", 0.25, 3, True, "bad"]), [-1.0, -0.5, 0.25, 1.0])

    def test_append_scope_samples_keeps_recent_values(self) -> None:
        self.assertEqual(append_scope_samples([0.1, 0.2], [0.3, 0.4], max_samples=3), [0.2, 0.3, 0.4])

    def test_scope_time_seconds_uses_sample_rate(self) -> None:
        self.assertAlmostEqual(scope_time_seconds(48, 48000), 0.001)
        self.assertIsNone(scope_time_seconds(48, 0))

    def test_scope_editor_accepts_title_case_display_name(self) -> None:
        self.assertTrue(is_scope_param({"metadata": {"editor": "Scope Display"}}))
        self.assertTrue(is_scope_param({"metadata": {"editor": "'Scope Display'"}}))

    def test_scope_text_meta_selects_scope_editor(self) -> None:
        node = {"CONTENTS": {"meta": {"VALUE": "scope"}}}

        self.assertEqual(extract_meta_info(node)["editor"], "scope")

    def test_scope_colon_meta_with_single_quotes_selects_scope_editor(self) -> None:
        node = {"CONTENTS": {"meta": {"VALUE": "editor: 'Scope Display'"}}}

        self.assertTrue(is_scope_param({"metadata": extract_meta_info(node)}))

    def test_scope_state_update_appends_visible_history(self) -> None:
        ui = ShadowboxUI()
        ui.state.instances = [
            {
                "id": "1",
                "params": [
                    {
                        "name": "SamplingRate",
                        "path": "/rnbo/inst/1/params/SamplingRate",
                        "value": 100.0,
                        "min": 1.0,
                        "max": 1000.0,
                        "metadata": {"editor": "scope"},
                    }
                ],
                "state": [{"name": "scope", "path": "/rnbo/inst/1/messages/out/scope", "value": 0.0, "metadata": {}}],
            }
        ]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"

        self.assertTrue(ui.apply_instance_state_update("1", "/rnbo/inst/1/messages/out/scope", [0.1, -0.2]))

        self.assertEqual(ui.state.edit_scope_samples, [0.1, -0.2])

    def test_scope_editor_turn_updates_sampling_rate_param(self) -> None:
        ui = ShadowboxUI()
        param = {
            "name": "SamplingRate",
            "path": "/rnbo/inst/1/params/SamplingRate",
            "value": 100.0,
            "min": 1.0,
            "max": 1000.0,
            "metadata": {"editor": "scope"},
        }
        ui.state.instances = [{"id": "1", "params": [param], "state": []}]
        ui.state.active_instance_id = "1"
        ui.state.param_cursor = 1
        ui.state.ui_mode = "EDIT"
        ui.state.edit_value = 100.0

        ui.handle_event(UIEvent("step", 1))

        self.assertGreater(param["value"], 100.0)
        self.assertTrue(any(action.kind == "set_param" and action.path == param["path"] for action in ui.pop_actions()))

    def test_renderer_draws_scope_pixels_and_time_label(self) -> None:
        display = _ScopeDisplay()
        renderer = ShadowboxRenderer(display)
        state = SimpleNamespace(edit_scope_samples=[-1.0, 0.0, 1.0], edit_value=3.0)

        renderer.draw_edit_scope(SimpleNamespace(), {"metadata": {"editor": "scope"}, "value": 3.0}, state)

        self.assertTrue(any(op[0] == "pixel" for op in display.ops))
        self.assertTrue(any(op[0] == "text" and "1.000s" in op[1] for op in display.ops))


if __name__ == "__main__":
    unittest.main()
