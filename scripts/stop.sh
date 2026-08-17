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

# Kill every eww process on the system (not just this config dir): the
# "stop" action must leave nothing behind. A wedged daemon can ignore the IPC
# kill (and even SIGTERM), so verify the processes are really gone and
# force-stop them otherwise. This guarantees that start.sh always brings up a
# fresh daemon.
stop_eww() {
  eww --config "$DIR" kill 2>/dev/null

  sleep 0.3
  local pid
  for pid in $(pgrep -x eww 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "eww process stopped (PID $pid)"
  done
}

# Stop helper processes that may linger (ESC listener, move keys)
stop_helpers() {
  pkill -f "esc_listener.py" 2>/dev/null || true
  pkill -f "move_keys.py" 2>/dev/null || true
}

main() {
  stop_watcher
  stop_monitor_watch
  stop_helpers
  stop_eww
  echo "Clock + weather widget and system monitor panel stopped (eww)."
}

main
