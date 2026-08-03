#!/usr/bin/env python3
"""Generate documentation PNGs from Shadowbox's real five-inch renderer."""

from __future__ import annotations

import argparse
import json
import math
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _allow_headless_rendering_without_pythonosc() -> None:
    """The renderer needs neither an OSC client nor an I2C device."""
    try:
        import pythonosc  # noqa: F401
    except ImportError:
        pythonosc_module = types.ModuleType("pythonosc")
        udp_client_module = types.ModuleType("pythonosc.udp_client")
        udp_client_module.SimpleUDPClient = object
        pythonosc_module.udp_client = udp_client_module
        sys.modules["pythonosc"] = pythonosc_module
        sys.modules["pythonosc.udp_client"] = udp_client_module

    try:
        import smbus2  # noqa: F401
    except ImportError:
        smbus_module = types.ModuleType("smbus2")
        smbus_module.SMBus = object
        sys.modules["smbus2"] = smbus_module


_allow_headless_rendering_without_pythonosc()

from shadowbox.display.waveshare_5inch_dsi import Waveshare5InchDSIDisplay
from shadowbox.editors.ttid import get_scale_names
from shadowbox.renderer import FIVE_INCH_THEME, create_renderer
from shadowbox.ui import ShadowboxUI


DEFAULT_OUTPUT = REPO_ROOT / "docs" / "images" / "ui-editors"


@dataclass(frozen=True)
class ScreenshotSpec:
    slug: str
    title: str
    category: str
    description: str
    build_ui: Callable[[], ShadowboxUI]


def _param(
    name: str,
    *,
    value=0.0,
    minimum=0.0,
    maximum=1.0,
    metadata: dict | None = None,
    instance_id: str = "7",
) -> dict:
    return {
        "name": name,
        "path": f"/rnbo/inst/{instance_id}/params/{name}",
        "value": value,
        "min": minimum,
        "max": maximum,
        "metadata": dict(metadata or {}),
    }


def _state(name: str, value, *, instance_id: str = "7") -> dict:
    return {
        "name": name,
        "path": f"/rnbo/inst/{instance_id}/messages/out/{name}",
        "value": value,
        "metadata": {},
    }


def _input(name: str, *, instance_id: str = "7") -> dict:
    return {
        "name": name,
        "path": f"/rnbo/inst/{instance_id}/messages/in/{name}",
        "metadata": {},
    }


def _editor_ui(param: dict, *, label: str, state_values: list[dict] | None = None) -> ShadowboxUI:
    ui = ShadowboxUI()
    ui.state.instances = [
        {
            "id": "7",
            "name": label.replace(" ", ""),
            "label": label,
            "params": [param],
            "state": list(state_values or []),
        }
    ]
    ui.state.active_instance_id = "7"
    ui.state.param_cursor = 1
    ui.state.ui_mode = "EDIT"
    ui.state.edit_value = param.get("value")
    return ui


def _ttid_ui() -> ShadowboxUI:
    param = _param(
        "TTID",
        value=sum(1 << pitch_class for pitch_class in (0, 2, 4, 5, 7, 9, 11)),
        minimum=0,
        maximum=4095,
        metadata={"editor": "ttid"},
    )
    ui = _editor_ui(param, label="TTID")
    ui.state.edit_ttid_mode = "keyboard"
    ui.state.edit_ttid_selected_pc = 0
    ui.state.edit_ttid_scale_names = get_scale_names() or ["major"]
    return ui


def _step16_ui() -> ShadowboxUI:
    active_steps = (0, 3, 4, 7, 10, 12, 14)
    mask = sum(1 << step for step in active_steps)
    param = _param(
        "Pattern",
        value=mask,
        minimum=0,
        maximum=65535,
        metadata={"editor": "step16", "playhead_state": "current_stage"},
    )
    ui = _editor_ui(param, label="Trigger Sequencer", state_values=[_state("current_stage", [8])])
    ui.state.edit_step16_focus = 4
    return ui


def _surface_ui(instance: dict, *, focus: int = 0) -> ShadowboxUI:
    ui = ShadowboxUI()
    ui.state.instances = [instance]
    ui.state.active_instance_id = str(instance["id"])
    if not ui._begin_instance_surface():
        raise RuntimeError(f"Specimen does not satisfy the {instance.get('name')} surface contract")
    ui.state.surface_focus = focus
    ui.pop_actions()
    return ui


def _organ_ui() -> ShadowboxUI:
    names = ("Bass", "Quint", "Neutral", "Octave", "Nazard", "Block-flute", "Tierce", "Larigot", "Sifflute")
    values = (-18, -36, -6, -48, -30, -12, -54, -42, -24)
    instance = {
        "id": "7",
        "name": "Organ",
        "label": "Tonewheel Organ",
        "params": [
            _param(f"Tonewheel/{name}", value=value, minimum=-96, maximum=0)
            for name, value in zip(names, values)
        ],
        "state": [],
    }
    return _surface_ui(instance, focus=2)


def _analog_sequencer_ui() -> ShadowboxUI:
    pitches = (36, 43, 48, 55, 60, 67, 72, 64, 57, 52, 45, 40, 48, 55, 62, 69)
    params = []
    for stage, pitch in enumerate(pitches, start=1):
        params.append(_param(f"{stage:02d}StageValue", value=pitch, minimum=0, maximum=127))
        params.append(_param(f"{stage:02d}StageStep", value=0 if stage in {4, 9, 14} else 1, minimum=0, maximum=1))
    params.extend(
        [
            _param("MaxCnt", value="16"),
            _param("Clock/Clock", value="On"),
            _param("Clock/Swing", value="Off"),
            _param("Clock/ClockInterval", value=240, minimum=30, maximum=3840),
            _param("Clock/SwingAmt", value=0.55, minimum=0.5, maximum=1),
        ]
    )
    instance = {
        "id": "7",
        "name": "AnalogSequencer",
        "label": "Analog Sequencer",
        "params": params,
        "state": [_state("current_stage", [6])],
    }
    return _surface_ui(instance, focus=5)


def _scope_ui() -> ShadowboxUI:
    samples = [
        0.72 * math.sin(index * 0.16) + 0.18 * math.sin(index * 0.53)
        for index in range(672)
    ]
    instance = {
        "id": "7",
        "name": "TimeDomainScope",
        "label": "Time Domain Scope",
        "params": [
            _param(
                "SamplingRate",
                value=48000,
                minimum=8000,
                maximum=96000,
                metadata={"editor": "scope", "scope_state": "scope"},
            )
        ],
        "state": [_state("scope", samples)],
    }
    return _surface_ui(instance)


def _tuner_ui() -> ShadowboxUI:
    instance = {
        "id": "7",
        "name": "Tuner",
        "label": "Tuner",
        "params": [
            _param(
                "Tuner",
                value=1,
                minimum=0,
                maximum=1,
                metadata={"editor": "pitch_display", "pitch_state": "pitch_name", "cents_state": "pitch_cents"},
            )
        ],
        "state": [_state("pitch_name", 69), _state("pitch_cents", -1.7)],
    }
    return _surface_ui(instance)


def _list_sequencer_ui() -> ShadowboxUI:
    names = ("Steps", "StepsSecondary", "PrimaryRotation", "SecondaryRotation", "Oct", "Velocity", "Duration")
    values = {
        "Steps": [0, 2, 4, 7, 9, 11],
        "StepsSecondary": [0, 3, 5, 8, 10],
        "PrimaryRotation": [-2],
        "SecondaryRotation": [3],
        "Oct": [-1, 0, 1],
        "Velocity": [96, 104, 112, 120],
        "Duration": [120, 240, 360, 480],
    }
    instance = {
        "id": "7",
        "name": "ListSequencer",
        "label": "List Sequencer",
        "params": [],
        "inputs": [_input(name) for name in names],
        "state": [_state(f"{name}Ack", values[name]) for name in names],
    }
    return _surface_ui(instance, focus=2)


def _list_vel_sequencer_ui() -> ShadowboxUI:
    rows = range(1, 9)
    instance = {
        "id": "7",
        "name": "ListVelSequencer",
        "label": "List Velocity Sequencer",
        "params": [_param(f"{row}map", value=35 + row, minimum=0, maximum=127) for row in rows],
        "inputs": [_input(f"{row}row") for row in rows],
        "state": [
            _state(f"{row}rowAck", [max(0, 112 - row * 5), max(0, 96 - row * 3), 72])
            for row in rows
        ],
    }
    return _surface_ui(instance, focus=3)


SCREENSHOTS = (
    ScreenshotSpec("ttid", "TTID", "parameter editor", "Pitch-class set keyboard and scale controls.", _ttid_ui),
    ScreenshotSpec("step16", "Step 16", "parameter editor", "Sixteen-step trigger-pattern editor.", _step16_ui),
    ScreenshotSpec("organ", "Organ", "instance surface", "Nine-drawbar organ surface.", _organ_ui),
    ScreenshotSpec("analog-sequencer", "Analog Sequencer", "instance surface", "Sixteen-stage pitch and gate surface.", _analog_sequencer_ui),
    ScreenshotSpec("time-domain-scope", "Time Domain Scope", "instance surface", "Live waveform and sampling-rate surface.", _scope_ui),
    ScreenshotSpec("tuner", "Tuner", "instance surface", "Pitch and cents display.", _tuner_ui),
    ScreenshotSpec("list-sequencer", "List Sequencer", "instance surface", "Seven list fields with direct-entry keypad.", _list_sequencer_ui),
    ScreenshotSpec("list-vel-sequencer", "List Velocity Sequencer", "instance surface", "Eight velocity rows with pitch context.", _list_vel_sequencer_ui),
)


def generate(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    manifest = []

    for spec in SCREENSHOTS:
        ui = spec.build_ui()
        display = Waveshare5InchDSIDisplay(
            physical_width=800,
            physical_height=480,
            logical_width=800,
            logical_height=480,
            fg_color=FIVE_INCH_THEME["text"],
            bg_color=FIVE_INCH_THEME["bg"],
        )
        renderer = create_renderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui)
        destination = display.save_bitmap(output_dir / f"{spec.slug}.png")
        generated.append(destination)
        manifest.append(
            {
                "file": destination.name,
                "title": spec.title,
                "category": spec.category,
                "description": spec.description,
                "width": 800,
                "height": 480,
            }
        )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"screenshots": manifest}, indent=2) + "\n", encoding="utf-8")
    generated.append(manifest_path)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"destination directory (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})",
    )
    args = parser.parse_args()

    for path in generate(args.output.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
