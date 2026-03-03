#!/bin/bash
# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Kill any existing eww daemon (optional, depends on if you want a clean start)
eww --config "$DIR" kill

# Start eww daemon
eww --config "$DIR" daemon

# Open the main window
eww --config "$DIR" open main_window
