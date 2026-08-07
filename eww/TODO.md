# eww TODO — állapotjegyzék (későbbi folytatáshoz)

Dátum: 2026-08-07
Ág: `feature/wayland`
Repo: `/home/takattila/.conky/Clock-With-Weather-Conky`

## Cél

1. **YAML-migráció**: az eww widget legyen önálló, YAML-alapú konfiggal —
   `config.json` → `config.yaml`, a Lua témák → `themes/appearance/<name>/appearance.yaml`
   + `themes/weather/<name>/weather.yaml`. A gyökér `themes/*.lua` érintetlen
   marad (Conky verzió tovább működik).
2. **Req 1 — auto-reload**: a `config.yaml` / téma YAML fájlok mentése azonnal
   érvényesüljön (watcher + `eww reload`), **erőforrás-kímélően** (ne pörögjön
   másodpercenként).
3. **Req 2 — panel a taskbarhoz képest**: a panel magassága a taskbar magasságának
   levonásával, dinamikusan a taskbar helyzete szerint (felső/alsó/oldalsó).
4. **README frissítés**: összes dependencia infó + változáslisták.

## Elkészült (implementálva)

- `eww/scripts/watch.py` (új): ctypes `inotify`, eseményvezérelt (blokkoló
  `select`, üresjáratban ~0 CPU), nincs külső csomag. Figyeli a `config.yaml`-t és
  az összes `themes/**/*.yaml`-t; változáskor ~0.5s settle után `theme.py` →
  siker esetén `eww --config <dir> reload`. Új téma-mappánál bővíti a watch-okat.
  A generált fájlok (`eww.theme.json/.scss`, `charts/`, `watch.log/.pid`) írásait
  név-szűrővel kiszűri → nincs reload-lop. Log: `watch.log`, PID: `watch.pid`.
- `start.sh`: `start_watcher()` — `nohup python3 scripts/watch.py` + PID fájl.
- `stop.sh`: `stop_watcher()` — PID-alapú kill.
- `eww/.gitignore`: `watch.log`, `watch.pid`.
- `eww.yuck`: `config` és `theme` defpoll 1h → **5s** (csak biztosíték).
- `workarea.py` (**újraírva, Req 2**): JSON kimenet — `screen`, `workarea`,
  `taskbar` pozíció (`top|bottom|left|right|none`), `panel` geometria
  (`anchor`/`x`/`y`/`width`/`height`) és `panel_gap`; `real_workarea` flag.
  A panel mindkét végén **szimmetrikus gap**-pel illeszkedik a taskbarhoz és a
  szemközti képernyőszélhez. A gap a `config.yaml` → `panel.gap` (default 16).
  Stderr log: `screen=… workarea=… taskbar=… gap=… panel=…`.
- `config.yaml`: új `panel.gap: 16` kulcs + dokumentáció.
- `start.sh` (`align_panel_to_taskbar`): a workarea.py JSON-ját fogyasztja,
  a **teljes** `panel_window` geometry blokkot írja át
  (`:anchor/:x/:y/:width/:height`); X nélkül (nincs valós workarea) **nem**
  írja felül a committed geometriát (fallback). `PANEL_HEIGHT` exportálva a
  `panel.py` chart-méretezéshez.
- `panel.py`: `get_screen_height()` fallback-sorrend → `_NET_WORKAREA` magasság
  (új `get_net_workarea_height()`), csak utána xrandr, majd 1080. Eredmény:
  `chart_h` a 1050-es workarea-ből → 192 (1080-ból 200 lett volna).
- `README.md` (gyökér): eww szekció újraírva — deps: eww 0.4.0+, Python3 +
  `requests`/`psutil`/**PyYAML**, `xprop`/`xrandr`, inotify csomag nélkül; **jq
  törölve**; `config.yaml` dokumentáció; auto-reload; panel-alignment (szimmetrikus
  gap, taskbar-pozíciók táblázata); changes.
- `eww/README.md`: defpoll tábla → 5s + `watch.py` sor + `panel.gap` a config
  táblában + "Panel alignment (Req 2)" szekció + megjegyzés.

## Verifikáció (elvégzett)

- `py_compile` minden érintett py-n; `bash -n` start/stop; 32 YAML parse OK.
- Sandbox (`/tmp/opencode/eww-test-watch`, stub `eww`): `config.yaml`,
  `appearance.yaml`, `weather.yaml` szerkesztés, új téma-mappa, config-váltás →
  mind 1-1 reload, **nincs loop**.
- Közben javított bug: az inotify nevet NUL-lal 4-bájtosra igazítja, a rövid
  nevek (`config.yaml`, `weather.yaml`) padding-NUL-okat kaptak →
  `rstrip(b"\x00")` (watch.py `_handle_events`).
- `workarea.py` élesen: `screen=1920x1080 workarea=0,30 1920x1050 taskbar=top gap=16 panel=top right 250x1018+0+16` (JSON + stderr) és `real_workarea=true`.
- **KDE layer-shell felfedezés**: a `:x`/`:y` offsetek a **workarea tetejéhez** relatívak (a taskbar exclusive zone-ja tolja az ablakot): `:y "0px"` → képernyőn y=30; `:y "16px"` → y=46. Ezért a top taskbarnál `y = gap` (16), nem `taskbar_h + gap` (46). Kontrollált kísérlettel igazolva (y=0/h=100 és y=16/h=1018 teszt).
- **Átlátszatlan verifikáció** (`$bg-alpha: 1.0` + reload + spectacle + PIL, majd visszaállítás 0.0-ra): `:y "16px" :height "1018px"` → ablak fekete téglalapja **y=46..1063** → fent gap=16 a taskbarhoz (30), lent gap=16 a képernyőszélig (1079). **Szimmetria ✓**.
- Átlátszó (éles) képen a tartalom kitölti az ablakot (chartok 184px-esek a `PANEL_HEIGHT`-ből); a kismértékű vizuális aszimmetria (31 vs 23) a belső marginokból adódik, nem a geometriából.
- `start.sh` élesen lefutott (env-vel): a logban `anchor=top right x=0px y=16px width=250px height=1018px (gap=16px)`, daemon+mindkét ablak+watcher (PID 405405) fent, a `defpoll` indítási hibák átmenetiek (az első pollig).

## NYITOTT — folytatandó

### 1. ~~Panel láthatóság~~ → **MEGOLDVA** (2026-08-07)
- Gyökér ok: **beragadt, régi daemon** (GTK főciklus leállt —
  `main application thread finished`; a windows-ok eww-bookkeeping-ben nyitva
  voltak, de nem rendereltek). `eww kill` + SIGTERM sem hatott, `kill -9`
  kellett. Újraindítás után mindkét ablak renderel.
- Az `:x "0%" :anchor "top right"` gyanú **nem bizonyult hibának**: Waylanden a
  gtk layer-shell anchor/margin a mérvadó (X11-es `apply_window_position` nem
  fut), a panel a jobb szélen jelenik meg (x=1670..1919).
- Tünet képekkel: régi daemon → panel hiányzik; új daemon → panel látszik
  (`/tmp/opencode/screen3.png`).

### 2. ~~Éles auto-reload teszt~~ → **KÉSZ** (2026-08-07)
- `config.yaml` `appearance: light → dark → light` futó daemon + watcher mellett:
  a `watch.log`-ban `change:` → theme regenerálás → **`eww reloaded`**; a
  widget ténylegesen frissült (screenshot diff: 17749 pixellel más a
  főablak-tartalom, dark színek). Visszaállítva light-ra, reload újra lefutott.
- **Watcher-élettartam bug javítva**: a `start.sh` `nohup … &`-tal indított
  watcher a hívó bash process-group takarítása után meghalt (a daemon azért
  élt, mert detachál). Megoldás: `setsid python3 …` → saját session,
  túléli (PID 552602).

### 3. `eww reload` viselkedés ellenőrzése
- Újra-futtatja-e azonnal a defpoll-okat? (Az 5s interval biztosítékként van.)

### 4. Commit / push döntés
- A teljes YAML-migráció + ez a munka **commitolatlan** (git status):
  `README.md`, `eww/README.md`, `eww/.gitignore`, `eww/eww.yuck`,
  `eww/scripts/{panel,setup_test_env,start,stop,theme,workarea}.py`,
  törölt `eww/config.json`, új: `eww/config.yaml`, `eww/fonts/`,
  `eww/scripts/{config,watch}.py`, `eww/themes/`.
- `eww/scripts/setup_test_env.sh`: kis indent-fix (2 sor) — a wallpaper-feladattal
  együtt maradt, bevonható a commitba.
- Korábbi commit: `ab439a3` (wallpaper), `4f7692f` (panel taskbar-igazítás).
- Utasítás: commit csak kérésre.

### 5. Eww config.yaml téma-számok
- Az eww verzió `config.yaml` `appearance`/`weather` név-alapú; a Conky verzió
  sorszám-alapú. Ha kell, dokumentáció finomítás.

## Fájlok (fontosabb)

| Fájl | Szerep |
|---|---|
| `eww/scripts/watch.py` | új inotify watcher |
| `eww/scripts/config.py` | YAML híd (config.yaml + weather téma) |
| `eww/scripts/theme.py` | YAML → `eww.theme.json/.scss` |
| `eww/config.yaml` | központi konfig (+ `panel.gap`) |
| `eww/themes/appearance/*/appearance.yaml` (20) | appearance témák |
| `eww/themes/weather/*/weather.yaml` (11) | weather témák |
| `eww/eww.yuck` | defpoll-ok + `panel_window` (sor ~195-203) |
| `eww/scripts/panel.py` | `get_screen_height()` (~47), `get_net_workarea_height()` (~47), chart geometria (~238) |
| `eww/scripts/workarea.py` | `_NET_WORKAREA` → JSON (taskbar-pozíció + szimmetrikus panel-geometria `panel.gap`-pel) |
