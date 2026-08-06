#!/usr/bin/env python3
import shutil
import psutil
import json

def format_bytes(n):
    if n is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            # Ha egész szám, ne legyen tizedesjegy
            if n == int(n):
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

def get_system_info():
    # HDD info
    total, used, free = shutil.disk_usage("/")
    # A Conky-hoz hasonlóan a szabad és az összes helyet mutatjuk
    hdd_fmt = f"{format_bytes(free)} / {format_bytes(total)}"

    # RAM info
    mem = psutil.virtual_memory()
    ram_fmt = f"{format_bytes(mem.used)} / {format_bytes(mem.total)}"

    # CPU info (short sampling window, since every run is a fresh process)
    cpu_usage = f"{int(psutil.cpu_percent(interval=0.2))}%"

    # SWAP info
    swap = psutil.swap_memory()
    swap_fmt = f"{int(swap.percent)}% (size: {format_bytes(swap.total)})"

    data = {
        "hdd": hdd_fmt,
        "ram": ram_fmt,
        "cpu": cpu_usage,
        "swap": swap_fmt
    }

    print(json.dumps(data))

if __name__ == "__main__":
    get_system_info()
