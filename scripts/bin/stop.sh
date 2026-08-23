#!/bin/bash
# Stop the eww widget.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"

# Stop the config watcher (PID file written by scripts/bin/start.sh)
stop_watcher() {
  if [ -f "$DIR/run/watch.pid" ]; then
    PID="$(cat "$DIR/run/watch.pid" 2>/dev/null)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      kill "$PID" 2>/dev/null || true
      echo "config watcher stopped (PID $PID)"
    fi
    rm -f "$DIR/run/watch.pid"
  fi
}

# Stop the monitor watcher (PID file written by scripts/bin/start.sh)
stop_monitor_watch() {
  if [ -f "$DIR/run/monitor_watch.pid" ]; then
    PID="$(cat "$DIR/run/monitor_watch.pid" 2>/dev/null)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
      kill "$PID" 2>/dev/null || true
      echo "monitor watcher stopped (PID $PID)"
    fi
    rm -f "$DIR/run/monitor_watch.pid"
  fi
}

# Kill every eww process on the system (not just this config dir): the
# "stop" action must leave nothing behind. A wedged daemon can ignore the IPC
# kill (and even SIGTERM), so verify the processes are really gone and
# force-stop them otherwise. This guarantees that start.sh always brings up a
# fresh daemon.
stop_eww() {
  eww --config "$DIR/eww" kill 2>/dev/null

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

# Stop helper processes that may linger (ESC listener, move keys).
#
# SAFETY: a plain `pkill -f <name>` can kill our own calling chain. Example:
# the one-line installer runs as `bash -c "<full install.sh source>"`, so the
# installer command line embeds this repo's file names; if any pkill pattern
# below appears in that text, the installer dies with SIGTERM mid-run. Walk
# the ancestor chain up to init and spare those PIDs explicitly.
helper_ancestor_pids() {
  local pid=$1
  while [ -n "$pid" ] && [ "$pid" != "0" ] && [ "$pid" != "1" ]; do
    printf '%s\n' "$pid"
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
  done
}

stop_helpers() {
  local protected pid
  protected=" $(helper_ancestor_pids $$ | tr '\n' ' ')"
  for pid in $(pgrep -f 'esc_listener\.py|move_keys\.py' 2>/dev/null || true); do
    case "${protected} " in
      *" ${pid} "*) continue ;;
    esac
    kill "$pid" 2>/dev/null || true
  done
}

main() {
  stop_watcher
  stop_monitor_watch
  stop_helpers
  stop_eww
  echo "Clock + weather widget and system monitor panel stopped (eww)."
}

main
