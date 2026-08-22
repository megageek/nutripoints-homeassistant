# shellcheck shell=bash disable=SC2139
# Resolve the active workspace. WORKSPACE_ROOT is set by devcontainer.json; the
# fallbacks keep this usable in Codespaces and older containers until rebuilt.
if [[ -z "${WORKSPACE_ROOT:-}" || ! -d "$WORKSPACE_ROOT" ]]; then
    WORKSPACE_ROOT=""
    if [[ "$PWD" == /workspaces/* || "$PWD" == /workspace* ]]; then
        WORKSPACE_ROOT="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
    fi
    if [[ -z "$WORKSPACE_ROOT" ]]; then
        for dir in /workspaces/* /workspace; do
            if [[ -d "$dir" ]]; then
                WORKSPACE_ROOT="$dir"
                break
            fi
        done
    fi
fi

# Show MOTD once per container lifecycle (new container or rebuild).
WORKSPACE_DIR=""
if [[ -n "${VSCODE_GIT_IPC_HANDLE:-}" || -n "${CODESPACES:-}" ]]; then
    WORKSPACE_DIR="$WORKSPACE_ROOT"
fi

if [[ -n "$WORKSPACE_DIR" && -f "$WORKSPACE_DIR/.devcontainer/motd" ]]; then
    HOST_TOKEN="${HOSTNAME:-unknown}"
    MOTD_MARKER_DIR="$HOME/.config/ha-devcontainer"
    MOTD_MARKER_FILE="$MOTD_MARKER_DIR/motd-shown-${HOST_TOKEN}"
    if [[ ! -f "$MOTD_MARKER_FILE" ]]; then
        mkdir -p "$MOTD_MARKER_DIR"
        "$WORKSPACE_DIR/.devcontainer/motd" 2>/dev/null || true
        touch "$MOTD_MARKER_FILE"
    fi
fi

# Home Assistant development aliases (work from anywhere!)
if [ -n "$WORKSPACE_ROOT" ]; then
    if [ -d "$WORKSPACE_ROOT/node_modules/.bin" ]; then
        export PATH="$WORKSPACE_ROOT/node_modules/.bin:$PATH"
    fi

    alias ha-develop="$WORKSPACE_ROOT/script/develop"
    alias ha-test="$WORKSPACE_ROOT/script/test"
    alias ha-lint="$WORKSPACE_ROOT/script/lint"
    alias ha-lint-check="$WORKSPACE_ROOT/script/lint-check"
    alias ha-check="$WORKSPACE_ROOT/script/check"
    alias ha-clean="$WORKSPACE_ROOT/script/clean"
    alias ha-type-check="$WORKSPACE_ROOT/script/type-check"
    alias ha-help="$WORKSPACE_ROOT/script/help"

    # Shorthand for common tasks
    alias ha-t="$WORKSPACE_ROOT/script/test"
    alias ha-l="$WORKSPACE_ROOT/script/lint"
    alias ha-d="$WORKSPACE_ROOT/script/develop"

    # Copilot CLI wrapper (project-managed defaults).
    if command -v copilot-safe >/dev/null 2>&1; then
        alias copilot='copilot-safe'
    fi
fi

# Change to workspace directory if we're in /home/vscode
if [ "$PWD" = "$HOME" ] && [ -n "$WORKSPACE_ROOT" ]; then
    cd "$WORKSPACE_ROOT" 2>/dev/null || true
fi
