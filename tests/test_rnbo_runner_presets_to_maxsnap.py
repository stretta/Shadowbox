import unittest

from tools.rnbo_runner_presets_to_maxsnap import (
    build_maxsnap,
    collect_params,
    param_value_for_snapshot,
)


class RunnerPresetToMaxsnapTests(unittest.TestCase):
    def test_string_enum_values_become_indices(self) -> None:
        node = {"TYPE": "s", "VALUE": "On", "RANGE": [{"VALS": ["Off", "On"]}]}

        self.assertEqual(param_value_for_snapshot(node), 1.0)

    def test_collect_params_walks_nested_nodes(self) -> None:
        params_root = {
            "CONTENTS": {
                "Volume": {"TYPE": "f", "VALUE": -6.0, "CONTENTS": {"index": {"VALUE": 0}}},
                "Voice": {
                    "CONTENTS": {
                        "Rate": {"TYPE": "f", "VALUE": 2.5, "CONTENTS": {"index": {"VALUE": 1}}},
                    }
                },
            }
        }

        self.assertEqual(collect_params(params_root), {("Volume",): -6.0, ("Voice", "Rate"): 2.5})

    def test_build_maxsnap_preserves_template_missing_values(self) -> None:
        template = {
            "snapshot": {
                "__presetid": "Poland",
                "__sps": {"poly": [{}, {}]},
                "Spread": {"value": 50.0},
                "VolA": {"value": 0.0},
            }
        }

        out = build_maxsnap(template, "Poland", "Bright", {("VolA",): -12.0})

        self.assertEqual(out["type"], "rnbo")
        self.assertEqual(out["name"], "Bright")
        self.assertEqual(out["origin"], "Poland")
        self.assertEqual(out["snapshot"]["__presetid"], "Poland")
        self.assertEqual(out["snapshot"]["__sps"], {"poly": [{}, {}]})
        self.assertEqual(out["snapshot"]["Spread"], {"value": 50.0})
        self.assertEqual(out["snapshot"]["VolA"], {"value": -12.0})


if __name__ == "__main__":
    unittest.main()
