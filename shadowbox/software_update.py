#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import os
import signal
import tempfile
from dataclasses import dataclass

from shadowbox.version import REPO_ROOT


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
            "available": self.available,
        }


def _run_git(*args: str, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
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
        return SoftwareUpdateStatus("nogit", "not a git checkout")

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
    timeout: float = 900.0,
    status_callback=None,
    cancel_event=None,
) -> tuple[bool, str]:
    installer = REPO_ROOT / "install.sh"
    process = subprocess.Popen(
        [str(installer)],
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
        return SoftwareUpdateStatus("error", "install.sh missing", branch=status.branch)

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

    try:
        ok, detail = _run_installer(env, status_callback=status_callback, cancel_event=cancel_event)
    except Exception as exc:
        if sudo_password_file:
            try:
                os.unlink(sudo_password_file)
            except OSError:
                pass
        try:
            os.unlink(status_path)
        except OSError:
            pass
        return SoftwareUpdateStatus("error", _short_error(str(exc)), branch=status.branch)

    try:
        os.unlink(status_path)
    except OSError:
        pass
    if not ok:
        if sudo_password_file:
            try:
                os.unlink(sudo_password_file)
            except OSError:
                pass
        return SoftwareUpdateStatus(
            "error",
            _short_error(detail),
            branch=status.branch,
            local=status.local,
            remote=status.remote,
            commit_date=status.commit_date,
        )

    return SoftwareUpdateStatus(
        "applied",
        detail,
        branch=status.branch,
        local=status.local,
        remote=status.remote,
        commit_date=status.commit_date,
        behind=status.behind,
        ahead=status.ahead,
    )
