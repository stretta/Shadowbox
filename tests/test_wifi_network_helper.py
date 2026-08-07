import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "tools" / "wifi_network.sh"


class WifiNetworkHelperTests(unittest.TestCase):
    def test_retry_replaces_password_on_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            log_path = temp_path / "nmcli.log"
            nmcli_path = temp_path / "nmcli"
            nmcli_path.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${NMCLI_LOG}"
if [[ "$*" == "-t -f UUID,TYPE connection show" ]]; then
  printf '%s\\n' 'bad-uuid:802-11-wireless'
elif [[ "$*" == "-g 802-11-wireless.ssid connection show uuid bad-uuid" ]]; then
  printf '%s\\n' 'studio'
fi
""",
                encoding="utf-8",
            )
            nmcli_path.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{temp_path}:{env['PATH']}"
            env["NMCLI_LOG"] = str(log_path)

            result = subprocess.run(
                [str(HELPER), "connect-new", "studio", "correct horse"],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log_path.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "connection modify uuid bad-uuid 802-11-wireless-security.psk correct horse",
                calls,
            )
            self.assertIn("connection up uuid bad-uuid", calls)
            self.assertFalse(any(call.startswith("device wifi connect") for call in calls))


if __name__ == "__main__":
    unittest.main()
