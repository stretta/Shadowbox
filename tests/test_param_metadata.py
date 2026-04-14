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

from shadowbox.renderer import ShadowboxRenderer, format_param_value, routing_port_display_name
from shadowbox.rnbo import discover_instances, discover_set_presets, discover_sets, discover_system, extract_meta_info
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

    def test_extract_meta_info_preserves_direct_unit_children(self) -> None:
        node = {
            "CONTENTS": {
                "meta": {"VALUE": '{"display_precision": 1}'},
                "unit": {"VALUE": "Hz"},
                "units": {"VALUE": "ignored once unit is present"},
            }
        }

        self.assertEqual(
            extract_meta_info(node),
            {
                "display_precision": 1,
                "unit": "Hz",
                "units": "ignored once unit is present",
            },
        )

    def test_discover_instances_uses_routing_label_metadata_for_display_name(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "info": {
                                    "CONTENTS": {
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {
                                                    "CONTENTS": {
                                                        "sources": {"VALUE": ["system:capture_1"]},
                                                        "sinks": {"VALUE": ["system:playback_1"]},
                                                    }
                                                },
                                                "midi": {
                                                    "CONTENTS": {
                                                        "sources": {"VALUE": []},
                                                        "sinks": {"VALUE": []},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "inst": {
                            "CONTENTS": {
                                "1": {
                                    "CONTENTS": {
                                        "name": {"VALUE": "My Synth"},
                                        "jack": {
                                            "CONTENTS": {
                                                "connections": {
                                                    "CONTENTS": {
                                                        "audio": {
                                                            "CONTENTS": {
                                                                "sinks": {
                                                                    "CONTENTS": {
                                                                        "in1": {
                                                                            "FULL_PATH": "/rnbo/inst/1/jack/connections/audio/sinks/in1",
                                                                            "VALUE": ["system:capture_1"],
                                                                            "CONTENTS": {
                                                                                "meta": {"VALUE": '["label:Main Input"]'},
                                                                            },
                                                                        }
                                                                    }
                                                                },
                                                                "sources": {
                                                                    "CONTENTS": {
                                                                        "out1": {
                                                                            "FULL_PATH": "/rnbo/inst/1/jack/connections/audio/sources/out1",
                                                                            "VALUE": ["system:playback_1"],
                                                                            "CONTENTS": {
                                                                                "display_name": {"VALUE": "Main Output"},
                                                                            },
                                                                        }
                                                                    }
                                                                },
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        instances = discover_instances(tree)

        self.assertEqual(instances[0]["routing"]["audio"]["inputs"][0]["name"], "in1")
        self.assertEqual(instances[0]["routing"]["audio"]["inputs"][0]["display_name"], "Main Input")
        self.assertEqual(instances[0]["routing"]["audio"]["outputs"][0]["display_name"], "Main Output")

    def test_discover_set_presets_reads_published_graph_preset_branch(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "presets": {
                                                    "CONTENTS": {
                                                        "save": {"FULL_PATH": "/rnbo/inst/control/sets/presets/save"},
                                                        "load": {
                                                            "FULL_PATH": "/rnbo/inst/control/sets/presets/load",
                                                            "RANGE": [{"VALS": ["Unipolar Positive", "linke synce"]}],
                                                        },
                                                        "loaded": {"VALUE": "linke synce"},
                                                        "count": {"VALUE": 2},
                                                        "destroy": {"FULL_PATH": "/rnbo/inst/control/sets/presets/destroy"},
                                                        "rename": {"FULL_PATH": "/rnbo/inst/control/sets/presets/rename"},
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        presets = discover_set_presets(tree)

        self.assertEqual(presets["save_path"], "/rnbo/inst/control/sets/presets/save")
        self.assertEqual(presets["load_path"], "/rnbo/inst/control/sets/presets/load")
        self.assertEqual(presets["rename_path"], "/rnbo/inst/control/sets/presets/rename")
        self.assertEqual(presets["destroy_path"], "/rnbo/inst/control/sets/presets/destroy")
        self.assertEqual(presets["loaded_name"], "linke synce")
        self.assertEqual(presets["count"], 2)
        self.assertEqual(presets["available_presets"], ["Unipolar Positive", "linke synce"])

    def test_discover_sets_reads_published_set_capabilities(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "save": {"FULL_PATH": "/rnbo/inst/control/sets/save"},
                                                "rename": {"FULL_PATH": "/rnbo/inst/control/sets/rename"},
                                                "load": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/load",
                                                    "RANGE": [{"VALS": ["Alpha", "Bravo"]}],
                                                },
                                                "reload": {"FULL_PATH": "/rnbo/inst/control/sets/reload"},
                                                "initial": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/initial",
                                                    "VALUE": "Alpha",
                                                },
                                                "current": {
                                                    "CONTENTS": {
                                                        "name": {"VALUE": "Bravo"},
                                                        "dirty": {"VALUE": True},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                },
                                "config": {
                                    "CONTENTS": {
                                        "auto_start_last": {
                                            "FULL_PATH": "/rnbo/inst/config/auto_start_last",
                                            "VALUE": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }

        sets = discover_sets(tree)

        self.assertEqual(sets["current_name"], "Bravo")
        self.assertTrue(sets["dirty"])
        self.assertEqual(sets["save_path"], "/rnbo/inst/control/sets/save")
        self.assertEqual(sets["rename_path"], "/rnbo/inst/control/sets/rename")
        self.assertEqual(sets["load_path"], "/rnbo/inst/control/sets/load")
        self.assertEqual(sets["reload_path"], "/rnbo/inst/control/sets/reload")
        self.assertEqual(sets["initial_path"], "/rnbo/inst/control/sets/initial")
        self.assertEqual(sets["initial_value"], "Alpha")
        self.assertEqual(sets["available_sets"], ["Alpha", "Bravo"])
        self.assertEqual(sets["auto_start_last_path"], "/rnbo/inst/config/auto_start_last")
        self.assertTrue(sets["auto_start_last"])

    def test_discover_instances_reads_preset_save_and_rename_capabilities(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "info": {
                                    "CONTENTS": {
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                                "midi": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "inst": {
                            "CONTENTS": {
                                "1": {
                                    "CONTENTS": {
                                        "name": {"VALUE": "Synth A"},
                                        "presets": {
                                            "CONTENTS": {
                                                "entries": {"VALUE": ["Init", "Bass"]},
                                                "load": {"FULL_PATH": "/rnbo/inst/1/presets/load"},
                                                "save": {"FULL_PATH": "/rnbo/inst/1/presets/save"},
                                                "rename": {"FULL_PATH": "/rnbo/inst/1/presets/rename"},
                                                "current": {"CONTENTS": {"name": {"VALUE": "Bass"}}},
                                            }
                                        },
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        instances = discover_instances(tree)

        self.assertEqual(instances[0]["preset_save_path"], "/rnbo/inst/1/presets/save")
        self.assertEqual(instances[0]["preset_rename_path"], "/rnbo/inst/1/presets/rename")
        self.assertEqual(instances[0]["current_preset_name"], "Bass")

    def test_discover_system_includes_set_name_and_sets_section(self) -> None:
        tree = {
            "CONTENTS": {
                "rnbo": {
                    "CONTENTS": {
                        "jack": {
                            "CONTENTS": {
                                "config": {
                                    "CONTENTS": {
                                        "card": {"FULL_PATH": "/rnbo/jack/config/card", "VALUE": "hw:ES8"},
                                        "period_frames": {"FULL_PATH": "/rnbo/jack/config/period_frames", "VALUE": 256},
                                        "sample_rate": {"FULL_PATH": "/rnbo/jack/config/sample_rate", "VALUE": 48000.0},
                                    }
                                },
                                "info": {
                                    "CONTENTS": {
                                        "cpu_load": {"VALUE": 1.5},
                                        "xrun_count": {"VALUE": 0},
                                        "ports": {
                                            "CONTENTS": {
                                                "audio": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                                "midi": {"CONTENTS": {"sources": {"VALUE": []}, "sinks": {"VALUE": []}}},
                                            }
                                        },
                                    }
                                },
                                "restart": {"FULL_PATH": "/rnbo/jack/restart"},
                            }
                        },
                        "info": {"CONTENTS": {"runner_version": {"VALUE": "1.4.3"}}},
                        "inst": {
                            "CONTENTS": {
                                "control": {
                                    "CONTENTS": {
                                        "sets": {
                                            "CONTENTS": {
                                                "load": {
                                                    "FULL_PATH": "/rnbo/inst/control/sets/load",
                                                    "RANGE": [{"VALS": ["StudioA"]}],
                                                },
                                                "current": {
                                                    "CONTENTS": {
                                                        "name": {"VALUE": "StudioA"},
                                                        "dirty": {"VALUE": False},
                                                    }
                                                },
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }

        system = discover_system(tree)

        self.assertEqual(system["set_name"], "StudioA")
        self.assertEqual(system["sets"]["current_name"], "StudioA")
        self.assertEqual(system["sets"]["available_sets"], ["StudioA"])


if __name__ == "__main__":
    unittest.main()
