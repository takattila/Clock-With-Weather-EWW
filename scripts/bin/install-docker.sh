#!/bin/bash
# ==============================================================================
# install-docker.sh - the Docker-mode installer (v5.0.0)
#
# Installs the widget as a Docker container. Unlike the native installer it
# does NOT install ew/p^-style system packages -- Docker is the only real
# dependency; everything else (eww + Python + GTK) is baked into the image.
#
# This file is sourced by install.sh when the user (or INSTALL_METHOD=docker)
# picks the Docker method. It relies on the helpers/variables already defined
# by install.sh (helperExistsProgram, helperPrompt, helperInstall, C_* colors,
# REPO_DIR, etc.). Call the entry point dockerInstallMain.
#
# Requires a boxed docker installation. Works without sudo for the build if
# the user is in the docker group; otherwise uses sudo for docker directly.
# ==============================================================================

# The helper scripts that host-side control scripts (start/stop/setup) call
# must resolve to OUR wrappers in the repo bin dir, so the widget commands
# route into the container. install.sh puts this dir first in PATH below.
DOCKER_RUN_SCRIPT="${REPO_DIR}/scripts/bin/docker-start.sh"
DOCKER_STOP_SCRIPT="${REPO_DIR}/scripts/bin/docker-stop.sh"
DOCKER_IMAGE="clock-weather-eww:latest"

dockerCmd() {
  # Run docker, preferring sudo docker when needed.
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

# --- group check --------------------------------------------------------------
dockerUserInGroup() {
  # 0 if the invoking user can talk to the docker daemon without sudo.
  if docker info >/dev/null 2>&1; then
    echo 0
  else
    echo 1
  fi
}

dockerInstall() {
  # Shell out to the distro package manager to make sure `docker` exists.
  echo
  echo "- Installing ${C_Y}Docker${C_D} (the only dependency of this install method)..."

  if dockerUserInGroup; then
    echo "  Docker already available (user ${C_Y}$(whoami)${C_D} can run it without sudo)."
    return 0
  fi

  # Try common package manager installs (best-effort, mirrors install.sh style).
  if [[ "$(helperExistsProgram yum)" = "0" ]]; then
    helperInstall "yum install -y" "docker-ce"
  elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
    helperInstall "apt update -y" "UPDATE"
    helperInstall "apt install -y" "docker.io docker-compose-plugin"
  elif [[ "$(helperExistsProgram pacman)" = "0" ]]; then
    helperInstall "pacman -Sy --noconfirm" "docker docker-compose"
  elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
    helperInstall "zypper -n in" "docker docker-compose"
  elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
    helperInstall "dnf install -y" "docker-ce docker-compose-plugin"
  else
    echo
    echo "${C_R}[ ERROR ]${C_D} Can't install Docker: ${C_Y}install system not known${C_D}"
    echo "  Please install Docker yourself and add your user to the 'docker' group."
    echo
    exit 1
  fi

  if ! docker info >/dev/null 2>&1 && ! sudo -n docker info >/dev/null 2>&1; then
    # Start the docker service if the daemon is not running.
    sudo systemctl start docker 2>/dev/null || true
    sudo systemctl enable docker 2>/dev/null || true
  fi

  if ! docker info >/dev/null 2>&1 && ! sudo docker info >/dev/null 2>&1; then
    echo
    echo "${C_R}[ ERROR ]${C_D} Docker is installed but the daemon is not reachable."
    echo "  Start it with: ${C_Y}sudo systemctl start docker${C_D}"
    echo "  and add your user to the docker group: ${C_Y}sudo usermod -aG docker \$(whoami)${C_D}"
    echo
    exit 1
  fi
}

# --- build ------------------------------------------------------------------
dockerBuild() {
  echo
  echo "- Building the docker image (${C_Y}${DOCKER_IMAGE}${C_D})..."
  echo "  This compiles eww from source inside the build -- it can take 5-10 minutes."

  local ctx
  ctx="$(dirname "$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")")"

  if ! dockerCmd build -t "${DOCKER_IMAGE}" "${ctx}"; then
    echo
    echo "${C_R}[ ERROR ]${C_D} Docker build failed."
    echo
    exit 1
  fi

  echo "  Done."
}

# --- container lifecycle helpers (written to bin/) ----------------------------
# These small scripts + the eww/python3 wrappers are what start.sh/stop.sh use
# at runtime, so we generate them next to the wrappers.
dockerWriteRunScript() {
  cat > "${DOCKER_RUN_SCRIPT}" <<'EOF'
#!/bin/bash
# Start the clock-weather-eww container (if not already running).
CONTAINER="${EWW_CONTAINER:-clock-weather-eww}"
IMAGE="${EWW_IMAGE:-clock-weather-eww:latest}"

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]; then
    exit 0   # already running (start.sh drives windows via the wrappers)
  fi
  docker start "$CONTAINER" >/dev/null && exit 0
fi

# Not created yet -> run fresh with the needed mounts.
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
RUN_ARGS=(
  -d --name "$CONTAINER" --restart unless-stopped --net=host
  -e DISPLAY="${DISPLAY:-:0}"
  -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  -e XAUTHORITY="${XAUTHORITY:-}"
  -e XDG_RUNTIME_DIR=/tmp/runtime-root
  -e XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-}"
  -v "${EWW_DIR:-$HOME/.eww/Clock-With-Weather-EWW}":/app
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw
  -v /tmp/.Xauthority:/tmp/.Xauthority:ro
  -v "$XDG_RUNTIME_DIR":/tmp/runtime-root:rw
  -v /proc:/proc:ro
  -v /sys:/sys:ro
  -v /etc/os-release:/etc/os-release:ro
  -v /usr/share/fonts:/usr/share/fonts:ro
)

docker run "${RUN_ARGS[@]}" --env OPENWEATHER_API_KEY "${IMAGE}"
EOF
  chmod +x "${DOCKER_RUN_SCRIPT}"
  echo "- Runtime helper written: ${C_Y}${DOCKER_RUN_SCRIPT}${C_D}"
}

dockerWriteStopScript() {
  cat > "${DOCKER_STOP_SCRIPT}" <<'EOF'
#!/bin/bash
# Stop/remove the clock-weather-eww container.
CONTAINER="${EWW_CONTAINER:-clock-weather-eww}"
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null 2>&1 || true
fi
EOF
  chmod +x "${DOCKER_STOP_SCRIPT}"
  echo "- Runtime helper written: ${C_Y}${DOCKER_STOP_SCRIPT}${C_D}"
}

# --- PATH: put the wrapper bin dir first so eww/python3 route into container --
dockerPrepPath() {
  # The wrappers live in ${REPO_DIR}/scripts/bin.
  local bindir="${REPO_DIR}/scripts/bin"
  case ":${PATH}:" in
    *":${bindir}:"*) : ;;
    *) export PATH="${bindir}:${PATH}" ;;
  esac
}

# --- main -------------------------------------------------------------------
dockerInstallMain() {
  echo
  echo "${C_Y}== Docker installation method ==${C_D}"

  dockerInstall
  dockerBuild
  dockerWriteRunScript
  dockerWriteStopScript
  dockerPrepPath

  echo
  echo "- Docker install ready. The container will be created on first start."
  echo "  Reminder: in Docker mode the keyboard (input daemon) control is"
  echo "  disabled; the widget still fully works via mouse/menu."
}

# Allow sourcing without auto-run (install.sh sources then calls this).
