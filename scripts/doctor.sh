#!/usr/bin/env bash

set -u

PASS=0
WARN=0
FAIL=0

RUNTIME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUNTIME_READER="${RUNTIME_DIR}/scripts/runtime.py"
SERVER_READER="${RUNTIME_DIR}/scripts/server.py"


ok() {
    printf '  ✓ %s\n' "$1"
    PASS=$((PASS + 1))
}


warn() {
    printf '  ! %s\n' "$1"
    WARN=$((WARN + 1))
}


fail() {
    printf '  ✗ %s\n' "$1"
    FAIL=$((FAIL + 1))
}


section() {
    printf '\n[%s]\n' "$1"
}


get_runtime_value() {
    python3 "$RUNTIME_READER" --get "$1" 2>/dev/null
}


get_server_value() {
    python3 "$SERVER_READER" 2>/dev/null |
        awk -F= -v key="$1" '
            $1 == key {
                print substr($0, index($0, "=") + 1)
                exit
            }
        '
}


get_active_profile() {
    get_runtime_value "active_profile"
}


get_profile_value() {
    local profile="$1"
    local key="$2"

    python3 - "$RUNTIME_DIR" "$profile" "$key" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

runtime_dir = Path(sys.argv[1])
profile_name = sys.argv[2]
key = sys.argv[3]

profile_path = runtime_dir / "profiles" / f"{profile_name}.yaml"

if not profile_path.is_file():
    raise SystemExit(1)

with profile_path.open("r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

if not isinstance(data, dict):
    raise SystemExit(1)

value: Any = data

for part in key.split("."):
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(1)

    value = value[part]

if isinstance(value, (dict, list)):
    raise SystemExit(1)

print(value)
PY
}


printf '%s\n' '========================================'
printf '%s\n' '          AI Runtime Doctor'
printf '%s\n' '========================================'


# ============================================================
# Environment
# ============================================================

section "Environment"


if [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    ok "WSL2 environment: ${WSL_DISTRO_NAME}"
else
    warn "WSL_DISTRO_NAME is not set"
fi


if command -v git >/dev/null 2>&1; then
    ok "Git: $(git --version)"
else
    fail "Git not found"
fi


if command -v python3 >/dev/null 2>&1; then
    ok "Python: $(python3 --version)"
else
    fail "Python3 not found"
fi


# ============================================================
# Runtime configuration
# ============================================================

section "AIRuntime"


ACTIVE_PROFILE="$(get_active_profile)"


if [[ -n "$ACTIVE_PROFILE" ]]; then
    ok "Active profile: ${ACTIVE_PROFILE}"
else
    fail "Unable to determine active_profile"
fi


if [[ -n "$ACTIVE_PROFILE" ]]; then
    PROFILE_PATH="${RUNTIME_DIR}/profiles/${ACTIVE_PROFILE}.yaml"

    if [[ -f "$PROFILE_PATH" ]]; then
        ok "Active profile file found"
    else
        fail "Active profile file not found: ${PROFILE_PATH}"
    fi
fi


EXPECTED_MODEL=""
EXPECTED_CONTEXT=""
EXPECTED_SLOTS=""
EXPECTED_ENDPOINT=""
EXPECTED_TOOLS=""
EXPECTED_TOOL_CALLS=""
EXPECTED_PARALLEL_TOOLS=""

if [[ -n "$ACTIVE_PROFILE" ]]; then
    EXPECTED_MODEL="$(
        get_profile_value "$ACTIVE_PROFILE" "model" || true
    )"

    EXPECTED_CONTEXT="$(
        get_profile_value "$ACTIVE_PROFILE" "context_length" || true
    )"

    EXPECTED_SLOTS="$(
        get_profile_value "$ACTIVE_PROFILE" "slots" || true
    )"

    EXPECTED_ENDPOINT="$(
        get_profile_value "$ACTIVE_PROFILE" "endpoint" || true
    )"

    EXPECTED_TOOLS="$(
        get_profile_value "$ACTIVE_PROFILE" "capabilities.tools" || true
    )"

    EXPECTED_TOOL_CALLS="$(
        get_profile_value \
            "$ACTIVE_PROFILE" \
            "capabilities.parallel_tool_calls" \
            || true
    )"
fi


if [[ -z "$EXPECTED_MODEL" ]]; then
    fail "Active profile does not define a model"
fi


if [[ -z "$EXPECTED_CONTEXT" ]]; then
    fail "Active profile does not define context_length"
fi


if [[ -z "$EXPECTED_SLOTS" ]]; then
    fail "Active profile does not define slots"
fi


if [[ -z "$EXPECTED_ENDPOINT" ]]; then
    fail "Active profile does not define endpoint"
fi


# ============================================================
# llama.cpp
# ============================================================

section "llama.cpp"


LLAMA_ROOT_URL="http://127.0.0.1:8080"


if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 5 \
        "${LLAMA_ROOT_URL}/v1/models" >/dev/null 2>&1; then
        ok "llama-server reachable at ${LLAMA_ROOT_URL}"
    else
        fail "llama-server unreachable at ${LLAMA_ROOT_URL}"
    fi
else
    fail "curl not found"
fi


SERVER_MODEL="$(get_server_value "model")"
SERVER_CONTEXT="$(get_server_value "context")"
SERVER_SLOTS="$(get_server_value "slots")"
SERVER_TOOLS="$(get_server_value "tools")"
SERVER_TOOL_CALLS="$(get_server_value "tool_calls")"
SERVER_PARALLEL_TOOLS="$(get_server_value "parallel_tool_calls")"


if [[ -n "$EXPECTED_MODEL" && "$SERVER_MODEL" == "$EXPECTED_MODEL" ]]; then
    ok "Active model matches: ${EXPECTED_MODEL}"
elif [[ -n "$SERVER_MODEL" ]]; then
    fail "Active model mismatch: config=${EXPECTED_MODEL}, server=${SERVER_MODEL}"
else
    fail "Unable to determine active server model"
fi


if [[ -n "$EXPECTED_CONTEXT" && "$SERVER_CONTEXT" == "$EXPECTED_CONTEXT" ]]; then
    ok "Context matches: ${EXPECTED_CONTEXT}"
elif [[ -n "$SERVER_CONTEXT" ]]; then
    fail "Context mismatch: config=${EXPECTED_CONTEXT}, server=${SERVER_CONTEXT}"
else
    fail "Unable to determine server context"
fi


if [[ -n "$EXPECTED_SLOTS" && "$SERVER_SLOTS" == "$EXPECTED_SLOTS" ]]; then
    ok "Slots match: ${EXPECTED_SLOTS}"
elif [[ -n "$SERVER_SLOTS" ]]; then
    fail "Slots mismatch: config=${EXPECTED_SLOTS}, server=${SERVER_SLOTS}"
else
    fail "Unable to determine server slots"
fi


if [[ "$SERVER_TOOLS" == "True" ]]; then
    ok "Tool support enabled"
else
    fail "Tool support is not enabled"
fi


if [[ "$SERVER_TOOL_CALLS" == "True" ]]; then
    ok "Tool-call support enabled"
else
    fail "Tool-call support is not enabled"
fi


if [[ "$SERVER_PARALLEL_TOOLS" == "True" ]]; then
    ok "Parallel tool calls supported"
else
    warn "Parallel tool calls are not reported as supported"
fi


# ============================================================
# OpenCode
# ============================================================

section "OpenCode"


if command -v opencode >/dev/null 2>&1; then
    OPENCODE_VERSION="$(opencode --version 2>/dev/null || true)"
    ok "OpenCode: ${OPENCODE_VERSION:-unknown}"
else
    fail "OpenCode not found"
fi


# ============================================================
# Hermes
# ============================================================

section "Hermes"


if command -v hermes >/dev/null 2>&1; then
    HERMES_VERSION="$(
        hermes --version 2>/dev/null |
        head -n 1 ||
        true
    )"

    ok "Hermes: ${HERMES_VERSION:-unknown}"
else
    fail "Hermes not found"
fi


# ============================================================
# Docker
# ============================================================

section "Docker"


if command -v docker >/dev/null 2>&1; then
    ok "Docker CLI: $(docker --version)"

    if docker info >/dev/null 2>&1; then
        ok "Docker daemon reachable"
    else
        warn "Docker CLI available, but Docker daemon is not reachable"
    fi
else
    warn "Docker CLI not available in this WSL2 distro"
fi


# ============================================================
# KinéFlow
# ============================================================

section "KinéFlow"


KINEFLOW_DIR="$(
    get_runtime_value "projects.kineflow.path"
)"


if [[ -n "$KINEFLOW_DIR" && -d "$KINEFLOW_DIR" ]]; then
    ok "KinéFlow workspace: ${KINEFLOW_DIR}"
else
    fail "KinéFlow workspace not found: ${KINEFLOW_DIR}"
fi


if [[ -n "$KINEFLOW_DIR" && -d "${KINEFLOW_DIR}/.git" ]]; then
    ok "KinéFlow Git repository detected"
else
    fail "KinéFlow Git repository not detected"
fi


if [[ -n "$KINEFLOW_DIR" && -f "${KINEFLOW_DIR}/package.json" ]]; then
    ok "KinéFlow package.json found"
else
    fail "KinéFlow package.json not found"
fi


if [[ -n "$KINEFLOW_DIR" && -f "${KINEFLOW_DIR}/AGENTS.md" ]]; then
    ok "KinéFlow AGENTS.md found"
else
    warn "KinéFlow AGENTS.md not found"
fi


# ============================================================
# Result
# ============================================================

printf '\n%s\n' '========================================'
printf 'Result: %d passed, %d warnings, %d failures\n' \
    "$PASS" "$WARN" "$FAIL"
printf '%s\n' '========================================'


if (( FAIL > 0 )); then
    exit 1
fi

exit 0