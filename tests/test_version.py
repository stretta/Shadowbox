import unittest
from unittest.mock import patch

from shadowbox.software_update import (
    read_shadowscore_update_status,
    read_software_update_status,
    start_shadowscore_update_install,
    start_software_update_install,
)
from shadowbox.version import GitVersionInfo, build_label, display_branch_name, read_git_version_info


class VersionTests(unittest.TestCase):
    def test_display_branch_name_uses_last_segment(self) -> None:
        self.assertEqual(display_branch_name("codex/port-local-changes"), "port-local-changes")

    def test_display_branch_name_shortens_long_names(self) -> None:
        self.assertEqual(display_branch_name("feature/this-branch-name-is-too-long"), "this-branch-nam...")

    def test_build_label_appends_dirty_marker(self) -> None:
        info = GitVersionInfo(branch="main", short_commit="847a7ce", commit_date="2026-03-24", dirty=True)
        self.assertEqual(build_label(info), "847a7ce* 2026-03-24")

    @patch("shadowbox.version._git_output")
    @patch("shadowbox.version._is_git_checkout", return_value=True)
    def test_read_git_version_info_reads_git_metadata(self, _is_git_checkout, git_output) -> None:
        git_output.side_effect = ["codex/port-local-changes", "847a7ce", "2026-03-24", " M shadowbox/version.py"]

        info = read_git_version_info()

        self.assertEqual(
            info,
            GitVersionInfo(
                branch="codex/port-local-changes",
                short_commit="847a7ce",
                commit_date="2026-03-24",
                dirty=True,
            ),
        )

    @patch("shadowbox.version._is_git_checkout", return_value=False)
    def test_read_git_version_info_returns_none_outside_git_checkout(self, _is_git_checkout) -> None:
        self.assertIsNone(read_git_version_info())

    @patch("shadowbox.software_update.REPO_ROOT")
    @patch("shadowbox.software_update._run_git")
    def test_software_update_status_reports_available_when_behind(self, run_git, repo_root) -> None:
        repo_root.__truediv__.return_value.exists.return_value = True
        run_git.side_effect = [
            (True, "main"),
            (True, "1111111"),
            (True, "2026-06-23"),
            (True, ""),
            (True, "origin/main"),
            (True, "2222222"),
            (True, "0\t1"),
        ]

        status = read_software_update_status()

        self.assertEqual(status.state, "available")
        self.assertTrue(status.available)
        self.assertEqual(status.behind, 1)
        self.assertEqual(status.remote, "2222222")

    @patch("shadowbox.software_update.REPO_ROOT")
    @patch("shadowbox.software_update._run_git")
    def test_software_update_status_refuses_dirty_checkout(self, run_git, repo_root) -> None:
        repo_root.__truediv__.return_value.exists.return_value = True
        run_git.side_effect = [
            (True, "main"),
            (True, "1111111"),
            (True, "2026-06-23"),
            (True, " M shadowbox/ui.py"),
            (True, "origin/main"),
            (True, "2222222"),
            (True, "0\t1"),
        ]

        status = read_software_update_status()

        self.assertEqual(status.state, "dirty")
        self.assertFalse(status.available)
        self.assertTrue(status.dirty)

    @patch("shadowbox.software_update.REPO_ROOT")
    @patch("shadowbox.software_update._run_installer", return_value=(False, "install timeout use ssh"))
    @patch("shadowbox.software_update._validate_sudo_password", return_value="")
    @patch("shadowbox.software_update._run_git")
    def test_software_update_install_reports_installer_failure(self, run_git, _validate_sudo, _run_installer, repo_root) -> None:
        repo_root.__truediv__.return_value.exists.return_value = True
        run_git.side_effect = [
            (True, "main"),
            (True, "1111111"),
            (True, "2026-06-23"),
            (True, ""),
            (True, "origin/main"),
            (True, ""),
            (True, "2222222"),
            (True, "0\t1"),
            (True, "pull ok"),
        ]

        status = start_software_update_install("password")

        self.assertEqual(status.state, "error")
        self.assertEqual(status.message, "install timeout use ssh")

    @patch("shadowbox.software_update.SHADOWSCORE_INSTALL_DIR")
    def test_shadowscore_update_status_reports_missing_when_not_installed(self, install_dir) -> None:
        install_dir.__truediv__.return_value.exists.return_value = False

        status = read_shadowscore_update_status()

        self.assertEqual(status.state, "missing")
        self.assertFalse(status.installed)

    @patch("shadowbox.software_update._run_command_with_status", return_value=(True, "installed"))
    @patch("shadowbox.software_update._validate_sudo_password", return_value="")
    @patch("shadowbox.software_update.read_shadowscore_update_status")
    def test_shadowscore_install_uses_remote_installer_when_missing(self, read_status, _validate_sudo, run_command) -> None:
        read_status.return_value.state = "missing"

        status = start_shadowscore_update_install("password")

        self.assertEqual(status.state, "applied")
        self.assertEqual(status.message, "installed")
        self.assertIn("curl -fsSL", run_command.call_args.args[0][2])


if __name__ == "__main__":
    unittest.main()
