#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess


def main() -> int:
    result = subprocess.run(
        ["hermes", "config"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("status=error")
        return 1

    output = result.stdout

    match = re.search(
        r"'default':\s*'([^']+)'",
        output,
    )

    if match:
        print(f"model={match.group(1)}")
    else:
        print("model=unknown")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())