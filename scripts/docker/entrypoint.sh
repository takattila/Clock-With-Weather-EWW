#!/bin/bash
# ==============================================================================
# entrypoint.sh - the container entrypoint (v5.0.0)
#
# Runs INSIDE the container and starts the long-lived processes of the widget:
#   - the eww daemon (with the /app/eww config)
#   - the config watcher  (scripts/core/watch.py)
#   - the monitor watcher (scripts/core/monitor_watch.py)
#
# It stays in the foreground (so the container keeps running and `tini` in the
# Dockerfile can reap the background watchers on shutdown).
#
# The host's start.sh drives the WINDOW layout through the eww / python3
# wrapper scripts (docker exec) -- the sync geometry queries and `eww open`
# calls -- while THIS script owns the daemon + watchers. The two talk over the
# shared /app volume and the eww daemon Unix socket.
#
# NOTE: the input daemon (scripts/move/input_daemon.py) is intentionally NOT
# started here: it needs /dev/input + root/'input' group, which is out of
# scope for the Docker container (keyboard control is skipped in Docker mode).
# ==============================================================================
set -uo pipefail

DIR="/app"

run_eww_daemon() {
  # Start eww daemon using the /app/eww config directory.
  if ! pgrep -x eww >/dev/null 2>&1; then
    echo "[entrypoint] starting eww daemon..."
    eww --config "${DIR}/eww" daemon
  else
    echo "[entrypoint] eww daemon already running."
  fi
}

run_watcher() {
  # inotify watcher so config.yaml / theme YAML edits take effect immediately.
  if ! pgrep -f 'core/watch\.py' >/dev/null 2>&1; then
    echo "[entrypoint] starting config watcher..."
    python3 "${DIR}/scripts/core/watch.py" "${DIR}" \
      >> "${DIR}/logs/watch.log" 2>&1 &
  fi
}

run_monitor_watch() {
  # monitor watcher (hotplug / mode changes).
  if ! pgrep -f 'core/monitor_watch\.py' >/dev/null 2>&1; then
    echo "[entrypoint] starting monitor watcher..."
    python3 "${DIR}/scripts/core/monitor_watch.py" "${DIR}" \
      >> "${DIR}/logs/monitor_watch.log" 2>&1 &
  fi
}

main() {
  mkdir -p "${DIR}/logs" "${DIR}/run"

  # The display env is exported by the host via -e / compose.
  if [[ -z "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
    echo "[entrypoint] WARNING: no graphical session detected (no DISPLAY / WAYLAND_DISPLAY); the widget may not be visible."
  fi

  run_eww_daemon
  run_watcher
  run_monitor_watch

  echo "[entrypoint] eww daemon + watchers started. Keeping container alive..."
  # Keep the container alive; tini reaps the background watchers on exit.
  tail -f /dev/null
}

main
