#!/usr/bin/env bash
SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_PATH="$PROJECT_ROOT/screenrecordervenv"

source "$VENV_PATH/bin/activate"

python "$PROJECT_ROOT/src/screenrecord.py" &

deactivate
