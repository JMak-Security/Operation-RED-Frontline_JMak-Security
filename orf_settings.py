"""
ORF runtime settings — Docker container + VPN enablement.

Two toggles, each with three modes:

    off  — feature disabled (ORF ignores it entirely)
    on   — feature required; ORF ensures it is available (and can install it)
    auto — detect and use it if present; degrade gracefully if not

Settings persist to ``orf_settings.json`` next to this module and are managed by
``python main.py settings``. Environment variables (``ORF_DOCKER_MODE`` /
``ORF_VPN_MODE``) provide defaults when the file has no value.

Installing system software (Docker Desktop / Engine, WireGuard) is a heavy,
admin-level, hard-to-reverse action, so ``run_install`` PRINTS the exact
OS-specific command by default and only executes it when ``execute=True`` (the
``--yes`` flag on the CLI).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

MODES = ("off", "on", "auto")
FEATURES = ("docker", "vpn")

_BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = _BASE_DIR / "orf_settings.json"
COMPOSE_FILE = _BASE_DIR / "docker-compose.yml"

# Services brought up by `docker=on` at run time. Defaults to the supporting DB
# sandbox only — NOT `redfront-engine`, which would re-run the whole audit inside
# the container and duplicate a host-side `run`. Override with a comma list in
# ORF_DOCKER_COMPOSE_SERVICES (empty string = the entire stack).
def _default_compose_services() -> Optional[List[str]]:
    raw = os.getenv("ORF_DOCKER_COMPOSE_SERVICES")
    if raw is None:
        return ["postgres-db"]
    raw = raw.strip()
    if not raw:
        return None  # whole stack
    return [s.strip() for s in raw.split(",") if s.strip()]

_DEFAULTS: Dict[str, str] = {"docker": "off", "vpn": "off"}


# Provider roles whose default can be PERSISTED via `settings` (overriding env).
# Target is intentionally excluded: it is normally the SSE system under test.
PROVIDER_ROLES = ("attacker", "judge")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _read_json() -> Dict[str, object]:
    """Return the raw settings dict (empty on missing/corrupt file)."""
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _write_json(data: Dict[str, object]) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _env_default(feature: str) -> Optional[str]:
    raw = os.getenv(f"ORF_{feature.upper()}_MODE", "").strip().lower()
    return raw if raw in MODES else None


def load_settings() -> Dict[str, str]:
    """Return the docker/vpn modes, layering file > env var > built-in default."""
    settings = dict(_DEFAULTS)
    for feat in FEATURES:
        ev = _env_default(feat)
        if ev:
            settings[feat] = ev
    stored = _read_json()
    for feat in FEATURES:
        val = str(stored.get(feat, "")).strip().lower()
        if val in MODES:
            settings[feat] = val
    return settings


def save_settings(settings: Dict[str, str]) -> None:
    """Persist the docker/vpn modes, preserving any other stored keys (providers)."""
    data = _read_json()
    for feat in FEATURES:
        data[feat] = settings.get(feat, _DEFAULTS[feat])
    _write_json(data)


def set_option(feature: str, mode: str) -> Dict[str, str]:
    feature = feature.strip().lower()
    mode = mode.strip().lower()
    if feature not in FEATURES:
        raise ValueError(f"unknown feature {feature!r} (choose from {', '.join(FEATURES)})")
    if mode not in MODES:
        raise ValueError(f"invalid mode {mode!r} (choose from {', '.join(MODES)})")
    settings = load_settings()
    settings[feature] = mode
    save_settings(settings)
    return settings


def load_providers() -> Dict[str, str]:
    """Return persisted provider defaults, e.g. {'attacker': 'groq'}. Only roles
    with a stored value are present."""
    stored = _read_json()
    out: Dict[str, str] = {}
    for role in PROVIDER_ROLES:
        val = str(stored.get(f"{role}_provider", "")).strip().lower()
        if val:
            out[role] = val
    return out


def set_provider(role: str, value: Optional[str]) -> Dict[str, str]:
    """Persist (or clear, when value is falsy/'clear') a role's provider default."""
    role = role.strip().lower()
    if role not in PROVIDER_ROLES:
        raise ValueError(f"unknown role {role!r} (choose from {', '.join(PROVIDER_ROLES)})")
    data = _read_json()
    key = f"{role}_provider"
    if not value or value.strip().lower() == "clear":
        data.pop(key, None)
    else:
        data[key] = value.strip().lower()
    _write_json(data)
    return load_providers()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def _which_any(*names: str) -> Optional[str]:
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def _run_ok(cmd: List[str], timeout: int = 15) -> bool:
    try:
        res = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout
        )
        return res.returncode == 0
    except Exception:
        return False


def _capture(cmd: List[str], timeout: int = 15) -> str:
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return (res.stdout or "") + (res.stderr or "")
    except Exception:
        return ""


def detect_docker() -> Dict[str, object]:
    """Detect the Docker CLI, daemon, and compose plugin."""
    docker_bin = _which_any("docker")
    installed = bool(docker_bin)
    running = bool(docker_bin) and _run_ok([docker_bin, "info"])
    compose = False
    if docker_bin:
        compose = _run_ok([docker_bin, "compose", "version"]) or bool(_which_any("docker-compose"))
    return {
        "installed": installed,
        "running": running,
        "compose": compose,
        "path": docker_bin or "",
    }


def _windows_wireguard() -> Optional[str]:
    """WireGuard on Windows may not be on PATH; check the default install dir."""
    for base in (os.getenv("ProgramFiles", r"C:\Program Files"),
                 os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        if not base:
            continue
        exe = Path(base) / "WireGuard" / "wireguard.exe"
        if exe.exists():
            return str(exe)
    return None


def _active_vpn_interfaces() -> List[str]:
    """Best-effort list of network interfaces that look like an active VPN tunnel."""
    system = platform.system().lower()
    hits: List[str] = []
    markers = ("wireguard", "wg", "tun", "tap", "utun", "vpn", "ppp")
    try:
        if system == "windows":
            out = _capture(["netsh", "interface", "show", "interface"])
            for line in out.splitlines():
                low = line.lower()
                if "connected" in low and any(m in low for m in ("wireguard", "tap", "tun", "vpn", "wg")):
                    hits.append(line.strip())
        else:
            out = _capture(["ip", "-o", "link", "show"]) or _capture(["ifconfig"])
            for line in out.splitlines():
                low = line.lower()
                name = low.split(":")[1].strip() if ":" in low else low
                if any(name.startswith(m) or m in name for m in markers):
                    hits.append(line.strip()[:120])
    except Exception:
        pass
    return hits


def detect_vpn() -> Dict[str, object]:
    """Detect WireGuard / OpenVPN tooling and any active tunnel interface."""
    wg = _which_any("wg", "wireguard") or _windows_wireguard()
    openvpn = _which_any("openvpn")
    active = _active_vpn_interfaces()
    return {
        "wireguard": wg or "",
        "openvpn": openvpn or "",
        "installed": bool(wg or openvpn),
        "active": active,
        "active_count": len(active),
    }


# ---------------------------------------------------------------------------
# Install plans
# ---------------------------------------------------------------------------
def _os_key() -> str:
    s = platform.system().lower()
    if s.startswith("win"):
        return "windows"
    if s == "darwin":
        return "macos"
    return "linux"


def docker_install_plan() -> Dict[str, object]:
    osk = _os_key()
    if osk == "windows":
        cmds = [
            ["winget", "install", "-e", "--id", "Docker.DockerDesktop"],
            ["choco", "install", "docker-desktop", "-y"],
        ]
        note = "Docker Desktop requires a reboot and WSL2 on Windows."
    elif osk == "macos":
        cmds = [["brew", "install", "--cask", "docker"]]
        note = "Launch Docker Desktop once after install to start the daemon."
    else:
        cmds = [["sh", "-c", "curl -fsSL https://get.docker.com | sh"]]
        note = "Then: sudo usermod -aG docker $USER && newgrp docker (to run without sudo)."
    return {"os": osk, "commands": cmds, "note": note,
            "url": "https://docs.docker.com/get-docker/"}


def wireguard_install_plan() -> Dict[str, object]:
    osk = _os_key()
    if osk == "windows":
        cmds = [
            ["winget", "install", "-e", "--id", "WireGuard.WireGuard"],
            ["choco", "install", "wireguard", "-y"],
        ]
        note = "Import a .conf tunnel in the WireGuard app, then activate it."
    elif osk == "macos":
        cmds = [["brew", "install", "wireguard-tools"]]
        note = "Place your tunnel at /usr/local/etc/wireguard/wg0.conf, then: wg-quick up wg0"
    else:
        cmds = [["sh", "-c", "sudo apt-get update && sudo apt-get install -y wireguard"]]
        note = "Place your tunnel at /etc/wireguard/wg0.conf, then: sudo wg-quick up wg0"
    return {"os": osk, "commands": cmds, "note": note,
            "url": "https://www.wireguard.com/install/"}


def _first_runnable(commands: List[List[str]]) -> Optional[List[str]]:
    """Pick the first command whose leading tool is on PATH."""
    for cmd in commands:
        lead = cmd[0]
        if lead in ("sh", "bash", "cmd"):
            return cmd  # shell wrapper — assume available
        if shutil.which(lead):
            return cmd
    return None


def run_install(kind: str, execute: bool = False, printer=print) -> int:
    """Show (and optionally run) the install plan for ``docker`` or ``vpn``.

    Returns 0 on success / plan-shown, non-zero on a failed execution.
    """
    kind = kind.strip().lower()
    if kind in ("vpn", "wireguard"):
        plan = wireguard_install_plan()
        label = "WireGuard (VPN)"
    elif kind == "docker":
        plan = docker_install_plan()
        label = "Docker"
    else:
        printer(f"[settings] unknown install target {kind!r}")
        return 2

    printer(f"[settings] Install plan for {label} on {plan['os']}:")
    for cmd in plan["commands"]:
        printer("    " + " ".join(cmd))
    printer(f"    note: {plan['note']}")
    printer(f"    docs: {plan['url']}")

    if not execute:
        printer("[settings] dry-run — re-run with --yes to execute the first available command.")
        return 0

    chosen = _first_runnable(plan["commands"])
    if not chosen:
        printer("[settings] no supported package manager found on PATH; install manually via the docs URL.")
        return 1

    printer(f"[settings] executing: {' '.join(chosen)}")
    try:
        res = subprocess.run(chosen)
        if res.returncode == 0:
            printer(f"[settings] {label} install command finished (exit 0).")
        else:
            printer(f"[settings] install command exited {res.returncode}.")
        return res.returncode
    except Exception as exc:
        printer(f"[settings] install failed: {exc}")
        return 1


# ---------------------------------------------------------------------------
# Docker compose sandbox control
# ---------------------------------------------------------------------------
def _compose_prefix(docker_bin: str) -> Optional[List[str]]:
    """Return the compose command prefix: `docker compose` or `docker-compose`."""
    if docker_bin and _run_ok([docker_bin, "compose", "version"]):
        return [docker_bin, "compose"]
    legacy = _which_any("docker-compose")
    if legacy:
        return [legacy]
    return None


def _compose_run(action: str, execute: bool, services: Optional[List[str]],
                 extra: List[str], printer) -> int:
    """Shared plan/execute path for `up` / `down`."""
    if not COMPOSE_FILE.exists():
        printer(f"[settings] no compose file at {COMPOSE_FILE}")
        return 1
    d = detect_docker()
    if not d["installed"]:
        printer("[settings] Docker is not installed — cannot run compose.")
        return 1
    prefix = _compose_prefix(d["path"])
    if not prefix:
        printer("[settings] no `docker compose` / `docker-compose` available.")
        return 1

    cmd = prefix + ["-f", str(COMPOSE_FILE), action] + extra
    if services:
        cmd += services
    printer(f"[settings] compose {action}: {' '.join(cmd)}")

    if not execute:
        printer("[settings] dry-run — add --yes to execute.")
        return 0
    if not d["running"]:
        printer("[settings] Docker daemon is not running — start Docker Desktop / the engine first.")
        return 1
    try:
        res = subprocess.run(cmd, cwd=str(_BASE_DIR))
        printer(f"[settings] compose {action} exited {res.returncode}.")
        return res.returncode
    except Exception as exc:
        printer(f"[settings] compose {action} failed: {exc}")
        return 1


def docker_compose_up(execute: bool = False, detach: bool = True,
                      services: Optional[List[str]] = None, printer=print) -> int:
    """Bring up the Docker sandbox (default: the supporting DB service only)."""
    if services is None:
        services = _default_compose_services()
    extra = ["-d"] if detach else []
    return _compose_run("up", execute, services, extra, printer)


def docker_compose_down(execute: bool = False, printer=print) -> int:
    """Tear down the whole Docker sandbox stack."""
    return _compose_run("down", execute, None, [], printer)


# ---------------------------------------------------------------------------
# Runtime application
# ---------------------------------------------------------------------------
def _log(logger, level: str, msg: str) -> None:
    if logger is not None:
        getattr(logger, level, logger.info)(msg)
    else:
        print(msg)


def apply_settings(
    settings: Optional[Dict[str, str]] = None,
    *,
    logger=None,
    assume_yes: bool = False,
    allow_install: bool = True,
) -> Dict[str, object]:
    """Enforce the Docker / VPN settings before a run.

    Returns ``{"ok": bool, "docker": {...}, "vpn": {...}}``. ``ok`` is False only
    when an ``on`` (required) feature could not be satisfied — the caller decides
    whether that is fatal (it is for ``run``).
    """
    settings = settings or load_settings()
    result: Dict[str, object] = {"ok": True}

    # ---- Docker ----
    dmode = settings.get("docker", "off")
    d = {"skipped": True}
    if dmode != "off":
        d = detect_docker()
        if d["running"]:
            _log(logger, "info", f"[settings] Docker: enabled and running ({d['path']}).")
            # docker=on brings up the sandbox stack automatically (behind --yes);
            # auto mode only reports and leaves the stack untouched.
            if dmode == "on" and allow_install and assume_yes:
                svcs = _default_compose_services()
                label = ", ".join(svcs) if svcs else "full stack"
                _log(logger, "info", f"[settings] Docker: bringing up sandbox ({label})...")
                rc = docker_compose_up(execute=True, printer=lambda m: _log(logger, "info", m))
                if rc != 0:
                    _log(logger, "warning", "[settings] compose up failed — continuing on host.")
            elif dmode == "on":
                _log(logger, "info",
                     "[settings] Docker: pass --yes to auto `docker compose up` the sandbox, "
                     "or run: python main.py settings --compose-up --yes")
        elif d["installed"]:
            msg = "[settings] Docker installed but the daemon is not running — start Docker Desktop / the engine."
            if dmode == "on":
                _log(logger, "error", msg + " (required by docker=on)")
                result["ok"] = False
            else:
                _log(logger, "warning", msg + " (auto → continuing on host)")
        else:
            if dmode == "on":
                _log(logger, "error", "[settings] Docker required (docker=on) but not installed.")
                if allow_install and assume_yes:
                    if run_install("docker", execute=True,
                                   printer=lambda m: _log(logger, "info", m)) == 0:
                        result["ok"] = detect_docker()["installed"]
                    else:
                        result["ok"] = False
                else:
                    _log(logger, "error", "[settings] run: python main.py settings --install-docker --yes")
                    result["ok"] = False
            else:
                _log(logger, "warning",
                     "[settings] Docker not installed (auto → continuing on host). "
                     "Install: python main.py settings --install-docker")
    result["docker"] = d

    # ---- VPN ----
    vmode = settings.get("vpn", "off")
    v = {"skipped": True}
    if vmode != "off":
        v = detect_vpn()
        if v["active"]:
            _log(logger, "info",
                 f"[settings] VPN: active tunnel detected ({v['active_count']}) — using existing connection.")
        elif v["installed"]:
            _log(logger, "info",
                 f"[settings] VPN tooling present ({v['wireguard'] or v['openvpn']}) but no active tunnel "
                 "— activate your tunnel (e.g. wg-quick up wg0).")
            if vmode == "on":
                _log(logger, "error", "[settings] VPN required (vpn=on) but no tunnel is active.")
                result["ok"] = False
        else:
            # No VPN at all → per policy, fall back to installing WireGuard.
            _log(logger, "warning", "[settings] No VPN detected — WireGuard is the fallback.")
            if allow_install and assume_yes:
                run_install("vpn", execute=True, printer=lambda m: _log(logger, "info", m))
                v = detect_vpn()
                if vmode == "on" and not v["installed"]:
                    result["ok"] = False
            else:
                _log(logger, "warning",
                     "[settings] install WireGuard: python main.py settings --install-vpn --yes")
                if vmode == "on":
                    result["ok"] = False
    result["vpn"] = v

    return result


def status_report(settings: Optional[Dict[str, str]] = None) -> str:
    """Human-readable status of both features (for `settings` with no changes)."""
    settings = settings or load_settings()
    d = detect_docker()
    v = detect_vpn()
    lines = [
        "ORF settings",
        f"  file        : {SETTINGS_PATH}",
        "",
        f"  docker mode : {settings['docker']}",
        f"    installed : {'yes' if d['installed'] else 'no'}"
        + (f"  ({d['path']})" if d["path"] else ""),
        f"    daemon    : {'running' if d['running'] else 'not running'}",
        f"    compose   : {'yes' if d['compose'] else 'no'}",
        "",
        f"  vpn mode    : {settings['vpn']}",
        f"    wireguard : {v['wireguard'] or 'not found'}",
        f"    openvpn   : {v['openvpn'] or 'not found'}",
        f"    active    : {v['active_count']} tunnel(s)"
        + (f" — {v['active'][0]}" if v["active"] else ""),
    ]
    return "\n".join(lines)
