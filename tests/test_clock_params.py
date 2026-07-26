import sys
import types
import unittest


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import shorten_param_name
from shadowbox.surfaces.analog_sequencer import resolve_analog_sequencer_bindings
from shadowbox.surfaces.clock import resolve_clock_bindings


def _param(name: str, *, value=0.0) -> dict:
    return {
        "name": name,
        "path": f"/rnbo/inst/7/params/{name}",
        "value": value,
        "metadata": {},
    }


def _grouped_clock_params() -> list[dict]:
    return [
        _param("Clock/Clock", value="On"),
        _param("Clock/Swing", value="Off"),
        _param("Clock/ClockInterval", value=240.0),
        _param("Clock/SwingAmt", value=0.5),
    ]


def _analog_instance() -> dict:
    params = []
    for stage in range(1, 17):
        params.append(_param(f"{stage:02d}StageValue", value=60.0))
        params.append(_param(f"{stage:02d}StageStep", value=1.0))
    params.extend([_param("MaxCnt", value="16"), *_grouped_clock_params()])
    return {
        "id": "7",
        "name": "AnalogSequencer",
        "params": params,
        "state": [
            {
                "name": "current_stage",
                "path": "/rnbo/inst/7/messages/out/current_stage",
                "value": [0.0],
            }
        ],
    }


class ClockParameterTests(unittest.TestCase):
    def test_grouped_clock_contract_binds_all_semantic_children(self) -> None:
        bindings = resolve_clock_bindings(_grouped_clock_params())

        self.assertIsNotNone(bindings)
        self.assertEqual(tuple(bindings), ("clock", "swing", "clockinterval", "swingamt"))
        self.assertEqual(bindings["clock"]["path"], "/rnbo/inst/7/params/Clock/Clock")
        self.assertEqual(bindings["clockinterval"]["path"], "/rnbo/inst/7/params/Clock/ClockInterval")

    def test_clock_binding_rejects_missing_child(self) -> None:
        params = [param for param in _grouped_clock_params() if param["name"] != "Clock/SwingAmt"]

        self.assertIsNone(resolve_clock_bindings(params))

    def test_clock_binding_rejects_legacy_and_grouped_duplicate(self) -> None:
        params = [*_grouped_clock_params(), _param("Clock", value="On")]

        self.assertIsNone(resolve_clock_bindings(params))

    def test_analog_surface_resolves_grouped_clock_export(self) -> None:
        resolved = resolve_analog_sequencer_bindings(_analog_instance())

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.params["clock"]["name"], "Clock/Clock")
        self.assertEqual(resolved.params["clockinterval"]["name"], "Clock/ClockInterval")
        self.assertEqual(resolved.params["swing"]["name"], "Clock/Swing")
        self.assertEqual(resolved.params["swingamt"]["name"], "Clock/SwingAmt")

    def test_clock_group_uses_clean_leaf_labels(self) -> None:
        self.assertEqual(shorten_param_name("Clock/Clock"), "Clock")
        self.assertEqual(shorten_param_name("Clock/ClockInterval"), "ClockInterval")
        self.assertEqual(shorten_param_name("Oscillator/Shape"), "O/Shape")


if __name__ == "__main__":
    unittest.main()
