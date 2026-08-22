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
# so a running widget snaps back immediately. Everything is best-effort:
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

echo "hard reset done."
