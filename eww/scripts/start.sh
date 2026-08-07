#!/bin/bash
# Start the eww widget (Wayland migration of the Conky widget).
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

# --- KDE Plasma check -----------------------------------------------------
# The widget needs a running desktop shell to be displayed. If KDE Plasma
# (plasmashell) is not running, restore the normal desktop first (this also
# (re)starts plasmashell). If there is no restore backup, start plasmashell
# directly as a fallback.
ensure_plasma_running() {
  if pgrep -x plasmashell >/dev/null 2>&1; then
    return 0
  fi
  echo "KDE Plasma (plasmashell) is not running; restoring normal desktop..."
  "$DIR/scripts/setup_test_env.sh" restore || {
    echo "No restore backup found; starting plasmashell directly..."
    nohup plasmashell >/dev/null 2>&1 & disown
    sleep 2
  }
}

# Generate the theme (SCSS variables + JSON) from config.yaml + appearance.yaml
generate_theme() {
  python3 "$DIR/scripts/theme.py" "$DIR" || { echo "ERROR: theme generation failed"; exit 1; }
}

# --- WM-independent taskbar alignment -------------------------------------
# Read the EWMH _NET_WORKAREA (usable area outside the taskbar) and the
# symmetric gap (config.yaml -> panel.gap), compute the panel geometry
# (anchor + x/y offsets + height, see workarea.py) and bake it into the
# panel_window geometry so the panel is inset from the taskbar and from the
# opposite screen edge by the SAME gap, for any taskbar position. The actual
# panel height is also exported as PANEL_HEIGHT for panel.py (chart sizing).
# If the X display is unreachable (no real workarea), the committed geometry
# is kept instead of being clobbered with a fallback.
align_panel_to_taskbar() {
  local json
  json="$(python3 "$DIR/scripts/workarea.py" "$DIR")" || json=""
  if [ -z "$json" ]; then
    echo "WARNING: workarea.py failed; keeping panel geometry in eww.yuck"
    return 1
  fi
  if [ "$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["real_workarea"])' "$json")" != "True" ]; then
    echo "WARNING: no X display / workarea; keeping panel geometry in eww.yuck"
    return 1
  fi

  local ANCHOR PANEL_X PANEL_Y PANEL_W PANEL_H GAP
  ANCHOR="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel"]["anchor"])' "$json")"
  PANEL_X="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel"]["x"])' "$json")"
  PANEL_Y="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel"]["y"])' "$json")"
  PANEL_W="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel"]["width"])' "$json")"
  PANEL_H="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel"]["height"])' "$json")"
  GAP="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["panel_gap"])' "$json")"
  export PANEL_HEIGHT="$PANEL_H"

  python3 - "$DIR/eww.yuck" "$ANCHOR" "$PANEL_X" "$PANEL_Y" "$PANEL_W" "$PANEL_H" <<'PYEOF'
import re
import sys

path, anchor, x, y, w, h = (
    sys.argv[1],
    sys.argv[2],
    int(sys.argv[3]),
    int(sys.argv[4]),
    int(sys.argv[5]),
    int(sys.argv[6]),
)
text = open(path, encoding="utf-8").read()
start = text.index("(defwindow panel_window")
end = text.index("(widget_panel)", start)
block = text[start:end]
block = re.sub(r'(:x ")[^"]*(")', r"\g<1>%dpx\g<2>" % x, block)
block = re.sub(r'(:y ")[^"]*(")', r"\g<1>%dpx\g<2>" % y, block)
block = re.sub(r'(:width ")[^"]*(")', r"\g<1>%dpx\g<2>" % w, block)
block = re.sub(r'(:height ")[^"]*(")', r"\g<1>%dpx\g<2>" % h, block)
block = re.sub(r'(:anchor ")[^"]*(")', r"\g<1>%s\g<2>" % anchor, block)
text = text[:start] + block + text[end:]
open(path, "w", encoding="utf-8").write(text)
PYEOF
  echo "panel aligned to taskbar: anchor=${ANCHOR} x=${PANEL_X}px y=${PANEL_Y}px width=${PANEL_W}px height=${PANEL_H}px (gap=${GAP}px)"
}

# Start the eww daemon and open both windows
start_eww() {
  # Kill any existing eww daemon for this config directory
  eww --config "$DIR" kill 2>/dev/null

  # Make the API key available to the eww daemon (and its defpoll children).
  # config.py reads the same key from the git-ignored .api_key file, so this
  # is just a convenience/consistency with the Conky side (OPENWEATHER_API_KEY).
  if [ -z "${OPENWEATHER_API_KEY:-}" ] && [ -f "$DIR/.api_key" ]; then
    export OPENWEATHER_API_KEY="$(head -n1 "$DIR/.api_key")"
  fi

  # Start eww daemon
  eww --config "$DIR" daemon

  # Open the clock/weather widget and the system monitor panel
  eww --config "$DIR" open main_window
  eww --config "$DIR" open panel_window
}

# Start the inotify-based watcher so config.yaml / theme YAML edits take effect
# immediately (event-driven, ~0 CPU while idle). Log goes to eww/watch.log.
# setsid detaches it into its own session so it survives the caller's shell /
# process-group cleanup (nohup alone is not enough here).
start_watcher() {
  setsid python3 "$DIR/scripts/watch.py" "$DIR" >> "$DIR/watch.log" 2>&1 &
  echo $! > "$DIR/watch.pid"
  disown 2>/dev/null || true
  echo "config watcher started (PID $(cat "$DIR/watch.pid"))"
}

main() {
  ensure_plasma_running
  generate_theme
  align_panel_to_taskbar
  start_eww
  start_watcher
  echo "Clock + weather widget and system monitor panel are running (eww)."
}

main
