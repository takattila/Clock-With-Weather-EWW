#!/bin/bash
# Factory-reset the widget configuration (hard reset).
#
# Deletes the git-ignored config.local.yaml -- the ONLY file the widget
# scripts ever write (positions, scales, hour format, appearance, units,
# panel state, gaps) -- so every setting falls back to the committed
# config.yaml defaults. NO backup is kept: config.yaml is never touched,
# and the local file only ever holds machine-generated / toggle values.
#
# Also removes a stale input-daemon session (generated/input_session.json),
# regenerates the theme files from the defaults and relayouts the windows,
# so a running widget snaps back immediately. (The raindrop layer needs no
# restart: scripts/core/rain.py polls config.yaml / config.local.yaml by mtime
# every 2s, so the dropped weather.rain.* overrides fall back to the
# config.yaml defaults on their own.) Everything is best-effort:
# when the widget is not running, the reset still succeeds on disk and the
# next start.sh picks it up. (If the watcher happens to be running it also
# detects the deletion itself; the explicit steps below just make the
# script self-sufficient.)
#
# Usage:
#   bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/hard-reset.sh
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"

echo "hard reset: removing $DIR/config.local.yaml"
rm -f "$DIR/config.local.yaml"

if [ -f "$DIR/generated/input_session.json" ]; then
  echo "hard reset: removing stale session file"
  rm -f "$DIR/generated/input_session.json"
fi

echo "hard reset: regenerating theme from defaults"
python3 "$DIR/scripts/core/theme.py" "$DIR" \
  || echo "WARN: theme regeneration failed (the watcher/start.sh will retry)"

echo "hard reset: re-laying-out the windows"
bash "$DIR/scripts/bin/start.sh" --relayout \
  || echo "WARN: relayout failed (widget not running?); next start.sh applies the defaults"

# Guarantee exactly one raindrop layer after a reset. start.sh --relayout above
# already calls start_rain(), so this is normally a no-op; it only matters when
# the relayout failed or a layer outlived its pid file. Skipped entirely when
# the widget is not running, so a hard reset on a stopped install cannot spawn a
# stray full-screen layer.
if pgrep -f "eww --config" >/dev/null 2>&1; then
  if [ -f "$DIR/scripts/bin/process_sweep.sh" ]; then
    # shellcheck source=process_sweep.sh
    . "$DIR/scripts/bin/process_sweep.sh"
    # Sweep only when nothing is running: a leftover layer that survived a
    # kill -9 is not in the pid file, so a start here would stack a second
    # full-screen window and double the CPU.
    if ! pgrep -f "${DIR}/scripts/core/rain\.py" >/dev/null 2>&1; then
      echo "hard reset: starting the raindrop layer"
      mkdir -p "$DIR/logs" "$DIR/run"
      setsid python3 "$DIR/scripts/core/rain.py" "$DIR" \
        >> "$DIR/logs/rain.log" 2>&1 &
      PID=$!
      disown 2>/dev/null || true
      echo "$PID" > "$DIR/run/rain.pid"
    fi
  fi
fi

echo "hard reset done."
