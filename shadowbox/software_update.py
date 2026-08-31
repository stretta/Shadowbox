#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from shadowbox.version import REPO_ROOT

SHADOWSCORE_REPO_URL = "https://github.com/stretta/ShadowscoreServer.git"
SHADOWSCORE_RAW_INSTALLER_URL = "https://raw.githubusercontent.com/stretta/ShadowscoreServer/main/deploy/install-shadowscore.sh"
SHADOWSCORE_INSTALL_DIR = Path(os.environ.get("SHADOWSCORE_INSTALL_DIR", "/home/pi/ShadowscoreServer"))
SHADOWBOX_REPO_URL = os.environ.get("SHADOWBOX_REPO_URL", "https://github.com/stretta/Shadowbox.git")
SHADOWBOX_BRANCH = os.environ.get("SHADOWBOX_BRANCH", "main")
SHADOWSCORE_BRANCH = os.environ.get("SHADOWSCORE_BRANCH", "main")
SOURCE_RELEASE_FILE = ".source-release.json"
UPDATE_RESULT_FILE = Path(
    os.environ.get("SHADOWBOX_UPDATE_RESULT_FILE", str(Path.home() / ".cache" / "shadowbox" / "software-update.json"))
)


@dataclass(frozen=True)
class SoftwareUpdateStatus:
    state: str
    message: str
    branch: str = "-"
    local: str = "-"
    remote: str = "-"
    commit_date: str = "-"
    dirty: bool = False
    behind: int = 0
    ahead: int = 0
    installed: bool = True
    layout: str = "git"

    @property
    def available(self) -> bool:
        return self.state == "available" and self.behind > 0

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "message": self.message,
            "branch": self.branch,
            "local": self.local,
            "remote": self.remote,
            "commit_date": self.commit_date,
            "dirty": self.dirty,
            "behind": self.behind,
            "ahead": self.ahead,
            "installed": self.installed,
            "layout": self.layout,
            "available": self.available,
        }


def _run_git_in(repo_root: Path, *args: str, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "git unavailable"
    except subprocess.TimeoutExpired:
        return False, "git timeout"
    except Exception as exc:
        return False, str(exc)

    output = (result.stdout or "").strip()
    detail = output or (result.stderr or "").strip() or f"exit {result.returncode}"
    return result.returncode == 0, detail


def _run_git(*args: str, timeout: float = 8.0) -> tuple[bool, str]:
    return _run_git_in(REPO_ROOT, *args, timeout=timeout)


def _remote_head(repo_url: str, branch: str, timeout: float = 20.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "git unavailable"
    except subprocess.TimeoutExpired:
        return False, "git timeout"
    except Exception as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    commit = (result.stdout or "").strip().split()
    if not commit:
        return False, "branch unavailable"
    return True, commit[0]


def _read_source_release(repo_root: Path) -> tuple[str, str]:
    try:
        payload = json.loads((repo_root / SOURCE_RELEASE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "", ""
    return str(payload.get("commit") or ""), str(payload.get("branch") or "")


def _write_source_release(repo_root: Path, *, project: str, commit: str, branch: str) -> None:
    payload = {
        "schema": 1,
        "project": project,
        "commit": commit,
        "branch": branch,
    }
    (repo_root / SOURCE_RELEASE_FILE).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_update_result(target: str, status: SoftwareUpdateStatus) -> None:
    payload = {
        "schema": 1,
        "target": target,
        "state": status.state,
        "message": status.message,
        "layout": status.layout,
        "timestamp": time.time(),
    }
    temp_path = ""
    try:
        UPDATE_RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="software-update.", dir=UPDATE_RESULT_FILE.parent, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.write("\n")
        os.replace(temp_path, UPDATE_RESULT_FILE)
    except OSError:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _read_recent_update_result(max_age: float = 300.0) -> dict:
    try:
        payload = json.loads(UPDATE_RESULT_FILE.read_text(encoding="utf-8"))
        timestamp = float(payload.get("timestamp", 0))
    except (OSError, ValueError, TypeError):
        return {}
    if timestamp <= 0 or time.time() - timestamp > max_age:
        return {}
    return payload


def _is_shadowbox_source_copy(repo_root: Path = REPO_ROOT) -> bool:
    return (repo_root / "install.sh").is_file() and (repo_root / "shadowbox" / "software_update.py").is_file()


def _is_shadowscore_source_copy(repo_root: Path = SHADOWSCORE_INSTALL_DIR) -> bool:
    if not (repo_root / "package.json").is_file() or not (repo_root / "src").is_dir():
        return False
    try:
        package = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return package.get("name") == "shadowscore-server"


def _source_copy_status(
    repo_root: Path,
    *,
    repo_url: str,
    branch: str,
    fetch: bool,
) -> SoftwareUpdateStatus:
    local_commit, recorded_branch = _read_source_release(repo_root)
    selected_branch = recorded_branch or branch
    local = local_commit[:7] if local_commit else "unmarked"
    if not fetch:
        return SoftwareUpdateStatus(
            "source-copy",
            "source copy",
            branch=selected_branch,
            local=local,
            installed=True,
            layout="source-copy",
        )
    ok, remote_detail = _remote_head(repo_url, selected_branch)
    if not ok:
        return SoftwareUpdateStatus(
            "error",
            _short_error(remote_detail),
            branch=selected_branch,
            local=local,
            installed=True,
            layout="source-copy",
        )
    remote_commit = remote_detail
    if local_commit and local_commit == remote_commit:
        return SoftwareUpdateStatus(
            "current",
            "up to date",
            branch=selected_branch,
            local=local,
            remote=remote_commit[:7],
            installed=True,
            layout="source-copy",
        )
    return SoftwareUpdateStatus(
        "available",
        "source refresh",
        branch=selected_branch,
        local=local,
        remote=remote_commit[:7],
        behind=1,
        installed=True,
        layout="source-copy",
    )


def _short_error(text: str, limit: int = 54) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _int_pair(text: str) -> tuple[int, int]:
    parts = str(text or "").split()
    if len(parts) < 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def read_software_update_status(fetch: bool = False) -> SoftwareUpdateStatus:
    if not (REPO_ROOT / ".git").exists():
        if _is_shadowbox_source_copy(REPO_ROOT):
            return _source_copy_status(
                REPO_ROOT,
                repo_url=SHADOWBOX_REPO_URL,
                branch=SHADOWBOX_BRANCH,
                fetch=fetch,
            )
        return SoftwareUpdateStatus("nogit", "unrecognized install")

    ok, branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    if not ok:
        return SoftwareUpdateStatus("error", _short_error(branch))

    ok, local = _run_git("rev-parse", "--short=7", "HEAD")
    if not ok:
        return SoftwareUpdateStatus("error", _short_error(local), branch=branch)

    ok, commit_date = _run_git("show", "-s", "--format=%cs", "HEAD")
    if not ok:
        commit_date = "-"

    ok, dirty_text = _run_git("status", "--porcelain", "--untracked-files=no")
    dirty = ok and bool(dirty_text)

    ok, upstream = _run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not ok:
        return SoftwareUpdateStatus(
            "no-upstream",
            "no upstream branch",
            branch=branch,
            local=local,
            commit_date=commit_date,
            dirty=dirty,
        )

    if dirty:
        return SoftwareUpdateStatus(
            "dirty",
            "local changes",
            branch=branch,
            local=local,
            remote=upstream,
            commit_date=commit_date,
            dirty=True,
        )

    if fetch:
        ok, fetch_output = _run_git("fetch", "--prune", "--quiet", timeout=20.0)
        if not ok:
            return SoftwareUpdateStatus(
                "error",
                _short_error(fetch_output),
                branch=branch,
                local=local,
                remote=upstream,
                commit_date=commit_date,
                dirty=dirty,
            )

    ok, remote = _run_git("rev-parse", "--short=7", "@{u}")
    if not ok:
        remote = upstream

    ok, counts = _run_git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    ahead, behind = _int_pair(counts) if ok else (0, 0)

    state = "current"
    message = "up to date"
    if ahead and behind:
        state = "diverged"
        message = f"{ahead} ahead {behind} behind"
    elif behind:
        state = "available"
        message = f"{behind} update{'s' if behind != 1 else ''}"
    elif ahead:
        state = "ahead"
        message = f"{ahead} ahead"

    return SoftwareUpdateStatus(
        state,
        message,
        branch=branch,
        local=local,
        remote=remote,
        commit_date=commit_date,
        dirty=dirty,
        behind=behind,
        ahead=ahead,
    )


def _validate_sudo_password(password: str) -> str:
    value = str(password or "")
    if not value:
        return ""
    try:
        result = subprocess.run(
            ["sudo", "-S", "-p", "", "-v"],
            cwd=REPO_ROOT,
            input=f"{value}\n",
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except FileNotFoundError:
        return "sudo unavailable"
    except subprocess.TimeoutExpired:
        return "sudo timeout"
    except Exception as exc:
        return _short_error(str(exc))
    if result.returncode == 0:
        return ""
    detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
    return _short_error(detail)


def _write_sudo_password_file(password: str) -> str:
    value = str(password or "")
    if not value:
        return ""
    fd, path = tempfile.mkstemp(prefix="shadowbox-sudo.", text=True)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(f"{value}\n")
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def _read_status_file(path: str) -> str:
    if not path:
        return ""
    try:
        return " ".join(open(path, encoding="utf-8").read().split())
    except OSError:
        return ""


def _stop_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5.0)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def _run_installer(
    env: dict[str, str],
    installer_args: list[str] | None = None,
    timeout: float = 900.0,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str]:
    installer = REPO_ROOT / "install.sh"
    process = subprocess.Popen(
        [str(installer), *(installer_args or [])],
        cwd=REPO_ROOT,
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    status_path = str(env.get("SHADOWBOX_INSTALL_STATUS_FILE", ""))
    last_status = ""
    started_at = None
    try:
        from time import monotonic, sleep

        started_at = monotonic()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _stop_process_group(process)
                return False, "install canceled"
            if timeout > 0 and monotonic() - started_at >= timeout:
                _stop_process_group(process)
                return False, "install timeout use ssh"
            status = _read_status_file(status_path)
            if status and status != last_status:
                last_status = status
                if status_callback is not None:
                    status_callback(status)
            sleep(0.5)
    finally:
        status = _read_status_file(status_path)
        if status and status != last_status and status_callback is not None:
            status_callback(status)

    if process.returncode == 0:
        return True, "updated"
    detail = f"exit {process.returncode}"
    return False, f"install failed {_short_error(detail, 36)}"


def start_software_update_install(sudo_password: str = "", status_callback=None, cancel_event=None) -> SoftwareUpdateStatus:
    status = read_software_update_status(fetch=True)
    if status.state == "dirty":
        return SoftwareUpdateStatus(
            "error",
            "local changes",
            branch=status.branch,
            local=status.local,
            remote=status.remote,
            commit_date=status.commit_date,
            dirty=True,
            behind=status.behind,
            ahead=status.ahead,
        )
    if status.state not in {"available", "current"}:
        return status
    if not status.available:
        return status

    sudo_error = _validate_sudo_password(sudo_password)
    if sudo_error:
        return SoftwareUpdateStatus("error", sudo_error, branch=status.branch)

    sudo_password_file = ""
    if sudo_password:
        try:
            sudo_password_file = _write_sudo_password_file(sudo_password)
        except Exception as exc:
            return SoftwareUpdateStatus("error", _short_error(str(exc)), branch=status.branch)

    env = os.environ.copy()
    if sudo_password_file:
        env["SHADOWBOX_SUDO_PASSWORD_FILE"] = sudo_password_file
    status_fd, status_path = tempfile.mkstemp(prefix="shadowbox-install-status.", text=True)
    os.close(status_fd)
    env["SHADOWBOX_INSTALL_STATUS_FILE"] = status_path
    source_temp: Path | None = None
    source_backup: Path | None = None

    try:
        if status.layout == "source-copy":
            source_temp = Path(tempfile.mkdtemp(prefix="shadowbox-source-update."))
            ok, detail, staged, _commit = _stage_source_release(
                SHADOWBOX_REPO_URL,
                status.branch or SHADOWBOX_BRANCH,
                source_temp,
                project="shadowbox",
                status_callback=status_callback,
                cancel_event=cancel_event,
            )
            if not ok or staged is None:
                return SoftwareUpdateStatus("error", _short_error(detail), branch=status.branch, layout="source-copy")
            if not _is_shadowbox_source_copy(staged):
                return SoftwareUpdateStatus("error", "invalid Shadowbox release", branch=status.branch, layout="source-copy")
            source_backup = source_temp / "backup"
            ok, detail = _install_staged_source(
                staged,
                REPO_ROOT,
                source_backup,
                SHADOWBOX_SOURCE_EXCLUDES,
                status_callback=status_callback,
                cancel_event=cancel_event,
            )
            if not ok:
                return SoftwareUpdateStatus("error", _short_error(detail), branch=status.branch, layout="source-copy")
        else:
            ok, pull_output = _run_git("pull", "--ff-only", timeout=45.0)
            if not ok:
                return SoftwareUpdateStatus(
                    "error",
                    _short_error(pull_output),
                    branch=status.branch,
                    local=status.local,
                    remote=status.remote,
                    commit_date=status.commit_date,
                    dirty=status.dirty,
                    behind=status.behind,
                    ahead=status.ahead,
                )

        installer = REPO_ROOT / "install.sh"
        if not installer.exists():
            if source_backup is not None:
                _restore_source_backup(source_backup, REPO_ROOT, SHADOWBOX_SOURCE_EXCLUDES, status_callback=status_callback)
            return SoftwareUpdateStatus("error", "install.sh missing", branch=status.branch, layout=status.layout)

        ok, detail = _run_installer(
            env,
            installer_args=["--no-restart"],
            status_callback=status_callback,
            cancel_event=cancel_event,
        )
        if not ok:
            if source_backup is not None:
                restored, restore_detail = _restore_source_backup(
                    source_backup,
                    REPO_ROOT,
                    SHADOWBOX_SOURCE_EXCLUDES,
                    status_callback=status_callback,
                )
                if not restored:
                    detail = f"{detail}; rollback failed {restore_detail}"
            return SoftwareUpdateStatus(
                "error",
                _short_error(detail),
                branch=status.branch,
                local=status.local,
                remote=status.remote,
                commit_date=status.commit_date,
                layout=status.layout,
            )

        if status_callback is not None:
            status_callback("scheduling restart")
        restart_ok, restart_detail = _schedule_shadowbox_restart()
        if not restart_ok:
            return SoftwareUpdateStatus(
                "error",
                _short_error(f"restart handoff failed {restart_detail}"),
                branch=status.branch,
                layout=status.layout,
            )
    except Exception as exc:
        return SoftwareUpdateStatus("error", _short_error(str(exc)), branch=status.branch)
    finally:
        if sudo_password_file:
            try:
                os.unlink(sudo_password_file)
            except OSError:
                pass
        try:
            os.unlink(status_path)
        except OSError:
            pass
        if source_temp is not None:
            shutil.rmtree(source_temp, ignore_errors=True)

    applied_status = SoftwareUpdateStatus(
        "applied",
        "updated; restarting",
        branch=status.branch,
        local=status.local,
        remote=status.remote,
        commit_date=status.commit_date,
        behind=status.behind,
        ahead=status.ahead,
        layout=status.layout,
    )
    _write_update_result("shadowbox", applied_status)
    return applied_status


def read_all_software_update_status(fetch: bool = False) -> dict:
    shadowbox = read_software_update_status(fetch=fetch).to_dict()
    shadowscore = read_shadowscore_update_status(fetch=fetch).to_dict()
    recent = _read_recent_update_result()
    recent_target = str(recent.get("target") or "")
    if recent_target in {"shadowbox", "shadowscore"} and recent.get("state") == "applied":
        selected = shadowbox if recent_target == "shadowbox" else shadowscore
        selected.update(
            {
                "state": "applied",
                "message": str(recent.get("message") or "updated"),
                "available": False,
                "layout": str(recent.get("layout") or selected.get("layout") or "git"),
            }
        )
    return {
        "targets": {
            "shadowbox": shadowbox,
            "shadowscore": shadowscore,
        },
        **shadowbox,
    }


def read_shadowscore_update_status(fetch: bool = False) -> SoftwareUpdateStatus:
    repo_root = SHADOWSCORE_INSTALL_DIR
    if not (repo_root / ".git").exists():
        if _is_shadowscore_source_copy(repo_root):
            return _source_copy_status(
                repo_root,
                repo_url=SHADOWSCORE_REPO_URL,
                branch=SHADOWSCORE_BRANCH,
                fetch=fetch,
            )
        if repo_root.exists():
            try:
                has_contents = next(repo_root.iterdir(), None) is not None
            except OSError:
                has_contents = True
            if has_contents:
                return SoftwareUpdateStatus("error", "unrecognized install", installed=True, layout="unknown")
        return SoftwareUpdateStatus("missing", "not installed", installed=False, layout="missing")

    ok, branch = _run_git_in(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if not ok:
        return SoftwareUpdateStatus("error", _short_error(branch))

    ok, local = _run_git_in(repo_root, "rev-parse", "--short=7", "HEAD")
    if not ok:
        return SoftwareUpdateStatus("error", _short_error(local), branch=branch)

    ok, commit_date = _run_git_in(repo_root, "show", "-s", "--format=%cs", "HEAD")
    if not ok:
        commit_date = "-"

    ok, dirty_text = _run_git_in(repo_root, "status", "--porcelain", "--untracked-files=no")
    dirty = ok and bool(dirty_text)

    ok, upstream = _run_git_in(repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not ok:
        return SoftwareUpdateStatus(
            "no-upstream",
            "no upstream branch",
            branch=branch,
            local=local,
            commit_date=commit_date,
            dirty=dirty,
        )

    if dirty:
        return SoftwareUpdateStatus(
            "dirty",
            "local changes",
            branch=branch,
            local=local,
            remote=upstream,
            commit_date=commit_date,
            dirty=True,
        )

    if fetch:
        ok, fetch_output = _run_git_in(repo_root, "fetch", "--prune", "--quiet", timeout=20.0)
        if not ok:
            return SoftwareUpdateStatus(
                "error",
                _short_error(fetch_output),
                branch=branch,
                local=local,
                remote=upstream,
                commit_date=commit_date,
                dirty=dirty,
            )

    ok, remote = _run_git_in(repo_root, "rev-parse", "--short=7", "@{u}")
    if not ok:
        remote = upstream

    ok, counts = _run_git_in(repo_root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    ahead, behind = _int_pair(counts) if ok else (0, 0)

    state = "current"
    message = "up to date"
    if ahead and behind:
        state = "diverged"
        message = f"{ahead} ahead {behind} behind"
    elif behind:
        state = "available"
        message = f"{behind} update{'s' if behind != 1 else ''}"
    elif ahead:
        state = "ahead"
        message = f"{ahead} ahead"

    return SoftwareUpdateStatus(
        state,
        message,
        branch=branch,
        local=local,
        remote=remote,
        commit_date=commit_date,
        dirty=dirty,
        behind=behind,
        ahead=ahead,
    )


def _run_command_with_status(
    args: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: float = 900.0,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str]:
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return False, f"{args[0]} unavailable"
    except Exception as exc:
        return False, _short_error(str(exc))

    last_status = ""
    lines: list[str] = []
    stdout_nonblocking = False
    if process.stdout is not None:
        try:
            os.set_blocking(process.stdout.fileno(), False)
            stdout_nonblocking = True
        except (AttributeError, OSError):
            pass
    try:
        from time import monotonic, sleep

        started_at = monotonic()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _stop_process_group(process)
                return False, "install canceled"
            if timeout > 0 and monotonic() - started_at >= timeout:
                _stop_process_group(process)
                return False, "install timeout use ssh"
            try:
                line = process.stdout.readline() if process.stdout else ""
            except (BlockingIOError, TypeError):
                line = ""
            if line:
                message = " ".join(line.strip().split())
                if message:
                    lines.append(message)
                    if status_callback is not None and message != last_status:
                        last_status = message
                        status_callback(_short_error(message, 48))
            else:
                sleep(0.2)
        if process.stdout:
            if stdout_nonblocking:
                try:
                    os.set_blocking(process.stdout.fileno(), True)
                except OSError:
                    pass
            for line in process.stdout:
                message = " ".join(line.strip().split())
                if message:
                    lines.append(message)
                    if status_callback is not None and message != last_status:
                        last_status = message
                        status_callback(_short_error(message, 48))
    finally:
        if process.stdout:
            process.stdout.close()

    if process.returncode == 0:
        return True, "updated"
    detail = lines[-1] if lines else f"exit {process.returncode}"
    return False, _short_error(detail)


SHADOWBOX_SOURCE_EXCLUDES = (
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "*.pyc",
    ".DS_Store",
)
SHADOWSCORE_SOURCE_EXCLUDES = (
    ".git",
    ".agents",
    ".codex",
    "node_modules",
    "data/***",
    "config/*.local.json",
    ".DS_Store",
)


def _rsync_tree(
    source: Path,
    destination: Path,
    excludes: tuple[str, ...],
    *,
    delete: bool = True,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str]:
    destination.mkdir(parents=True, exist_ok=True)
    args = ["rsync", "-a", "--checksum"]
    if delete:
        args.append("--delete")
    for pattern in excludes:
        args.extend(["--exclude", pattern])
    args.extend([f"{source}/", f"{destination}/"])
    return _run_command_with_status(
        args,
        cwd=source,
        env=os.environ.copy(),
        timeout=180.0,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )


def _stage_source_release(
    repo_url: str,
    branch: str,
    temp_root: Path,
    *,
    project: str,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str, Path | None, str]:
    staged = temp_root / "release"
    if status_callback is not None:
        status_callback(f"download {project}")
    ok, detail = _run_command_with_status(
        ["git", "clone", "--depth", "1", "--branch", branch, "--single-branch", repo_url, str(staged)],
        cwd=temp_root,
        env=os.environ.copy(),
        timeout=180.0,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )
    if not ok:
        return False, detail, None, ""
    ok, commit = _run_git_in(staged, "rev-parse", "HEAD")
    if not ok:
        return False, _short_error(commit), None, ""
    shutil.rmtree(staged / ".git", ignore_errors=True)
    _write_source_release(staged, project=project, commit=commit, branch=branch)
    return True, "staged", staged, commit


def _install_staged_source(
    staged: Path,
    destination: Path,
    backup: Path,
    excludes: tuple[str, ...],
    *,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str]:
    if status_callback is not None:
        status_callback("backup current source")
    ok, detail = _rsync_tree(
        destination,
        backup,
        excludes,
        delete=False,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )
    if not ok:
        return False, f"backup failed {detail}"
    if status_callback is not None:
        status_callback("install staged source")
    ok, detail = _rsync_tree(
        staged,
        destination,
        excludes,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )
    if not ok:
        _rsync_tree(backup, destination, excludes)
        return False, f"source install failed {detail}"
    return True, "source installed"


def _restore_source_backup(
    backup: Path,
    destination: Path,
    excludes: tuple[str, ...],
    *,
    status_callback=None,
) -> tuple[bool, str]:
    if status_callback is not None:
        status_callback("restoring previous source")
    return _rsync_tree(backup, destination, excludes, status_callback=status_callback)


def _schedule_shadowbox_restart() -> tuple[bool, str]:
    unit = f"shadowbox-update-restart-{os.getpid()}"
    try:
        result = subprocess.run(
            [
                "sudo",
                "-n",
                "systemd-run",
                "--quiet",
                "--collect",
                f"--unit={unit}",
                "--on-active=2s",
                "/bin/systemctl",
                "restart",
                "shadowbox.service",
            ],
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except FileNotFoundError:
        return False, "systemd-run unavailable"
    except subprocess.TimeoutExpired:
        return False, "restart handoff timeout"
    except Exception as exc:
        return False, _short_error(str(exc))
    detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.returncode == 0, detail


def _detect_shadowscore_service() -> str:
    for service_name in ("shadowscore-server.service", "shadowscore-registration-agent.service"):
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service_name],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except Exception:
            continue
        if result.returncode == 0:
            return service_name
    return "shadowscore-server.service"


def _restart_shadowscore_service(sudo_password: str, status_callback=None, cancel_event=None) -> tuple[bool, str]:
    service_name = _detect_shadowscore_service()
    sudo_error = _validate_sudo_password(sudo_password)
    if sudo_error:
        return False, sudo_error
    if status_callback is not None:
        status_callback(f"restart {service_name.replace('.service', '')}")
    return _run_command_with_status(
        ["sudo", "-n", "systemctl", "restart", service_name],
        cwd=SHADOWSCORE_INSTALL_DIR,
        env=os.environ.copy(),
        timeout=45.0,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )


def start_shadowscore_update_install(sudo_password: str = "", status_callback=None, cancel_event=None) -> SoftwareUpdateStatus:
    sudo_error = _validate_sudo_password(sudo_password)
    if sudo_error:
        return SoftwareUpdateStatus("error", sudo_error)

    env = os.environ.copy()
    env.setdefault("SHADOWSCORE_REPO_URL", SHADOWSCORE_REPO_URL)
    env.setdefault("SHADOWSCORE_INSTALL_DIR", str(SHADOWSCORE_INSTALL_DIR))
    env.setdefault("SHADOWSCORE_ROLE", "host")
    sudo_password_file = ""
    source_temp: Path | None = None
    source_backup: Path | None = None
    if sudo_password:
        try:
            sudo_password_file = _write_sudo_password_file(sudo_password)
            env["SHADOWBOX_SUDO_PASSWORD_FILE"] = sudo_password_file
        except Exception as exc:
            return SoftwareUpdateStatus("error", _short_error(str(exc)))

    try:
        status = read_shadowscore_update_status(fetch=True)
        if status.state == "missing":
            if status_callback is not None:
                status_callback("installing Shadowscore")
            install_command = f"curl -fsSL {SHADOWSCORE_RAW_INSTALLER_URL!r} | bash"
            if sudo_password_file:
                install_command = (
                    "set -e; "
                    "sudo_keepalive() { while true; do sudo -S -p '' -v < \"$SHADOWBOX_SUDO_PASSWORD_FILE\" >/dev/null 2>&1 || exit 1; sleep 45; done; }; "
                    "sudo_keepalive & keeper=$!; "
                    "trap 'kill \"$keeper\" 2>/dev/null || true' EXIT; "
                    f"{install_command}"
                )
            ok, detail = _run_command_with_status(
                ["bash", "-lc", install_command],
                cwd=Path.home(),
                env=env,
                status_callback=status_callback,
                cancel_event=cancel_event,
            )
            if not ok:
                return SoftwareUpdateStatus("error", detail, installed=False)
            return SoftwareUpdateStatus("applied", "installed")

        if status.state == "dirty":
            return SoftwareUpdateStatus(
                "error",
                "local changes",
                branch=status.branch,
                local=status.local,
                remote=status.remote,
                commit_date=status.commit_date,
                dirty=True,
                behind=status.behind,
                ahead=status.ahead,
            )
        if status.state not in {"available", "current"}:
            return status
        if not status.available:
            return status

        if status.layout == "source-copy":
            source_temp = Path(tempfile.mkdtemp(prefix="shadowscore-source-update."))
            ok, detail, staged, _commit = _stage_source_release(
                SHADOWSCORE_REPO_URL,
                status.branch or SHADOWSCORE_BRANCH,
                source_temp,
                project="shadowscore",
                status_callback=status_callback,
                cancel_event=cancel_event,
            )
            if not ok or staged is None:
                return SoftwareUpdateStatus("error", _short_error(detail), branch=status.branch, layout="source-copy")
            if not _is_shadowscore_source_copy(staged):
                return SoftwareUpdateStatus("error", "invalid Shadowscore release", branch=status.branch, layout="source-copy")
            source_backup = source_temp / "backup"
            ok, detail = _install_staged_source(
                staged,
                SHADOWSCORE_INSTALL_DIR,
                source_backup,
                SHADOWSCORE_SOURCE_EXCLUDES,
                status_callback=status_callback,
                cancel_event=cancel_event,
            )
            if not ok:
                return SoftwareUpdateStatus("error", _short_error(detail), branch=status.branch, layout="source-copy")
        else:
            if status_callback is not None:
                status_callback("pulling Shadowscore")
            ok, pull_output = _run_git_in(SHADOWSCORE_INSTALL_DIR, "pull", "--ff-only", timeout=45.0)
            if not ok:
                return SoftwareUpdateStatus(
                    "error",
                    _short_error(pull_output),
                    branch=status.branch,
                    local=status.local,
                    remote=status.remote,
                    commit_date=status.commit_date,
                    dirty=status.dirty,
                    behind=status.behind,
                    ahead=status.ahead,
                )

        if status_callback is not None:
            status_callback("npm deps")
        ok, npm_detail = _run_command_with_status(
            ["npm", "install", "--omit=dev"],
            cwd=SHADOWSCORE_INSTALL_DIR,
            env=env,
            timeout=300.0,
            status_callback=status_callback,
            cancel_event=cancel_event,
        )
        if not ok:
            if source_backup is not None:
                restored, restore_detail = _restore_source_backup(
                    source_backup,
                    SHADOWSCORE_INSTALL_DIR,
                    SHADOWSCORE_SOURCE_EXCLUDES,
                    status_callback=status_callback,
                )
                if not restored:
                    npm_detail = f"{npm_detail}; rollback failed {restore_detail}"
            return SoftwareUpdateStatus("error", _short_error(npm_detail), branch=status.branch, layout=status.layout)

        ok, restart_detail = _restart_shadowscore_service(
            sudo_password,
            status_callback=status_callback,
            cancel_event=cancel_event,
        )
        if not ok:
            if source_backup is not None:
                restored, restore_detail = _restore_source_backup(
                    source_backup,
                    SHADOWSCORE_INSTALL_DIR,
                    SHADOWSCORE_SOURCE_EXCLUDES,
                    status_callback=status_callback,
                )
                if restored:
                    _run_command_with_status(
                        ["npm", "install", "--omit=dev"],
                        cwd=SHADOWSCORE_INSTALL_DIR,
                        env=env,
                        timeout=300.0,
                        status_callback=status_callback,
                        cancel_event=cancel_event,
                    )
                    _restart_shadowscore_service(
                        sudo_password,
                        status_callback=status_callback,
                        cancel_event=cancel_event,
                    )
                else:
                    restart_detail = f"{restart_detail}; rollback failed {restore_detail}"
            return SoftwareUpdateStatus("error", restart_detail, branch=status.branch, layout=status.layout)

        return SoftwareUpdateStatus(
            "applied",
            "updated",
            branch=status.branch,
            local=status.local,
            remote=status.remote,
            commit_date=status.commit_date,
            behind=status.behind,
            ahead=status.ahead,
            layout=status.layout,
        )
    finally:
        if sudo_password_file:
            try:
                os.unlink(sudo_password_file)
            except OSError:
                pass
        if source_temp is not None:
            shutil.rmtree(source_temp, ignore_errors=True)
