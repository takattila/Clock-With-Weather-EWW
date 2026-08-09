#!/bin/bash
# Start the eww widget.
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
  "$DIR/scripts/setup-test-env.sh" restore || {
    echo "No restore backup found; starting plasmashell directly..."
    nohup plasmashell >/dev/null 2>&1 & disown
    sleep 2
  }
}

# Generate the theme (SCSS variables + JSON) from config.yaml + appearance.yaml
generate_theme() {
  python3 "$DIR/scripts/theme.py" "$DIR" || { echo "ERROR: theme generation failed"; exit 1; }
}

# --- Multi-monitor layout ------------------------------------------------
# Detect the compositor (X11/Wayland), enumerate the monitors
# (scripts/monitors.py) and compute the panel geometry for every monitor
# (scripts/workarea.py --per-monitor). The layout is stored in .layout.json
# for panel.py (chart sizes per monitor height) and the windows are opened
# once per monitor with `eww open --screen/--id/--arg`.
layout_windows() {
  local monitors layout count compositor win_main win_panel
  local alignment main_anchor main_x main_y panel_enabled
  monitors="$(python3 "$DIR/scripts/monitors.py")" || {
    echo "ERROR: monitors.py failed"; return 1
  }
  layout="$(printf '%s' "$monitors" | python3 "$DIR/scripts/workarea.py" --per-monitor "$DIR")" || {
    echo "ERROR: workarea.py --per-monitor failed"; return 1
  }
  printf '%s\n' "$layout" > "$DIR/.layout.json"

  # PANEL_HEIGHT fallback (primary monitor) for panel.py when .layout.json is stale
  export PANEL_HEIGHT="$(printf '%s' "$layout" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["monitors"][0]["panel"]["height"])')"

  # eww 0.5.0 ignores `:stacking "bottom"` on X11 (only "foreground"/"background"
  # are honoured), so use the *_x11 window definitions there to keep the widget
  # below opened windows (set_keep_below) instead of floating above them.
  compositor="$(printf '%s' "$layout" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["compositor"])')"
  if [ "$compositor" = "x11" ]; then
    win_main="main_window_x11"; win_panel="panel_window_x11"
  else
    win_main="main_window"; win_panel="panel_window"
  fi

  # Clock widget placement from config.yaml (conky-style alignment + pixel
  # offset) and whether the system monitor panel should be started.
  alignment="$(python3 "$DIR/scripts/config.py" --key alignment)"
  main_x="$(python3 "$DIR/scripts/config.py" --key position_x)"
  main_y="$(python3 "$DIR/scripts/config.py" --key position_y)"
  panel_enabled="$(python3 "$DIR/scripts/config.py" --key panel_enabled)"
  case "$alignment" in
    top_left)     main_anchor="top left" ;;
    top_right)    main_anchor="top right" ;;
    top_middle)   main_anchor="top center" ;;
    bottom_left)  main_anchor="bottom left" ;;
    bottom_right) main_anchor="bottom right" ;;
    bottom_middle) main_anchor="bottom center" ;;
    middle_left)  main_anchor="center left" ;;
    middle_right) main_anchor="center right" ;;
    middle_middle) main_anchor="center" ;;
    *)            main_anchor="center" ;;
  esac

  count=0
  while IFS='|' read -r idx px py pw ph panchor; do
    [ -z "$idx" ] && continue
    eww --config "$DIR" open --id "main_$idx" --screen "$idx" \
      --arg "main_anchor=$main_anchor" --arg "main_x=$main_x" --arg "main_y=$main_y" \
      "$win_main"
    if [ "$panel_enabled" = "true" ]; then
      eww --config "$DIR" open --id "panel_$idx" --screen "$idx" \
        --arg "screen=$idx" --arg "px=$px" --arg "py=$py" \
        --arg "pw=$pw" --arg "ph=$ph" --arg "panchor=$panchor" \
        "$win_panel"
    fi
    count=$((count + 1))
  done < <(printf '%s' "$layout" | python3 -c '
import json, sys
for m in json.load(sys.stdin)["monitors"]:
    p = m["panel"]
    print("%s|%s|%s|%s|%s|%s" % (m["index"], p["x"], p["y"], p["width"], p["height"], p["anchor"]))
')
  if [ "$panel_enabled" = "true" ]; then
    echo "layout: opened main+panel on $count monitor(s)"
  else
    echo "layout: opened main on $count monitor(s) (panel disabled)"
  fi
}

# Start the eww daemon
start_eww() {
  # Kill any existing eww daemon for this config directory
  eww --config "$DIR" kill 2>/dev/null

  # Make the API key available to the eww daemon (and its defpoll children).
  # config.py reads the same key from the git-ignored .api_key file, so this
  # is just a convenience/consistency for the OPENWEATHER_API_KEY handling.
  if [ -z "${OPENWEATHER_API_KEY:-}" ] && [ -f "$DIR/.api_key" ]; then
    export OPENWEATHER_API_KEY="$(head -n1 "$DIR/.api_key")"
  fi

  # Start eww daemon
  eww --config "$DIR" daemon
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

# Start the monitor watcher (hotplug / mode changes). Event-driven and ~0 CPU
# while idle; see scripts/monitor_watch.py.
start_monitor_watch() {
  setsid python3 "$DIR/scripts/monitor_watch.py" "$DIR" >> "$DIR/monitor_watch.log" 2>&1 &
  echo $! > "$DIR/monitor_watch.pid"
  disown 2>/dev/null || true
  echo "monitor watcher started (PID $(cat "$DIR/monitor_watch.pid"))"
}

# Recompute the layout and reopen every window (keeps the daemon running).
relayout() {
  eww --config "$DIR" close-all 2>/dev/null
  layout_windows
}

main() {
  "$DIR/scripts/stop.sh"
  # KDE Plasma (plasmashell) is only relevant on Wayland: the widget does not
  # need a desktop shell on X11 (e.g. Linux Mint / Cinnamon), where the GTK
  # windows are positioned with absolute screen coordinates.
  if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    ensure_plasma_running
  fi
  generate_theme
  start_eww
  layout_windows
  start_watcher
  start_monitor_watch
  echo "Clock + weather widget and system monitor panel are running (eww)."
}

# --- Determine how to run (called from .desktop launcher / manual) ---
if [[ "${1:-}" = "--screenshot" ]]; then
  main
  exit 0
fi
if [[ "${1:-}" = "--relayout" ]]; then
  relayout
  exit 0
fi

# On a normal start, run main() and then keep watching for config changes.
echo "- starting the widget..."
main
echo "Widget started."
