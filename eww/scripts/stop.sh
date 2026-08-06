#!/bin/bash
# Stop the eww widget (Wayland migration of the Conky widget).
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

# Kill the eww daemon for this config directory (closes all windows)
stop_eww() {
  eww --config "$DIR" kill 2>/dev/null
}

main() {
  stop_eww
  echo "Clock + weather widget and system monitor panel stopped (eww)."
}

main
