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

# --- Display environment bootstrap ----------------------------------------
# The widget is often started from a terminal/autostart context that does not
# export the graphical session variables (DISPLAY / WAYLAND_DISPLAY /
# XAUTHORITY / XDG_RUNTIME_DIR / XDG_SESSION_TYPE). The eww daemon (a GTK
# application) needs them to connect to the compositor; without them every
# window fails with "Display parsing error" and the defpolls stay empty.
# Import the variables from a running desktop process (kwin_wayland first,
# then plasma/x11/gnome shells) when they are missing.
ensure_display_env() {
  if [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ]; then
    return 0
  fi
  local pid line
  for pid in $(pgrep -x kwin_wayland 2>/dev/null) \
             $(pgrep -x plasmashell 2>/dev/null) \
             $(pgrep -x gnome-shell 2>/dev/null) \
             $(pgrep -x cinnamon 2>/dev/null) \
             $(pgrep -x Xorg 2>/dev/null); do
    [ -r "/proc/$pid/environ" ] || continue
    while IFS= read -r -d '' line; do
      case "$line" in
        DISPLAY=*|WAYLAND_DISPLAY=*|XAUTHORITY=*|XDG_RUNTIME_DIR=*|XDG_SESSION_TYPE=*)
          export "$line" ;;
      esac
    done < "/proc/$pid/environ"
    if [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ]; then
      echo "display env imported from session process (PID $pid)"
      break
    fi
  done
  if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
    echo "WARNING: no graphical session detected (no DISPLAY/WAYLAND_DISPLAY); the widget may not be visible."
  fi
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
  local panel_enabled
  monitors="$(python3 "$DIR/scripts/monitors.py")" || {
    echo "ERROR: monitors.py failed"; return 1
  }
  panel_alignment="$(python3 "$DIR/scripts/config.py" --key panel_alignment)"
  layout="$(printf '%s' "$monitors" | python3 "$DIR/scripts/workarea.py" --per-monitor --align "$panel_alignment" "$DIR")" || {
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

  # The clock widget is positioned with a "top left" anchor: scripts/widget_rect.py
  # computes the top-left corner from config.yaml (window.alignment + pixel
  # offsets, resolved per-monitor) using the same geometry rules as eww 0.5.0,
  # so the anchor math lives in one place.
  panel_enabled="$(python3 "$DIR/scripts/config.py" --key panel_enabled)"

  count=0
  while IFS='|' read -r idx px py pw ph panchor; do
    [ -z "$idx" ] && continue

    # Clock widget geometry (top-left position; the window keeps its natural
    # 745x250 size and the transform widget scales the content, so the window
    # size does NOT depend on the scale -- only the visual position/size do,
    # which widget_rect.py computes).
    local main_geom main_x main_y main_w main_h main_scale_perc panel_scale_perc panel_translate_x panel_translate_y
    main_geom="$(python3 "$DIR/scripts/widget_rect.py" --widget clock --monitor "$idx")" || {
      echo "ERROR: widget_rect.py (clock, monitor $idx) failed"; return 1
    }
    main_x="$(printf '%s' "$main_geom" | python3 -c 'import json,sys; print(json.load(sys.stdin)["x"])')"
    main_y="$(printf '%s' "$main_geom" | python3 -c 'import json,sys; print(json.load(sys.stdin)["y"])')"
    main_w="745"
    main_h="250"
    main_scale_perc="$(python3 -c "print(int(round($(python3 "$DIR/scripts/config.py" --key scale --monitor "$idx") * 100)))")"

    eww --config "$DIR" open --id "main_$idx" --screen "$idx" \
      --arg "main_x=$main_x" --arg "main_y=$main_y" \
      --arg "main_w=$main_w" --arg "main_h=$main_h" \
      --arg "main_scale_perc=$main_scale_perc" --arg "screen=$idx" \
      "$win_main"

    if [ "$panel_enabled" = "true" ]; then
      panel_scale_perc="$(python3 -c "print(int(round($(python3 "$DIR/scripts/config.py" --key panel_scale --monitor "$idx") * 100)))")"
      panel_translate_x="$(python3 -c "print(int(round(250 * (1.0/$(python3 "$DIR/scripts/config.py" --key panel_scale --monitor "$idx") - 1))))")"
      case "$panchor" in
        *bottom*) panel_translate_y="$(python3 -c "print(int(round($ph * (1.0/$(python3 "$DIR/scripts/config.py" --key panel_scale --monitor "$idx") - 1))))")" ;;
        *)         panel_translate_y="0" ;;
      esac
      eww --config "$DIR" open --id "panel_$idx" --screen "$idx" \
        --arg "screen=$idx" --arg "px=$px" --arg "py=$py" \
        --arg "pw=$pw" --arg "ph=$ph" --arg "panchor=$panchor" \
        --arg "panel_scale_perc=$panel_scale_perc" \
        --arg "panel_translate_x=$panel_translate_x" \
        --arg "panel_translate_y=$panel_translate_y" \
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

# Start the invisible keyboard daemon (scripts/input_daemon.py). It reads the
# physical keyboard through evdev (/dev/input/event*), which needs root or the
# 'input' group, so it is started via passwordless sudo. The display variables
# are passed explicitly because sudo resets the environment; the daemon drops
# back to the invoking user after opening the devices so the eww commands it
# spawns keep the user's display access. It creates NO window, so nothing ever
# appears on screen or in the taskbar. Log goes to input_daemon.log, its PID to
# input_daemon.pid.
start_input_daemon() {
  if [ -f "$DIR/input_daemon.pid" ]; then
    local opid
    opid="$(cat "$DIR/input_daemon.pid" 2>/dev/null)"
    if [ -n "$opid" ] && kill -0 "$opid" 2>/dev/null; then
      echo "input daemon already running (PID $opid)"
      return
    fi
  fi
  sudo -n env DISPLAY="$DISPLAY" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    XAUTHORITY="$XAUTHORITY" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    setsid python3 "$DIR/scripts/input_daemon.py" >> "$DIR/input_daemon.log" 2>&1 &
  disown 2>/dev/null || true
  sleep 0.5
  if [ -f "$DIR/input_daemon.pid" ]; then
    echo "input daemon started (PID $(cat "$DIR/input_daemon.pid"))"
  else
    echo "input daemon: failed to start (passwordless sudo or evdev unavailable); keyboard control disabled"
  fi
}

# Recompute the layout and reopen every window (keeps the daemon running).
relayout() {
  eww --config "$DIR" close-all 2>/dev/null
  layout_windows
}

main() {
  ensure_display_env
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
