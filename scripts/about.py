#!/usr/bin/env python3
"""Git repository metadata for the About window.

Output (stdout, JSON):
  {"url": "https://github.com/takattila/Clock-With-Weather-Conky",
   "branch": "master", "commit": "abc1234", "date": "2026-08-17",
   "message": "first commit line", "tag": "v1.0"}

The `.git` suffix is stripped from the URL so xdg-open opens the project page.
"""

import json
import os
import subprocess
import sys

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts"))

import session


def git(args):
    try:
        out = subprocess.check_output(
            ["git", "-C", CONFIG_DIR] + args, stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        return out.strip()
    except Exception:
        return ""


def run(cmd):
    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def collect():
    url = git(["config", "--get", "remote.origin.url"])
    if url.endswith(".git"):
        url = url[:-4]
    tag = git(["describe", "--tags", "--always", "--abbrev=0"])
    if not tag:
        tag = git(["rev-parse", "--short", "HEAD"])
    return {
        "url": url,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": git(["log", "-1", "--format=%h"]),
        "date": git(["log", "-1", "--format=%cs"]),
        "message": git(["log", "-1", "--format=%s"]),
        "tag": tag,
    }


def main():
    args = sys.argv[1:]
    if "--open" in args and os.environ.get("EWW_ABOUT_BG") != "1":
        # eww kills widget commands whose runtime exceeds its timeout (default
        # 200ms) even when :timeout is set on the widget. --open spawns several
        # subprocesses (git + eww calls), so re-spawn ourselves detached: the
        # eww command returns immediately and the work keeps running.
        env = dict(os.environ, EWW_ABOUT_BG="1")
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)] + args,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        return
    if "--open" in args:
        monitor = "0"
        for i, a in enumerate(args):
            if a == "--monitor" and i + 1 < len(args):
                monitor = args[i + 1]
        info = json.dumps(collect())
        # `eww update` stores the value as a string; the eww expression engine
        # parses it as JSON at evaluation time (as_json_value), so the yuck can
        # access about_json.branch / .commit / ... directly.
        run(["eww", "--config", CONFIG_DIR, "update", "about_json=" + info])
        # Close the context menu (About is opened from it) and start the ESC
        # listener so ESC / click-outside close the About window.
        run(["eww", "--config", CONFIG_DIR, "close", "ctx_menu"])
        # Transparent dismiss layer first (so the About window stacks above it):
        # clicking outside the About window closes it.
        run(["eww", "--config", CONFIG_DIR, "open",
             "--id", "dismiss_overlay",
             "--screen", monitor,
             "--arg", "screen=" + monitor,
             "dismiss_overlay"])
        run(["eww", "--config", CONFIG_DIR, "open", "--arg", "monitor=" + monitor, "about_window"])
        # The invisible keyboard daemon reads the session file: while it exists,
        # ESC closes the About window.
        session.set_session({"mode": "ctx"})
        return
    print(json.dumps(collect()))


if __name__ == "__main__":
    main()