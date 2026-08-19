# PLAN

## 1. About ablak – több részletes info
**Fájlok:** `scripts/about.py`, `scripts/about_win.py`

- **about.py `collect()`** – új kulcsok: `full_commit` (%H), `author` (%an), `author_email` (%ae), `author_date` (%cI). Meglévő kulcsok maradnak.
- **about_win.py** – ablak ~540×430, szekciókra bontva:
  - **Repository**: URL, branch, tag, commit (rövid + teljes), dátum, szerző (`Név <email>`), üzenet.
  - **Runtime**: kompozitor (X11/Wayland) + monitor felbontás (meglévő `get_monitors()`), `eww --version`, Python verzió, OS név (`/etc/os-release`).
  - **Configuration**: appearance, ikonkészlet + `bg_radius` + `font_face` (eww.theme.json), city, units, lang, hour_format, scale (config.py `--key`).
  - Teteje a meglévő húzható sáv, alul Open repository / Close gombok.

## 2. Sys-info rések egységesítése
**Fájl:** `eww.scss`

Mért címkeszélességek (Noto Sans 15px bold): HDD 33.4, CPU 30.3, RAM 34.4, SWAP 41.9 → cél egyenletes **~14px** rés (címke vége → érték kezdete):
- `.hdd-value`: 64 → **63**
- `.cpu-value`: 64 → **60**
- `.ram-value`: 259 (marad)
- `.swap-value`: 259 → **267**

Eredmény: HDD 13.6, CPU 13.7, RAM 14, SWAP 14 px.

## 3. Weather widget Move/Resize négyszög = widget mérete
**Fájlok:** `scripts/widget_rect.py`, `scripts/move.py`, `scripts/move_ctl.py`, `scripts/start.sh`, `eww.yuck`, `eww.scss`

- **widget_rect.py**: PIL mérés (30px bold, rendszer `NotoSans-Bold.ttf`, fallback a repo `fonts/NotoSans-Regular.ttf`-re). `clock_natural_size()`: `natural_w = max(465 + városnév_szélesség, ~584) + 8px`, ahol 584 a jobb szélső fix elem (feels-like label vége); `natural_h = 250`. A `clock_rect` outputba `natural_w`/`natural_h`.
- **start.sh**: `main_w`/`main_h` a widget_rect outputból (a hardcodeolt "745"/"250" helyett).
- **move.py / move_ctl.py**: clock `base_w`/`base_h` a `rect["natural_w"]`/`["natural_h"]`-ből (már úgyis hívják a widget_rect-et).
- **eww.yuck**: `widget_clock_weather` kap `main_w` paramétert; a `section-sizer` `:width {main_w}`, a bg mérete is `main_w` (inline). `main_window`/`main_window_x11` átadja `main_w`-t.
- **eww.scss**: `.widget-overlay` fix `min-width: 745px` és `.widget-bg` fix `min-width: 630px` eltávolítva (méretezés a yuck-ból).
- "Budapest" esetén a szélesség ~614px lesz; `middle_middle` igazításnál a widget újra középre kerül (jóváhagyva).

**Ellenőrzés:** `python3 scripts/widget_rect.py --widget clock --monitor 0` → szélesség ~614; widget újraindítás után vizuálisan ellenőrizni a rést, a négyszöget és az About ablakot. (Nincs automatizált teszt a repóban.) Megjegyzés: ha az időjárás-leírás hosszabb lenne a városnévnél, az új jobb szélénél elvághatja – a jelenlegi városnál nem fordul elő.

## 4. About cím középre + Sys-info táblázat
**Fájlok:** `scripts/about_win.py`, `eww.yuck`, `eww.scss`, `README.md`

- **about_win.py** – a húzható címsáv labelje (`Gtk.Align.START` → `Gtk.Align.CENTER`), így a cím középre kerül. A label `pack_start(label, True, True, 0)`-tal expandál.
- **eww.yuck / eww.scss** – 8 abszolút pozicionált label, 4 oszlop + 2 sor:
  - Oszlopok: [HDD/CPU] (x=16) [értékek] (x=65) [RAM/SWAP] (x=219) [értékek] (x=276). Oszloprések és az elválasztóvonal-utolsó-oszlop rés ~15px (számított: G = (414 - 16 - oszlopszélességek)/4, a pillanatnyi értékszélességekből: HDD 139px, SWAP 123px).
  - Sorok: y=178 / 192 (14px sorpitch = az időjárás leírás–MIN/MAX/Feels sorok közti távolság).
- **README.md (633. sor)** – osztálydokumentáció frissítése.

**Megjegyzés:** a `:space-evenly` box-layout (default true) az oszlopokat a teljes szélességre egyenletesen osztotta volna el, ezért abszolút pozicionálás maradt. Az oszlop-koordináták a pillanatnyi értékszélességeken alapulnak (a HDD/RAM/SWAP összegek fixek a rendszeren).

**Ellenőrzés:** `python3 -m py_compile scripts/about_win.py`, `eww reload` + vizuális ellenőrzés (a `watch.py` amúgy is reloadol).