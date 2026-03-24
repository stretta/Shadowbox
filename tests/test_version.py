import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
