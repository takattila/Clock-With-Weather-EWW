# Screenshots (headless Chrome capture)

Vendored headless-Chrome screenshot generator, originally from the
`takattila/monitor` project. It drives Chrome/Chromium via Puppeteer, logs in to
a locally running web service and captures PNGs for every skin (dark + light
mode) plus a few special shots.

> **Important:** the eww widget is a **native GTK window**, not a web page, so
> this tool cannot capture it directly — for widget screenshots use `spectacle`
> (see `eww/README.md`, section 7 "Verified facts and measurement method"). This
> harness is kept here as a reusable web-dashboard capture tool; to point it at a
> different web service, edit the constants at the top of `capture.js`
> (`BASE`, `VIEWPORT`, `SKINS`, the `/monitor/...` paths and the login form
> selectors).

## What it captures

Against the locally running web service (default `http://127.0.0.1:8383`):

| Option | Files |
|---|---|
| `--themes` (default) | `desktop-<skin>-<mode>.png` for every skin, dark + light |
| `--defaults` | `desktop-dark.png`, `desktop-light.png`, `desktop-full-light.png` |
| `--network` | `network.png` — the expanded Network Traffic section with generated loopback traffic |
| `--all` | all of the above |

## Requirements

- The web service running locally, with valid login credentials (the user/pass
  stored in its auth database).
- A Chrome/Chromium binary (default `/opt/google/chrome/chrome`).
- Node.js with npm.

## Install

```sh
cd eww/tools/screenshots
npm install
```

## Usage

```sh
node capture.js [options]
```

| Option | Description |
|---|---|
| `--themes` | Capture `desktop-<skin>-<mode>.png` for every skin (default). |
| `--defaults` | Capture `desktop-dark.png`, `desktop-light.png` and `desktop-full-light.png`. |
| `--network` | Capture `network.png`: the expanded Network Traffic section with generated loopback traffic. |
| `--skin <n>` | Limit the theme capture to a single skin (with `--themes`). |
| `--all` | Shortcut for `--themes --defaults --network`. |
| `-h` / `--help` | Show help. |

Examples:

```sh
# All skins, dark + light
node capture.js --themes

# One skin, for quick iteration
node capture.js --themes --skin mint

# Everything
node capture.js --all
```

With non-default credentials:

```sh
MONITOR_USER=myuser MONITOR_PASS=mypass node capture.js --all
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `MONITOR_BASE` | `http://127.0.0.1:8383` | Web service base URL. |
| `MONITOR_OUT` | `./out` (this directory) | Output directory for the PNGs. |
| `MONITOR_USER` | `admin` | Login user name. |
| `MONITOR_PASS` | `admin` | Login password. |
| `MONITOR_CHROME` | `/opt/google/chrome/chrome` | Chrome/Chromium executable. |

## Notes

- The network capture generates loopback traffic with `curl` so the charts show
  real movement; `curl` must be available for that shot to look meaningful.
- Each shot persists the chosen skin/mode through the `/monitor/settings`
  endpoint (like the UI does), so the dashboard's `loadSettings()` applies it
  instead of falling back to the default dark skin.
- `node_modules/` and the output directory `out/` are git-ignored.
