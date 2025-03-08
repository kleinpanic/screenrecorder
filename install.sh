#!/usr/bin/env bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

VENV_PATH="$PROJECT_ROOT/screenrecordervenv"

if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment. Exiting."
        exit 1
    fi
fi

source "$VENV_PATH/bin/activate"

echo "Installing requirements from requirements.txt..."
pip install -r "$SCRIPT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "Error: Failed to install requirements. Exiting."
    deactivate
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/start_screenrecorder.sh" ]; then
    echo "Error: start_screenrecord.sh not found. Exiting."
    deactivate
    exit 1
fi

echo "Making start_screenrecord.sh executable..."
chmod +x "$SCRIPT_DIR/start_screenrecorder.sh"
if [ $? -ne 0 ]; then
    echo "Error: Failed to make start_screenrecord.sh executable. Exiting."
    deactivate
    exit 1
fi

if [ ! -L /usr/local/bin/start_screenrecorder ]; then
    echo "Linking start_screenrecorder.sh to /usr/local/bin/start_screenrecorder..."
    sudo ln -s "$SCRIPT_DIR/start_screenrecorder.sh" /usr/local/bin/start_screenrecorder
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create symlink. Exiting."
        deactivate
        exit 1
    fi
fi

deactivate

echo "Installation complete. You can now run the screen recorder with 'start_screenrecorder'."
