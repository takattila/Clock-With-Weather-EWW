# PLAN: Context menu – Move / Resize / About

## 1. Goal
Right-clicking the **weather/clock** widget or the **panel** widget (on any monitor) opens a context menu with: **Move**, **Resize**, **About**. Every action works **per widget and per monitor** individually; coordinates / `scale` values are written to `config.yaml`. Works on both Wayland and X11. The Move/Resize session can be driven by the mouse (dragging/resizing the rectangle) as well as by the keyboard.

## 2. Current architecture (implemented)

**Context menu**
- Right click (`eventbox`/`button :onrightclick`) → `scripts/ctx.py` opens `ctx_menu` (Move / Resize / About) above a transparent `dismiss_overlay`; clicking outside the menu closes it.
- `scripts/about.py` opens the `about_window` with git data (remote, branch, commit, date, message); the button opens the repo URL.

**Move / Resize session**
- `scripts/move.py` computes the widget rectangle (`scripts/widget_rect.py`), activates the keyboard daemon session, sets the `move_x/move_y/move_w/move_h/move_pct` eww defvars, spawns the rectangle window (`scripts/move_rect.py`, BEFORE the panel so the panel stacks above) and the control panel. It returns immediately (eww command timeout), the rest runs in the background.
- The **rectangle** (`scripts/move_rect.py`) is a full-monitor transparent GTK3 window that draws the dashed rectangle itself from `move_x/move_y/move_w/move_h`. Dragging inside moves it, dragging a corner/edge resizes it (aspect ratio kept, scale 0.3..1.5), clicking outside cancels the session. While not dragging it re-syncs from the eww defvars (arrows / +/- keep working).
- The **control panel** (`scripts/move_panel.py`) is a GTK3 window (not eww: eww 0.5.0 cannot move windows and a `transform`-wrapped panel loses button clicks). Buttons call `scripts/move_ctl.py`; the title bar is mouse-draggable on both backends (X11: `GtkWindow.begin_move_drag` / WM-driven; Wayland: layer-shell margins, pointer-chasing). It polls `move_pct` for the % label and quits when the session file is cleared.
- `scripts/move_ctl.py` actions: `left/right/up/down` (move ±10 px, clamped to the frame), `zoom_in/zoom_out` (±0.05 scale, clamped 0.3..1.5, anchor / right-gap preserved), `reset` (defaults), `save`, `cancel`. Save writes `position_x`/`position_y`/`scale` via `scripts/config_set.py` (line-aware YAML write that preserves comments) → the `watch.py` watcher triggers `start.sh --relayout` → the widget moves/resizes.
- The `move`/`resize` menu modes are currently identical (both open the same combined session).

**Keyboard handling**
- `scripts/input_daemon.py` reads `/dev/input/event*` via evdev (started by `start.sh` through passwordless sudo, drops to the user afterwards). It creates **no window**. While `generated/input_session.json` exists it maps keys, then goes idle:
  - ctx mode: `ESC` → close popups.
  - move mode: arrows → move, `Shift+3`/numpad `+` → zoom_in, `-` → zoom_out, `Enter` → save, `ESC` → cancel.
- `scripts/session.py` manages the session file and lazily restarts the daemon.

**Configuration** (`config.yaml`)
- `weather.window`: `position_x`, `position_y`, `scale`, optional `per_monitor` overrides; `panel.window`: `scale` (+ `per_monitor`). Per-monitor keys override the globals.
- Scale is a single uniform factor: window size = base × scale (clock 745×250, panel width 250) and the widget root is wrapped in `transform :scale-x {scale} :scale-y {scale}`.

**Environment / dependencies**
- PyGObject GTK3 (`python3-gi`, `gir1.2-gtk-3.0`), `gir1.2-gtk-layer-shell-0.1` for Wayland layer-shell, `xdotool` (X11 cursor position), `xdg-utils`, `librsvg` (SVG loader), evdev access (root / `input` group).

## 3. Implemented – mouse-dragging the rectangle (move + resize)
Goal: during a Move/Resize session the **weather** and **panel** rectangles must be draggable **and** resizable with the mouse, and a click **outside** the rectangle still cancels. eww 0.5.0 has no drag support, so the eww `move_overlay` is replaced by a GTK3 window that draws the rectangle itself.

**New `scripts/move_rect.py`** – full-monitor transparent GTK3 window:
- Positioning: Wayland → layer-shell `TOP` anchored to all four edges of the monitor; X11 → undecorated `override-redirect` toplevel at the monitor origin/size from `Gdk.Monitor.get_geometry()`, `keep_above`. Transparency via `app-paintable` + rgba visual.
- Stacking so the control panel stays clickable: the panel is a layer-shell **OVERLAY** surface on Wayland (the protocol guarantees OVERLAY > TOP, so it is always above this full-monitor window regardless of the map order – with both in OVERLAY the slower-starting rectangle window mapped last, swallowed every panel click and turned Save/Cancel into "click outside -> cancel"). On X11 both are override-redirect toplevels (required to float above the eww widgets), so the panel **raises itself every tick** to stay above the rectangle.
- Drawing: Cairo renders the dashed white outline + faint fill at `(move_x, move_y, move_w, move_h)` (same style as `generated/move_rect.svg`).
- Hit-test on press (≈8-10 px):
  - **corner** → resize keeping the opposite corner fixed;
  - **edge** → resize keeping the opposite edge fixed;
  - **inside** → move;
  - **outside** → `move_ctl.py ... --action cancel`.
- Resize preserves the aspect ratio: `scale = clamp(s0 · dist(pointer, anchor) / dist(pointer₀, anchor), 0.3, 1.5)` → `w = base_w·scale`, `h = base_h·scale`, `x/y` recomputed from the fixed anchor; updates `move_w/move_h/move_pct` (the panel's % label follows).
- Move: `eww update move_x/move_y`, throttled to ≈50 ms + a final flush on release.
- 250 ms tick: while not dragging, sync from `move_x/move_y/move_w/move_h/move_pct` (keyboard arrows / +− buttons keep working), and quit when `generated/input_session.json` is cleared.
- Cursor feedback per hit-test (`grab` / resize arrows); `set_accept_focus(False)`.
- The `move_*` eww defvars stay the single shared state for keyboard, panel buttons and mouse.

**Modified files**
- `scripts/move.py` – drop the eww `move_overlay` open/close and the `gen_rect_svg.py` call; spawn `move_rect.py` **before** `move_panel.py` (panel stacks above and stays clickable); the `move_*` updates remain.
- `scripts/move_ctl.py` – `finish()` no longer closes `move_overlay` (the rect window exits via the session file).
- `scripts/widget_rect.py` – report `frame_ox`/`frame_oy` (frame origin inside the monitor) for the full-monitor rect window.
- `eww.yuck` – remove the `move_overlay` defwindow and `widget_move_overlay` defwidget (+ header comment); keep the `move_x/y/w/h/pct` defvars.
- `eww.scss` – remove `.move-overlay` / `.move-rect`.
- `PLAN.md` – this section.

**Notes**
- The full-screen transparent window is modal while the session is active (intended, same as today).
- Mouse resize mirrors the scale model of the +− buttons (aspect ratio preserved, scale bounds 0.3..1.5).
- Splitting the unused `--mode move|resize` into move-only / resize-only sessions is possible later but not required.

## 4. Testing
- `python3 -m py_compile` on all touched scripts; `eww reload` / `start.sh --relayout`.
- X11 (XWayland, `DISPLAY=:0` via xdotool): drag inside → `move_x/move_y` change; drag a corner/edge → `move_w/move_h` + `move_pct` change; click outside → session ends.
- Wayland smoke test: rect + panel start, run cleanly, quit when the session file is removed (mouse synthesis is not possible on Wayland, but the logic is backend-independent because the rectangle is drawn, not a window).
- Regression: `config.py --key ...`, `start.sh` layout, panel charts, monitor changes. Debug: `eww logs`.