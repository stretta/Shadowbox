import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load(name: str):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HDMI = _load("hdmi_mirror_config")
POWER = _load("system_power")


class SystemHelperTests(unittest.TestCase):
    def test_hdmi_helper_replaces_duplicates_with_one_normalized_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shadowbox"
            path.write_text("OTHER=kept\nSHADOWBOX_DSI_HDMI_MIRROR=0\nSHADOWBOX_DSI_HDMI_MIRROR=1\n", encoding="utf-8")

            HDMI.write_enabled(path, False)

            contents = path.read_text(encoding="utf-8")
            self.assertIn("OTHER=kept", contents)
            self.assertEqual(contents.count("SHADOWBOX_DSI_HDMI_MIRROR="), 1)
            self.assertIn("SHADOWBOX_DSI_HDMI_MIRROR=0", contents)
            self.assertFalse(HDMI.read_enabled(path))

    def test_root_hdmi_helper_ignores_caller_path_override(self) -> None:
        with mock.patch.dict(os.environ, {"SHADOWBOX_HDMI_MIRROR_TEST_CONFIG": "/tmp/not-system"}), mock.patch.object(os, "geteuid", return_value=0):
            self.assertEqual(HDMI.config_path(), HDMI.DEFAULT_CONFIG_PATH)

    def test_system_power_helper_runs_only_fixed_reboot_command(self) -> None:
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))

        self.assertEqual(POWER.reboot_system(run), 0)
        run.assert_called_once_with(["/usr/bin/systemctl", "reboot"], check=False)

    def test_system_power_cli_rejects_other_commands(self) -> None:
        self.assertEqual(POWER.main(["system_power.py", "poweroff"]), 2)


if __name__ == "__main__":
    unittest.main()
