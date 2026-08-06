#!/usr/bin/env bash
# ===========================================================================
# setup_test_env.sh — KDE Plasma tesztkörnyezet beállítása / visszaállítása
#
# Az eww widget képernyőkép-alapú ellenőrzéséhez tiszta, egyszínű hátterű,
# widget- és asztali-ikonmentes asztalt hoz létre. A normál asztalod a
# "restore" alparanccsal áll vissza.
#
# Használat:
#   ./setup_test_env.sh hide                # tesztmód bekapcsolása
#   ./setup_test_env.sh hide "#RRGGBB"      # tesztmód bekapcsolása egyedi színnel
#   ./setup_test_env.sh restore             # normál asztal visszaállítása
#   ./setup_test_env.sh status              # aktuális állapot kiírása
#
# Mit csinál:
#   1. Elrejti az asztali widgeteket (desktopcontainment -> folder view)
#   2. Elrejti az asztali ikonokat (pozíciók törlése)
#   3. Egyszínű hátteret állít be (alapértelmezett #2d3034, ld. EWW_TEST_BG_COLOR)
#   4. Újraindítja a plasmashell-t, hogy a módosítás életbe lépjen
# ===========================================================================
set -euo pipefail

APLETSRC="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
BACKUP="$APLETSRC.backup"
BG_FILE="$HOME/.config/eww-test-background.png"
BG_COLOR="${EWW_TEST_BG_COLOR:-#2d3034}"

log() { echo "[setup_test_env] $*"; }
die() { echo "[setup_test_env] HIBA: $*" >&2; exit 1; }

# ---------------------------------------------------------------- generálás
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
    sys.exit("Érvénytelen szín: %s (pl. #2d3034)" % color)
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
print("  hatter: %s (%dx%d) %s" % (bg_file, w, h, "#%02x%02x%02x" % rgb))
PY
}

# ------------------------------------------------ teszt-konfig létrehozása
make_test_config() {
  # Az aktuális appletsrc-t tesztmódra alakítjuk: desktopcontainment helyett
  # folder view (widgetek nincsenek), ikon-pozíciók és ScreenMapping törölve,
  # háttér az egyszínű PNG-re cserélve. A panelt (Containments[2]) érintetlen
  # hagyjuk.
  python3 - "$APLETSRC" "$BG_FILE" <<'PY'
import re
import sys

cfg_path, bg_path = sys.argv[1], sys.argv[2]
text = open(cfg_path, encoding="utf-8").read()

out = []
section = ""
for line in text.splitlines(keepends=True):
    stripped = line.strip()
    # a teljes szekciófejléc, pl. "[Containments][1][General]"
    if stripped.startswith("[") and stripped.endswith("]") and "=" not in stripped:
        section = stripped
        out.append(line)
        continue

    # desktop ikon-pozíciók törlése (üres folder view = nincs ikon)
    if section == "[Containments][1][General]" and re.match(
        r"^(changedPositions|positions|arrangement)=", stripped
    ):
        continue

    # desktop containment -> folder view (asztali widgetek elrejtése)
    if section == "[Containments][1]" and stripped == "plugin=org.kde.desktopcontainment":
        line = line.replace(
            "plugin=org.kde.desktopcontainment", "plugin=org.kde.plasma.folder"
        )

    # háttér cseréje az egyszínű PNG-re
    if section == "[Containments][1][Wallpaper][org.kde.image][General]" and stripped.startswith("Image="):
        line = "Image=file://%s\n" % bg_path

    out.append(line)

text = "".join(out)
# ikonok képernyőleképezésének törlése
text = re.sub(r"(?m)^(itemsOnDisabledScreens|screenMapping)=.*\n", "", text)
open(cfg_path, "w", encoding="utf-8").write(text)
PY
  log "teszt-konfig írva: $APLETSRC"
}

# ------------------------------------------------------------ plasmashell
restart_plasmashell() {
  log "plasmashell újraindítása..."
  kquitapp6 plasmashell 2>/dev/null || true
  sleep 1
  nohup plasmashell >/dev/null 2>&1 &
  disown
  sleep 2
  log "plasmashell fut."
}

# ----------------------------------------------------------------- parancsok
cmd_hide() {
  local color="${1:-$BG_COLOR}"

  [[ -f "$APLETSRC" ]] || die "Nem található: $APLETSRC"

  # biztonsági mentés csak egyszer (a normál asztal megőrzése)
  if [[ ! -f "$BACKUP" ]]; then
    cp "$APLETSRC" "$BACKUP"
    log "biztonsági mentés készült: $BACKUP"
  else
    log "biztonsági mentés már létezik: $BACKUP (megtartom)"
  fi

  generate_background "$color"
  make_test_config
  restart_plasmashell
  log "Tesztkörnyezet aktív (widgetek + ikonok rejtve, egyszínű háttér)."
}

cmd_restore() {
  [[ -f "$BACKUP" ]] || die "Nincs visszaállítható mentés ($BACKUP). Futtasd előbb a 'hide'-ot."

  cp "$BACKUP" "$APLETSRC"
  log "visszaállítva: $APLETSRC (a .backup megmaradt)"
  restart_plasmashell
  log "Normál asztal visszaállítva."
}

cmd_status() {
  if [[ -f "$APLETSRC" ]] && grep -q "plugin=org.kde.plasma.folder" "$APLETSRC"; then
    echo "Állapot: TESZTMÓD aktív (folder view, nincs widget/ikon). Visszaállítás: $0 restore"
  elif [[ -f "$BACKUP" ]]; then
    echo "Állapot: NORMÁL asztal (van mentés: $BACKUP). Tesztmód: $0 hide"
  else
    echo "Állapot: NORMÁL asztal (nincs mentés). Tesztmód: $0 hide"
  fi
}

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# ------------------------------------------------------------- dispatch
main() {
  case "${1:-}" in
    hide)    cmd_hide "${2:-}" ;;
    restore) cmd_restore ;;
    status)  cmd_status ;;
    -h|--help|"") usage ;;
    *) die "Ismeretlen alparancs: ${1} (használat: hide | restore | status)" ;;
  esac
}

main "$@"
