#!/bin/bash
# Start the eww widget (Wayland migration of the Conky widget).
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Generate the theme (SCSS variables + JSON) from config.json
python3 "$DIR/scripts/theme.py" "$DIR" || { echo "ERROR: theme generation failed"; exit 1; }

# --- WM-independent taskbar alignment -------------------------------------
# Read the EWMH _NET_WORKAREA (usable area outside the taskbar) and bake it
# into the panel_window geometry so the panel height always matches the
# taskbar on any window manager. PANEL_HEIGHT is also exported for panel.py.
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

# Kill any existing eww daemon for this config directory
eww --config "$DIR" kill 2>/dev/null

# Start eww daemon
eww --config "$DIR" daemon

# Open the clock/weather widget and the system monitor panel
eww --config "$DIR" open main_window
eww --config "$DIR" open panel_window

echo "Clock + weather widget and system monitor panel are running (eww)."
