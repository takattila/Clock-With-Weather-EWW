# ==============================================================================
# Dockerfile for Clock-With-Weather-EWW (v5.0.0)
#
# Multi-stage build:
#   Stage 1 "eww-builder" compiles the `eww` binary from source (pinned
#   version). Stage 2 "runtime" installs the Python + GTK runtime deps and
#   copies the application into the image.
#
# The eww version is pinned to match the native installer (EWW_REPO_REF). The
# system is read at runtime from the host via mounted sockets, so the widget
# runs surfaced on the user's own graphical session (see docker-compose.yml /
# install-docker.sh for the required mounts and env vars).
# ==============================================================================

# --- Stage 1: Build eww from source -------------------------------------------
FROM ubuntu:22.04 AS eww-builder

ENV DEBIAN_FRONTEND=noninteractive

ARG EWW_REPO_REF=v0.6.0
ARG EWW_REPO=elkowar/eww

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential pkg-config git \
    libgtk-3-dev libgtk-layer-shell-dev \
    libpango1.0-dev libgdk-pixbuf2.0-dev \
    libcairo2-dev libglib2.0-dev libdbusmenu-gtk3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust via rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Clone and build eww. Build BOTH x11 + wayland so the same image works on any
# session (the widget detects the compositor at runtime and picks the right
# feature automatically).
RUN git clone --depth 1 --branch "${EWW_REPO_REF}" \
    "https://github.com/${EWW_REPO}.git" /tmp/eww \
  && cd /tmp/eww \
  && cargo build --release --no-default-features --features "x11 wayland" \
  && cp target/release/eww /usr/local/bin/eww \
  && rm -rf /tmp/eww /root/.cargo/registry

# --- Stage 2: Runtime image ---------------------------------------------------
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# System runtime dependencies (mirrors install.sh installEwwDependencies for
# apt). python3-xprop / python3-xrandr are not real packages; the tools come
# from x11-utils / x11-xserver-utils. qdbus6 (qt6-tools) for the KDE taskbar
# gap detection is intentionally omitted - it is optional and not packaged as
# `qt6-tools` on ubuntu:22.04; workarea.py falls back without it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ca-certificates \
    python3-requests \
    python3-psutil \
    python3-yaml \
    python3-pillow \
    python3-gi \
    gir1.2-gtk-3.0 \
    xdotool \
    xdg-utils \
    librsvg2-common \
    libdbusmenu-gtk3-4 \
    libgtk-3-0 \
    libgtk-layer-shell0 \
    libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libglib2.0-0 \
    x11-utils \
    x11-xserver-utils \
    fonts-noto-core \
    inotify-tools \
    python3-pip \
    tini \
    && rm -rf /var/lib/apt/lists/*

# The Python runtime deps (requirements.txt) pin the same minimums as native.
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy the eww binary built in stage 1
COPY --from=eww-builder /usr/local/bin/eww /usr/local/bin/eww

# Copy the application (git-ignored runtime dirs are excluded via .dockerignore)
WORKDIR /app
COPY . /app/

# Make scripts executable
RUN chmod +x /app/scripts/bin/*.sh /app/scripts/docker/*.sh

# Create the runtime directories that start.sh expects
RUN mkdir -p /app/logs /app/run /app/generated /app/charts

# eww's GTK layer-shell needs a display socket and an XDG_RUNTIME_DIR; these
# are mounted/exported at runtime (docker-compose.yml / install-docker.sh).
ENV DISPLAY=:0
ENV WAYLAND_DISPLAY=wayland-0

# tini reaps orphaned background processes (the watchers / monitor watcher)
# that start.sh spawns, so the container shuts down cleanly.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/docker/entrypoint.sh"]
