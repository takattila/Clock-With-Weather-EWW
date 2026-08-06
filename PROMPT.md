# Clock-With-Weather-Conky — EWW Port Progress & Plan

Goal: port the Lua-based Conky clock/weather widget to EWW (Wayland) so all overlay rows
(date/time, system info, weather) land at the exact pixel positions from `cwDraw.lua`.

## Project Layout (relevant files)

- `eww/eww.yuck` — widget tree, defpoll definitions (hour/minutes/seconds, date, system_info, weather_info, panel, config, theme)
- `eww/eww.scss` — all row margins/fonts/colors (`date-row`, `time-row`, `sys-row`, `city-row`, `temp-row`, `details-row`, `stats-row`)
- `eww/eww.theme.scss` / `eww.theme.json` — theme/font config (theme is "light"; font `Noto Sans`; `bg-alpha: 0.0`)
- `images/screenshots/new-york-light.png` — ground-truth reference of the Lua widget
- Config dir: `/home/takattila/.conky/Clock-With-Weather-Conky/eww`
- Scratch dir: `/tmp/opencode/ewwtest2` (minimal EWW test configs)

## Verified Facts (do NOT re-derive)

### Window geometry
- Widget target size 745x250.
- Real on-screen window origin: `x=587, y=392`. KDE work-area centering; plain center would be y415 (because EWW centers against the work area excluding the panel).
- Verified with a magenta experimental window. Do not change window anchoring; this is expected behaviour.

### Overlay margins are correct
- Minimal test configs (`ewwtest`/`ewwtest2`) prove overlay children obey `margin-top` exactly
  (50→y50, 100→y100, 150→y150) and `margin-left` exactly (80→x80, 90→x90), for both
  top-left and center-anchored windows. Earlier "-23px offset" was a measurement error
  (wrong window origin). Row boxes land exactly where their CSS margins say.

### Main-config row measurements (with debug borders in `eww.scss`)
- `date-row` top y15/16; `time-row` y55/56; `sys-row` y190/191 — match CSS margins.
- `city-row` y115/116; `details-row` border y195/196; `temp-row` huge magenta block y0-249 (probably label fill bleeding; needs isolation).
- `stats-row` border: **NONE — box never renders** (open issue).
- Weather region right side currently renders: city cyan x500-654 y115; temp magenta x495-618 y127; details yellow x500-598 y195.

### Font metrics
- Hour digits at 145px `Noto Sans` render ~106px tall (PIL reference: `"23:05"` at 145px = y60-166, glyph height 106-107).
- PIL `:05`/`05`/`3`/`23` at 145px are all ~106px tall; at 112px they are ~82px tall.
- `fc-match "Noto Sans"` → `NotoSans-Regular.ttf`.

### THE CURRENT BUG — time-row label clipping
In a minimal config (window 485x250, top-left, sizer 485x250, time-row h-box with labels):

- t13 (hour "23" 145px white + minutes ":05" 145px gray + seconds ": 05" 20px white `margin-top:108`):
  - hour "23" renders FULL and CORRECT: y108-213, x80-240 (145px font, baseline y213).
  - minutes ":05" is CLIPPED/mangled: only fragments visible —
    - colon top dot at y132-149 (x250-268)
    - "05" bottom ~18px band at y195-213 (x250-390) — widths match a 145px "05", so the glyphs ARE 145px but cut off at the bottom.
  - seconds ": 05" renders correctly at x455, y204-214.
- t14 (hour + `:05` + `05` + `x05`, all 145px, no seconds; total width 658 > 485 window):
  - ALL labels clipped to a bottom ~18px band (y194-212). Content exceeding window → everything clips.
- t15b (hour + minutes ONLY, no seconds label): hour full; **minutes ":05" ABSENT entirely**.
  - i.e. WITHOUT the seconds label the minutes label does not render at all; WITH the seconds label it renders clipped.
  - NOTE: t15 series used class names `m1`/`sec` (vs `minutes`/`seconds` in t13) — class-name influence is NOT yet ruled out.

No systematic conclusion yet. Working hypothesis: EWW sizes/clips the label to its allocation;
something about a later sibling (seconds label w/ margin-top) or total width influences the
minutes label's allocation. Must be isolated before pixel-calibrating the time row.

### Daemon/screenshot workflow quirks
- Main daemon: `eww --config .../eww daemon` (pid ~79031).
- For scratch configs: `timeout 8 eww --config /tmp/opencode/ewwtest2 close t; sleep 0.5; timeout 8 eww --config /tmp/opencode/ewwtest2 open t` then `timeout 25 spectacle -b -o shot.png`.
- `eww daemon` in foreground + `nohup` caused shell timeouts; prefer the implicit-daemon
  `eww open` pattern above, and always wrap long-running commands in `timeout`.
- Screenshots are captured 0.8-1.5s after open.

## TODO / Open Issues

- [ ] Isolate why the second h-box label (minutes ":05") gets clipped/absent (see bug section).
      Test matrix: class name (`minutes` vs `m1`), text content (`:05` vs `05` vs `x05`),
      presence/absence of seconds label, seconds `margin-top`, total width vs window width.
- [ ] Fix stats-row not rendering (check `eww.yuck` weather section + `stats-row` widget; verify `border-top` is in the stylesheet; maybe empty defpoll variable).
- [ ] Isolate the giant magenta `temp-row` block (y0-249) on the right side.
- [ ] Once time-row rendering is fixed, compare hour/minute digit metrics against
      `new-york-light.png` (reference: hour digits white bands y51-64, y85-190, y205-214, y225-234)
      and adjust font-size / margins to match exactly.
- [ ] Remove all diagnostic borders/backgrounds from `eww.scss` (backup at `/tmp/opencode/eww.scss.bak`) and do a final visual comparison against the reference screenshot.

## Plan to Continue (next concrete steps)

1. **Isolate the label-clipping bug** with a controlled matrix in `/tmp/opencode/ewwtest2`:
   a. hour + `:05` (class `minutes`) only → is it clipped, absent, or full?
   b. hour + `:05` (class `m1`) only → same question (rules out class-name effect).
   c. hour + `05` (no colon) only → does the leading `:` matter?
   d. hour + `:05` + seconds (mt108) → reproduce t13 fragments, then remove `margin-top` from seconds → does the minutes render full?
   e. Narrow the width factor: keep total content < window width, then >= window width.
   For each variant, capture and dump ASCII (see `python3` dump snippets already used).
2. **Hypothesis check**: if a later sibling with `margin-top` changes an earlier label's allocation,
   test reordering children and moving the margin from `seconds` to a wrapping box.
3. **Fix** by restructuring `time-row` in `eww.yuck` (e.g. nest seconds in its own box, or give the
   minutes label an explicit `min-width`/`min-height`, or drop `:space-evenly false`).
4. **Re-verify** hour+minutes+seconds render full at y55+ and match reference metrics.
5. Then proceed to stats-row, temp-row isolation, and final calibration/cleanup.
