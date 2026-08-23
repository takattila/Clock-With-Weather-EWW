#!/usr/bin/env python3
"""Button handler for the Move / Resize control panel (move_controls).

Each click updates the overlay preview rectangle (defvars move_x/move_y/
move_w/move_h) through `eww update` and returns. The whole script is fast
(<200ms) so it stays inside eww's command timeout; the buttons also set
:timeout "5s" as a safety net.

Actions:
  left/right/up/down  move the rectangle by STEP px (clamped to the frame)
  zoom_in/zoom_out    PROPORTIONAL scale by SCALE_STEP (clamped 0.3..1.5),
                      keeping the widget's anchored corner / right gap fixed
  set_scale           scale BOTH axes to an EXACT percentage given via
                      --value (30..150; out-of-range values are clamped),
                      same anchoring rules as zoom_in/zoom_out -- used by
                      the hand-typed resize field of the GTK control panel
  zoom_in_x/zoom_out_x  scale ONLY THE WIDTH (aspect ratio NOT preserved);
                      the anchored horizontal edge stays fixed (panel: right
                      gap, clock: alignment), height/vertical position are
                      untouched
  zoom_in_y/zoom_out_y  scale ONLY THE HEIGHT; anchored vertical edge stays
                      fixed (clock: vertical alignment), width/horizontal
                      position are untouched
  set_scale_x / set_scale_y   exact percentage for ONE axis via --value,
                      same rules as the matching zoom_*_x / zoom_*_y --
                      used by the W / H fields of the GTK control panel
  reset               write the defaults to config.yaml via scripts/
                      config_set.py and close, like save but with the default
                      values (both widgets: position 0/0, scale/scale_x/
                      scale_y 1.0)
  save                write the position to config.yaml via scripts/
                      config_set.py, then close. Both widgets store
                      position_x/position_y per monitor: for the clock they are
                      the offset from the alignment base, for the panel the
                      offset from the global panel.gap base (the dragged
                      rectangle minus workarea.py --base-rect). The resize is
                      saved per axis: scale_x = dragged_width/base_width and
                      scale_y = dragged_height/base_height (plus a `scale`
                      mirror of scale_x for backward-compatible readers).
                      position/scales are always written into per_monitor[N]
                      (there are no global position/scale keys anymore; only
                      the panel gaps stay global).
  cancel              close without saving

The resize percentages shown in the panel (move_pct = width, move_pct_h =
height) are updated together with move_w/move_h so the labels always
reflect the current scales. The invisible keyboard daemon
(scripts/input_daemon.py) maps the arrow keys / +/- / Shift+arrows (axis
resize) / ENTER / ESC to the same actions while the session file exists;
save/cancel end the session (scripts/session.py clears the file) and the
daemon goes back to idle.

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

# Action groups of the resize family (see the module docstring).
PROPORTIONAL_ACTIONS = ("zoom_in", "zoom_out", "set_scale")
WIDTH_ACTIONS = ("zoom_in_x", "zoom_out_x", "set_scale_x")
HEIGHT_ACTIONS = ("zoom_in_y", "zoom_out_y", "set_scale_y")

# Every action is spawned DETACHED with stderr discarded (eww button
# timeouts), so failures would be invisible. This log is the permanent
# trace: one line per action plus the computed save/resize numbers and any
# refusal/exception.
LOG_FILE = os.path.join(CONFIG_DIR, "logs", "move_ctl.log")


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        from datetime import datetime

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (stamp, msg))
    except Exception:
        pass


def run(cmd, capture=False, input_data=None):
    try:
        if capture:
            return subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                input=input_data, text=True, timeout=15,
            ).stdout.strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        return ""
    except Exception as exc:
        log("run failed: %s -> %r" % (" ".join(map(str, cmd[:4])), exc))
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
        log("widget_rect FAILED for %s/%s: %r" % (widget, monitor, out))
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
    out = run(cmd, capture=True)
    if out:
        log("wrote %s[%d].%s=%s (%s)" % (widget, monitor, key, value, out))
    else:
        log("wrote %s[%d].%s=%s" % (widget, monitor, key, value))


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
        log("base_rect FAILED: monitors.py produced no output")
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
        log("base_rect FAILED: %r" % out)
        sys.exit("ERROR: workarea.py --base-rect failed:\n%s" % out)


def is_degenerate_rect(x, y, w, h):
    """True when move_x/y/w/h still carry the pre-session defaults.

    eww variables persist between sessions; if a Save somehow fires before
    move.py ever initialized them for this round (race, stray keypress,
    ghost panel), the stored rect reads 100x100 at (0,0). Writing THAT
    produced scale=MIN + top-left positions for users (measured bug), so
    such a state is refused instead of saved.
    """
    return (w, h) == (100, 100) and (x, y) == (0, 0)


def finish():
    # Close every popup window that is still mapped BEFORE ending the
    # keyboard-daemon session. The per-monitor dismiss overlays are
    # deliberately left OPEN for the whole Move/Resize session (they are the
    # click-outside-to-cancel surface), so a session ended HERE -- Save /
    # Cancel / Reset button, Enter / ESC on the keyboard -- must clean them
    # up itself. Skipping this left an invisible full-monitor layer above
    # the widget that swallowed every further right-click until restart
    # (measured). close_popup reads generated/input_session.json for the
    # per-monitor overlay ids, hence the ordering.
    try:
        sys.path.insert(0, os.path.join(SCRIPTS_DIR, "widgets"))
        import close_popup

        close_popup.close_popups_verified(close_popup.read_session_data())
    except Exception:
        pass
    session.clear_session()


def base_sizes(widget, monitor, rect):
    """(base_w, base_h, right_gap, h_align, v_align)

    The natural (scale = 1.0) sizes come from widget_rect.py, which reports
    them for BOTH widgets (the panel's natural height is the gap-derived
    layout height), so the per-axis scales are simply w/base_w and h/base_h.
    """
    alignment = config("alignment") or "middle_middle"
    h_align, v_align = split_anchor(alignment)
    if widget == "clock":
        # The clock's natural width is dynamic (ends at the city name).
        base_w = rect.get("natural_w") or 745
        base_h = rect.get("natural_h") or CLOCK_H
    else:
        base_w = rect.get("natural_w") or PANEL_WIDTH
        base_h = rect.get("natural_h") or int(round(rect["height"]))
    return base_w, base_h, rect.get("right_gap"), h_align, v_align


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--action", required=True,
                    choices=["left", "right", "up", "down",
                             "zoom_in", "zoom_out", "set_scale",
                             "zoom_in_x", "zoom_out_x", "set_scale_x",
                             "zoom_in_y", "zoom_out_y", "set_scale_y",
                             "reset", "save", "cancel"])
    ap.add_argument("--value", type=float, default=None,
                    help="percentage for --action set_scale/set_scale_x/set_scale_y")
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
    log("action=%s widget=%s monitor=%d value=%s rect=(%d,%d %dx%d)"
        % (args.action, args.widget, args.monitor, args.value, x, y, w, h))

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
        save_value(args.widget, args.monitor, "scale_x", "1.00")
        save_value(args.widget, args.monitor, "scale_y", "1.00")
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

    if args.action in PROPORTIONAL_ACTIONS + WIDTH_ACTIONS + HEIGHT_ACTIONS:
        base_w, base_h, right_gap, h_align, v_align = base_sizes(args.widget, args.monitor, rect)
        # Start from the CURRENT session size (move_w/move_h), not the saved
        # config scale: clicking zoom_out repeatedly must keep stepping down
        # instead of recomputing from the untouched config value each time.
        cur_x = (w / base_w) if base_w else 1.0
        cur_y = (h / base_h) if base_h else 1.0
        proportional = args.action in PROPORTIONAL_ACTIONS
        touch_w = proportional or args.action in WIDTH_ACTIONS
        touch_h = proportional or args.action in HEIGHT_ACTIONS
        if args.action.startswith("set_scale"):
            if args.value is None:
                sys.exit("ERROR: --action %s requires --value <percent>" % args.action)
            target = clamp(args.value / 100.0, MIN_SCALE, MAX_SCALE)
        else:
            delta = SCALE_STEP if args.action.startswith("zoom_in") else -SCALE_STEP
            ref = cur_x if (proportional or touch_w) else cur_y
            target = clamp(ref + delta, MIN_SCALE, MAX_SCALE)
        new_scale_x = target if touch_w else cur_x
        new_scale_y = target if touch_h else cur_y
        w = int(round(base_w * new_scale_x)) if base_w else w
        h = int(round(base_h * new_scale_y)) if base_h else h
        # Only the touched axis is re-anchored; the other stays exactly where
        # the previous step put it (so W and H steps compose freely).
        pos_x = float(config("position_x", args.monitor) or 0)
        pos_y = float(config("position_y", args.monitor) or 0)
        if touch_w:
            if right_gap is not None:
                x = frame_w - right_gap - w
            else:
                x = int(align_pos(w, frame_w, h_align) + pos_x)
        if touch_h and right_gap is None:
            # Clock: realign vertically to the anchor. The panel keeps its y:
            # its baseline is the top edge / gap-derived position, same as the
            # proportional path always did.
            y = int(align_pos(h, frame_h, v_align) + pos_y)
        eww("update", "move_x=%d" % x, "move_y=%d" % y, "move_w=%d" % w, "move_h=%d" % h,
            "move_pct=%d" % int(round(new_scale_x * 100)),
            "move_pct_h=%d" % int(round(new_scale_y * 100)))
        return

    if args.action == "save":
        # SAFETY: never persist a degenerate/unreachable rect (see helpers).
        if is_degenerate_rect(x, y, w, h):
            log("save REFUSED: degenerate rect at origin")
            sys.exit("ERROR: refusing to save default-sized rect at origin "
                     "(nothing was resized/dragged this session)")
        base_w, base_h, right_gap, h_align, v_align = base_sizes(args.widget, args.monitor, rect)
        # Per-axis scales: the dragged rectangle may be non-proportional.
        scale_x = clamp(w / base_w, MIN_SCALE, MAX_SCALE) if base_w else 1.0
        scale_y = clamp(h / base_h, MIN_SCALE, MAX_SCALE) if base_h else 1.0
        margin = 40  # the saved widget must keep at least this much on-screen

        def refuse_outside(px, py, pw, ph):
            """Refuse (exit) when the saved widget would be fully off-screen."""
            if px + pw < margin or px > frame_w - margin or \
               py + ph < margin or py > frame_h - margin:
                log("save REFUSED off-screen: pos=(%d,%d) %dx%d frame=%dx%d"
                    % (px, py, pw, ph, frame_w, frame_h))
                sys.exit("ERROR: refusing to save off-screen position "
                         "(%d,%d %dx%d on %dx%d frame)" % (px, py, pw, ph, frame_w, frame_h))

        if args.widget == "panel":
            # The panel position is a per-monitor offset added to the global
            # panel.gap baseline, so Save writes the delta between the dragged
            # rectangle and the gap-derived base rectangle (frame coords, at
            # the dragged size). Positive offsets shift right/down.
            base = base_rect(args.monitor, w, h)
            new_x = int(round(x - base["base_left"]))
            new_y = int(round(y - base["base_top"]))
            log("save panel: dragged=(%d,%d) base=(%s,%s) -> offsets=(%d,%d) scales=%.2f/%.2f"
                % (x, y, base["base_left"], base["base_top"], new_x, new_y, scale_x, scale_y))
            # new_x/new_y are OFFSETS relative to the gap baseline and may
            # legitimately be NEGATIVE (dragging away from the anchored edge
            # measured bug: offsets like -880 were validated as absolute
            # coordinates and refused). The rendered widget lands exactly on
            # the dragged rectangle (baseline + offsets), so THAT is what the
            # on-screen check must see.
            refuse_outside(x, y, w, h)
            save_value(args.widget, args.monitor, "position_x", new_x)
            save_value(args.widget, args.monitor, "position_y", new_y)
        else:
            new_x = int(round(x - align_pos(w, frame_w, h_align)))
            new_y = int(round(y - align_pos(h, frame_h, v_align)))
            vw = int(round(base_w * scale_x))
            vh = int(round(base_h * scale_y))
            log("save clock: dragged=(%d,%d) align=(%s,%s) -> offsets=(%d,%d) scales=%.2f/%.2f"
                % (x, y, h_align, v_align, new_x, new_y, scale_x, scale_y))
            refuse_outside(new_x, new_y, vw, vh)
            save_value(args.widget, args.monitor, "position_x", new_x)
            save_value(args.widget, args.monitor, "position_y", new_y)
        save_value(args.widget, args.monitor, "scale_x", "%.2f" % scale_x)
        save_value(args.widget, args.monitor, "scale_y", "%.2f" % scale_y)
        # Backward-compatible mirror: readers that only know the shared
        # `scale` keep seeing the width axis (the pre-v2.3.0 behavior).
        save_value(args.widget, args.monitor, "scale", "%.2f" % scale_x)
        finish()
        return


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if str(exc) and str(exc) != "None":
            log("exit: %s" % exc)
        raise
    except Exception:
        import traceback

        log("EXCEPTION:\n%s" % traceback.format_exc())
        raise