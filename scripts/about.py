#!/usr/bin/env python3
"""Git repository metadata for the About window.

Output (stdout, JSON):
  {"url": "https://github.com/takattila/Clock-With-Weather-EWW",
   "branch": "master", "commit": "abc1234", "full_commit": "<40 hex>",
   "date": "2026-08-17", "author": "Name", "author_email": "name@host",
   "author_date": "2026-08-17T..+00:00",
   "message": "first commit line", "tag": "v1.0"}

The URL is normalized to https:// (scripts/about.py https_url handles
git@host:path / ssh://git@host/path remotes) and the `.git` suffix is stripped,
so xdg-open opens the project page regardless of the remote transport.
"""

import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts"))

import session


def https_url(url):
    """Normalize a git remote URL to an https:// URL for xdg-open.

    Handles SSH (git@host:path, ssh://git@host/path), plain https and local
    paths; strips the trailing ".git" so xdg-open lands on the project page.
    """
    url = (url or "").strip().rstrip("/")
    m = re.match(r"^git@([^:]+):(.+)$", url)
    if m:
        url = "https://%s/%s" % (m.group(1), m.group(2))
    else:
        m = re.match(r"^ssh://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url)
        if m:
            url = "https://%s/%s" % (m.group(1), m.group(2))
    if url.endswith(".git"):
        url = url[:-4]
    return url


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
    url = https_url(git(["config", "--get", "remote.origin.url"]))
    tag = git(["describe", "--tags", "--always", "--abbrev=0"])
    if not tag:
        tag = git(["rev-parse", "--short", "HEAD"])
    return {
        "url": url,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": git(["log", "-1", "--format=%h"]),
        "full_commit": git(["log", "-1", "--format=%H"]),
        "date": git(["log", "-1", "--format=%cs"]),
        "author": git(["log", "-1", "--format=%an"]),
        "author_email": git(["log", "-1", "--format=%ae"]),
        "author_date": git(["log", "-1", "--format=%cI"]),
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
        # Close the context menu (About is opened from it) and start the ESC
        # listener so ESC / click-outside close the About window.
        run(["eww", "--config", CONFIG_DIR, "close", "ctx_menu"])
        # Transparent dismiss layer first (so the GTK About window stacks above
        # it): clicking outside the About window closes it.
        run(["eww", "--config", CONFIG_DIR, "open",
             "--id", "dismiss_overlay",
             "--screen", monitor,
             "--arg", "screen=" + monitor,
             "dismiss_overlay"])
        # The invisible keyboard daemon reads the session file: while it exists,
        # ESC closes the About window. about_win.py watches the same file and
        # quits once it disappears (ESC / click-outside / Close button).
        session.set_session({"mode": "ctx"})
        # The About dialog is a draggable GTK window (eww 0.5.0 cannot move its
        # own windows); it computes its own repository data.
        subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, "about_win.py"),
             "--monitor", monitor],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
        )
        return
    print(json.dumps(collect()))


if __name__ == "__main__":
    main()