#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


RUNTIME_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = RUNTIME_ROOT / "config" / "runtime.yaml"
PROFILES_DIR = RUNTIME_ROOT / "profiles"

HERMES_CONFIG_PATH = (
    Path.home()
    / ".hermes"
    / "config.yaml"
)

OPENCODE_CONFIG_PATH = (
    Path.home()
    / ".config"
    / "opencode"
    / "opencode.jsonc"
)

BACKUP_ROOT = (
    Path.home()
    / ".local"
    / "share"
    / "ai-runtime"
    / "backups"
)


@dataclass(frozen=True)
class Backup:
    original: Path
    backup: Path


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

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


def get_active_profile(
    runtime: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    active_name = runtime.get("active_profile")

    if not active_name:
        raise RuntimeError(
            "runtime.yaml does not define active_profile"
        )

    profile = profiles.get(str(active_name))

    if profile is None:
        raise RuntimeError(
            f"Active profile '{active_name}' was not found"
        )

    return profile


def get_hermes_model() -> str | None:
    result = subprocess.run(
        [
            "python3",
            str(RUNTIME_ROOT / "scripts" / "hermes.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("model="):
            return line[len("model="):].strip()

    return None


def strip_jsonc(text: str) -> str:
    text = re.sub(
        r"/\*.*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(^|[^:])//.*$",
        r"\1",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r",(\s*[}\]])",
        r"\1",
        text,
    )

    return text


def get_opencode_model() -> str | None:
    if not OPENCODE_CONFIG_PATH.is_file():
        return None

    content = OPENCODE_CONFIG_PATH.read_text(
        encoding="utf-8"
    )

    cleaned = strip_jsonc(content)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    model = data.get("model")

    if not isinstance(model, str):
        return None

    return model


def print_check(
    label: str,
    expected: str,
    actual: str | None,
) -> bool:
    actual_display = actual or "unknown"

    if actual == expected:
        print(f"  ✓ {label}")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual_display}")
        return True

    print(f"  ✗ {label}")
    print(f"      expected: {expected}")
    print(f"      actual:   {actual_display}")
    return False


def create_backup_directory() -> Path:
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    backup_dir = BACKUP_ROOT / timestamp
    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    return backup_dir


def backup_file(
    path: Path,
    backup_dir: Path,
) -> Backup | None:
    if not path.exists():
        return None

    backup_path = backup_dir / path.name

    shutil.copy2(
        path,
        backup_path,
    )

    return Backup(
        original=path,
        backup=backup_path,
    )


def restore_backups(
    backups: list[Backup],
) -> None:
    for backup in reversed(backups):
        shutil.copy2(
            backup.backup,
            backup.original,
        )


def run_command(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def apply_hermes_model(
    expected_model: str,
) -> None:
    result = run_command(
        [
            "hermes",
            "config",
            "set",
            "model.default",
            expected_model,
        ]
    )

    if result.returncode != 0:
        details = (
            result.stderr.strip()
            or result.stdout.strip()
            or "unknown Hermes configuration error"
        )

        raise RuntimeError(
            f"Failed to configure Hermes: {details}"
        )


def replace_opencode_model(
    expected_model: str,
) -> None:
    if not OPENCODE_CONFIG_PATH.is_file():
        raise RuntimeError(
            f"OpenCode configuration not found: "
            f"{OPENCODE_CONFIG_PATH}"
        )

    content = OPENCODE_CONFIG_PATH.read_text(
        encoding="utf-8"
    )

    expected_opencode_model = (
        f"llama.cpp/{expected_model}"
    )

    top_level_model_pattern = re.compile(
        r'(?m)^(\s*"model"\s*:\s*")([^"]*)("\s*,?\s*)$'
    )

    match = top_level_model_pattern.search(content)

    if match is None:
        raise RuntimeError(
            "Could not locate the top-level OpenCode "
            '"model" property'
        )

    replacement = (
        f"{match.group(1)}"
        f"{expected_opencode_model}"
        f"{match.group(3)}"
    )

    updated = (
        content[:match.start()]
        + replacement
        + content[match.end():]
    )

    if updated == content:
        return

    OPENCODE_CONFIG_PATH.write_text(
        updated,
        encoding="utf-8",
    )


def apply_changes(
    expected_model: str,
) -> list[Backup]:
    backup_dir = create_backup_directory()

    backups: list[Backup] = []

    try:
        hermes_backup = backup_file(
            HERMES_CONFIG_PATH,
            backup_dir,
        )

        if hermes_backup is not None:
            backups.append(hermes_backup)

        opencode_backup = backup_file(
            OPENCODE_CONFIG_PATH,
            backup_dir,
        )

        if opencode_backup is not None:
            backups.append(opencode_backup)

        if hermes_backup is None:
            raise RuntimeError(
                f"Hermes configuration not found: "
                f"{HERMES_CONFIG_PATH}"
            )

        if opencode_backup is None:
            raise RuntimeError(
                f"OpenCode configuration not found: "
                f"{OPENCODE_CONFIG_PATH}"
            )

        print(
            f"  Backup created: {backup_dir}"
        )

        current_hermes = get_hermes_model()

        if current_hermes != expected_model:
            print(
                f"  Applying Hermes model: "
                f"{current_hermes or 'unknown'} "
                f"→ {expected_model}"
            )

            apply_hermes_model(
                expected_model
            )
        else:
            print(
                "  Hermes already synchronized"
            )

        expected_opencode_model = (
            f"llama.cpp/{expected_model}"
        )

        current_opencode = get_opencode_model()

        if current_opencode != expected_opencode_model:
            print(
                f"  Applying OpenCode model: "
                f"{current_opencode or 'unknown'} "
                f"→ {expected_opencode_model}"
            )

            replace_opencode_model(
                expected_model
            )
        else:
            print(
                "  OpenCode already synchronized"
            )

        return backups

    except Exception:
        restore_backups(backups)
        raise


def verify_final_state(
    expected_model: str,
) -> tuple[bool, bool]:
    expected_opencode_model = (
        f"llama.cpp/{expected_model}"
    )

    hermes_model = get_hermes_model()
    opencode_model = get_opencode_model()

    hermes_ok = (
        hermes_model == expected_model
    )

    opencode_ok = (
        opencode_model
        == expected_opencode_model
    )

    print()
    print("[Verification]")

    if hermes_ok:
        print(
            "  ✓ Hermes synchronized"
        )
        print(
            f"      model: {hermes_model}"
        )
    else:
        print(
            "  ✗ Hermes synchronization failed"
        )
        print(
            f"      expected: {expected_model}"
        )
        print(
            f"      actual:   {hermes_model or 'unknown'}"
        )

    if opencode_ok:
        print(
            "  ✓ OpenCode synchronized"
        )
        print(
            f"      model: {opencode_model}"
        )
    else:
        print(
            "  ✗ OpenCode synchronization failed"
        )
        print(
            f"      expected: {expected_opencode_model}"
        )
        print(
            f"      actual:   {opencode_model or 'unknown'}"
        )

    return hermes_ok, opencode_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check and synchronize "
            "AIRuntime integrations"
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply the active AIRuntime model "
            "to Hermes and OpenCode"
        ),
    )

    args = parser.parse_args()

    try:
        runtime = load_runtime()
        profiles = load_profiles()
        active = get_active_profile(
            runtime,
            profiles,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    active_name = str(
        active["_name"]
    )

    expected_model = str(
        active["model"]
    )

    expected_opencode_model = (
        f"llama.cpp/{expected_model}"
    )

    print()
    print("========================================")
    print("          AI Runtime Sync")
    print("========================================")
    print()

    print("[Desired configuration]")
    print(
        f"  Active profile: {active_name}"
    )
    print(
        f"  Model:          {expected_model}"
    )
    print()

    print("[Current state]")

    current_hermes = get_hermes_model()
    current_opencode = get_opencode_model()

    hermes_ok = print_check(
        "Hermes model",
        expected_model,
        current_hermes,
    )

    opencode_ok = print_check(
        "OpenCode model",
        expected_opencode_model,
        current_opencode,
    )

    print()

    if not args.apply:
        print("[Policy]")
        print(
            "  No configuration changes were performed."
        )

        print()
        print("========================================")
        print(
            "Result: "
            f"{int(hermes_ok) + int(opencode_ok)}/2 "
            "integrations synchronized"
        )
        print("========================================")

        return (
            0
            if hermes_ok and opencode_ok
            else 1
        )

    if hermes_ok and opencode_ok:
        print("[Apply]")
        print(
            "  All integrations are already "
            "synchronized."
        )

        print()
        print("========================================")
        print(
            "Result: 2/2 integrations synchronized"
        )
        print("========================================")

        return 0

    print("[Apply]")

    backups: list[Backup] = []

    try:
        backups = apply_changes(
            expected_model
        )
    except Exception as exc:
        print(
            f"  ✗ Apply failed: {exc}"
        )
        print(
            "  ✓ Previous configuration restored"
        )

        print()
        print("========================================")
        print(
            "Result: synchronization failed"
        )
        print("========================================")

        return 1

    final_hermes_ok, final_opencode_ok = (
        verify_final_state(expected_model)
    )

    if not (
        final_hermes_ok
        and final_opencode_ok
    ):
        restore_backups(backups)

        print()
        print(
            "  ✗ Final verification failed"
        )
        print(
            "  ✓ Previous configuration restored"
        )

        print()
        print("========================================")
        print(
            "Result: synchronization failed"
        )
        print("========================================")

        return 1

    print()
    print("[Policy]")
    print(
        "  Configuration changes were explicitly "
        "requested with --apply."
    )

    print()
    print("========================================")
    print(
        "Result: 2/2 integrations synchronized"
    )
    print("========================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())