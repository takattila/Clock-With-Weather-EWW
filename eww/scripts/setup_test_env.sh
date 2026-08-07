#!/usr/bin/env bash
# ===========================================================================
# setup_test_env.sh - KDE Plasma test environment setup / restore
#
# Creates a clean desktop (solid color or wallpaper background, no desktop
# widgets, no desktop icons) for screenshot-based verification of the eww
# widget. The normal desktop is restored with the "restore" subcommand.
#
# How it works:
#   - The original appletsrc is backed up once (used by "restore").
#   - Desktop containments are detected dynamically (plugin + formfactor);
#     nothing is hardcoded.
#   - A test copy is written while plasmashell is stopped, so the daemon
#     cannot overwrite it on exit. Desktop widgets, icon positions and the
#     video wallpaper are removed; the test background (solid color or
#     wallpaper image) is set. The panel (taskbar) is kept untouched.
#   - plasmashell is restarted with nohup so the changes take effect.
# ===========================================================================
set -euo pipefail

APLETSRC="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
BACKUP="$APLETSRC.backup"
BG_FILE="$HOME/.config/eww-test-background.png"
BG_COLOR="${EWW_TEST_BG_COLOR:-#2d3034}"

log() { echo "[setup_test_env] $*"; }
die() { echo "[setup_test_env] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- generate
generate_background() {
  local color="$1"
  python3 - "$BG_FILE" "$color" <<'PY'
import re
import subprocess
import sys

from PIL import Image

bg_file, color = sys.argv[1], sys.argv[2]
color = color.lstrip("#")
if len(color) == 3:
    color = "".join(ch * 2 for ch in color)
if not re.fullmatch(r"[0-9a-fA-F]{6}", color):
    sys.exit("Invalid color: %s (e.g. #2d3034)" % color)
rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))

w, h = 1920, 1080
try:
    out = subprocess.check_output(["xrandr"], text=True, stderr=subprocess.DEVNULL)
    m = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
except Exception:
    pass

Image.new("RGB", (w, h), rgb).save(bg_file)
print("  background: %s (%dx%d) %s" % (bg_file, w, h, "#%02x%02x%02x" % rgb))
PY
}

install_wallpaper() {
  local src="$1"
  cp "$src" "$BG_FILE"
  log "wallpaper installed: $src -> $BG_FILE"
}

# --------------------------------------------------------- test config
# Build the test appletsrc from the backup: strip desktop widgets and icon
# positions, set the solid wallpaper, drop the ScreenMapping. The panel is
# detected dynamically (formfactor != 0) and left untouched.
make_test_config() {
  python3 - "$BACKUP" "$APLETSRC" "$BG_FILE" <<'PY'
import re
import sys

src, dst, bg_path = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src, encoding="utf-8").read()

# Pass 1: detect desktop containments (plugin + formfactor=0).
desktop_ids = set()
cur = None
cur_keys = {}
for line in text.splitlines():
    s = line.strip()
    m = re.match(r"^\[Containments\]\[(\d+)\]$", s)
    if m:
        if cur is not None and cur_keys.get("formfactor") == "0" and cur_keys.get("plugin") in (
            "org.kde.desktopcontainment",
            "org.kde.plasma.folder",
        ):
            desktop_ids.add(cur)
        cur = int(m.group(1))
        cur_keys = {}
        continue
    if cur is not None and s.startswith("[Containments]"):
        if cur_keys.get("formfactor") == "0" and cur_keys.get("plugin") in (
            "org.kde.desktopcontainment",
            "org.kde.plasma.folder",
        ):
            desktop_ids.add(cur)
        cur = None
        cur_keys = {}
        continue
    if cur is not None and not s.startswith("[") and "=" in s:
        k, _, v = s.partition("=")
        cur_keys[k.strip()] = v.strip()
if cur is not None and cur_keys.get("formfactor") == "0" and cur_keys.get("plugin") in (
    "org.kde.desktopcontainment",
    "org.kde.plasma.folder",
):
    desktop_ids.add(cur)

# Pass 2: rewrite the file.
out = []
section = ""
skip = False
desktop_wallpaper_seen = set()

for line in text.splitlines(keepends=True):
    stripped = line.strip()

    if stripped.startswith("[") and stripped.endswith("]") and "=" not in stripped:
        section = stripped
        keep = True
        if section == "[ScreenMapping]":
            keep = False
        else:
            m = re.match(r"^\[Containments\]\[(\d+)\](.*)$", section)
            if m:
                cid = int(m.group(1))
                rest = m.group(2)
                if cid in desktop_ids:
                    if "[Applets]" in rest:
                        keep = False
                    else:
                        wm = re.match(r"^\[Wallpaper\]\[([^\]]+)\]", rest)
                        if wm and wm.group(1) != "org.kde.image":
                            keep = False
                        elif wm:
                            desktop_wallpaper_seen.add(cid)
        skip = not keep
        if keep:
            out.append(line)
        continue

    if skip:
        continue

    # drop icon geometry keys from the desktop containment body
    cm = re.match(r"^\[Containments\]\[(\d+)\]$", section)
    if cm and int(cm.group(1)) in desktop_ids and (
        stripped.startswith("ItemGeometries-") or stripped.startswith("ItemGeometriesHorizontal")
    ):
        continue

    # drop icon positions / widget order from the desktop [General] group
    gm = re.match(r"^\[Containments\]\[(\d+)\]\[General\]$", section)
    if gm and int(gm.group(1)) in desktop_ids:
        if (
            re.match(r"^(positions|changedPositions|arrangement|lastResolution|AppletOrder|sortMode)=", stripped)
            or stripped.startswith("ItemGeometries-")
            or stripped.startswith("ItemGeometriesHorizontal")
        ):
            continue

    # solid wallpaper
    wm = re.match(r"^\[Containments\]\[(\d+)\]\[Wallpaper\]\[org\.kde\.image\]\[General\]$", section)
    if wm and int(wm.group(1)) in desktop_ids and stripped.startswith("Image="):
        line = "Image=file://%s\n" % bg_path

    out.append(line)

for cid in sorted(desktop_ids):
    if cid not in desktop_wallpaper_seen:
        out.append("\n[Containments][%d][Wallpaper][org.kde.image][General]\n" % cid)
        out.append("Image=file://%s\n" % bg_path)

text = "".join(out)
text = re.sub(r"(?m)^(itemsOnDisabledScreens|screenMapping)=.*\n", "", text)
open(dst, "w", encoding="utf-8").write(text)
PY
  log "test config written: $APLETSRC"
}

# ------------------------------------------------------------ plasmashell
stop_plasmashell() {
  log "stopping plasmashell..."
  kquitapp6 plasmashell 2>/dev/null || true
  sleep 1
}

start_plasmashell() {
  nohup plasmashell >/dev/null 2>&1 &
  disown
  sleep 2
  log "plasmashell running."
}

# ----------------------------------------------------------------- commands
cmd_hide() {
  local arg="${1:-}"

  [[ -f "$APLETSRC" ]] || die "Not found: $APLETSRC"

  # back up the original desktop once (kept for restore)
  if [[ ! -f "$BACKUP" ]]; then
    cp "$APLETSRC" "$BACKUP"
    log "backup created: $BACKUP"
  else
    log "backup already exists: $BACKUP (keeping it)"
  fi

  # background source: color (#RRGGBB) or a wallpaper image file
  if [[ "$arg" == "#"* ]]; then
    generate_background "$arg"
  elif [[ -z "$arg" ]]; then
    generate_background "$BG_COLOR"
  elif [[ -f "$arg" ]]; then
    install_wallpaper "$arg"
  else
    die "Not a color or existing file: $arg"
  fi

  stop_plasmashell
  make_test_config
  start_plasmashell
  log "Test environment active (desktop widgets + icons hidden, test background set)."
}

cmd_restore() {
  [[ -f "$BACKUP" ]] || die "No backup to restore ($BACKUP). Run 'hide' first."

  stop_plasmashell
  cp "$BACKUP" "$APLETSRC"
  log "restored: $APLETSRC (the .backup is kept)"
  start_plasmashell
  log "Normal desktop restored."
}

cmd_status() {
  if [[ -f "$APLETSRC" ]] && grep -q "Image=file://$BG_FILE" "$APLETSRC"; then
    echo "Status: TEST MODE active (desktop widgets + icons hidden, test background). Restore: $0 restore"
  elif [[ -f "$BACKUP" ]]; then
    echo "Status: NORMAL desktop (backup exists: $BACKUP). Test mode: $0 hide"
  else
    echo "Status: NORMAL desktop (no backup). Test mode: $0 hide"
  fi
}

usage() {
  cat <<EOF
Usage: $0 <command> [color|wallpaper]

Commands:
  hide                Enable test mode (default background color $BG_COLOR)
  hide "#RRGGBB"      Enable test mode with a custom background color
  hide /path/to/img   Enable test mode with a wallpaper image
  restore             Restore the normal desktop from the backup
  status              Print the current state
  -h, --help          Show this help

Environment:
  EWW_TEST_BG_COLOR   Background color used by 'hide' (default $BG_COLOR)
EOF
  exit 0
}

# ------------------------------------------------------------- dispatch
main() {
  case "${1:-}" in
    hide)    cmd_hide "${2:-}" ;;
    restore) cmd_restore ;;
    status)  cmd_status ;;
    -h|--help|"") usage ;;
    *) die "Unknown command: ${1} (usage: hide | restore | status)" ;;
  esac
}

main "$@"
