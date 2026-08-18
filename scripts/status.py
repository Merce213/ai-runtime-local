#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


RUNTIME_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = RUNTIME_ROOT / "config" / "runtime.yaml"
PROFILES_DIR = RUNTIME_ROOT / "profiles"

HERMES_READER = RUNTIME_ROOT / "scripts" / "hermes.py"
OPENCODE_READER = RUNTIME_ROOT / "scripts" / "opencode.py"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"{path} must contain a YAML object"
        )

    return data


def load_runtime() -> dict[str, Any]:
    return load_yaml(CONFIG_PATH)


def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}

    if not PROFILES_DIR.exists():
        return profiles

    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        profile = load_yaml(path)

        if not profile.get("model"):
            continue

        profile["_name"] = path.stem
        profiles[path.stem] = profile

    return profiles


def get_active_profile_name(
    runtime: dict[str, Any],
) -> str:
    active = runtime.get("active_profile")

    if not active:
        raise RuntimeError(
            "runtime.yaml does not define active_profile"
        )

    return str(active)


def get_server_info() -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8080/props",
            timeout=3,
        ) as response:
            data = json.load(response)

        if not isinstance(data, dict):
            return None

        return data

    except (
        OSError,
        urllib.error.URLError,
        TimeoutError,
    ):
        return None


def get_process_status() -> tuple[bool, str | None]:
    command = r"""
Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" |
    Select-Object -First 1 ProcessId |
    ConvertTo-Json -Compress
"""

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if (
        result.returncode != 0
        or not result.stdout.strip()
    ):
        return False, None

    try:
        data = json.loads(result.stdout)

        if (
            isinstance(data, dict)
            and data.get("ProcessId") is not None
        ):
            return True, str(data["ProcessId"])

    except json.JSONDecodeError:
        return False, None

    return False, None


def get_reader_value(
    path: Path,
    key: str,
) -> str | None:
    if not path.is_file():
        return None

    result = subprocess.run(
        ["python3", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    prefix = f"{key}="

    for line in result.stdout.splitlines():
        line = line.strip()

        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return None


def get_command_output(
    command: list[str],
) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)

    if result.returncode != 0:
        return False, result.stderr.strip()

    return True, result.stdout.strip()


def get_command_version(
    command: list[str],
) -> tuple[bool, str]:
    return get_command_output(command)


def print_row(
    label: str,
    value: str,
) -> None:
    print(f"  {label:<20} {value}")


def main() -> int:
    try:
        runtime = load_runtime()
        profiles = load_profiles()
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    try:
        active_name = get_active_profile_name(runtime)
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    active = profiles.get(active_name)

    if active is None:
        print(
            f"error: active profile '{active_name}' "
            "was not found"
        )
        return 1

    expected_model = str(
        active.get("model", "unknown")
    )

    expected_context = str(
        active.get("context_length", "unknown")
    )

    expected_slots = str(
        active.get("slots", "unknown")
    )

    expected_opencode_model = (
        f"llama.cpp/{expected_model}"
    )

    server = get_server_info()
    process_running, pid = get_process_status()

    print()
    print("========================================")
    print("            AI Runtime Status")
    print("========================================")
    print()

    # =========================================================
    # Runtime
    # =========================================================

    print("[Runtime]")

    print_row(
        "Active profile:",
        active_name,
    )

    print_row(
        "Model:",
        expected_model,
    )

    print_row(
        "Context:",
        expected_context,
    )

    print_row(
        "Slots:",
        expected_slots,
    )

    print()

    # =========================================================
    # llama.cpp
    # =========================================================

    print("[llama.cpp]")

    if process_running and server is not None:
        generation = server.get(
            "default_generation_settings",
            {},
        )

        server_context = str(
            generation.get("n_ctx", "unknown")
        )

        server_model = str(
            server.get("model_alias", "unknown")
        )

        server_slots = str(
            server.get("total_slots", "unknown")
        )

        print_row(
            "Status:",
            "running",
        )

        print_row(
            "PID:",
            pid or "unknown",
        )

        print_row(
            "Model:",
            server_model,
        )

        print_row(
            "Context:",
            server_context,
        )

        print_row(
            "Slots:",
            server_slots,
        )

        print_row(
            "Model match:",
            "YES"
            if server_model == expected_model
            else "NO",
        )

        print_row(
            "Context match:",
            "YES"
            if server_context == expected_context
            else "NO",
        )

        print_row(
            "Slots match:",
            "YES"
            if server_slots == expected_slots
            else "NO",
        )

        capabilities = server.get(
            "chat_template_caps",
            {},
        )

        print_row(
            "Tools:",
            "yes"
            if capabilities.get(
                "supports_tools",
                False,
            )
            else "no",
        )

        print_row(
            "Tool calls:",
            "yes"
            if capabilities.get(
                "supports_tool_calls",
                False,
            )
            else "no",
        )

        print_row(
            "Parallel tools:",
            "yes"
            if capabilities.get(
                "supports_parallel_tool_calls",
                False,
            )
            else "no",
        )

    elif process_running:
        print_row(
            "Status:",
            "running",
        )

        print_row(
            "PID:",
            pid or "unknown",
        )

        print_row(
            "API:",
            "unreachable",
        )

    else:
        print_row(
            "Status:",
            "stopped",
        )

    print()

    # =========================================================
    # Hermes
    # =========================================================

    print("[Hermes]")

    hermes_ok, hermes_version = get_command_version(
        ["hermes", "--version"]
    )

    print_row(
        "Installed:",
        "yes" if hermes_ok else "no",
    )

    if hermes_ok:
        print_row(
            "Version:",
            hermes_version.splitlines()[0]
            if hermes_version
            else "unknown",
        )

    hermes_model = get_reader_value(
        HERMES_READER,
        "model",
    )

    print_row(
        "Model:",
        hermes_model or "unknown",
    )

    print_row(
        "Model match:",
        "YES"
        if hermes_model == expected_model
        else "NO",
    )

    print()

    # =========================================================
    # OpenCode
    # =========================================================

    print("[OpenCode]")

    opencode_ok, opencode_version = get_command_version(
        ["opencode", "--version"]
    )

    print_row(
        "Installed:",
        "yes" if opencode_ok else "no",
    )

    if opencode_ok:
        print_row(
            "Version:",
            opencode_version.splitlines()[0]
            if opencode_version
            else "unknown",
        )

    opencode_model = get_reader_value(
        OPENCODE_READER,
        "model",
    )

    print_row(
        "Model:",
        opencode_model or "unknown",
    )

    print_row(
        "Model match:",
        "YES"
        if opencode_model
        == expected_opencode_model
        else "NO",
    )

    print()

    # =========================================================
    # Docker
    # =========================================================

    print("[Docker]")

    docker_ok, docker_version = get_command_version(
        ["docker", "--version"]
    )

    print_row(
        "CLI:",
        "available"
        if docker_ok
        else "missing",
    )

    if docker_ok:
        print_row(
            "Version:",
            docker_version,
        )

        docker_daemon_ok, _ = get_command_output(
            ["docker", "info"]
        )

        print_row(
            "Daemon:",
            "running"
            if docker_daemon_ok
            else "stopped",
        )

    print()

    # =========================================================
    # KinéFlow
    # =========================================================

    print("[KinéFlow]")

    projects = runtime.get("projects", {})
    project = projects.get("kineflow", {})

    if not isinstance(project, dict):
        print_row(
            "Workspace:",
            "invalid configuration",
        )
    else:
        project_path_value = project.get("path")

        if not project_path_value:
            print_row(
                "Workspace:",
                "not configured",
            )
        else:
            project_path = Path(
                str(project_path_value)
            )

            print_row(
                "Workspace:",
                "available"
                if project_path.is_dir()
                else "missing",
            )

            print_row(
                "Git:",
                "yes"
                if (project_path / ".git").is_dir()
                else "no",
            )

    print()
    print("========================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())