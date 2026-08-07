# Screenshots

Headless Chrome screenshot generator for the monitor dashboard. It captures the
dashboard for every available skin (in dark and light mode) plus a few special
shots (default theme and the Network Traffic section) from the locally running
monitor web service.

The generated PNGs are meant to be copied into the repository's `assets/`
folder, which the README references.

## Requirements

- The monitor stack must be running locally (web on port `8383`, api on `7070`).
- Valid login credentials for the web interface (`MONITOR_USER`/`MONITOR_PASS`).
- A Chrome/Chromium binary. Default: `/opt/google/chrome/chrome`.
- Node.js with npm.

## Install

```sh
cd tools/screenshots
npm install
```

## Usage

```sh
node capture.js [options]
```

### Options

| Option        | Description                                                    |
|---------------|----------------------------------------------------------------|
| `--themes`    | Capture `desktop-<skin>-<mode>.png` for every skin (default).  |
| `--defaults`  | Capture `desktop-dark.png`, `desktop-light.png` and `desktop-full-light.png`. |
| `--network`   | Capture `network.png`: the expanded Network Traffic section with generated loopback traffic. |
| `--skin <n>`  | Limit the theme capture to a single skin (with `--themes`).    |
| `--all`       | Shortcut for `--themes --defaults --network`.                  |
| `-h` / `--help` | Show help.                                                   |

### Examples

```sh
# All theme screenshots (dark + light for all 33 skins)
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

Limit to a single skin in both modes, e.g. while styling `github_red`:

```sh
MONITOR_USER=myuser MONITOR_PASS=mypass node capture.js --themes --skin github_red
```

Capture only the light variants of one skin:

```sh
MONITOR_USER=myuser MONITOR_PASS=mypass node capture.js --themes --skin mint
# then copy just the *_light.png files you need:
cp out/desktop-mint-light.png ../../assets/
```

Full workflow from a fresh checkout:

```sh
cd tools/screenshots
npm install
MONITOR_USER=myuser MONITOR_PASS=mypass node capture.js --all
cp out/*.png ../../assets/
```

## Environment variables

| Variable         | Default                   | Description                         |
|------------------|---------------------------|-------------------------------------|
| `MONITOR_BASE`   | `http://127.0.0.1:8383`   | Web service base URL.               |
| `MONITOR_OUT`    | `./out` (this directory)  | Output directory for the PNGs.      |
| `MONITOR_USER`   | `admin`                   | Login user name.                    |
| `MONITOR_PASS`   | `admin`                   | Login password.                     |
| `MONITOR_CHROME` | `/opt/google/chrome/chrome` | Chrome/Chromium executable.       |

## Deploying to assets/

```sh
node capture.js --all
cp out/*.png ../../assets/
```

The assets are referenced from `../../README.md`.

## Notes

- The network capture generates loopback traffic with `curl` so the charts show
  real movement; `curl` must be available for that shot to look meaningful.
- Each shot persists the chosen skin/mode through the `/monitor/settings`
  endpoint (like the UI does), so the dashboard's `loadSettings()` applies light
  mode instead of falling back to the default dark skin.
- The script logs in with the credentials set in `configs/auth.db` of your
  instance. The database is not shipped with the repository; it is created on
  first run (by the installer or `cmd/credentials`) with your own user name and
  password. Point `MONITOR_USER`/`MONITOR_PASS` at those credentials.
