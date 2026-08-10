#!/usr/bin/env python3
"""
Watch the eww config and theme YAML files and hot-reload the widget when they
change (auto-reload, low resource usage).

Uses the Linux inotify API directly through ctypes, so no third-party packages
are needed. The main loop blocks in select(), so it wakes up only when a
watched file changes (~0 CPU while idle). After a burst of changes it runs
theme.py and then `eww reload`, so edits to config.yaml / the appearance theme
take effect immediately without restarting the widget. A config.yaml change
(panel.gap etc.) additionally triggers `start.sh --relayout` so the per-monitor
panel geometry is recomputed and reapplied.

Usage: ./watch.py [config_dir]
"""

import ctypes
import errno
import os
import select
import subprocess
import sys
import time

# --- inotify constants ------------------------------------------------------
IN_ACCESS = 0x00000001
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN = 0x00000020
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_UNMOUNT = 0x00002000
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ISDIR = 0x40000000

WATCH_MASK = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_DELETE

SETTLE = 0.5  # seconds of quiet before applying a burst of changes


class InotifyEvent(ctypes.Structure):
    _fields_ = [
        ("wd", ctypes.c_int),
        ("mask", ctypes.c_uint32),
        ("cookie", ctypes.c_uint32),
        ("len", ctypes.c_uint32),
    ]


libc = ctypes.CDLL(None, use_errno=True)
libc.inotify_init1.argtypes = [ctypes.c_int]
libc.inotify_init1.restype = ctypes.c_int
libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
libc.inotify_add_watch.restype = ctypes.c_int


class Watcher(object):
    def __init__(self, config_dir):
        self.config_dir = os.path.abspath(config_dir)
        self.config_changed = False
        self.fd = libc.inotify_init1(0)
        if self.fd < 0:
            raise OSError(
                errno.errorcode.get(ctypes.get_errno(), "?"), "inotify_init1 failed"
            )
        self._by_wd = {}  # wd -> (dir_path, interesting names or None)
        self._dirs = {}   # dir_path -> wd
        self._scan()

    # --- watch management --------------------------------------------------
    def _add_watch(self, path, interesting):
        path = os.path.realpath(path)
        if path in self._dirs:
            return
        wd = libc.inotify_add_watch(self.fd, path.encode(), WATCH_MASK)
        if wd < 0:
            self.log(
                "WARN: cannot watch %s (%s)"
                % (path, errno.errorcode.get(ctypes.get_errno(), "?"))
            )
            return
        self._by_wd[wd] = (path, interesting)
        self._dirs[path] = wd

    def _scan(self):
        # config.yaml is watched in the eww root dir; the generated theme files
        # (eww.theme.json/.scss), charts/, watch.log and watch.pid never match
        # the interesting-name filter, so they cannot trigger a reload loop.
        self._add_watch(self.config_dir, {"config.yaml"})
        for kind, fname in (("appearance", "appearance.yaml"), ("weather", "weather.yaml")):
            base = os.path.join(self.config_dir, "themes", kind)
            if not os.path.isdir(base):
                continue
            # None interesting -> also catch new theme subdirectories here
            self._add_watch(base, None)
            for name in sorted(os.listdir(base)):
                p = os.path.join(base, name)
                if os.path.isdir(p):
                    self._add_watch(p, {fname})

    def _add_new_dir(self, path):
        self._add_watch(path, {"appearance.yaml", "weather.yaml"})
        self.log("new theme directory watched: %s" % path)

    # --- helpers -----------------------------------------------------------
    def log(self, msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)

    def _relevant(self, path, interesting, fname):
        if interesting is None:
            return False  # handled separately by the caller (dir events)
        return fname in interesting

    # --- event loop --------------------------------------------------------
    def run(self):
        self.log("watching %s (inotify; stop with stop.sh)" % self.config_dir)
        pending = False
        while True:
            # Block indefinitely when idle (0 CPU); poll briefly only while a
            # burst of changes is still settling.
            timeout = SETTLE if pending else None
            readable, _, _ = select.select([self.fd], [], [], timeout)
            if readable:
                if self._handle_events():
                    pending = True
                continue
            if pending:
                pending = False
                self._apply()

    def _handle_events(self):
        changed = False
        buf = os.read(self.fd, 65536)
        hdr_size = ctypes.sizeof(InotifyEvent)
        offset = 0
        while offset < len(buf):
            ev = InotifyEvent.from_buffer_copy(buf, offset)
            name = b""
            if ev.len > 0:
                # ev.len includes the NUL terminator plus 4-byte alignment
                # padding, so strip every trailing NUL from the file name.
                name = buf[offset + hdr_size : offset + hdr_size + ev.len].rstrip(b"\x00")
            offset += hdr_size + ev.len

            info = self._by_wd.get(ev.wd)
            if info is None:
                continue
            path, interesting = info
            fname = name.decode("utf-8", "replace")

            if ev.mask & IN_ISDIR and (ev.mask & (IN_CREATE | IN_MOVED_TO)):
                self._add_new_dir(os.path.join(path, fname))
                changed = True
                continue

            if not self._relevant(path, interesting, fname):
                continue
            if ev.mask & (IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_DELETE):
                self.log("change: %s" % os.path.join(path, fname))
                if fname == "config.yaml":
                    self.config_changed = True
                changed = True
        return changed

    def _reload_eww(self):
        """Run `eww reload`, retrying when it fails.

        The eww 0.5.0 IPC client occasionally fails to read the daemon's
        response with EAGAIN (os error 11) when the daemon is busy; without a
        retry that drops the reload and the SCSS theme changes (colors, corner
        radius, fonts) never get applied. Returns True on success.
        """
        attempts = 5
        delay = 0.75
        for attempt in range(1, attempts + 1):
            try:
                reload = subprocess.run(
                    ["eww", "--config", self.config_dir, "reload"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except subprocess.TimeoutExpired:
                self.log(
                    "eww reload timed out (attempt %d/%d)" % (attempt, attempts)
                )
                time.sleep(delay)
                continue
            if reload.returncode == 0:
                return True
            if attempt < attempts:
                self.log(
                    "eww reload failed (attempt %d/%d): %s"
                    % (attempt, attempts, reload.stderr.strip().splitlines()[-1])
                )
                time.sleep(delay)
        return False

    def _apply(self):
        self.log("regenerating theme + reloading eww ...")
        try:
            gen = subprocess.run(
                [sys.executable, os.path.join(self.config_dir, "scripts", "theme.py"), self.config_dir],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            self.log("theme generation timed out")
            return
        if gen.returncode != 0:
            self.log("theme generation failed, skipping reload:\n" + gen.stderr.strip())
            return
        for line in gen.stdout.splitlines():
            self.log("  " + line.strip())
        if self._reload_eww():
            self.log("eww reloaded")
        else:
            self.log("eww reload failed (after retries)")
        if self.config_changed:
            self.config_changed = False
            self.log("config.yaml changed; re-laying-out windows")
            # Redirect the relayout output to watch.log instead of a pipe: the
            # eww open clients it spawns can outlive start.sh and would keep the
            # pipe write-end open, making subprocess.run block forever (which
            # wedges the watcher so further config edits are ignored).
            log_path = os.path.join(self.config_dir, "watch.log")
            try:
                with open(log_path, "a", encoding="utf-8") as logf:
                    relayout = subprocess.run(
                        [os.path.join(self.config_dir, "scripts", "start.sh"), "--relayout"],
                        stdout=logf,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=45,
                    )
                if relayout.returncode != 0:
                    self.log("relayout exited with status %d" % relayout.returncode)
            except subprocess.TimeoutExpired:
                self.log("relayout timed out (killed); watcher continues")


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    try:
        Watcher(config_dir).run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
