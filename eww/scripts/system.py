#!/usr/bin/env python3
import shutil
import psutil
import json

def get_system_info():
    # HDD info
    total, used, free = shutil.disk_usage("/")
    hdd_free = f"{free // (2**30)} GB"
    hdd_total = f"{total // (2**30)} GB"
    hdd_fmt = f"{hdd_free} / {hdd_total}"

    # RAM info
    mem = psutil.virtual_memory()
    ram_used = f"{mem.used // (2**20)} MB"
    ram_max = f"{mem.total // (2**20)} MB"
    ram_fmt = f"{ram_used} / {ram_max}"

    # CPU info
    cpu_usage = f"{psutil.cpu_percent()}%"

    # SWAP info
    swap = psutil.swap_memory()
    swap_perc = f"{swap.percent}%"
    swap_max = f"{swap.total // (2**20)} MB"
    swap_fmt = f"{swap_perc} (size: {swap_max})"

    data = {
        "hdd": hdd_fmt,
        "ram": ram_fmt,
        "cpu": cpu_usage,
        "swap": swap_fmt
    }
    
    print(json.dumps(data))

if __name__ == "__main__":
    get_system_info()
