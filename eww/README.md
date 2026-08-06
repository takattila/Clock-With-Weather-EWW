# Clock-With-Weather-Conky — EWW (Wayland) verzió

Az eredeti Lua/Cairo alapú Conky óra + időjárás widget **EWW** (`ElKowar's Wacky
Widgets`) átírása Wayland alá. Két ablak tükrözi az eredeti Conky elrendezést:

| Ablak | Méret | Tartalom |
|---|---|---|
| `main_window` | 745x250, középre igazítva | óra + dátum + rendszerinfó + időjárás |
| `panel_window` | 250 széles, teljes magasságú, jobb felső sarok | CPU / MEMORY / NET DOWN / NET UP grafikonok |

A koordináták, betűméretek és színek a `cwDraw.lua` / `panelDraw.lua` értékeit
követik pixel-pontosan.

---

## 1. Függőségek

### Kötelező

| Függőség | Minimum / tesztelt verzió | Szerepe |
|---|---|---|
| `eww` | 0.5.0+ (tesztelt: `0.5.0 d87c2fd`) | az ablakok és a widget-fa renderelése |
| `python3` | 3.14+ (tesztelt: 3.14.6) | az adat-előállító scriptek |
| `python3-requests` | 2.x (tesztelt: 2.34.2) | OpenWeatherMap API hívás (`weather.py`) |
| `python3-psutil` | 5.x–7.x (tesztelt: 7.2.2) | CPU/RAM/SWAP/HDD/hálózat (`system.py`, `panel.py`) |
| `jq` | 1.6+ (tesztelt: 1.8.2) | `config.json` értékek kiolvasása a `defpoll` parancsokban |
| `xprop` | bármely | `_NET_WORKAREA` kiolvasása (panel magasság) |
| `xrandr` | bármely | felbontás / workarea fallback |
| `Noto Sans` font | tetszőleges | az egyetlen használt betűcsalád |

### Teszteléshez / fejlesztéshez

| Függőség | Szerepe |
|---|---|
| `spectacle` | képernyőkép készítése ellenőrzéshez |
| `PIL` (pillow) | képmérés / -összehasonlítás (fejlesztési segédeszköz) |

### A Lua (Conky) verzió külön követelményei

A `../` gyökérben található eredeti Lua verzió **külön** Conky-t igényel
(`conky`, `lua-cairo`, `lua-json`, `curl`, `OPENWEATHER_API_KEY` környezeti
változó). Az `eww/` könyvtár **nem** függ tőle — a Lua fájlok csak a
koordináták és a `themes/` könyvtár forrásai.

---

## 2. Verzió-változás kockázatai („nem indul a widget”)

A widget érzékeny a következő verzió-változásokra. A legtöbb hibajel megjelenése
néma (üres ablak, hiányzó szöveg), ezért indulás után **mindenképp ellenőrizd a
terminált** (`eww` naplózza a `defpoll` hibákat).

| Mi változik | Milyen tünet | Ok / megoldás |
|---|---|---|
| **`eww` major verzió** (0.5 → 0.6/1.0) | a widget nem indul, vagy CSS nem tölt be | A `yuck` szintaxis (`:geometry`, `defpoll`, `:anchor`) és a SCSS `@import` API változhat. Ellenőrizd a [eww release-eket](https://github.com/elkowar/eww/releases). |
| **`eww` minor/patch** | ritkán gond | Ha a `daemon` `Error while forwarding command` hibát ad, a config betöltése után előfordul, de a widget renderel — ne ijedj meg, mérd a képernyőt. |
| **`python` major** (3.x → 4.x) | `system.py` / `panel.py` hibák | A `psutil`/`requests` binary-wheel elérhetősége függ tőle. |
| **`psutil` major** | `panel.py` nem ad JSON-t | API eltérések (pl. `cpu_times` sorrend, `net_io_counters`). Tünet: a panel-ablak üres. |
| **`jq` hiányzik / régi** | az óra és a `defpoll`-ok üresek | A `config.json` kiolvasás `$(jq -r ...)` minden `defpoll`-ban — ha nincs `jq`, az egész widget üres. |
| **`xprop` hiányzik** | a panel magassága hibás | A `workarea.py` fallback-láncba esik (`xrandr` → 1080). |
| **`Noto Sans` nincs telepítve** | minden eltolódik | A `fc-match "Noto Sans"` → `NotoSans-Regular.ttf` kell legyen. Másik fontra cserélni a `eww.theme.scss` `$font-face`-ben, és újrakalibrálni a margókat. |
| **KDE/kwin verzió** | ablak-eltolódás | Az ablak középre igazítása a workarea-hez képest történik (lásd 6. fejezet, „Ablak-geometria”). |

**Legfontosabb szabály:** a `defpoll`-ok minden értéke külső parancs kimenete
(`date`, `jq`, `./scripts/*.py`). Ha bármelyik parancs hibázik vagy hiányzik,
**üres/nyers `null`** érték kerül a widget-be, ami gyakran „láthatatlan” hiba.

---

## 3. A widget indítása

```bash
cd ~/.conky/Clock-With-Weather-Conky/eww
./start.sh
```

A `start.sh` a következőket csinálja:

1. **`theme.py`** — legenerálja az `eww.theme.scss` és `eww.theme.json` fájlt a
   `config.json` `appearance` mezője + `../themes/appearance/<név>/appearance.lua`
   alapján (színek, font, ikonkészlet, háttér-átlátszóság).
2. **`workarea.py`** — kiolvassa a `_NET_WORKAREA`-t, és a `panel_window`
   magasságát a taskbar-mentes területhez igazítja (a `eww.yuck`-ban a
   `panel_window` geometry-t felülírja futás közben).
3. Elöli a régi daemont: `eww --config . kill`
4. `eww --config . daemon` + `eww --config . open main_window` + `eww --config . open panel_window`

### Leállítás

```bash
cd ~/.conky/Clock-With-Weather-Conky/eww
./stop.sh
```

A `stop.sh` az eww daemont állítja le ehhez a config-könyvtárhoz
(`eww --config . kill`), ami mindkét ablakot bezárja. Manuálisan ennyi:

```bash
eww --config ~/.conky/Clock-With-Weather-Conky/eww kill
```

### Konfiguráció (`eww/config.json`)

```json
{
    "api_key": "YOUR_OPENWEATHER_API_KEY",
    "city": "Tatabánya",
    "lang": "hu",
    "units": "metric",
    "appearance": "light",
    "hour_format": "24"
}
```

| Mező | Értékek | Hatás |
|---|---|---|
| `api_key` | OpenWeatherMap kulcs | kötelező, kulcs nélkül nincs időjárás |
| `city` | tetszőleges város | a városnév a widgeten + az API lekérdezés |
| `lang` | `hu`, `en`, ... | az időjárás-leírás nyelve |
| `units` | `metric` / `imperial` | °C / °F, a `weather.py` a `°C`/`°F` utótagot vezérli |
| `appearance` | `light`, `dark`, `light-bg`, ... | milyen `../themes/appearance/<név>/appearance.lua` színeit használja |
| `hour_format` | `24` / `12` | a `defpoll hour` `%H` / `%I` formátuma |

---

## 4. Tesztkörnyezet kialakítása (KDE Plasma)

A widget méréséhez tiszta asztal kell: nincs rajta másik widget, nincsenek
asztali ikonok, és egyszínű a háttér. Ehhez a **`eww/setup_test_env.sh`**
script:

```bash
cd ~/.conky/Clock-With-Weather-Conky/eww

./setup_test_env.sh hide                # tesztmód: widgetek + ikonok rejtve, egyszínű háttér
./setup_test_env.sh hide "#112233"      # ... egyedi háttérszínnel
./setup_test_env.sh status              # aktuális állapot
./setup_test_env.sh restore             # normál asztal visszaállítása
```

### Mit csinál a script?

1. **Biztonsági mentés** — az aktuális
   `~/.config/plasma-org.kde.plasma.desktop-appletsrc`-et
   `...desktop-appletsrc.backup`-ba menti (csak egyszer, a normál asztal
   megőrzésére).
2. **Egyszínű háttér** — `PIL`-lel legenerál egy egyszínű PNG-t
   (`~/.config/eww-test-background.png`, alapértelmezett szín `#2d3034`,
   `EWW_TEST_BG_COLOR` környezeti változóval felülírható), és azt állítja be a
   Plasma háttérképeként.
3. **Widgetek elrejtése** — a desktop containment
   (`org.kde.desktopcontainment`) helyett **folder view**
   (`org.kde.plasma.folder`) lesz, így az asztali widgetek eltűnnek.
4. **Ikonok elrejtése** — a folder view `positions`/`changedPositions`/`arrangement`
   és a `screenMapping` bejegyzései törlődnek, ezért az asztali ikonok sem
   látszanak.
5. **`plasmashell` újraindítása** — a változások életbe lépnek.

### Megjegyzések (ellenőrzött tények, 2026-08-05)

- Plasma verzió: **6.7.3**; a `kquitapp6` használandó (`kquitapp5` nincs).
- A `plasma-org.kde.plasma.desktop-appletsrc` fájlban a widgetek **nem**
  rendelkeznek külön láthatósági állapottal — léteznek vagy nem. Ezért a
  fájl-mozgatás a megbízható módszer.
- A `plasmashell` **manuálisan** fut (a `plasma-plasmashell.service` inactive),
  ezért a script `nohup plasmashell & disown`-nal indítja újra.
- Manuális tesztelésnél a KDE Session-t is használhatod (System Settings →
  Users → Create Session): tiszta környezet fájlmozgatás nélkül.

---

## 5. Struktúra — mi mit csinál

### `eww/eww.yuck` — a widget-fa és az adatforrások

A fájl három nagy részből áll:

1. **`defpoll` blokkok** — az adatok. Minden `defpoll` időközönként futtat egy
   shell parancsot, és annak kimenetét a widget-be tölti:

   | defpoll | Időköz | Parancs |
   |---|---|---|
   | `hour` | 1s | `date +%H` (vagy `%I` 12-órás formátum) |
   | `minutes` | 1s | `date +:%M` |
   | `seconds` | 1s | `date +%S` |
   | `date_year` | 1m | `date +%Y.` |
   | `date_day` | 1m | `date "+| %B %d. | %A"` (en_US locale) |
   | `system_info` | 5s | `./scripts/system.py` (JSON) |
   | `weather_info` | 10m | `./scripts/weather.py <key> <city> <lang> <units>` (JSON) |
   | `panel` | 1s | `./scripts/panel.py` (JSON + SVG grafikonok) |
   | `config` | 1h | `cat config.json` |
   | `theme` | 1h | `cat eww.theme.json` |

2. **`defwidget widget_clock_weather`** — a fő ablak. Egy `overlay` + fix
   `745x250` sizer, amiben minden elem `margin-left`/`margin-top`-tal van
   **abszolút pozícionálva** (lásd 6. fejezet). Az elemek a
   `cwDraw.lua` koordinátáit tükrözik: év/dátum, óra/perc/másodperc, HDD/RAM,
   CPU/SWAP, elválasztó vonal, időjárás-ikon, város, hőmérséklet, leírás,
   MIN/MAX/Feels-like.

3. **`defwidget widget_panel`** — a rendszerfigyelő panel. Négy
   `panel-section`: `CPU`, `MEMORY`, `NET DOWN`, `NET UP`. Mindegyikben egy
   cím (`panel-title`), egy állapotszöveg (`panel-status`) és egy
   SVG-grafikon (`panel-chart`).

4. **`defwindow` blokkok** — `main_window` (745x250, center) és
   `panel_window` (250 széles, top-right, teljes magasság).

### `eww/scripts/` — az adat-előállító Python scriptek

| Script | Kimenet | Felel |
|---|---|---|
| `system.py` | `{hdd, ram, cpu, swap}` | `psutil`/`shutil` alapú rendszerinfó, dinamikus `format_bytes` (B/KB/MB/GB/TB) |
| `weather.py` | OpenWeatherMap JSON + `temp_fmt`, `unit_symbol`, `icon_path` | API hívás, kerekítés, °C/°F |
| `panel.py` | `{cpu_file, mem_file, down_file, up_file, cpu_txt, ...}` | grafikon-SVG-k generálása (`charts/*.svg`, 100 pontos görgetett hisztória), aktív NIC felderítés |
| `theme.py` | `eww.theme.scss` + `eww.theme.json` | a `config.json` `appearance` + `../themes/appearance/<név>/appearance.lua` → EWW téma |
| `workarea.py` | `"Y HEIGHT"` | `_NET_WORKAREA` kiolvasása a panel magasságához |

### `eww/charts/` — generált SVG-k

A `panel.py` minden poll-nál új, időbélyegzett SVG-t ír a `charts/`-ba
(`cpu_00042.svg`, ...), és a `defpoll panel` JSON-ban a fájlnevet adja vissza.
A régieket automatikusan törli (3-at tart meg típusonként). **Ne commitold** —
gitignore-olt (`.gitignore`).

### `eww/images/`, `../images/`

- `../images/theme/<theme>/elements/` — vonal, lokáció-ikon, hőmérő, nyilak.
- `../images/theme/<theme>/weather/<icon-set>/` — időjárás-ikonok
  (`01d.png`, `02d`, ...). A `theme.py` az `icon_set`-et a `config.json`
  `appearance`-éből veszi.

---

## 6. Az elemek megjelenítésének módosítása (EWW CSS)

Az összes formázás az **`eww/eww.scss`** fájlban van. Az `eww.yuck` csak a
**szerkezetet** és az **adatokat** adja; a méret, szín, pozíció mind CSS.

### Alapszabály: a pozícionálás módja

- Minden elem a `745x250`-es overlay-ben **abszolút pozícionált**:
  `margin-left` = X koordináta, `margin-top` = Y koordináta (a label tetejét
  helyezi el).
- A `cwDraw.lua` **baseline** koordinátákat használ (`text(x, y)` a betűk
  alapsorára igazít). Átszámítás:
  `margin-top = baseline_y − 0.73 × font_size` (kb. a cap-height).
- A képek (`image`) a `cwDraw.lua`-ban **középre** igazítottak
  (`pos - size/2`), az EWW-ben viszont a bal-felső sarokra → ezért
  `margin-left = pos_x − width/2`, `margin-top = pos_y − height/2`.

Példa: a hőmérséklet-szöveg a `cwDraw.lua`-ban
`text(460, 155, ..., 40, BOLD, light)`, az EWW CSS-ben:

```scss
.temp-label {
  font-size: 44px;
  font-weight: bold;
  color: $color-light;
  margin-left: 460px;   /* X pozíció */
  margin-top: 128px;    /* Y pozíció (baseline → top) */
}
```

### Fontosabb CSS osztályok és mit befolyásolnak

| Osztály | Mit jelenít meg | Fő szabályok |
|---|---|---|
| `.year-label`, `.date-label` | év, dátum sor | `font-size: 20px`, `margin-left/margin-top` |
| `.hour-label`, `.minutes-label` | óra / perc | `font-size: 145px`, `margin-left: 10/170`, `margin-top: 18` |
| `.seconds-label` | másodperc | `font-size: 20px`, `margin-left: 370`, `margin-top: 154` |
| `.hdd-label`...`.swap-value` | rendszerinfó 2 sor | `.sys-label` (világos, bold 15px) + `.sys-value` (sötét 15px) |
| `.divider` | elválasztó vonal | `margin-left: 414`, `margin-top: 14` |
| `.weather-icon` | időjárás-ikon | 64x64 a `:image-width/height`-tel (a yuck-ban) |
| `.city-icon`, `.city-label` | város ikon + név | ikon 20x20; label `font-size: 30px`, bold |
| `.temp-icon`, `.temp-label` | hőmérő + hőmérséklet | ikon 32x32; label `font-size: 44px`, bold |
| `.details-icon`, `.details-label` | leírás | 15px |
| `.stat-min/...` | MIN/MAX/Feels | 15px |
| `.panel-title`, `.panel-status`, `.panel-chart` | panel részei | 22px bold / 14px / SVG |

### Témaváltozók (`eww.theme.scss`)

A fájlt a `theme.py` generálja; ne kézzel írd át (elvész a következő
indításkor). Inkább a `../themes/appearance/<név>/appearance.lua`-t módosítsd:

```scss
$theme: "light";
$icon-set: "dovora";
$font-face: "Noto Sans";
$color-light: #ffffff;
$color-dark: #9e9e9e;
$bg-color: #000000;
$bg-alpha: 0.0;
```

### Újraméret / újrapozícionálás munkamenete

1. Módosítsd az `eww.scss`-t.
2. `eww --config ~/.conky/Clock-With-Weather-Conky/eww reload`
3. `spectacle -b -o shot.png` és képmérés (PIL) — lásd a 7. fejezetet.

---

## 7. Ellenőrzött tények és mérési módszer

### Ablak-geometria

- Widget méret: **745x250**. A képernyőn az ablak eredete **x=587, y=392**.
- Ez a KDE workarea-középpontozás eredménye (a sima középre igazítás y415
  lenne, mert az EWW a taskbar nélküli területhez igazít). **Ne változtasd az
  anchoringot** — ez elvárt viselkedés.

### Átlátszó háttér

- A `main-container` / `panel-container` `background-color: rgba($bg-color, $bg-alpha)`
  — `bg-alpha: 0.0` esetén teljesen átlátszó, csak a szövegek/ikonok látszanak.
- A tesztkörnyezet (4. fejezet) egyszínű hátterével szemben a fekete/fehér
  szövegek ellenőrizhetők.

### Képernyőkép-mérés (fejlesztési segédlet)

```bash
export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000
eww --config ~/.conky/Clock-With-Weather-Conky/eww reload
sleep 2
spectacle -b -o /tmp/opencode/shots/check.png
```

Majd PIL-lel a színes képpontok koordinátái (a widget origója x=587, y=392):

```python
from PIL import Image
import numpy as np
a = np.array(Image.open('/tmp/opencode/shots/check.png').convert('RGB')).astype(int)
lum = a.mean(axis=2)
sub = lum[392:392+250, 587:587+745]  # widget területe
m = sub > 100
rows = np.where(m.sum(axis=1) > 0)[0]
cols = np.where(m.sum(axis=0) > 0)[0]
print('tartalom:', (rows.min()+392, rows.max()+392), (cols.min()+587, cols.max()+587))
```

---

## 8. Az eredeti Lua konfiguráció — lehetőségek

Az `eww/` verzió a Lua configot **forrásként** használja: a `theme.py` a
`../themes/` Lua fájlokból generálja az EWW témát. Ha az eredeti Conky-t is
futtatod, itt a beállítható lehetőségek.

### `cwTheme.lua` — a fő kapcsolók

```lua
settings = {
    appearance = { name = "light" },   -- a ../themes/appearance/<név>/ mappát választja
    weather    = { name = "default" }, -- a ../themes/weather/<név>/ mappát választja
    system = {
        hour_format_12 = false,        -- true = 12 órás (%I) + AM/PM kijelző
        locale = "en_US.UTF-8",        -- a dátumozáshoz használt locale
    },
}
```

### `themes/appearance/<név>/appearance.lua` — megjelenés

```lua
settings.appearance = {
    theme = "light",                       -- mappa: ../images/theme/<theme>/
    icon = {
        set = "dovora",                    -- ikonkészlet: ../images/theme/<theme>/weather/<set>/
        transparency = { light = 1.0, dark = 0.5 },
    },
    font = {
        face = "Noto Sans",                -- betűcsalád
        color = { light = "#ffffff", dark = "#9e9e9e" },
        transparency = { light = 1.0, dark = 1.0 },
    },
    background = {
        transparency = 0.0,                -- 0 = átlátszó, 1 = teljesen takaró
        color = "#000000",
    },
}
```

Elérhető appearance témák (`themes/appearance/`): `light`, `dark`,
`light-bg`, `dark-bg`, `light-blue`, `dark-blue`, `light-blue-bg`,
`dark-blue-bg`, `light-green`, ..., `light-orange`, `dark-orange`, stb.
A `-bg` utótagúak háttérrel is rendelkeznek.

### `themes/weather/<város>/weather.lua` — időjárás-beállítások

```lua
settings.weather = {
    city = "Tatabánya",
    language_code = "hu",                  -- a város/ország a lekérdezésben
    lang = "hu",                           -- a leírás nyelve (hu, en, de, ...)
    units = "metric",                      -- metric = °C, imperial = °F
    api_key = os.getenv("OPENWEATHER_API_KEY"),
    api_url = "https://api.openweathermap.org/data/2.5/weather",
}
```

Elérhető városok (`themes/weather/`): `default`, `berlin`, `budapest`,
`delhi`, `london`, `moscow`, `new-york`, `paris`, `sidney`, `tokyo`, `wien`.

### `cwDraw.lua` — a rajzolás (a pozíciók forrása)

Minden függvény `text(cr, x, y, trans, str, font, size, weight, color)` vagy
`image(cr, x, y, trans, path)` alakban rajzol, a koordinátákhoz hozzáadódik
`abs_pos_x=70`, `abs_pos_y=25`.

| Függvény | Mit rajzol | Kulcspozíciók |
|---|---|---|
| `background(cr)` | lekerekített (r=20) háttér | szín/átlátszóság az appearance-ből |
| `element_clock` | év(20,30), dátum(70,30), óra(10,155), perc(170,155), másodperc(370,155) | font 20/145/20 |
| `element_system` | HDD/RAM (y180), CPU/SWAP (y200) | font 15 |
| `element_weather` | vonal(415,110), ikon(470,45), város-ikon(440,100)+név(455,110), hőmérő(440,140)+hőfok(460,155), leírás(435,175), MIN/MAX/Feels(y195) | |

Az `eww/eww.scss` margói ezekből a koordinátákból származnak (6. fejezet
átszámítási szabálya).

### `cwApp.lua`, `panelApp.lua` — Conky ablakbeállítások

- `cwApp.lua`: `minimum_width=745`, `minimum_height=250`,
  `alignment="middle_middle"`, `own_window_transparent=true`,
  `lua_draw_hook_pre="cwMain"`.
- `panelApp.lua`: `minimum_width=250`, magasság = workarea magassága,
  `alignment="top_right"`, `START_PANEL_ENABLED=true`.

### `cwUtils.lua` — API hibakezelés

- Ha nincs `OPENWEATHER_API_KEY`, a widget hibaüzenetet rajzol a képernyőre
  (lásd `is_set_api_key`).
- `check_api_response_status` — ha az API `cod != 200`, a válaszüzenetet
  rajzolja ki (pl. rossz kulcs, ismeretlen város).

---

## 9. Ismert hibák / TODO (a port-folyamatból)

- [ ] A `stats-row` korábban nem renderelt (diagnosztikai hibakeresés
      befejezve a layout commitokkal; az `eww.yuck`-ban a stats elemek a
      `widget_clock_weather`-ben vannak, lásd `stat-min/max/feels`).
- [ ] A `time-row` label-klip hibája (t13/t14/t15 mátrix) **megoldva** az
      aktuális layout-ban; az itt leírt `eww.scss` margók a végső, ellenőrzött
      értékek.
- [ ] Végső vizuális összehasonlítás a `../images/screenshots/new-york-light.png`
      referencia képével a 7. fejezet mérési módszerével.

---

## Kapcsolódó dokumentáció

- `../README.md` — a teljes projekt leírása (Conky verzió, install, setup).
- `../TESTS.md` — a sikeres tesztek listája.
- `../themes/themes.md` — a példa-témák.
