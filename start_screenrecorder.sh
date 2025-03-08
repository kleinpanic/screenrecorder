#!/usr/bin/env bash
SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_PATH="$PROJECT_ROOT/venv"

source "$VENV_PATH/bin/activate"

python3 "$PROJECT_ROOT/src/screenrecord.py" &

deactivate
