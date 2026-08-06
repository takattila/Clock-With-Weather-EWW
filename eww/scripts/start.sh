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

# Generate the theme (SCSS variables + JSON) from config.json
generate_theme() {
  python3 "$DIR/scripts/theme.py" "$DIR" || { echo "ERROR: theme generation failed"; exit 1; }
}

# --- WM-independent taskbar alignment -------------------------------------
# Read the EWMH _NET_WORKAREA (usable area outside the taskbar) and bake it
# into the panel_window geometry so the panel height always matches the
# taskbar on any window manager. PANEL_HEIGHT is also exported for panel.py.
align_panel_to_taskbar() {
  read -r PANEL_Y PANEL_H < <(python3 "$DIR/scripts/workarea.py" "$DIR") || { PANEL_Y=0; PANEL_H=1080; }
  export PANEL_HEIGHT="$PANEL_H"

  python3 - "$DIR/eww.yuck" "$PANEL_Y" "$PANEL_H" <<'PYEOF'
import re
import sys

path, y, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
text = open(path, encoding="utf-8").read()
start = text.index("(defwindow panel_window")
end = text.index("(widget_panel)", start)
block = text[start:end]
block = re.sub(
    r'(:geometry \(geometry :x "[^"]*"\n\s*:y ")[^"]*(")',
    r"\g<1>%dpx\g<2>" % y, block,
)
block = re.sub(r'(:height ")[^"]*(")', r"\g<1>%dpx\g<2>" % h, block)
text = text[:start] + block + text[end:]
open(path, "w", encoding="utf-8").write(text)
PYEOF
  echo "panel aligned to taskbar: y=${PANEL_Y}px height=${PANEL_H}px"
}

# Start the eww daemon and open both windows
start_eww() {
  # Kill any existing eww daemon for this config directory
  eww --config "$DIR" kill 2>/dev/null

  # Start eww daemon
  eww --config "$DIR" daemon

  # Open the clock/weather widget and the system monitor panel
  eww --config "$DIR" open main_window
  eww --config "$DIR" open panel_window
}

main() {
  ensure_plasma_running
  generate_theme
  align_panel_to_taskbar
  start_eww
  echo "Clock + weather widget and system monitor panel are running (eww)."
}

main
