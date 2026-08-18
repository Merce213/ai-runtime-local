#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path


CONFIG_PATH = (
    Path.home()
    / ".config"
    / "opencode"
    / "opencode.jsonc"
)


def strip_jsonc(text: str) -> str:
    """
    Remove JSONC comments and trailing commas.

    This parser is intentionally limited to the structures
    we need from the OpenCode configuration.
    """
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


def get_configured_model() -> str | None:
    if not CONFIG_PATH.is_file():
        return None

    content = CONFIG_PATH.read_text(
        encoding="utf-8"
    )

    cleaned = strip_jsonc(content)

    match = re.search(
        r'"model"\s*:\s*"([^"]+)"',
        cleaned,
    )

    if not match:
        return None

    return match.group(1)


def main() -> int:
    if not CONFIG_PATH.is_file():
        print("config_missing")
        return 0

    model = get_configured_model()

    if model:
        print(f"model={model}")
    else:
        print("model=unknown")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())