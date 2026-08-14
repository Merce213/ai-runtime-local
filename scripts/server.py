#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any


def get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON returned by {url}") from exc


def main() -> int:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"

    models = get_json(f"{base_url}/v1/models")
    props = get_json(f"{base_url}/props")

    model_ids = [
        item.get("id")
        for item in models.get("data", [])
        if isinstance(item, dict)
    ]

    print(f"model={props.get('model_alias', 'unknown')}")
    print(f"context={props.get('default_generation_settings', {}).get('n_ctx', 'unknown')}")
    print(f"slots={props.get('total_slots', 'unknown')}")
    print(f"build={props.get('build_info', 'unknown')}")
    print(f"models={','.join(str(model) for model in model_ids)}")

    caps = props.get("chat_template_caps", {})
    print(f"tools={caps.get('supports_tools', False)}")
    print(f"tool_calls={caps.get('supports_tool_calls', False)}")
    print(f"parallel_tool_calls={caps.get('supports_parallel_tool_calls', False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
