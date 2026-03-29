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

from shadowbox.renderer import ShadowboxRenderer, format_param_value
from shadowbox.rnbo import extract_meta_info
from shadowbox.ui import ShadowboxUI, apply_edit_delta, edit_as_int, is_boolish, normalize_current_value_for_edit, numeric_step


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


class ParamMetadataTests(unittest.TestCase):
    def test_numeric_step_prefers_metadata_edit_step(self) -> None:
        param = {"type": "f", "min": 0, "max": 100, "metadata": {"edit_step": 2.5}}
        self.assertEqual(numeric_step(param), 2.5)

    def test_normalize_current_value_for_edit_coerces_integer_style(self) -> None:
        param = {"type": "f", "value": 7.6, "metadata": {"edit_as": "int"}}
        self.assertEqual(normalize_current_value_for_edit(param), 8)

    def test_apply_edit_delta_uses_integer_style_and_edit_step(self) -> None:
        param = {"type": "f", "min": 0, "max": 10, "metadata": {"edit_as": "int", "edit_step": 1}}
        self.assertEqual(apply_edit_delta(param, 2.2, 1), 3)
        self.assertEqual(apply_edit_delta(param, 2.2, -1), 1)

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

    def test_format_param_value_uses_display_precision(self) -> None:
        param = {"metadata": {"display_precision": 2}}
        self.assertEqual(format_param_value(param, 1.234), "1.23")

    def test_format_param_value_uses_integer_display_hint(self) -> None:
        param = {"metadata": {"display_as": "int"}}
        self.assertEqual(format_param_value(param, 3.7), "4")

    def test_format_param_value_appends_units_after_precision_formatting(self) -> None:
        param = {"metadata": {"display_precision": 1, "unit": "Hz"}}
        self.assertEqual(format_param_value(param, 42.34), "42.3Hz")

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


if __name__ == "__main__":
    unittest.main()
