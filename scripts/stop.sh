#!/bin/bash
# Stop the eww widget.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

# Stop the config watcher (PID file written by start.sh)
stop_watcher() {
  if [ -f "$DIR/watch.pid" ]; then
    PID="$(cat "$DIR/watch.pid" 2>/dev/null)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      kill "$PID" 2>/dev/null || true
      echo "config watcher stopped (PID $PID)"
    fi
    rm -f "$DIR/watch.pid"
  fi
}

# Stop the monitor watcher (PID file written by start.sh)
stop_monitor_watch() {
  if [ -f "$DIR/monitor_watch.pid" ]; then
    PID="$(cat "$DIR/monitor_watch.pid" 2>/dev/null)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      kill "$PID" 2>/dev/null || true
      echo "monitor watcher stopped (PID $PID)"
    fi
    rm -f "$DIR/monitor_watch.pid"
  fi
}

# Kill the eww daemon for this config directory (closes all windows)
stop_eww() {
  eww --config "$DIR" kill 2>/dev/null
}

main() {
  stop_watcher
  stop_monitor_watch
  stop_eww
  echo "Clock + weather widget and system monitor panel stopped (eww)."
}

main
