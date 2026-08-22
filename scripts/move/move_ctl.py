#!/usr/bin/env python3
"""Button handler for the Move / Resize control panel (move_controls).

Each click updates the overlay preview rectangle (defvars move_x/move_y/
move_w/move_h) through `eww update` and returns. The whole script is fast
(<200ms) so it stays inside eww's command timeout; the buttons also set
:timeout "5s" as a safety net.

Actions:
  left/right/up/down  move the rectangle by STEP px (clamped to the frame)
  zoom_in/zoom_out    scale by SCALE_STEP (clamped 0.3..1.5), keeping the
                      widget's anchored corner / right gap fixed
  set_scale           scale to an EXACT percentage given via --value
                      (30..150; out-of-range values are clamped), same
                      anchoring rules as zoom_in/zoom_out -- used by the
                      hand-typed resize field of the GTK control panel
  reset               write the defaults to config.yaml via scripts/
                      config_set.py and close, like save but with the default
                      values (both widgets: position 0/0, scale 1.0)
  save                write the position to config.yaml via scripts/
                      config_set.py, then close. Both widgets store
                      position_x/position_y per monitor: for the clock they are
                      the offset from the alignment base, for the panel the
                      offset from the global panel.gap base (the dragged
                      rectangle minus workarea.py --base-rect). The resize
                      scale is saved for both. position/scale are always
                      written into per_monitor[N] (there are no global
                      position/scale keys anymore; only the panel gaps stay
                      global).
  cancel              close without saving

The resize percentage shown in the panel (move_pct) is updated together with
move_w/move_h so the label always reflects the current scale. The invisible
keyboard daemon (scripts/input_daemon.py) maps the arrow keys / +/- / ENTER /
ESC to the same actions while the session file exists; save/cancel end the
session (scripts/session.py clears the file) and the daemon goes back to idle.

Usage:
  ./move_ctl.py --widget clock --monitor 0 --action save
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(SCRIPTS_DIR, "core"))

import session


CLOCK_H = 247
PANEL_WIDTH = 250
STEP = 10
SCALE_STEP = 0.05
MIN_SCALE = 0.3
MAX_SCALE = 1.5


def run(cmd, capture=False, input_data=None):
    try:
        if capture:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True,
                                           input=input_data).strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception:
        return ""


def eww(*args):
    run(["eww", "--config", EWW_CONFIG_DIR] + list(args))


def eww_get(name):
    return run(["eww", "--config", EWW_CONFIG_DIR, "get", name], capture=True)


def config(key, monitor=None):
    cmd = ["python3", os.path.join(SCRIPTS_DIR, "core", "config.py"), "--key", key]
    if monitor is not None:
        cmd += ["--monitor", str(monitor)]
    return run(cmd, capture=True)


def split_anchor(alignment):
    if not alignment:
        return "center", "middle"
    h = "left" if "left" in alignment else ("right" if "right" in alignment else "center")
    v = "top" if "top" in alignment else ("bottom" if "bottom" in alignment else "middle")
    return h, v


def align_pos(size, frame_size, alignment):
    if alignment in ("left", "top"):
        return 0
    if alignment in ("right", "bottom"):
        return frame_size - size
    return (frame_size - size) / 2


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def widget_rect(widget, monitor):
    out = run(
        ["python3", os.path.join(SCRIPT_DIR, "widget_rect.py"), "--widget", widget, "--monitor", str(monitor)],
        capture=True,
    )
    try:
        return json.loads(out)
    except Exception:
        sys.exit("ERROR: widget_rect.py failed:\n%s" % out)


def save_value(widget, monitor, key, value):
    cmd = [
        "python3", os.path.join(SCRIPTS_DIR, "core", "config_set.py"),
        "--widget", "clock" if widget == "clock" else "panel",
        "--key", key, "--value", str(value),
    ]
    # position/scale are always written into per_monitor[N] (there are no
    # global position/scale keys anymore); only the panel gaps stay global.
    if not key.startswith("gap_"):
        cmd += ["--monitor", str(monitor)]
    run(cmd)


def base_rect(monitor, w, h):
    """Gap-derived (offset-free) panel rectangle for the dragged size.

    The panel's saved position is a per-monitor position_x/position_y OFFSET
    added to the global panel.gap baseline (scripts/workarea.py), so Move /
    Resize Save computes it as dragged_rect - base_rect, where base_rect is
    the gap-only rectangle in the same frame coordinates (workarea.py
    --base-rect). Returns {"base_left": .., "base_top": .., "frame_w": ..,
    "frame_h": .., "anchor": ".."}.
    """
    monitors = run(["python3", os.path.join(SCRIPTS_DIR, "core", "monitors.py")], capture=True)
    if not monitors:
        sys.exit("ERROR: monitors.py failed")
    out = run(
        [
            "python3", os.path.join(SCRIPTS_DIR, "core", "workarea.py"), "--base-rect",
            "--monitor", str(monitor),
            "--w", str(w), "--h", str(h), CONFIG_DIR,
        ],
        capture=True, input_data=monitors,
    )
    try:
        data = json.loads(out)
        if "base_left" not in data or "base_top" not in data:
            raise ValueError(out)
        return data
    except Exception:
        sys.exit("ERROR: workarea.py --base-rect failed:\n%s" % out)


def finish():
    # The rectangle window (scripts/move_rect.py) and the control panel
    # (scripts/move_panel.py) both watch the session file and quit by
    # themselves when it disappears, so only the keyboard-daemon session needs
    # to be ended here.
    session.clear_session()


def base_sizes(widget, monitor, rect):
    """(base_w, base_h, current_scale, right_gap, h_align, v_align)"""
    scale = float(config("scale" if widget == "clock" else "panel_scale", monitor) or 1.0)
    alignment = config("alignment") or "middle_middle"
    h_align, v_align = split_anchor(alignment)
    if widget == "clock":
        # The clock's natural width is dynamic (ends at the city name), so the
        # resize base comes from widget_rect.py, not a fixed constant.
        base_w = rect.get("natural_w") or 745
        base_h = rect.get("natural_h") or CLOCK_H
    else:
        base_w = PANEL_WIDTH
        base_h = int(round(rect["height"] / scale)) if scale else rect["height"]
    return base_w, base_h, scale, rect.get("right_gap"), h_align, v_align


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--action", required=True,
                    choices=["left", "right", "up", "down", "zoom_in", "zoom_out",
                             "set_scale", "reset", "save", "cancel"])
    ap.add_argument("--value", type=float, default=None,
                    help="percentage for --action set_scale")
    args = ap.parse_args()

    if args.action == "cancel":
        finish()
        return

    def fval(name, fallback=0):
        try:
            return float(eww_get(name) or fallback)
        except ValueError:
            return fallback

    x = int(round(fval("move_x")))
    y = int(round(fval("move_y")))
    w = int(round(fval("move_w", 100)))
    h = int(round(fval("move_h", 100)))

    if args.action == "reset":
        # Restore the factory defaults immediately (like save, but with the
        # default values): position (0, 0) at scale 1.0 for BOTH widgets. For
        # the panel the position offsets are cleared while the global panel.gap
        # baseline stays untouched. The config watcher then reloads +
        # relayouts, so the widget actually moves/resizes on screen. Reset
        # needs no widget_rect, so it also works when monitors.py cannot
        # resolve the target monitor yet (e.g. a freshly plugged-in one).
        save_value(args.widget, args.monitor, "position_x", 0)
        save_value(args.widget, args.monitor, "position_y", 0)
        save_value(args.widget, args.monitor, "scale", "1.00")
        finish()
        return

    rect = widget_rect(args.widget, args.monitor)
    frame_w, frame_h = rect["frame_w"], rect["frame_h"]

    if args.action in ("left", "right", "up", "down"):
        dx = -STEP if args.action == "left" else (STEP if args.action == "right" else 0)
        dy = -STEP if args.action == "up" else (STEP if args.action == "down" else 0)
        x = int(clamp(x + dx, 0, frame_w - w))
        y = int(clamp(y + dy, 0, frame_h - h))
        eww("update", "move_x=%d" % x, "move_y=%d" % y)
        return

    if args.action in ("zoom_in", "zoom_out", "set_scale"):
        base_w, base_h, scale, right_gap, h_align, v_align = base_sizes(args.widget, args.monitor, rect)
        # Start from the CURRENT session size (move_w/move_h), not the saved
        # config scale: clicking zoom_out repeatedly must keep stepping down
        # instead of recomputing from the untouched config value each time.
        current = (w / base_w) if base_w else scale
        if args.action == "set_scale":
            if args.value is None:
                sys.exit("ERROR: --action set_scale requires --value <percent>")
            scale = clamp(args.value / 100.0, MIN_SCALE, MAX_SCALE)
        else:
            delta = SCALE_STEP if args.action == "zoom_in" else -SCALE_STEP
            scale = clamp(current + delta, MIN_SCALE, MAX_SCALE)
        w = int(round(base_w * scale))
        h = int(round(base_h * scale))
        if right_gap is not None:
            x = frame_w - right_gap - w
        else:
            pos_x = float(config("position_x", args.monitor) or 0)
            pos_y = float(config("position_y", args.monitor) or 0)
            x = int(align_pos(w, frame_w, h_align) + pos_x)
            y = int(align_pos(h, frame_h, v_align) + pos_y)
        eww("update", "move_x=%d" % x, "move_y=%d" % y, "move_w=%d" % w, "move_h=%d" % h,
            "move_pct=%d" % int(round(scale * 100)))
        return

    if args.action == "save":
        base_w, base_h, scale, right_gap, h_align, v_align = base_sizes(args.widget, args.monitor, rect)
        if base_w:
            scale = clamp(w / base_w, MIN_SCALE, MAX_SCALE)
        if args.widget == "panel":
            # The panel position is a per-monitor offset added to the global
            # panel.gap baseline, so Save writes the delta between the dragged
            # rectangle and the gap-derived base rectangle (frame coords, at
            # the dragged size). Positive offsets shift right/down.
            base = base_rect(args.monitor, w, h)
            new_x = int(round(x - base["base_left"]))
            new_y = int(round(y - base["base_top"]))
            save_value(args.widget, args.monitor, "position_x", new_x)
            save_value(args.widget, args.monitor, "position_y", new_y)
        else:
            new_x = int(round(x - align_pos(w, frame_w, h_align)))
            new_y = int(round(y - align_pos(h, frame_h, v_align)))
            save_value(args.widget, args.monitor, "position_x", new_x)
            save_value(args.widget, args.monitor, "position_y", new_y)
        save_value(args.widget, args.monitor, "scale", "%.2f" % scale)
        finish()
        return


if __name__ == "__main__":
    main()