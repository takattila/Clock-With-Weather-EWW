# PLAN: Context menu – Move / Resize / About

## 1. Goal
Right-clicking the **weather/clock** widget or the **panel** widget (on any monitor) opens a context menu with: **Move**, **Resize**, **About**. Every action works **per widget and per monitor** individually; coordinates / `scale` values are written to `config.yaml`. It must work on both Wayland and X11.

## 2. Research findings (eww 0.5.0)
- **Right click**: the `eventbox`/`button` widget supports `:onrightclick` → native solution, works on both compositors.
- **Keyboard**: eww 0.5.0 **cannot** capture arrow keys/ENTER/ESC (no keybinding support). A small **PyGObject GTK3 helper window** must therefore capture the keys (available on the system).
- **Positioning**: eww window geometry is fixed at open time; it can be overridden via `eww open ... --arg pos="x y" --arg size="w h" --arg screen=N --arg anchor=...`.
- **Dynamic movement**: the `transform` widget (`:translate-x/:translate-y/:scale-x/:scale-y`) can be bound to a `defvar` → `eww update move_x=...` moves smoothly inside a full-monitor overlay.
- **Commit mechanism**: the `watch.py` inotify watcher auto-reloads + runs `start.sh --relayout` when `config.yaml` changes → writing the file moves/resizes the widget.
- **Multi-monitor** infrastructure already exists: `monitors.py`, `workarea.py`, `.layout.json`, `start.sh` per-monitor open.
- **X11/Wayland equivalence**: the plan builds on both backends of eww 0.5.0. The positioning math (X11: absolute coordinates vs. Wayland: workarea-relative layer-shell margins) reuses the `workarea.py` logic.

## 3. New dependencies + `install.sh` changes
New programs required:
- **PyGObject GTK3** (keyboard helper): `import gi; from gi.repository import Gtk`
- **xdotool** (X11 cursor position for the menu)
- **xdg-utils** (`xdg-open` for the About URL)

Extend the package lists of the `installEwwDependencies()` function in `scripts/install.sh` (following the existing per-distro structure):

| Distro | Packages to add |
|---|---|
| apt (Debian/Ubuntu) | `python3-gi gir1.2-gtk-3.0 xdotool xdg-utils` |
| dnf / yum (Fedora/RHEL/EPEL) | `python3-gobject gtk3 xdotool xdg-utils` |
| pacman (Arch) | `python-gobject gtk3 xdotool xdg-utils` |
| zypper (openSUSE) | `python3-gobject gtk3 xdotool xdg-utils` |

`requirements.txt` stays **unchanged** (PyGObject is a system package, not pip). The GTK3 runtime typelib (`gir1.2-gtk-3.0`) guarantees that `gi.repository.Gtk` can be imported.

## 4. Configuration (`config.yaml`)
New keys (commented), global default + optional per-monitor override:

```yaml
weather:
  window:
    alignment: middle_middle
    position_x: 0
    position_y: 0
    scale: 1.0                 # new
    per_monitor: {}            # new: {0: {position_x, position_y, scale}}

panel:
  window:
    alignment: right
    scale: 1.0                 # new
    per_monitor: {}            # new: {0: {scale}}
```

Merge rule: `per_monitor[monitor]` keys override the global keys.

## 5. Scale semantics ("single object")
The relative distances of the inner elements are preserved because the scale is applied uniformly in two places:
1. **Window size** = base size × scale (computed by `start.sh`: clock 745×250×s; panel 250×s wide, height ×s).
2. **Content**: the widget root is wrapped in `transform :scale-x {scale} :scale-y {scale}` → fonts, icons and margins scale proportionally.

`panel.py` stays unchanged (the charts are generated for the scaled height; the transform scales them).

## 6. New / modified files

**New scripts**
| Script | Role |
|---|---|
| `scripts/ctx.py` | `--widget clock\|panel --monitor N` → opens the `ctx_menu` at the cursor / widget corner |
| `scripts/widget_rect.py` | Absolute rectangle of the widget on the monitor (handles X11/Wayland differences, reusing `workarea.py` logic) |
| `scripts/menu_pos.py` | Menu position: on X11 at the cursor (`xdotool getmouselocation`), on Wayland anchored to the widget corner |
| `scripts/move.py` | Move/resize mode controller: opens the overlay, starts the key helper, ENTER→save, ESC→exit |
| `scripts/move_keys.py` | GTK3 key helper window (arrows/ENTER/ESC) |
| `scripts/about.py` | Git repo data as JSON (remote URL, branch, commit, date, message, tag) |
| `scripts/config_set.py` | **Line-aware** YAML writing (only touches the target key lines, PRESERVES the comments – a plain YAML dump would destroy the file) |

**Files to modify**
- `config.yaml` – new keys.
- `scripts/config.py` – new keys (`scale`, per-monitor resolution).
- `scripts/install.sh` – dependencies (see section 3).
- `scripts/start.sh` – per-monitor merge, scaled window sizes, new `--arg`s (`screen`, `main_w`, `main_h`, `main_scale`; panel `pw/ph` × scale).
- `eww.yuck` – new windows, eventboxes, defvars, transform scaling.
- `eww.scss` – menu / overlay / about styles.
- `generated/move_rect.svg` – SVG rectangle file (sized for the weather and panel widgets).

## 7. New windows in `eww.yuck`
- **`ctx_menu`** `[widget monitor]`: 3 buttons – "Move", "Resize", "About"; `:onclick` points to the corresponding scripts.
- **`move_overlay`** `[screen]`: full-monitor transparent layer, `:stacking "overlay"` (Wayland) / `"foreground"` (X11), not focusable; content: `transform :translate-x {move_x} ...` + `image :path "generated/move_rect.svg" :image-width {move_w} :image-height {move_h}`.
- **`about_window`**: repo data + "Open" button (`xdg-open <url>`, with `.git` stripped).
- defvars: `move_x`, `move_y`, `move_w`, `move_h`, `about_json`.
- The clock/panel root is wrapped in `eventbox :onrightclick "scripts/ctx.py ..."` and `transform`; `main_window` also gets a `screen` argument.

## 8. Interaction flow
1. Right-click the widget → `ctx.py` opens the menu.
2. **Move**: `move.py` computes the current rectangle, opens the overlay, starts the key helper. Arrows (±10px) → `eww update move_x/move_y`; **ENTER** → `config_set.py` writes `position_x/y` to `config.yaml` (per-monitor or global) → watcher relayout → the widget moves; **ESC** → exit without saving.
3. **Resize**: arrows ±0.05 scale (Shift: ±0.01), `move_w/h` = base×scale live; **ENTER** → scale saved to `config.yaml`; **ESC** → exit.
4. **About**: `about.py` JSON → `about_window`; the button opens the repo URL.

## 9. X11 vs Wayland – differences
Functionally identical on both compositors, with two planned UX differences:
1. **Menu position**: on X11 exactly at the cursor (`xdotool`); on Wayland anchored to the widget corner (no global cursor position API). Optionally improvable via KWin scripting.
2. **Keyboard focus**: on X11 the key helper performs a keyboard grab (receives the arrows immediately); on Wayland the compositor decides, so one click on the helper window may be needed.

## 10. Risks / notes
- `config_set.py` preserves the `config.yaml` comments via line-aware editing.
- During move/resize the overlay covers the monitor modally (intended).
- If the dynamic `transform` update turns out not to be smooth, fallback: reopen the overlay with `--arg pos/size` per step.

## 11. Testing
- On both compositors: right-click → menu; move → widget relocates (watcher); resize → proportional scaling; About → URL opens.
- Regression: `config.py --key ...`, `start.sh` layout, panel charts, monitor changes.
- Debug: `eww logs`.
