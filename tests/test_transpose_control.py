from __future__ import annotations

import unittest

from shadowbox.transpose_control import (
    ROLE_CHROMATIC,
    ROLE_SCALAR,
    MidiInputPort,
    common_target_range,
    note_to_offset,
    parse_aconnect_inputs,
    parse_aseqdump_note_on,
    target_status,
    transpose_targets,
)


class TransposeControlTests(unittest.TestCase):
    def test_aconnect_parser_uses_stable_names_and_ignores_system_ports(self) -> None:
        ports = parse_aconnect_inputs(
            """client 0: 'System' [type=kernel]
    0 'Timer           '
client 14: 'Midi Through' [type=kernel]
    0 'Midi Through Port-0'
client 24: 'KeyStep 37' [type=kernel,card=2]
    0 'KeyStep 37 MIDI 1'
client 31: 'Launch Control XL' [type=kernel,card=3]
    1 'Launch Control XL DAW'
"""
        )
        self.assertEqual(
            [(port.client_name, port.port_name, port.address) for port in ports],
            [
                ("KeyStep 37", "KeyStep 37 MIDI 1", "24:0"),
                ("Launch Control XL", "Launch Control XL DAW", "31:1"),
            ],
        )
        self.assertEqual(ports[0].identity, "KeyStep 37\0KeyStep 37 MIDI 1")

    def test_aseqdump_parser_accepts_positive_velocity_note_on_only(self) -> None:
        port = MidiInputPort("KeyStep 37", "MIDI 1", "24:0")
        event = parse_aseqdump_note_on(" 24:0   Note on                 2, note 60, velocity 99", port)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual((event.channel, event.note, event.velocity), (2, 60, 99))
        self.assertIsNone(parse_aseqdump_note_on(" 24:0   Note on                 2, note 60, velocity 0", port))
        self.assertIsNone(parse_aseqdump_note_on(" 24:0   Note off                2, note 60, velocity 0", port))

    def test_middle_c_is_neutral_absolute_offset(self) -> None:
        self.assertEqual(note_to_offset(59), -1)
        self.assertEqual(note_to_offset(60), 0)
        self.assertEqual(note_to_offset(61), 1)

    def test_target_discovery_requires_exact_standard_parameter_name(self) -> None:
        instances = [
            {
                "id": "1",
                "name": "Voice",
                "params": [
                    {"name": "ChromaticTranspose", "path": "/rnbo/inst/1/params/ChromaticTranspose", "value": 0, "min": -12, "max": 12},
                    {"name": "chromatictranspose", "path": "/wrong", "value": 0},
                    {"name": "ScalarTranspose", "path": "/rnbo/inst/1/params/ScalarTranspose", "value": 2, "min": -7, "max": 7},
                ],
            }
        ]
        chromatic = transpose_targets(instances, ROLE_CHROMATIC)
        scalar = transpose_targets(instances, ROLE_SCALAR)
        self.assertEqual([target.path for target in chromatic], ["/rnbo/inst/1/params/ChromaticTranspose"])
        self.assertEqual([target.path for target in scalar], ["/rnbo/inst/1/params/ScalarTranspose"])

    def test_status_reports_mixed_and_unsupported_targets(self) -> None:
        instances = [
            {"id": "1", "params": [{"name": "ChromaticTranspose", "path": "/a", "value": 3, "min": -12, "max": 12}]},
            {"id": "2", "params": [{"name": "ChromaticTranspose", "path": "/b", "value": 2, "min": -2, "max": 2}]},
        ]
        status = target_status(instances, ROLE_CHROMATIC, 3)
        self.assertEqual((status.compatible, status.matching, status.unsupported), (2, 1, 1))
        self.assertTrue(status.mixed)
        self.assertEqual(common_target_range(instances, ROLE_CHROMATIC), (-2, 2))


if __name__ == "__main__":
    unittest.main()
