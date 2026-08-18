#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


RUNTIME_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = RUNTIME_ROOT / "config" / "runtime.yaml"
PROFILES_DIR = RUNTIME_ROOT / "profiles"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")

    return data


def load_runtime() -> dict[str, Any]:
    return load_yaml(CONFIG_PATH)


def list_profiles() -> dict[str, dict[str, Any]]:
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


def load_profile(profile_name: str) -> dict[str, Any]:
    profiles = list_profiles()

    if profile_name in profiles:
        return profiles[profile_name]

    for profile in profiles.values():
        if profile.get("model") == profile_name:
            return profile

    available = ", ".join(sorted(profiles))

    raise RuntimeError(
        f"Profile not found: {profile_name}. "
        f"Available profiles: {available}"
    )


def load_active_profile(runtime: dict[str, Any]) -> dict[str, Any]:
    active = runtime.get("active_profile")

    if not active:
        raise RuntimeError(
            "runtime.yaml does not define active_profile"
        )

    return load_profile(str(active))


def powershell(script: str) -> str:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or f"PowerShell failed with exit code {result.returncode}"
        )

    return result.stdout.strip()


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def get_running_processes() -> list[dict[str, Any]]:
    script = r"""
$processes = @(
    Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" |
    Select-Object ProcessId, CommandLine
)

$processes | ConvertTo-Json -Compress
"""

    output = powershell(script)

    if not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse Windows process information: {exc}"
        ) from exc

    if isinstance(data, dict):
        return [data]

    if isinstance(data, list):
        return data

    return []


def find_running_profile(
    profiles: dict[str, dict[str, Any]],
) -> tuple[str, int] | None:
    processes = get_running_processes()

    for profile_name, profile in profiles.items():
        server = profile.get("server")

        if not isinstance(server, dict):
            continue

        alias = server.get("alias")

        if not alias:
            continue

        alias = str(alias)

        for process in processes:
            command_line = str(process.get("CommandLine") or "")
            pid = process.get("ProcessId")

            if alias in command_line and pid is not None:
                return profile_name, int(pid)

    return None


def find_profile_process(
    profile: dict[str, Any],
) -> int | None:
    server = profile.get("server")

    if not isinstance(server, dict):
        raise RuntimeError(
            f"Profile {profile.get('_name', '<unknown>')} "
            "has no server configuration"
        )

    alias = server.get("alias")

    if not alias:
        raise RuntimeError(
            f"Profile {profile.get('_name', '<unknown>')} "
            "has no server.alias"
        )

    alias = str(alias)

    processes = get_running_processes()

    for process in processes:
        command_line = str(process.get("CommandLine") or "")
        pid = process.get("ProcessId")

        if alias in command_line and pid is not None:
            return int(pid)

    return None


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=3) as response:
        data = json.load(response)

    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON returned by {url}")

    return data


def wait_for_server(
    endpoint: str,
    expected_model: str,
    timeout: int = 90,
) -> None:
    deadline = time.monotonic() + timeout
    models_url = f"{endpoint.rstrip('/')}/models"

    last_error = "unknown"

    while time.monotonic() < deadline:
        try:
            data = get_json(models_url)

            models = data.get("data", [])

            model_ids = {
                model.get("id")
                for model in models
                if isinstance(model, dict)
            }

            if expected_model in model_ids:
                return

            last_error = (
                f"server reachable, but model "
                f"{expected_model!r} was not reported"
            )

        except (
            OSError,
            urllib.error.URLError,
            RuntimeError,
        ) as exc:
            last_error = str(exc)

        time.sleep(1)

    raise RuntimeError(
        f"llama-server did not become ready within "
        f"{timeout}s: {last_error}"
    )


def wait_for_process_exit(
    pid: int,
    timeout: int = 15,
) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        processes = get_running_processes()

        alive = any(
            int(process.get("ProcessId", -1)) == pid
            for process in processes
        )

        if not alive:
            return True

        time.sleep(0.5)

    return False


def build_arguments(profile: dict[str, Any]) -> list[str]:
    server = profile["server"]

    arguments = [
        "-m",
        str(server["model_path"]),
        "--alias",
        str(server["alias"]),
        "--port",
        str(server["port"]),
    ]

    arguments.extend(
        str(value)
        for value in server.get("arguments", [])
    )

    return arguments


def start_profile(profile: dict[str, Any]) -> None:
    server = profile["server"]

    executable = str(server["executable"])
    working_directory = str(server["working_directory"])

    args = build_arguments(profile)

    powershell_arguments = ",".join(
        ps_quote(value)
        for value in args
    )

    script = (
        f"$p = Start-Process "
        f"-FilePath {ps_quote(executable)} "
        f"-WorkingDirectory {ps_quote(working_directory)} "
        f"-ArgumentList @({powershell_arguments}) "
        f"-WindowStyle Hidden "
        f"-PassThru; "
        f"Write-Output $p.Id"
    )

    pid_output = powershell(script)

    try:
        pid = int(pid_output)
    except ValueError as exc:
        raise RuntimeError(
            f"Windows returned an invalid PID: {pid_output!r}"
        ) from exc

    print(f"Started llama-server (PID {pid})")
    print(f"Profile: {profile['_name']}")
    print(f"Model: {profile['model']}")
    print(f"Endpoint: {profile['endpoint']}")
    print("Waiting for server...")

    try:
        wait_for_server(
            endpoint=str(profile["endpoint"]),
            expected_model=str(profile["model"]),
        )
    except Exception:
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            pass

        raise

    print("llama-server is ready")


def stop_profile(
    profile: dict[str, Any],
    *,
    quiet: bool = False,
) -> bool:
    pid = find_profile_process(profile)

    if pid is None:
        if not quiet:
            print(
                f"Profile {profile['_name']} is not running"
            )
        return False

    print(
        f"Stopping profile {profile['_name']} "
        f"(PID {pid})"
    )

    result = subprocess.run(
        [
            "taskkill.exe",
            "/PID",
            str(pid),
            "/T",
            "/F",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        stderr = (
            result.stderr.decode("utf-8", errors="replace").strip()
            if result.stderr
            else ""
        )

        raise RuntimeError(
            "Failed to stop llama-server "
            f"(PID {pid}). "
            f"{stderr or 'taskkill failed'}"
        )

    if not wait_for_process_exit(pid):
        raise RuntimeError(
            f"llama-server PID {pid} is still running "
            "after the stop request"
        )

    print(
        f"Stopped profile {profile['_name']} "
        f"(PID {pid})"
    )

    return True


def start(profile: dict[str, Any]) -> None:
    profiles = list_profiles()

    running = find_running_profile(profiles)

    if running is not None:
        running_name, running_pid = running

        if running_name == profile["_name"]:
            print(
                f"Profile {profile['_name']} is already running "
                f"(PID {running_pid})"
            )
            return

        print(
            f"Switching from {running_name} "
            f"(PID {running_pid}) "
            f"to {profile['_name']}"
        )

        stop_profile(profiles[running_name])

        time.sleep(1)

    start_profile(profile)


def stop(profile: dict[str, Any]) -> None:
    stop_profile(profile)


def up() -> None:
    runtime = load_runtime()
    profiles = list_profiles()
    active = load_active_profile(runtime)

    running = find_running_profile(profiles)

    if running is not None:
        running_name, running_pid = running

        if running_name == active["_name"]:
            print(
                f"Active profile {active['_name']} is already running "
                f"(PID {running_pid})"
            )
        else:
            print(
                f"Switching from {running_name} "
                f"(PID {running_pid}) "
                f"to {active['_name']}"
            )

            stop_profile(profiles[running_name])
            time.sleep(1)
            start_profile(active)
    else:
        start_profile(active)


def down() -> None:
    profiles = list_profiles()

    running = find_running_profile(profiles)

    if running is None:
        print(
            "No AIRuntime-managed llama-server is running"
        )
        return

    running_name, running_pid = running
    profile = profiles[running_name]

    print(
        f"Stopping active AIRuntime profile "
        f"{running_name} (PID {running_pid})"
    )

    stop_profile(profile)


def status(
    profile: dict[str, Any] | None,
) -> None:
    profiles = list_profiles()

    if profile is None:
        running = find_running_profile(profiles)

        if running is None:
            print("Status: stopped")
            return

        running_name, pid = running
        running_profile = profiles[running_name]

        print(f"Profile: {running_name}")
        print("Status: running")
        print(f"PID: {pid}")
        print(f"Model: {running_profile['model']}")
        print(f"Endpoint: {running_profile['endpoint']}")
        return

    pid = find_profile_process(profile)

    print(f"Profile: {profile['_name']}")

    if pid is None:
        print("Status: stopped")
        return

    print("Status: running")
    print(f"PID: {pid}")
    print(f"Model: {profile['model']}")
    print(f"Endpoint: {profile['endpoint']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIRuntime llama.cpp server controller"
    )

    parser.add_argument(
        "command",
        choices=(
            "status",
            "start",
            "stop",
            "up",
            "down",
        ),
    )

    parser.add_argument(
        "--profile",
        default=None,
        help="Profile name or model name",
    )

    args = parser.parse_args()

    try:
        runtime = load_runtime()

        if args.command == "up":
            if args.profile:
                raise RuntimeError(
                    "'ai up' uses active_profile. "
                    "Use 'ai server start --profile NAME' "
                    "for an explicit profile."
                )

            up()
            return 0

        if args.command == "down":
            if args.profile:
                raise RuntimeError(
                    "'ai down' manages the currently running "
                    "AIRuntime server. "
                    "Use 'ai server stop --profile NAME' "
                    "for an explicit profile."
                )

            down()
            return 0

        if args.profile:
            profile = load_profile(args.profile)
        else:
            profile = load_active_profile(runtime)

        if args.command == "status":
            status(profile)

        elif args.command == "start":
            start(profile)

        elif args.command == "stop":
            stop(profile)

        return 0

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())