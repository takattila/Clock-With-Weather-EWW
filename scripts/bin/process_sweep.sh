#!/bin/bash
# Shared process-sweep helper for start.sh / stop.sh.
#
# Kills every process whose full command line matches an extended regex,
# EXCEPT the caller's own ancestor chain. The ancestor protection is the
# same safety idea stop_helpers() has always used: a plain `pkill -f` can
# kill the calling chain itself when a caller's command line embeds this
# repo's file names (measured: the one-line installer runs as
# `bash -c "<install.sh source>"`, so any pattern appearing in that text
# would SIGTERM the installer mid-run).
#
# Usage (after sourcing):
#   sweep_kill "${DIR}/scripts/core/watch\.py"

# PIDs of the calling process's ancestors up to init (newline list).
sweep_ancestors() {
  local pid=$1
  while [ -n "$pid" ] && [ "$pid" != "0" ] && [ "$pid" != "1" ]; do
    printf '%s\n' "$pid"
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
  done
}

# Kill every process matching $1 (ERE). TERM first, wait up to ~1.5 s,
# then KILL whatever survived. Prints each stopped PID.
sweep_kill() {
  local pattern=$1 protected pid
  protected=" $(sweep_ancestors $$ | tr '\n' ' ')"
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    [ "$pid" = "$$" ] && continue
    case "${protected} " in
      *" ${pid} "*) continue ;;
    esac
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "stopped leftover: $(cat "/proc/$pid/comm" 2>/dev/null || echo "pid $pid") (PID $pid)"
  done
}
