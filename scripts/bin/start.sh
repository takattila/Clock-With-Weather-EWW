#!/bin/bash
# Start the eww widget.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"

# Pattern-based leftover killer shared with stop.sh (single-instance
# guarantee: repeated starts used to accumulate orphaned watcher/daemon
# generations whose pidfile entry had been overwritten).
if [ -f "$DIR/scripts/bin/process_sweep.sh" ]; then
  # shellcheck source=process_sweep.sh
  . "$DIR/scripts/bin/process_sweep.sh"
fi

# Runtime output locations (git-ignored via the global *.log / *.pid rules)
LOGS_DIR="$DIR/logs"   # every *.log file
RUN_DIR="$DIR/run"     # every *.pid file
mkdir -p "$LOGS_DIR" "$RUN_DIR"

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
  "$DIR/scripts/bin/setup-test-env.sh" restore || {
    echo "No restore backup found; starting plasmashell directly..."
    nohup plasmashell >/dev/null 2>&1 & disown
    sleep 2
  }
}

# --- Display environment bootstrap ----------------------------------------
# The widget is often started from a terminal/autostart context that does not
# export the full graphical session variables. A shell may carry DISPLAY
# (XWayland) WITHOUT WAYLAND_DISPLAY even on a Wayland desktop -- the stack
# then misdetects X11 and opens WM-managed windows whose positions KWin
# ignores (widgets could not be parked at screen edges). So instead of an
# early exit, every MISSING variable is imported individually from a running
# desktop process; existing values always win.
missing_session_vars() {
  local v out=""
  for v in DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR XDG_SESSION_TYPE; do
    [ -n "${!v:-}" ] || out="$out $v"
  done
  printf '%s' "$out"
}

ensure_display_env() {
  while :; do
    local need imported=0 pid line v
    need="$(missing_session_vars)"
    [ -n "$need" ] || return 0
    for pid in $(pgrep -x kwin_wayland 2>/dev/null) \
               $(pgrep -x plasmashell 2>/dev/null) \
               $(pgrep -x gnome-shell 2>/dev/null) \
               $(pgrep -x cinnamon 2>/dev/null) \
               $(pgrep -x Xorg 2>/dev/null); do
      [ -r "/proc/$pid/environ" ] || continue
      while IFS= read -r -d '' line; do
        v="${line%%=*}"
        case "$need" in
          *" $v "*)
            export "$line"
            imported=1
            ;;
        esac
      done < "/proc/$pid/environ"
    done
    [ "$imported" = "1" ] || break   # nothing new found -> stop retrying
  done
  if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ]; then
    echo "WARNING: no graphical session detected (no DISPLAY/WAYLAND_DISPLAY); the widget may not be visible."
  fi
}

# Generate the theme (SCSS variables + JSON) from config.yaml + appearance.yaml
generate_theme() {
  python3 "$DIR/scripts/core/theme.py" "$DIR" || { echo "ERROR: theme generation failed"; exit 1; }
}

# --- Multi-monitor layout ------------------------------------------------
# Detect the compositor (X11/Wayland), enumerate the monitors
# (scripts/core/monitors.py) and compute the panel geometry for every monitor
# (scripts/core/workarea.py --per-monitor). The layout is stored in .layout.json
# for panel.py (chart sizes per monitor height) and the windows are opened
# once per monitor with `eww open --screen/--id/--arg`.
layout_windows() {
  local monitors layout count compositor win_main win_panel
  local panel_enabled
  monitors="$(python3 "$DIR/scripts/core/monitors.py")" || {
    echo "ERROR: monitors.py failed"; return 1
  }
  panel_alignment="$(python3 "$DIR/scripts/core/config.py" --key panel_alignment)"
  layout="$(printf '%s' "$monitors" | python3 "$DIR/scripts/core/workarea.py" --per-monitor --align "$panel_alignment" "$DIR")" || {
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

  # The clock widget is positioned with a "top left" anchor: scripts/move/widget_rect.py
  # computes the top-left corner from config.yaml (window.alignment + the
  # per-monitor position/scale from weather.window.per_monitor) using the same
  # geometry rules as eww 0.5.0, so the anchor math lives in one place.
  panel_enabled="$(python3 "$DIR/scripts/core/config.py" --key panel_enabled)"

  count=0
  # px/py/panchor are no longer consumed here (the panel geometry comes from
  # widget_rect.py's canvas keys); the layout line keeps its 6-field shape.
  while IFS='|' read -r idx _ _ pw ph _; do
    [ -z "$idx" ] && continue

    # Clock widget geometry. The eww window is a fixed-size transparent
    # CANVAS and the transform widget only scales the drawing inside it, so
    # widget_rect.py computes BOTH:
    #   - the VISIBLE rectangle (x/y/width/height: what the user sees, what
    #     the Move/Resize overlay drags and Save persists), and
    #   - the CANVAS geometry (win_x/win_y/win_w/win_h + translate_x/y):
    #     above 100% the canvas grows to the scaled size (otherwise the
    #     window surface would clip the enlarged drawing), below 100% it
    #     stays natural-sized but is positioned so it always fits the
    #     monitor — an overflowing managed X11 window would be relocated by
    #     the WM, dragging the widget away from its saved spot — while the
    #     transform :translate values (device pixels) place the scaled
    #     content exactly on the visible rectangle.
    # The natural width is dynamic (hugs the content, ends after the city
    # name). Width and height scale INDEPENDENTLY (scale_x / scale_y, each
    # falling back to `scale`).
    local main_geom main_scale_perc_x main_scale_perc_y \
          main_win_x main_win_y main_win_w main_win_h main_translate_x main_translate_y \
          main_natural_w main_natural_h val k \
          panel_geom panel_scale_x panel_scale_y \
          panel_scale_perc_x panel_scale_perc_y \
          pwin_x pwin_y pwin_w pwin_h ptranslate_x ptranslate_y
    main_geom="$(python3 "$DIR/scripts/move/widget_rect.py" --widget clock --monitor "$idx")" || {
      echo "ERROR: widget_rect.py (clock, monitor $idx) failed"; return 1
    }
    for k in win_x win_y win_w win_h translate_x translate_y natural_w natural_h; do
      # shellcheck disable=SC2034  # consumed through the eval below
      val="$(printf '%s' "$main_geom" | python3 -c "import json,sys; print(json.load(sys.stdin)[\"$k\"])")"
      eval "main_$k=\$val"
    done
    main_scale_perc_x="$(python3 -c "print(int(round($(python3 "$DIR/scripts/core/config.py" --key scale_x --monitor "$idx") * 100)))")"
    main_scale_perc_y="$(python3 -c "print(int(round($(python3 "$DIR/scripts/core/config.py" --key scale_y --monitor "$idx") * 100)))")"

    eww --config "$DIR/eww" open --id "main_$idx" --screen "$idx" \
      --arg "main_win_x=$main_win_x" --arg "main_win_y=$main_win_y" \
      --arg "main_win_w=$main_win_w" --arg "main_win_h=$main_win_h" \
      --arg "main_w=$main_natural_w" --arg "main_h=$main_natural_h" \
      --arg "main_scale_perc_x=$main_scale_perc_x" \
      --arg "main_scale_perc_y=$main_scale_perc_y" \
      --arg "main_translate_x=$main_translate_x" \
      --arg "main_translate_y=$main_translate_y" \
      --arg "screen=$idx" \
      "$win_main"

    if [ "$panel_enabled" = "true" ]; then
      panel_scale_x="$(python3 "$DIR/scripts/core/config.py" --key panel_scale_x --monitor "$idx")"
      panel_scale_y="$(python3 "$DIR/scripts/core/config.py" --key panel_scale_y --monitor "$idx")"
      panel_scale_perc_x="$(python3 -c "print(int(round($panel_scale_x * 100)))")"
      panel_scale_perc_y="$(python3 -c "print(int(round($panel_scale_y * 100)))")"
      # Same canvas rule as the clock, computed by widget_rect.py (panel):
      # pwin_* is max(natural, visible) positioned so it always fits the
      # monitor; the translates (device px) put the scaled content exactly
      # on the visible rectangle. Geometry uses a "top left" anchor with
      # these absolute frame coords on both compositors.
      local panel_geom pwin_x pwin_y
      panel_geom="$(python3 "$DIR/scripts/move/widget_rect.py" --widget panel --monitor "$idx")" || {
        echo "ERROR: widget_rect.py (panel, monitor $idx) failed"; return 1
      }
      for k in win_x win_y win_w win_h translate_x translate_y; do
        # shellcheck disable=SC2034  # consumed through the eval below
        val="$(printf '%s' "$panel_geom" | python3 -c "import json,sys; print(json.load(sys.stdin)[\"$k\"])")"
        eval "p$k=\$val"
      done
      eww --config "$DIR/eww" open --id "panel_$idx" --screen "$idx" \
        --arg "screen=$idx" \
        --arg "pw=$pw" --arg "ph=$ph" \
        --arg "pwin_x=$pwin_x" --arg "pwin_y=$pwin_y" \
        --arg "pwin_w=$pwin_w" --arg "pwin_h=$pwin_h" \
        --arg "panel_scale_perc_x=$panel_scale_perc_x" \
        --arg "panel_scale_perc_y=$panel_scale_perc_y" \
        --arg "panel_translate_x=$ptranslate_x" \
        --arg "panel_translate_y=$ptranslate_y" \
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
  eww --config "$DIR/eww" kill 2>/dev/null

  # Make the API key available to the eww daemon (and its defpoll children).
  # config.py reads the same key from the git-ignored .api_key file, so this
  # is just a convenience/consistency for the OPENWEATHER_API_KEY handling.
  if [ -z "${OPENWEATHER_API_KEY:-}" ] && [ -f "$DIR/.api_key" ]; then
    export OPENWEATHER_API_KEY="$(head -n1 "$DIR/.api_key")"
  fi

  # Start eww daemon
  eww --config "$DIR/eww" daemon
}

# Start the inotify-based watcher so config.yaml / theme YAML edits take effect
# immediately (event-driven, ~0 CPU while idle). Log goes to logs/watch.log.
# setsid detaches it into its own session so it survives the caller's shell /
# process-group cleanup (nohup alone is not enough here).
start_watcher() {
  # Single-instance guarantee: sweep older generations first (a stale
  # pidfile would otherwise leave them running forever).
  sweep_kill "${DIR}/scripts/core/watch\.py"
  setsid python3 "$DIR/scripts/core/watch.py" "$DIR" >> "$LOGS_DIR/watch.log" 2>&1 &
  echo $! > "$RUN_DIR/watch.pid"
  disown 2>/dev/null || true
  echo "config watcher started (PID $(cat "$RUN_DIR/watch.pid"))"
}

# Start the monitor watcher (hotplug / mode changes). Event-driven and ~0 CPU
# while idle; see scripts/core/monitor_watch.py.
start_monitor_watch() {
  sweep_kill "${DIR}/scripts/core/monitor_watch\.py"
  setsid python3 "$DIR/scripts/core/monitor_watch.py" "$DIR" >> "$LOGS_DIR/monitor_watch.log" 2>&1 &
  echo $! > "$RUN_DIR/monitor_watch.pid"
  disown 2>/dev/null || true
  echo "monitor watcher started (PID $(cat "$RUN_DIR/monitor_watch.pid"))"
}

# Start the invisible keyboard daemon (scripts/move/input_daemon.py). It reads the
# physical keyboard through evdev (/dev/input/event*), which needs root or the
# 'input' group, so it is started via passwordless sudo. The display variables
# are passed explicitly because sudo resets the environment; the daemon drops
# back to the invoking user after opening the devices so the eww commands it
# spawns keep the user's display access. It creates NO window, so nothing ever
# appears on screen or in the taskbar. Log goes to logs/input_daemon.log, its PID to
# run/input_daemon.pid.
start_input_daemon() {
  # Single-instance guarantee (same rationale as the watchers): kill any
  # leftover daemon first -- its pidfile may point at a newer instance,
  # leaving older ones running invisible in the background.
  sweep_kill "${DIR}/scripts/move/input_daemon\.py"
  if [ -f "$RUN_DIR/input_daemon.pid" ]; then
    local opid
    opid="$(cat "$RUN_DIR/input_daemon.pid" 2>/dev/null)"
    if [ -n "$opid" ] && kill -0 "$opid" 2>/dev/null; then
      echo "input daemon already running (PID $opid)"
      return
    fi
  fi
  sudo -n env DISPLAY="$DISPLAY" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    XAUTHORITY="$XAUTHORITY" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    setsid python3 "$DIR/scripts/move/input_daemon.py" >> "$LOGS_DIR/input_daemon.log" 2>&1 &
  disown 2>/dev/null || true
  sleep 0.5
  if [ -f "$RUN_DIR/input_daemon.pid" ]; then
    echo "input daemon started (PID $(cat "$RUN_DIR/input_daemon.pid"))"
  else
    echo "input daemon: failed to start (passwordless sudo or evdev unavailable); keyboard control disabled"
  fi
}

# Recompute the layout and reopen every window (keeps the daemon running).
relayout() {
  eww --config "$DIR/eww" close-all 2>/dev/null
  layout_windows
}

main() {
  ensure_display_env
  "$DIR/scripts/bin/stop.sh"
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
