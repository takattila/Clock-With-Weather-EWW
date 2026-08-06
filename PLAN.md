# PLAN.md — Folytatási terv & Plasma-widget-elrejtés tudástár

> A teljes debug-progress és az ellenőrzött tények a `PROMPT.md`-ben vannak.
> Ez a fájl: (1) a további lépések rövid terve, (2) a Plasma 6 widget-elrejtési módszer dokumentációja.

## Következő lépések (részletesen lásd PROMPT.md)

1. **Time-row label-klip bug izolálása** — tesztmátrix az `/tmp/opencode/ewwtest2`-ben:
   - hour + `:05` (class `minutes`) csak; class `m1` csak → class-név hatás kizárása
   - `05` (kettőspont nélkül) → számít-e a vezető `:` karakter
   - `:05` + seconds (`margin-top:108`) → t13 töredékek reprodukálása, majd seconds `margin-top` eltávolítása
   - Szélesség faktor: teljes tartalom < vs >= ablakszélesség
   - Minden variánsnál képernyőkép + ASCII dump.
2. **Hipotézis ellenőrzés**: ha egy későbbi testvér `margin-top`-ja elrontja egy korábbi label allokációját → gyermekek sorrendjének / a margin elhelyezésének tesztelése (wrap box).
3. **Fix**: `time-row` átalakítása `eww.yuck`-ban (pl. seconds saját boxba; `min-width`/`min-height`; `:space-evenly` változtatás).
4. **Újraellenőrzés**: hour+minutes+seconds teljesen rendereljen y55-től, metrikák egyezzenek a referencia képpel.
5. **Stats-row** (nem renderel), **temp-row** (óriás magenta blokk) izolálása.
6. **Végső kalibráció** + diagnosztikai keretek eltávolítása (`/tmp/opencode/eww.scss.bak` visszaállítása), vizuális összehasonlítás.

---

## Plasma 6 — widgetek elrejtése/visszaállítása (megbízható módszer)

**Fontos:** a `plasmashell --export-layout` kapcsoló **Plasma 6-ban már NEM létezik**
(„Ismeretlen kapcsoló” hiba). A widgetek nincsenek külön „láthatósági” állapottal —
a `plasma-org.kde.plasma.desktop-appletsrc` fájlban léteznek vagy nem léteznek.

### Widgetek elrejtése (üres indítás)
```bash
kquitapp6 plasmashell
mv ~/.config/plasma-org.kde.plasma.desktop-appletsrc ~/.config/plasma-org.kde.plasma.desktop-appletsrc.backup
plasmashell &
```
A Plasma új, üres appletsrc-t hoz létre → minden widget eltűnik (a `.backup` megmarad).

### Visszaállítás
```bash
kquitapp6 plasmashell
mv ~/.config/plasma-org.kde.plasma.desktop-appletsrc ~/.config/plasma-org.kde.plasma.desktop-appletsrc.empty   # aktuális üres mentése
mv ~/.config/plasma-org.kde.plasma.desktop-appletsrc.backup ~/.config/plasma-org.kde.plasma.desktop-appletsrc
plasmashell &
```

### Alternatíva
- Külön KDE Session (System Settings → Users → Create Session): tiszta, fájlmozgatás nélkül.

### Megjegyzések / ellenőrzött állapot (2026-08-05)
- Plasma verzió: **6.7.3**; `kquitapp6` használandó (kquitapp5 nincs telepítve).
- A `plasma-plasmashell.service` **inactive** — a plasmashell manuálisan fut, ezért
  `nohup plasmashell & disown` indítja újra.
- Visszaállítás megvalósítva: a `.backup` (10469 B, 68 applet) visszakerült az
  appletsrc-be; az üres állapot mentve: `plasma-org.kde.plasma.desktop-appletsrc.empty`.
