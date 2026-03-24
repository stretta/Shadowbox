#!/usr/bin/env python3

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GitVersionInfo:
    branch: str
    short_commit: str
    commit_date: str
    dirty: bool = False


def _git_output(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _is_git_checkout() -> bool:
    return (REPO_ROOT / ".git").exists()


def _shorten(text: str, max_chars: int) -> str:
    value = str(text).strip()
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3] + "..."


def display_branch_name(branch: str, max_chars: int = 18) -> str:
    value = str(branch).strip()
    if not value or value == "HEAD":
        return "detached"
    parts = [part for part in value.split("/") if part]
    display_name = parts[-1] if parts else value
    return _shorten(display_name, max_chars)


def build_label(info: GitVersionInfo) -> str:
    ref = info.short_commit.strip() or "nogit"
    if info.dirty:
        ref = f"{ref}*"
    date_text = info.commit_date.strip()
    return f"{ref} {date_text}".strip()


def read_git_version_info() -> GitVersionInfo | None:
    if not _is_git_checkout():
        return None

    branch = _git_output("rev-parse", "--abbrev-ref", "HEAD")
    short_commit = _git_output("rev-parse", "--short=7", "HEAD")
    commit_date = _git_output("show", "-s", "--format=%cs", "HEAD")
    dirty_status = _git_output("status", "--porcelain", "--untracked-files=no")

    if not branch or not short_commit or not commit_date:
        return None

    return GitVersionInfo(
        branch=branch,
        short_commit=short_commit,
        commit_date=commit_date,
        dirty=bool(dirty_status),
    )


_GIT_VERSION_INFO = read_git_version_info()

if _GIT_VERSION_INFO is None:
    SHADOWBOX_VERSION = "local"
    SHADOWBOX_BUILD_DATE = "nogit"
    SHADOWBOX_BUILD_INFO = "nogit"
else:
    SHADOWBOX_VERSION = display_branch_name(_GIT_VERSION_INFO.branch)
    SHADOWBOX_BUILD_DATE = _GIT_VERSION_INFO.commit_date
    SHADOWBOX_BUILD_INFO = build_label(_GIT_VERSION_INFO)
