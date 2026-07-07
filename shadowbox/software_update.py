#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import os
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path

from shadowbox.version import REPO_ROOT

SHADOWSCORE_REPO_URL = "https://github.com/stretta/ShadowscoreServer.git"
SHADOWSCORE_RAW_INSTALLER_URL = "https://raw.githubusercontent.com/stretta/ShadowscoreServer/main/deploy/install-shadowscore.sh"
SHADOWSCORE_INSTALL_DIR = Path(os.environ.get("SHADOWSCORE_INSTALL_DIR", "/home/pi/ShadowscoreServer"))


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


def read_all_software_update_status(fetch: bool = False) -> dict:
    shadowbox = read_software_update_status(fetch=fetch).to_dict()
    shadowscore = read_shadowscore_update_status(fetch=fetch).to_dict()
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
        return SoftwareUpdateStatus("missing", "not installed", installed=False)

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
            line = process.stdout.readline() if process.stdout else ""
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
        ["sudo", "-S", "-p", "", "systemctl", "restart", service_name],
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
            return SoftwareUpdateStatus("error", npm_detail, branch=status.branch)

        ok, restart_detail = _restart_shadowscore_service(
            sudo_password,
            status_callback=status_callback,
            cancel_event=cancel_event,
        )
        if not ok:
            return SoftwareUpdateStatus("error", restart_detail, branch=status.branch)

        return SoftwareUpdateStatus(
            "applied",
            "updated",
            branch=status.branch,
            local=status.local,
            remote=status.remote,
            commit_date=status.commit_date,
            behind=status.behind,
            ahead=status.ahead,
        )
    finally:
        if sudo_password_file:
            try:
                os.unlink(sudo_password_file)
            except OSError:
                pass
