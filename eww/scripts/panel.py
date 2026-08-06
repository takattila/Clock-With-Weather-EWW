#!/usr/bin/env python3
"""
System monitor panel chart generator for the eww widget.

Reads CPU / Memory / Network statistics, keeps a rolling history
(mirroring the Conky panel in panelDraw.lua) and renders SVG line
charts with a soft area fill.

The SVG files are written into ./charts/ with a unique name per poll;
eww reloads them because the returned filenames change every second.

Usage: ./panel.py [config_dir]
Prints a JSON object consumed by eww.yuck.
"""

import json
import os
import re
import subprocess
import sys
import time

import psutil

CONFIG_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
CHARTS_DIR = os.path.join(CONFIG_DIR, "charts")
STATE_FILE = os.path.join(CHARTS_DIR, "state.json")
THEME_FILE = os.path.join(CONFIG_DIR, "eww.theme.scss")

MAX_POINTS = 100
PANEL_WIDTH = 250
CHART_W = PANEL_WIDTH - 20


def format_bytes(n):
    if n is None:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024.0:
            if n == int(n):
                return "%d %s" % (int(n), unit)
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f PB" % n


def get_screen_height():
    override = os.environ.get("PANEL_HEIGHT") or os.environ.get("EWW_PANEL_HEIGHT")
    if override:
        return int(override)
    try:
        out = subprocess.check_output(
            ["xrandr"], stderr=subprocess.DEVNULL, text=True, timeout=3
        )
        match = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
        if match:
            return int(match.group(2))
    except Exception:
        pass
    return 1080


def get_active_iface():
    try:
        out = subprocess.check_output(
            ["ip", "route", "get", "8.8.8.8"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        match = re.search(r"dev\s+(\S+)", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    counters = psutil.net_io_counters(pernic=True)
    for name, _ in sorted(counters.items()):
        if name != "lo":
            return name
    return "eth0"


def read_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def write_state(state):
    try:
        os.makedirs(CHARTS_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def update_history(hist, value):
    hist.append(value)
    if len(hist) > MAX_POINTS:
        del hist[: len(hist) - MAX_POINTS]


def get_dynamic_max(hist, min_ceiling):
    max_val = min_ceiling
    for v in hist:
        if v > max_val:
            max_val = v
    return max_val * 1.1


def load_chart_color():
    default = "#ffffff"
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            match = re.search(r"\$color-light:\s*(#[0-9a-fA-F]{3,8});", f.read())
        if match:
            return match.group(1)
    except Exception:
        pass
    return default


def hex_to_rgb255(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def render_chart(filename, hist, max_val, color_hex, w, h):
    r, g, b = hex_to_rgb255(color_hex)
    points = []
    area = ["%d,%d" % (0, h)]
    if len(hist) > 1:
        step = w / (MAX_POINTS - 1)
        for i, val in enumerate(hist):
            val_h = (val / max_val) * h
            if val_h > h:
                val_h = h
            pos_x = i * step
            pos_y = h - val_h
            points.append("%.1f,%.1f" % (pos_x, pos_y))
        area = list(points) + ["%.1f,%d" % (w * (len(hist) - 1) / (MAX_POINTS - 1), h)]
    elif len(hist) == 1:
        val_h = (hist[0] / max_val) * h
        if val_h > h:
            val_h = h
        points.append("0,%.1f" % (h - val_h))
        area = ["0,%.1f" % (h - val_h), "%d,%d" % (w, h)]

    line = ""
    if len(points) > 1:
        line = (
            '<polyline points="%s" fill="none" stroke="rgba(%d,%d,%d,0.8)" '
            'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>\n'
            % (" ".join(points), r, g, b)
        )
    area_fill = (
        '<polygon points="%s" fill="rgba(%d,%d,%d,0.15)"/>\n' % (" ".join(area), r, g, b)
    )

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'shape-rendering="geometricPrecision">\n'
        '<rect width="%d" height="%d" fill="rgba(255,255,255,0.05)"/>\n'
        "%s%s"
        "</svg>\n" % (w, h, w, h, area_fill, line)
    )

    with open(filename, "w", encoding="utf-8") as f:
        f.write(svg)


def main():
    state = read_state()
    counter = state.get("counter", 0) + 1

    cpu_hist = state.get("cpu_hist", [])
    mem_hist = state.get("mem_hist", [])
    down_hist = state.get("down_hist", [])
    up_hist = state.get("up_hist", [])

    now = time.time()

    # --- CPU usage (delta based on /proc/stat) ---
    cpu_times = psutil.cpu_times()
    cpu_raw = [float(v) for v in cpu_times]
    cpu = 0.0
    prev_raw = state.get("cpu_times_raw")
    if prev_raw:
        total_d = sum(cpu_raw) - sum(prev_raw)
        idle_d = (cpu_raw[3] + cpu_raw[4]) - (prev_raw[3] + prev_raw[4])
        if total_d > 0:
            cpu = 100.0 * (1.0 - idle_d / total_d)
    state["cpu_times_raw"] = cpu_raw
    update_history(cpu_hist, cpu)

    # --- Memory usage ---
    mem = psutil.virtual_memory()
    mem_percent = mem.percent
    mem_total = mem.total
    update_history(mem_hist, mem_percent)

    # --- Network traffic ---
    iface = get_active_iface()
    counters = psutil.net_io_counters(pernic=True)
    net = state.get("net", {})
    down = up = 0.0
    if iface in counters:
        c = counters[iface]
        last = net.get("last")
        if net.get("iface") == iface and last:
            dt = now - last.get("ts", now)
            if dt > 0:
                down = max(0.0, (c.bytes_recv - last.get("recv", c.bytes_recv)) / dt)
                up = max(0.0, (c.bytes_sent - last.get("sent", c.bytes_sent)) / dt)
        net["iface"] = iface
        net["last"] = {"recv": c.bytes_recv, "sent": c.bytes_sent, "ts": now}
    update_history(down_hist, down)
    update_history(up_hist, up)

    state["cpu_hist"] = cpu_hist
    state["mem_hist"] = mem_hist
    state["down_hist"] = down_hist
    state["up_hist"] = up_hist
    state["net"] = net
    state["counter"] = counter

    # --- Dynamic ceilings ---
    dynamic_down_max = get_dynamic_max(down_hist, 1024)
    dynamic_up_max = get_dynamic_max(up_hist, 512)

    # --- Chart geometry (mirrors panelDraw.lua) ---
    screen_h = get_screen_height()
    section_height = screen_h / 4
    title_space = 50
    gap = 20
    chart_h = int(section_height - title_space - gap)
    chart_w = CHART_W

    # --- Chart color from the active theme ---
    color_hex = load_chart_color()

    os.makedirs(CHARTS_DIR, exist_ok=True)
    stamp = counter
    files = {}
    for key, hist, max_val in (
        ("cpu", cpu_hist, 100),
        ("mem", mem_hist, 100),
        ("down", down_hist, dynamic_down_max),
        ("up", up_hist, dynamic_up_max),
    ):
        name = "%s_%05d.svg" % (key, stamp)
        files[key] = "charts/" + name
        render_chart(
            os.path.join(CHARTS_DIR, name),
            hist,
            max_val,
            color_hex,
            chart_w,
            chart_h,
        )

    # --- Cleanup old charts (keep the last 3 per chart type) ---
    try:
        for entry in os.listdir(CHARTS_DIR):
            if not entry.endswith(".svg"):
                continue
            match = re.match(r"(cpu|mem|down|up)_(\d+)\.svg$", entry)
            if match and int(match.group(2)) < stamp - 3:
                os.remove(os.path.join(CHARTS_DIR, entry))
    except Exception:
        pass

    # --- Status texts (mirrors panelDraw.lua) ---
    cpu_freq = None
    try:
        cpu_freq = psutil.cpu_freq().current / 1000.0
    except Exception:
        pass

    def net_status(hist):
        current = hist[-1] if hist else 0
        return "Current: " + format_bytes(current) + "/s"

    cpu_txt = "Current: %.1f%%" % cpu
    if cpu_freq is not None:
        cpu_txt += "  @ %.2f GHz" % cpu_freq
    mem_txt = "Current: %.1f%%  (Total: %s)" % (mem_percent, format_bytes(mem_total))
    down_txt = net_status(down_hist)
    up_txt = net_status(up_hist)

    write_state(state)

    print(
        json.dumps(
            {
                "cpu_file": files["cpu"],
                "mem_file": files["mem"],
                "down_file": files["down"],
                "up_file": files["up"],
                "cpu_txt": cpu_txt,
                "mem_txt": mem_txt,
                "down_txt": down_txt,
                "up_txt": up_txt,
                "chart_w": chart_w,
                "chart_h": chart_h,
            }
        )
    )


if __name__ == "__main__":
    main()
