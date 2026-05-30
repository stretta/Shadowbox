import json
import tempfile
import unittest
from pathlib import Path

from shadowbox.midi_mappings import (
    apply_midi_profile_to_instance,
    collect_instance_midi_mappings,
    mapping_profile_for_instance,
    save_instance_midi_profile,
)


class _FakeRNBO:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    def send_value(self, path: str, value: object) -> None:
        self.sent.append((path, value))


class MidiMappingProfileTests(unittest.TestCase):
    def test_collect_instance_midi_mappings_uses_parameter_names(self) -> None:
        instance = {
            "name": "Poland",
            "params": [
                {"name": "WaveBiasA", "metadata": {"midi": {"chan": 4.0, "ctrl": 16.0}}},
                {"name": "WaveModVelA", "metadata": {}},
                {"name": "WaveBiasB", "metadata": {"midi": {"chan": "4", "ctrl": "28"}}},
            ],
        }

        self.assertEqual(
            collect_instance_midi_mappings(instance),
            {
                "WaveBiasA": {"chan": 4, "ctrl": 16},
                "WaveBiasB": {"chan": 4, "ctrl": 28},
            },
        )

    def test_save_and_load_instance_midi_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "midi_mappings.json"
            instance = {
                "name": "Poland",
                "params": [
                    {"name": "WaveBiasA", "metadata": {"midi": {"chan": 4, "ctrl": 16}}},
                ],
            }

            self.assertEqual(save_instance_midi_profile(instance, path), 1)

            self.assertEqual(mapping_profile_for_instance({"name": "Poland"}, path), {"WaveBiasA": {"chan": 4, "ctrl": 16}})

    def test_apply_midi_profile_merges_with_current_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "midi_mappings.json"
            old_instance = {
                "name": "Poland",
                "params": [
                    {"name": "WaveBiasA", "metadata": {"midi": {"chan": 4, "ctrl": 16}}},
                ],
            }
            new_instance = {
                "name": "Poland",
                "params": [
                    {
                        "name": "WaveBiasA",
                        "path": "/rnbo/inst/8/params/WaveBiasA",
                        "metadata": {"display_precision": "0", "edit_as": "int"},
                    },
                    {
                        "name": "Unmapped",
                        "path": "/rnbo/inst/8/params/Unmapped",
                        "metadata": {},
                    },
                ],
            }
            rnbo = _FakeRNBO()
            save_instance_midi_profile(old_instance, path)

            self.assertEqual(apply_midi_profile_to_instance(new_instance, rnbo, path), 1)

            self.assertEqual(len(rnbo.sent), 1)
            self.assertEqual(rnbo.sent[0][0], "/rnbo/inst/8/params/WaveBiasA/meta")
            self.assertEqual(
                json.loads(str(rnbo.sent[0][1])),
                {
                    "display_precision": "0",
                    "edit_as": "int",
                    "midi": {"chan": 4, "ctrl": 16},
                },
            )

    def test_boolish_midi_mappings_are_preserved_for_future_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "midi_mappings.json"
            old_instance = {
                "name": "Poland",
                "params": [
                    {"name": "ModEnvLoopA", "metadata": {"midi": {"chan": 2, "ctrl": 20}}},
                ],
            }
            new_instance = {
                "name": "Poland",
                "params": [
                    {
                        "name": "ModEnvLoopA",
                        "path": "/rnbo/inst/8/params/ModEnvLoopA",
                        "metadata": {},
                        "vals": ["Off", "On"],
                    },
                ],
            }
            rnbo = _FakeRNBO()
            save_instance_midi_profile(old_instance, path)

            self.assertEqual(mapping_profile_for_instance({"name": "Poland"}, path), {"ModEnvLoopA": {"chan": 2, "ctrl": 20}})
            self.assertEqual(apply_midi_profile_to_instance(new_instance, rnbo, path), 1)
            self.assertEqual(rnbo.sent[0][0], "/rnbo/inst/8/params/ModEnvLoopA/meta")
            self.assertEqual(json.loads(str(rnbo.sent[0][1])), {"midi": {"chan": 2, "ctrl": 20}})


if __name__ == "__main__":
    unittest.main()
