#!/usr/bin/env node
'use strict';

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const BASE = process.env.MONITOR_BASE || 'http://127.0.0.1:8383';
const OUT = process.env.MONITOR_OUT || path.join(__dirname, 'out');
const USER = process.env.MONITOR_USER || 'admin';
const PASS = process.env.MONITOR_PASS || 'admin';
const CHROME = process.env.MONITOR_CHROME || '/opt/google/chrome/chrome';

const VIEWPORT = { width: 1248, height: 990 };
const NETWORK_VIEWPORT = { width: 1379, height: 600 };
const FULL_VIEWPORT = { width: 927, height: 700 };

// Skins are the theme css files served by the web app (see /monitor/api/skins).
const SKINS = [
    'cachyos', 'candy', 'centos', 'cyber', 'debian', 'fedora', 'forest',
    'github_blue', 'github_green', 'github_purple', 'github_red', 'github_yellow',
    'ice', 'lava', 'linuxmint', 'manjaro', 'matrix', 'midnight', 'mint',
    'ocean', 'opi', 'proxmox', 'redhat', 'retro', 'royal', 'rpi', 'steel',
    'sunset', 'suse', 'synthwave', 'tokyo', 'ubuntu', 'vanilla'
];
const MODES = ['dark', 'light'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function usage() {
    console.log(`
Usage: node capture.js [options]

Captures headless screenshots of the monitor dashboard for every skin
(in dark and light mode) from the locally running monitor web service.

Options:
  --themes          Capture desktop-<skin>-<mode>.png for every skin (default).
  --defaults        Capture desktop-dark.png, desktop-light.png and
                    desktop-full-light.png for the default (dark) theme.
  --network         Capture network.png: the expanded Network Traffic section
                    with generated loopback traffic.
  --skin <name>     Limit the theme capture to a single skin (with --themes).
  --all             Shortcut for --themes --defaults --network.
  -h, --help        Show this help.

Environment variables:
  MONITOR_BASE      Web service base URL (default: ${BASE})
  MONITOR_OUT       Output directory (default: ${OUT})
  MONITOR_USER      Login user name (default: ${USER})
  MONITOR_PASS      Login password (default: ${PASS})
  MONITOR_CHROME    Chrome/Chromium executable (default: ${CHROME})
`);
}

function parseArgs(argv) {
    const opts = {
        themes: false,
        defaults: false,
        network: false,
        skin: null,
        help: false
    };

    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--themes':
                opts.themes = true;
                break;
            case '--defaults':
                opts.defaults = true;
                break;
            case '--network':
                opts.network = true;
                break;
            case '--all':
                opts.themes = true;
                opts.defaults = true;
                opts.network = true;
                break;
            case '--skin':
                opts.skin = argv[++i] || null;
                break;
            case '-h':
            case '--help':
                opts.help = true;
                break;
            default:
                console.error('Unknown argument:', argv[i]);
                opts.help = true;
        }
    }

    // Default to themes only.
    if (!opts.themes && !opts.defaults && !opts.network) {
        opts.themes = true;
    }

    return opts;
}

async function login(page) {
    await page.goto(BASE + '/monitor/login', { waitUntil: 'domcontentloaded' });
    await page.type('input[name=uname]', USER);
    await page.type('input[name=psw]', PASS);
    await Promise.all([
        page.click('button[type=submit]'),
        page.waitForNavigation({ waitUntil: 'domcontentloaded' })
    ]);
}

async function setSkin(page, skin, mode) {
    await page.setCookie({ name: 'css', value: skin, url: BASE, path: '/monitor/' });
    await page.setCookie({ name: 'skin', value: mode, url: BASE, path: '/monitor/' });

    // Persist server-side so the dashboard's loadSettings() honors the choice.
    await page.evaluate(async (settings) => {
        for (const [key, value] of settings) {
            await fetch('/monitor/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value })
            });
        }
    }, [['skin', mode], ['css', skin]]);
}

async function shoot(page, skin, mode, fname, viewport) {
    if (viewport) {
        await page.setViewport(viewport);
    } else {
        await page.setViewport(VIEWPORT);
    }

    await setSkin(page, skin, mode);
    await page.goto(BASE + '/monitor/internal', { waitUntil: 'domcontentloaded' });
    await sleep(3500);

    const file = path.join(OUT, fname);
    await page.screenshot({ path: file });
    console.log('saved', fname);
}

async function captureThemes(page, skin) {
    const skins = skin ? [skin] : SKINS;
    for (const name of skins) {
        for (const mode of MODES) {
            await shoot(page, name, mode, `desktop-${name}-${mode}.png`);
        }
    }
}

async function captureDefaults(page) {
    await shoot(page, 'dark', 'dark', 'desktop-dark.png');
    await shoot(page, 'dark', 'light', 'desktop-light.png');

    // Full page light capture of the default theme.
    await page.setViewport(FULL_VIEWPORT);
    await setSkin(page, 'dark', 'light');
    await page.goto(BASE + '/monitor/internal', { waitUntil: 'domcontentloaded' });
    await sleep(4000);

    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    const file = path.join(OUT, 'desktop-full-light.png');
    await page.screenshot({ path: file, clip: { x: 0, y: 0, width: FULL_VIEWPORT.width, height } });
    console.log('saved desktop-full-light.png');
}

async function captureNetwork(page) {
    await page.setViewport(NETWORK_VIEWPORT);
    await setSkin(page, 'dark', 'dark');
    await page.goto(BASE + '/monitor/internal', { waitUntil: 'domcontentloaded' });
    await sleep(2500);

    // The Network Traffic section is collapsed on load; expand it.
    await page.evaluate(() => {
        const h = document.getElementById('network');
        if (h && h.getAttribute('data-click-state') === '0') {
            h.click();
        }
    });
    await sleep(1500);

    // Generate loopback traffic so the charts show movement.
    const traffic = spawn('bash', [
        '-c',
        `for i in $(seq 1 60); do curl -s -o /dev/null ${BASE}/monitor/web/js/monitor.js; done`
    ]);
    await sleep(10000);
    traffic.kill();

    await page.evaluate(() => document.getElementById('network').scrollIntoView());
    await sleep(1500);

    const file = path.join(OUT, 'network.png');
    await page.screenshot({ path: file });
    console.log('saved network.png');
}

(async () => {
    const opts = parseArgs(process.argv.slice(2));

    if (opts.help) {
        usage();
        process.exit(0);
    }

    fs.mkdirSync(OUT, { recursive: true });

    if (!fs.existsSync(CHROME)) {
        console.error(`Chrome not found at ${CHROME}. Set MONITOR_CHROME to your Chrome/Chromium binary.`);
        process.exit(1);
    }

    const browser = await puppeteer.launch({
        executablePath: CHROME,
        headless: true,
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb']
    });

    try {
        const page = await browser.newPage();
        await page.setViewport(VIEWPORT);
        await login(page);
        console.log('logged in:', page.url());

        if (opts.themes) {
            await captureThemes(page, opts.skin);
        }
        if (opts.defaults) {
            await captureDefaults(page);
        }
        if (opts.network) {
            await captureNetwork(page);
        }
    } finally {
        await browser.close();
    }

    console.log('DONE ->', OUT);
})().catch((e) => {
    console.error('ERROR:', e);
    process.exit(1);
});
