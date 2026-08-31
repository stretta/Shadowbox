import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from shadowbox.software_update import (
    SoftwareUpdateStatus,
    SHADOWBOX_SOURCE_EXCLUDES,
    _install_staged_source,
    _restore_source_backup,
    _run_command_with_status,
    read_shadowscore_update_status,
    read_all_software_update_status,
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
        install_dir.exists.return_value = False
        with patch("shadowbox.software_update._is_shadowscore_source_copy", return_value=False):
            status = read_shadowscore_update_status()

        self.assertEqual(status.state, "missing")
        self.assertFalse(status.installed)

    @patch("shadowbox.software_update._read_source_release", return_value=("b46f35b9", "main"))
    @patch("shadowbox.software_update._remote_head", return_value=(True, "b46f35b9"))
    @patch("shadowbox.software_update.SHADOWSCORE_INSTALL_DIR")
    def test_shadowscore_update_status_recognizes_current_source_copy(
        self,
        install_dir,
        _remote_head,
        _read_release,
    ) -> None:
        install_dir.__truediv__.return_value.exists.return_value = False
        with patch("shadowbox.software_update._is_shadowscore_source_copy", return_value=True):
            status = read_shadowscore_update_status(fetch=True)

        self.assertEqual(status.state, "current")
        self.assertEqual(status.layout, "source-copy")
        self.assertTrue(status.installed)

    @patch("shadowbox.software_update._read_source_release", return_value=("", "main"))
    @patch("shadowbox.software_update._remote_head", return_value=(True, "b46f35b9"))
    @patch("shadowbox.software_update.SHADOWSCORE_INSTALL_DIR")
    def test_shadowscore_update_status_offers_refresh_for_unmarked_source_copy(
        self,
        install_dir,
        _remote_head,
        _read_release,
    ) -> None:
        install_dir.__truediv__.return_value.exists.return_value = False
        with patch("shadowbox.software_update._is_shadowscore_source_copy", return_value=True):
            status = read_shadowscore_update_status(fetch=True)

        self.assertEqual(status.state, "available")
        self.assertEqual(status.layout, "source-copy")
        self.assertEqual(status.message, "source refresh")

    @patch("shadowbox.software_update.REPO_ROOT")
    @patch("shadowbox.software_update._read_source_release", return_value=("653f96e", "main"))
    @patch("shadowbox.software_update._remote_head", return_value=(True, "61e9d16"))
    def test_shadowbox_update_status_recognizes_source_copy(
        self,
        _remote_head,
        _read_release,
        repo_root,
    ) -> None:
        repo_root.__truediv__.return_value.exists.return_value = False
        with patch("shadowbox.software_update._is_shadowbox_source_copy", return_value=True):
            status = read_software_update_status(fetch=True)

        self.assertEqual(status.state, "available")
        self.assertEqual(status.layout, "source-copy")
        self.assertEqual(status.local, "653f96e")
        self.assertEqual(status.remote, "61e9d16")

    def test_unknown_non_git_shadowscore_directory_is_not_treated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir)
            (install_dir / "unrelated.txt").write_text("keep me", encoding="utf-8")
            with patch("shadowbox.software_update.SHADOWSCORE_INSTALL_DIR", install_dir):
                status = read_shadowscore_update_status()

        self.assertEqual(status.state, "error")
        self.assertEqual(status.message, "unrecognized install")
        self.assertTrue(status.installed)

    @patch(
        "shadowbox.software_update._read_recent_update_result",
        return_value={
            "target": "shadowbox",
            "state": "applied",
            "message": "updated; restarting",
            "layout": "source-copy",
        },
    )
    @patch("shadowbox.software_update.read_shadowscore_update_status")
    @patch("shadowbox.software_update.read_software_update_status")
    def test_recent_shadowbox_result_survives_service_restart(
        self,
        read_shadowbox,
        read_shadowscore,
        _read_result,
    ) -> None:
        read_shadowbox.return_value = SoftwareUpdateStatus("source-copy", "source copy", layout="source-copy")
        read_shadowscore.return_value = SoftwareUpdateStatus("current", "up to date")

        statuses = read_all_software_update_status(fetch=False)

        self.assertEqual(statuses["targets"]["shadowbox"]["state"], "applied")
        self.assertEqual(statuses["targets"]["shadowbox"]["message"], "updated; restarting")

    def test_staged_source_install_preserves_runtime_files_and_can_roll_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "current"
            staged = root / "staged"
            backup = root / "backup"
            (current / ".venv").mkdir(parents=True)
            (current / ".venv" / "keep").write_text("runtime", encoding="utf-8")
            (current / "old.txt").write_text("old", encoding="utf-8")
            (current / "stale.txt").write_text("stale", encoding="utf-8")
            staged.mkdir()
            (staged / "old.txt").write_text("new", encoding="utf-8")
            (staged / "added.txt").write_text("added", encoding="utf-8")

            installed, detail = _install_staged_source(
                staged,
                current,
                backup,
                SHADOWBOX_SOURCE_EXCLUDES,
            )

            self.assertTrue(installed, detail)
            self.assertEqual((current / "old.txt").read_text(encoding="utf-8"), "new")
            self.assertTrue((current / "added.txt").exists())
            self.assertFalse((current / "stale.txt").exists())
            self.assertEqual((current / ".venv" / "keep").read_text(encoding="utf-8"), "runtime")

            restored, detail = _restore_source_backup(backup, current, SHADOWBOX_SOURCE_EXCLUDES)

            self.assertTrue(restored, detail)
            self.assertEqual((current / "old.txt").read_text(encoding="utf-8"), "old")
            self.assertTrue((current / "stale.txt").exists())
            self.assertFalse((current / "added.txt").exists())
            self.assertEqual((current / ".venv" / "keep").read_text(encoding="utf-8"), "runtime")

    def test_silent_staged_command_can_be_canceled_without_waiting_for_output(self) -> None:
        cancel = Event()
        cancel.set()

        ok, detail = _run_command_with_status(
            ["bash", "-lc", "sleep 10"],
            cwd=Path.cwd(),
            env={},
            cancel_event=cancel,
        )

        self.assertFalse(ok)
        self.assertEqual(detail, "install canceled")

    @patch("shadowbox.software_update._run_command_with_status", return_value=(True, "installed"))
    @patch("shadowbox.software_update._validate_sudo_password", return_value="")
    @patch("shadowbox.software_update.read_shadowscore_update_status")
    def test_shadowscore_install_uses_remote_installer_when_missing(self, read_status, _validate_sudo, run_command) -> None:
        read_status.return_value.state = "missing"

        status = start_shadowscore_update_install("password")

        self.assertEqual(status.state, "applied")
        self.assertEqual(status.message, "installed")
        self.assertIn("curl -fsSL", run_command.call_args.args[0][2])

    @patch("shadowbox.software_update._write_update_result")
    @patch("shadowbox.software_update._schedule_shadowbox_restart", return_value=(True, "scheduled"))
    @patch("shadowbox.software_update._run_installer", return_value=(True, "updated"))
    @patch("shadowbox.software_update._install_staged_source", return_value=(True, "source installed"))
    @patch("shadowbox.software_update._is_shadowbox_source_copy", return_value=True)
    @patch("shadowbox.software_update._stage_source_release")
    @patch("shadowbox.software_update._validate_sudo_password", return_value="")
    @patch("shadowbox.software_update.read_software_update_status")
    def test_shadowbox_source_copy_update_stages_installs_and_hands_off_restart(
        self,
        read_status,
        _validate_sudo,
        stage_source,
        _is_source,
        install_source,
        run_installer,
        schedule_restart,
        write_result,
    ) -> None:
        read_status.return_value = SoftwareUpdateStatus(
            "available",
            "source refresh",
            branch="main",
            local="old",
            remote="new",
            behind=1,
            layout="source-copy",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            staged = Path(temp_dir) / "release"
            stage_source.return_value = (True, "staged", staged, "new-commit")
            status = start_software_update_install("")

        self.assertEqual(status.state, "applied")
        install_source.assert_called_once()
        self.assertEqual(run_installer.call_args.kwargs["installer_args"], ["--no-restart"])
        schedule_restart.assert_called_once()
        write_result.assert_called_once()

    @patch("shadowbox.software_update._restart_shadowscore_service", return_value=(True, "restarted"))
    @patch("shadowbox.software_update._run_command_with_status", return_value=(True, "npm ok"))
    @patch("shadowbox.software_update._install_staged_source", return_value=(True, "source installed"))
    @patch("shadowbox.software_update._is_shadowscore_source_copy", return_value=True)
    @patch("shadowbox.software_update._stage_source_release")
    @patch("shadowbox.software_update._validate_sudo_password", return_value="")
    @patch("shadowbox.software_update.read_shadowscore_update_status")
    def test_shadowscore_source_copy_update_does_not_run_first_install_path(
        self,
        read_status,
        _validate_sudo,
        stage_source,
        _is_source,
        install_source,
        run_command,
        restart_service,
    ) -> None:
        read_status.return_value = SoftwareUpdateStatus(
            "available",
            "source refresh",
            branch="main",
            local="old",
            remote="new",
            behind=1,
            layout="source-copy",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            staged = Path(temp_dir) / "release"
            stage_source.return_value = (True, "staged", staged, "new-commit")
            status = start_shadowscore_update_install("")

        self.assertEqual(status.state, "applied")
        install_source.assert_called_once()
        self.assertEqual(run_command.call_args.args[0], ["npm", "install", "--omit=dev"])
        restart_service.assert_called_once()


if __name__ == "__main__":
    unittest.main()
