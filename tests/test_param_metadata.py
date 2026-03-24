import sys
import types
import unittest


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import format_param_value
from shadowbox.ui import apply_edit_delta, normalize_current_value_for_edit, numeric_step


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

    def test_format_param_value_uses_display_precision(self) -> None:
        param = {"metadata": {"display_precision": 2}}
        self.assertEqual(format_param_value(param, 1.234), "1.23")

    def test_format_param_value_uses_integer_display_hint(self) -> None:
        param = {"metadata": {"display_as": "int"}}
        self.assertEqual(format_param_value(param, 3.7), "4")

    def test_format_param_value_appends_units_after_precision_formatting(self) -> None:
        param = {"metadata": {"display_precision": 1, "unit": "Hz"}}
        self.assertEqual(format_param_value(param, 42.34), "42.3Hz")


if __name__ == "__main__":
    unittest.main()
