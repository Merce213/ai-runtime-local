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

printf '%s\n' '========================================'
printf '%s\n' '          AI Runtime Doctor'
printf '%s\n' '========================================'

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

PRIMARY_MODEL="$(get_runtime_value "llm.primary.model")"
PRIMARY_CONTEXT="$(get_runtime_value "llm.primary.context_length")"
PRIMARY_SLOTS="$(get_runtime_value "llm.primary.slots")"

SERVER_MODEL="$(get_server_value "model")"
SERVER_CONTEXT="$(get_server_value "context")"
SERVER_SLOTS="$(get_server_value "slots")"
SERVER_TOOLS="$(get_server_value "tools")"
SERVER_TOOL_CALLS="$(get_server_value "tool_calls")"
SERVER_PARALLEL_TOOLS="$(get_server_value "parallel_tool_calls")"

if [[ -n "$PRIMARY_MODEL" && "$SERVER_MODEL" == "$PRIMARY_MODEL" ]]; then
    ok "Primary model matches: ${PRIMARY_MODEL}"
elif [[ -n "$SERVER_MODEL" ]]; then
    fail "Primary model mismatch: config=${PRIMARY_MODEL}, server=${SERVER_MODEL}"
else
    fail "Unable to determine active server model"
fi

if [[ -n "$PRIMARY_CONTEXT" && "$SERVER_CONTEXT" == "$PRIMARY_CONTEXT" ]]; then
    ok "Context matches: ${PRIMARY_CONTEXT}"
elif [[ -n "$SERVER_CONTEXT" ]]; then
    fail "Context mismatch: config=${PRIMARY_CONTEXT}, server=${SERVER_CONTEXT}"
else
    fail "Unable to determine server context"
fi

if [[ -n "$PRIMARY_SLOTS" && "$SERVER_SLOTS" == "$PRIMARY_SLOTS" ]]; then
    ok "Slots match: ${PRIMARY_SLOTS}"
elif [[ -n "$SERVER_SLOTS" ]]; then
    fail "Slots mismatch: config=${PRIMARY_SLOTS}, server=${SERVER_SLOTS}"
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

section "OpenCode"

if command -v opencode >/dev/null 2>&1; then
    OPENCODE_VERSION="$(opencode --version 2>/dev/null || true)"
    ok "OpenCode: ${OPENCODE_VERSION:-unknown}"
else
    fail "OpenCode not found"
fi

section "Hermes"

if command -v hermes >/dev/null 2>&1; then
    HERMES_VERSION="$(hermes --version 2>/dev/null | head -n 1 || true)"
    ok "Hermes: ${HERMES_VERSION:-unknown}"
else
    fail "Hermes not found"
fi

section "Docker"

if command -v docker >/dev/null 2>&1; then
    ok "Docker CLI: $(docker --version)"

    if docker info >/dev/null 2>&1; then
        ok "Docker daemon reachable"
    else
        warn "Docker CLI available, but Docker daemon is not reachable"
    fi
else
    fail "Docker CLI not found"
fi

section "KinéFlow"

KINEFLOW_DIR="$(get_runtime_value "projects.kineflow.path")"

if [[ -n "$KINEFLOW_DIR" && -d "$KINEFLOW_DIR" ]]; then
    ok "KinéFlow workspace: ${KINEFLOW_DIR}"
else
    fail "KinéFlow workspace not found: ${KINEFLOW_DIR}"
fi

if [[ -d "${KINEFLOW_DIR}/.git" ]]; then
    ok "KinéFlow Git repository detected"
else
    fail "KinéFlow Git repository not detected"
fi

if [[ -f "${KINEFLOW_DIR}/package.json" ]]; then
    ok "KinéFlow package.json found"
else
    fail "KinéFlow package.json not found"
fi

if [[ -f "${KINEFLOW_DIR}/AGENTS.md" ]]; then
    ok "KinéFlow AGENTS.md found"
else
    warn "KinéFlow AGENTS.md not found"
fi

printf '\n%s\n' '========================================'
printf 'Result: %d passed, %d warnings, %d failures\n' \
    "$PASS" "$WARN" "$FAIL"
printf '%s\n' '========================================'

if (( FAIL > 0 )); then
    exit 1
fi

exit 0