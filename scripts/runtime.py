#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


RUNTIME_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = RUNTIME_ROOT / "config" / "runtime.yaml"
PROFILES_DIR = RUNTIME_ROOT / "profiles"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")

    return data


def load_runtime() -> dict[str, Any]:
    return load_yaml(CONFIG_PATH)


def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}

    if not PROFILES_DIR.exists():
        return profiles

    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        profiles[path.stem] = load_yaml(path)

    return profiles


def get_value(data: dict[str, Any], key: str) -> Any:
    value: Any = data

    for part in key.split("."):
        if not isinstance(value, dict):
            raise KeyError(f"Invalid configuration path: {key}")

        if part not in value:
            raise KeyError(f"Configuration key not found: {key}")

        value = value[part]

    return value


def print_config(config: dict[str, Any]) -> None:
    runtime = config.get("runtime", {})
    llm = config.get("llm", {})
    primary = llm.get("primary", {})
    secondary = llm.get("secondary", {})
    projects = config.get("projects", {})

    print(f"Runtime: {runtime.get('name', 'unknown')}")
    print(f"Environment: {runtime.get('environment', 'unknown')}")
    print()

    print("LLM:")
    print(f"  Provider: {llm.get('provider', 'unknown')}")
    print(f"  Endpoint: {llm.get('endpoint', 'unknown')}")
    print(f"  Primary: {primary.get('model', 'unknown')}")
    print(f"  Primary context: {primary.get('context_length', 'unknown')}")
    print(f"  Primary slots: {primary.get('slots', 'unknown')}")
    print(f"  Secondary: {secondary.get('model', 'unknown')}")
    print()

    print("Profiles:")

    for name, profile in load_profiles().items():
        print(f"  {name}:")
        print(f"    model: {profile.get('model', 'unknown')}")
        print(f"    provider: {profile.get('provider', 'unknown')}")
        print(f"    context: {profile.get('context_length', 'unknown')}")

        capabilities = profile.get("capabilities", {})

        print(
            f"    tools: "
            f"{capabilities.get('tools', False)}"
        )

        print(
            f"    parallel_tool_calls: "
            f"{capabilities.get('parallel_tool_calls', False)}"
        )

        print(
            f"    reasoning: "
            f"{capabilities.get('reasoning', False)}"
        )

    print()
    print("Projects:")

    for name, project in projects.items():
        if isinstance(project, dict):
            print(f"  {name}: {project.get('path', 'unknown')}")


def print_profiles() -> None:
    profiles = load_profiles()

    if not profiles:
        print("No model profiles found.")
        return

    for name, profile in profiles.items():
        print(f"Profile: {name}")
        print(f"  Model: {profile.get('model', 'unknown')}")
        print(f"  Provider: {profile.get('provider', 'unknown')}")
        print(f"  Endpoint: {profile.get('endpoint', 'unknown')}")
        print(f"  Context: {profile.get('context_length', 'unknown')}")
        print(f"  Slots: {profile.get('slots', 'unknown')}")

        capabilities = profile.get("capabilities", {})

        print(f"  Tools: {capabilities.get('tools', False)}")
        print(
            "  Parallel tool calls: "
            f"{capabilities.get('parallel_tool_calls', False)}"
        )
        print(f"  Reasoning: {capabilities.get('reasoning', False)}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read AIRuntime configuration"
    )

    parser.add_argument(
        "--get",
        dest="key",
        help="Read a dotted runtime configuration value",
    )

    parser.add_argument(
        "--profiles",
        action="store_true",
        help="List configured model profiles",
    )

    args = parser.parse_args()

    try:
        runtime = load_runtime()

        if args.key:
            value = get_value(runtime, args.key)

            if isinstance(value, (dict, list)):
                print(yaml.safe_dump(value, sort_keys=False).rstrip())
            else:
                print(value)

            return 0

        if args.profiles:
            print_profiles()
            return 0

        print_config(runtime)
        return 0

    except Exception as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())