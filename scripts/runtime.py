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
        profile = load_yaml(path)

        if not profile.get("model"):
            continue

        profile["_name"] = path.stem
        profiles[path.stem] = profile

    return profiles


def get_active_profile_name(runtime: dict[str, Any]) -> str:
    active = runtime.get("active_profile")

    if not active:
        raise KeyError(
            "runtime.yaml does not define 'active_profile'"
        )

    return str(active)


def get_active_profile(
    runtime: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    active_name = get_active_profile_name(runtime)

    profile = profiles.get(active_name)

    if profile is None:
        available = ", ".join(sorted(profiles))

        raise KeyError(
            f"Active profile '{active_name}' was not found. "
            f"Available profiles: {available}"
        )

    return profile


def get_value(data: dict[str, Any], key: str) -> Any:
    value: Any = data

    for part in key.split("."):
        if not isinstance(value, dict):
            raise KeyError(
                f"Invalid configuration path: {key}"
            )

        if part not in value:
            raise KeyError(
                f"Configuration key not found: {key}"
            )

        value = value[part]

    return value


def set_active_profile(profile_name: str) -> None:
    runtime = load_runtime()
    profiles = load_profiles()

    if profile_name not in profiles:
        available = ", ".join(sorted(profiles))

        raise ValueError(
            f"Unknown profile '{profile_name}'. "
            f"Available profiles: {available}"
        )

    runtime["active_profile"] = profile_name

    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            runtime,
            file,
            sort_keys=False,
            default_flow_style=False,
        )


def print_config(
    config: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> None:
    runtime = config.get("runtime", {})
    llm = config.get("llm", {})
    projects = config.get("projects", {})

    active_name = get_active_profile_name(config)
    active = profiles.get(active_name)

    print(f"Runtime: {runtime.get('name', 'unknown')}")
    print(
        f"Environment: "
        f"{runtime.get('environment', 'unknown')}"
    )
    print(f"Active profile: {active_name}")
    print()

    print("LLM:")
    print(
        f"  Provider: "
        f"{llm.get('provider', 'unknown')}"
    )
    print(
        f"  Endpoint: "
        f"{llm.get('endpoint', 'unknown')}"
    )

    if active is None:
        print("  Model: unknown")
        print("  Context: unknown")
        print("  Slots: unknown")
    else:
        print(
            f"  Model: "
            f"{active.get('model', 'unknown')}"
        )
        print(
            f"  Context: "
            f"{active.get('context_length', 'unknown')}"
        )
        print(
            f"  Slots: "
            f"{active.get('slots', 'unknown')}"
        )

    print()
    print("Profiles:")

    for name, profile in profiles.items():
        print(f"  {name}:")
        print(
            f"    model: "
            f"{profile.get('model', 'unknown')}"
        )
        print(
            f"    provider: "
            f"{profile.get('provider', 'unknown')}"
        )
        print(
            f"    endpoint: "
            f"{profile.get('endpoint', 'unknown')}"
        )
        print(
            f"    context: "
            f"{profile.get('context_length', 'unknown')}"
        )
        print(
            f"    slots: "
            f"{profile.get('slots', 'unknown')}"
        )

        capabilities = profile.get(
            "capabilities",
            {},
        )

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
            print(
                f"  {name}: "
                f"{project.get('path', 'unknown')}"
            )


def print_profiles(
    profiles: dict[str, dict[str, Any]],
) -> None:
    if not profiles:
        print("No model profiles found.")
        return

    for name, profile in profiles.items():
        print(f"Profile: {name}")
        print(
            f"  Model: "
            f"{profile.get('model', 'unknown')}"
        )
        print(
            f"  Provider: "
            f"{profile.get('provider', 'unknown')}"
        )
        print(
            f"  Endpoint: "
            f"{profile.get('endpoint', 'unknown')}"
        )
        print(
            f"  Context: "
            f"{profile.get('context_length', 'unknown')}"
        )
        print(
            f"  Slots: "
            f"{profile.get('slots', 'unknown')}"
        )

        capabilities = profile.get(
            "capabilities",
            {},
        )

        print(
            f"  Tools: "
            f"{capabilities.get('tools', False)}"
        )
        print(
            f"  Parallel tool calls: "
            f"{capabilities.get('parallel_tool_calls', False)}"
        )
        print(
            f"  Reasoning: "
            f"{capabilities.get('reasoning', False)}"
        )
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read and manage AIRuntime configuration"
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

    parser.add_argument(
        "--set-active",
        dest="set_active",
        help="Set the active model profile",
    )

    args = parser.parse_args()

    try:
        runtime = load_runtime()
        profiles = load_profiles()

        if args.set_active:
            set_active_profile(args.set_active)

            print(
                f"Active profile: "
                f"{args.set_active}"
            )
            print(
                "Server unchanged. "
                "Run 'ai up' to apply the profile."
            )

            return 0

        if args.key:
            value = get_value(runtime, args.key)

            if isinstance(value, (dict, list)):
                print(
                    yaml.safe_dump(
                        value,
                        sort_keys=False,
                    ).rstrip()
                )
            else:
                print(value)

            return 0

        if args.profiles:
            print_profiles(profiles)
            return 0

        print_config(runtime, profiles)
        return 0

    except Exception as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())