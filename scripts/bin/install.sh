#!/bin/bash

# --- Standalone widget repo -------------------------------------------------
# The eww widget is its own repository; the repo root IS the widget directory.
GITHUB_USER="takattila"
REPO="Clock-With-Weather-EWW"
REPO_BRANCH="${REPO_BRANCH:-master}"
# ----------------------------------------------------------------------------

EWW_REPO="elkowar/eww"
# Pinned eww release built when no distro package provides eww. Override by
# exporting EWW_REPO_REF before running the installer.
#
# IDENTITY RULE: the ONLY reliable identifier of an eww build is the 40-hex
# git hash embedded in `eww --version`. The printed version NUMBER is
# cosmetic -- upstream tagged v0.6.0 while its Cargo string still said
# "eww 0.5.0" (that tag build also applies transform :scale before
# :translate), and later master commits print "eww 0.6.0". The widget
# scripts read exactly this hash, and ensurePinnedEww() below compares it
# against the ref's commit SHA and offers a pinned source build whenever
# they differ -- even when a distro package or a newer master build is
# already present.
EWW_REPO_REF="${EWW_REPO_REF:-v0.6.0}"
BASE_DIR="${HOME}/.eww"
REPO_DIR="${BASE_DIR}/${REPO}"
EWW_DIR="${REPO_DIR}"
EWW_BUILD_DIR="${EWW_BUILD_DIR:-/tmp/eww-src}"
EWW_INSTALL_BIN="${EWW_INSTALL_BIN:-/usr/local/bin/eww}"

# City preselected by the setup wizard during the installation (Enter picks
# this instead of the value saved in config.local.yaml; override by exporting
# DEFAULT_CITY before running the installer).
DEFAULT_CITY="${DEFAULT_CITY:-Budapest}"

C_D=$(echo -en "\e[0m")    # COLOR: DEFAULT
C_Y=$(echo -en "\e[1;93m") # COLOR: YELLOW
C_R=$(echo -en "\e[1;31m") # COLOR: RED
C_G=$(echo -en "\e[1;92m") # COLOR: GREEN
C_U=$(echo -en "\e[1;4m")  # UNDERLINED

# --- Terminal colors ---------------------------------------------------------
# Save the terminal's current default fg/bg colors (OSC 10/11 query) before
# switching to the installer palette, and restore the saved colors when this
# script exits (normally, on Ctrl+C or on SIGTERM). When setup.sh is sourced
# below, it detects the already-saved colors and keeps them instead of saving
# the installer palette as the "original" ones.
TERMINAL_ORIG_FG=""
TERMINAL_ORIG_BG=""

function terminalQueryColor() {
    local osc=$1
    local out=""
    local ch=""
    local escSeen=false

    { stty -F /dev/tty flushi; } &> /dev/null
    { printf '\e]%s;?\e\\' "${osc}" > /dev/tty; } 2> /dev/null || return 1

    while IFS= read -r -n 1 -s -t 1 ch < /dev/tty; do
        if [[ "${escSeen}" = "true" ]]; then
            if [[ "${ch}" = "\\" ]]; then
                out="${out%?}" # drop the trailing ESC (ST terminator)
                break
            fi
            escSeen=false
        fi
        if [[ "${ch}" = $'\e' ]]; then
            escSeen=true
        elif [[ "${ch}" = $'\a' ]]; then
            break # BEL terminator
        fi
        out+="${ch}"
    done

    out="${out#*;}"

    if ! [[ "${out}" =~ ^(#|rgb:) ]]; then
        return 1
    fi

    printf '%s' "${out}"
}

function terminalSetInstallerColors() {
    # White default foreground (OSC 10) on black default background (OSC 11).
    { printf '\e]10;#ffffff\e\\\e]11;#000000\e\\' > /dev/tty; } 2> /dev/null
    return 0
}

function terminalRestoreColors() {
    [[ "${TERMINAL_COLORS_RESTORED:-}" = "true" ]] && return 0
    TERMINAL_COLORS_RESTORED="true"

    if [[ -n "${TERMINAL_ORIG_FG}" && -n "${TERMINAL_ORIG_BG}" ]]; then
        {
            printf '\e]10;%s\e\\\e]11;%s\e\\' \
                "${TERMINAL_ORIG_FG}" "${TERMINAL_ORIG_BG}" > /dev/tty
        } 2> /dev/null
    else
        # Query unsupported: fall back to the terminal's built-in defaults.
        { printf '\e]110\e\\\e]111\e\\' > /dev/tty; } 2> /dev/null
    fi

    return 0
}

if [[ -z "${TERMINAL_COLORS_SAVED:-}" ]]; then
    TERMINAL_COLORS_SAVED="true"
    TERMINAL_ORIG_FG="$(terminalQueryColor 10 || true)"
    TERMINAL_ORIG_BG="$(terminalQueryColor 11 || true)"
    trap terminalRestoreColors EXIT
    trap 'terminalRestoreColors; exit 130' INT
    trap 'terminalRestoreColors; exit 143' TERM
    terminalSetInstallerColors
else
    terminalSetInstallerColors
fi

function helperExistsProgram() {
    local program=$1

    if command -v "${program}" &> /dev/null; then
        echo 0
        return 0
    fi

    if command -v sudo &> /dev/null; then
        if sudo -n command -v "${program}" &> /dev/null; then
            echo 0
            return 0
        fi
    fi

    echo 1
}

function helperCheckDir() {
    local dir=$1

    if [[ -d "${dir}" ]]; then
        echo 0
    else
        echo 1
    fi
}

function helperGetLatestRelease() {
  curl --silent "https://api.github.com/repos/$1/releases/latest" |
    grep '"tag_name":' |
    sed -E 's/.*"([^"]+)".*/\1/'
}

function helperGetEwwRefSha() {
  # Full commit SHA the pinned ${EWW_REPO_REF} points at ("" when the API is
  # unreachable / rate-limited / the ref is unknown). The top-level "sha" is
  # the first match in the commits-API response.
  curl --silent --max-time 10 \
    "https://api.github.com/repos/${EWW_REPO}/commits/${EWW_REPO_REF}" |
    grep -m1 '"sha":' |
    sed -E 's/.*"([0-9a-f]{40})".*/\1/'
}

function helperCheckout() {
    echo

    {
        cd "${REPO_DIR}"
        git fetch --all --tags --prune
        git checkout -f -B "${REPO_BRANCH}" "origin/${REPO_BRANCH}"
    } &> /dev/null

    if [[ "$(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD)" != "${REPO_BRANCH}" ]]; then
        echo
        echo "${C_R}[ ERROR ]${C_D} The widget repo is not on the '${C_Y}${REPO_BRANCH}${C_D}' branch."
        echo
        exit 1
    fi
}

function helperCloneAndCheckout() {
    echo
    echo -n "- Downloading ${C_Y}${REPO}${C_D} ... "

    {
      git clone --branch "${REPO_BRANCH}" https://github.com/"${GITHUB_USER}"/"${REPO}".git \
          "${REPO_DIR}"
    } &> /dev/null

    echo "done."

    helperCheckout

    echo -e "- The ${C_Y}'${REPO_DIR}'${C_D} application installed."
}

function helperInArray() {
    local what=$1
    shift

    local validAnswersArray=($@)
    local match=false

    for str in "${validAnswersArray[@]}" ; do
        if [[ "${str}" = "${what}" ]]; then
            match=true
            break
        fi
    done

    echo ${match}
}

function helperPrompt() {
    local printHelperText=$1
    local defaultAnswer=$2
    shift

    local validAnswersArray=("${@:2}")
    local promptText="${printHelperText}"

    # Mark the default answer (taken on plain Enter).
    if [[ -n "${defaultAnswer}" && "${defaultAnswer}" != "EMPTY_ANSWER_NOT_ALLOWED" ]]; then
        promptText+="${C_Y} [default: ${defaultAnswer}]${C_D} "
    fi

    read -p "${promptText}" answer

    if [[ -z "${answer}" ]]; then
        if [[ "${defaultAnswer}" = "EMPTY_ANSWER_NOT_ALLOWED" ]]; then
            helperPrompt "${printHelperText}" "${defaultAnswer}" "${validAnswersArray[@]}"
            return
        fi
        echo "${defaultAnswer}"
        return
    fi

    if [[ "${validAnswersArray}" = "VALIDATE_NUMBER" ]]; then
        if ! [[ ${answer} =~ ^[-0-9]+$ ]]; then
            helperPrompt "${printHelperText}" "${defaultAnswer}" "${validAnswersArray[@]}"
            return
        fi
        echo "${answer}"
        return
    fi

    if [[ "${validAnswersArray}" != "NO_VALIDATE" ]]; then
        if [[ "$(helperInArray "${answer}" "${validAnswersArray[@]}")" = "false" ]]; then
            helperPrompt "${printHelperText}" "${defaultAnswer}" "${validAnswersArray[@]}"
            return
        fi
    fi

    echo "${answer}"
}

function helperInstall() {
    local cmd=$1
    shift

    local packages=$@

    if [[ "${packages}" = "UPDATE" ]]; then
        echo -n "  == Running ${C_Y}${cmd}${C_D} ... "
        eval "sudo ${cmd}" &> /dev/null
        echo "done."
        return
    fi

    for package in $(echo ${packages}) ; do
        echo -n "  == Installing ${C_Y}${package}${C_D} ... "
        eval "sudo ${cmd} ${package}" &> /dev/null
        echo "done."
    done
}

function helperInstallRust() {
    if [[ "$(helperExistsProgram cargo)" = "0" ]]; then
        return 0
    fi

    echo
    echo "- Installing ${C_Y}Rust${C_D} (rustup) ... "

    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y &> /dev/null
    source "${HOME}/.cargo/env"

    if [[ "$(helperExistsProgram cargo)" = "1" ]]; then
        echo
        echo "${C_R}[ ERROR ]${C_D} Rust (cargo) installation failed."
        echo
        exit 1;
    fi

    echo "done."
}

function helperInstallEwwBuildDeps() {
    echo
    echo "- Installing ${C_Y}eww build dependencies${C_D} ... "
    if [[ "$(helperExistsProgram yum)" = "0" ]]; then
        helperInstall "yum install -y" "epel-release"
        helperInstall "yum install -y" "gcc make pkgconfig gtk3-devel gtk-layer-shell-devel pango-devel gdk-pixbuf2-devel cairo-devel glib2-devel libdbusmenu-gtk3-devel"
    elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
        helperInstall "apt update -y" "UPDATE"
        helperInstall "apt install -y" "build-essential pkg-config libgtk-3-dev libgtk-layer-shell-dev libpango1.0-dev libgdk-pixbuf2.0-dev libcairo2-dev libglib2.0-dev libdbusmenu-gtk3-dev"
    elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
        helperInstall "zypper -n in" "gcc make pkgconf-pkg-config gtk3-devel gtk-layer-shell-devel pango-devel gdk-pixbuf-devel cairo-devel glib2-devel libdbusmenu-gtk3-devel"
    elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
        helperInstall "dnf install -y" "gcc make pkgconf-pkg-config gtk3-devel gtk-layer-shell-devel pango-devel gdk-pixbuf2-devel cairo-devel glib2-devel libdbusmenu-gtk3-devel"
    else
        echo
        echo "${C_R}[ ERROR ]${C_D} Can't install eww build dependencies: ${C_Y}install system not known${C_D}"
        echo
        exit 1;
    fi
}

function helperBuildEwwFromSource() {
    local force=${1:-n}
    local eww_features="x11"
    [[ -n "${WAYLAND_DISPLAY}" ]] && eww_features="wayland"
    local eww_bin="${EWW_INSTALL_BIN}"
    local rebuild_eww="n"

    echo
    echo "- Building ${C_Y}eww${C_D} from source (feature: ${eww_features}) ... "

    if [[ -x "${eww_bin}" && "${force}" != "force" ]]; then
        rebuild_eww="$(
            helperPrompt "  == ${C_Y}eww${C_D} is already installed at ${C_Y}${eww_bin}${C_D}. Rebuild it from source? ${C_Y}[y or n]${C_D}: " "n" "y n"
        )"

        if [[ "${rebuild_eww}" != "y" ]]; then
            echo "  == Skipping build."
            return 0
        fi
    fi

    helperInstallRust
    helperInstallEwwBuildDeps

    rm -rf "${EWW_BUILD_DIR}"

    echo -n "  == Cloning: ${C_Y}https://github.com/${EWW_REPO}${C_D} (ref: ${C_Y}${EWW_REPO_REF}${C_D}) ... "
    git clone --depth 1 --branch "${EWW_REPO_REF}" https://github.com/"${EWW_REPO}".git "${EWW_BUILD_DIR}" &> /dev/null
    echo "done."

    echo "  == Running ${C_Y}cargo build --release${C_D} (this can take a while, typically 5-10 minutes on this machine) ... "
    echo "     ${C_Y}Please wait${C_D}: the build is compiling eww from source."
    ( cd "${EWW_BUILD_DIR}" && cargo build --release --no-default-features --features "${eww_features}" ) &> /dev/null

    if [[ ! -f "${EWW_BUILD_DIR}/target/release/eww" ]]; then
        echo
        echo "${C_R}[ ERROR ]${C_D} eww build failed."
        echo
        exit 1;
    fi

    sudo cp "${EWW_BUILD_DIR}/target/release/eww" "${EWW_INSTALL_BIN}"
    rm -rf "${EWW_BUILD_DIR}"

    echo "  == The ${C_Y}eww${C_D} installation has been finished."
}

function installProceed() {
    local proceed="$(
            helperPrompt "- Do you ${C_Y}want to start${C_D} the installation? ${C_Y}[y or n]${C_D}: " "y" "y n"
    )"

    if [[ "${proceed}" = "n" ]]; then
        exit
    fi
}

function installPrintLogo() {
    printf "${C_Y}"
cat <<-'EOF'
  ____ _            _               _ _   _     
 / ___| | ___   ___| | __ __      _(_) |_| |__  
| |   | |/ _ \ / __| |/ / \ \ /\ / / | __| '_ \ 
| |___| | (_) | (__|   <   \ V  V /| | |_| | | |
 \____|_|\___/ \___|_|\_\   \_/\_/ |_|\__|_| |_|
   __        __         _   _               
   \ \      / /__  __ _| |_| |__   ___ _ __ 
    \ \ /\ / / _ \/ _` | __| '_ \ / _ \ '__|
     \ V  V /  __/ (_| | |_| | | |  __/ |   
      \_/\_/ \___|\__,_|\__|_| |_|\___|_|   

               ... EWW Widget ....
EOF
    printf "${C_D}\n"

}

function installCheckOS() {
    local os="$(uname -s)"
    if [[ "${os}" != "Linux" ]]; then
        echo "${C_R}[ ERROR ]${C_D} The ${C_Y}${os}${C_D} OS is not supported by this script."
        echo
        echo "          eww (ElKowar's Wacky Widgets) is ${C_Y}Linux only${C_D}."
        echo
        exit 1
    fi
}

function installSetRootPassword() {
    sudo -p "$(
        echo
        echo "- A password is required for installation."
        echo "  Please enter the ${C_Y}root password${C_D}: "
    )" echo -n "" 2> /dev/null
}

function installUsLocale() {
        local en="en_US"
        local utf8="UTF-8"
        local usLocale="${en}.${utf8}"
        local dpkgReCfg="dpkg-reconfigure"
        local localeGenCmd="$(
            if [[ "$(helperExistsProgram "${dpkgReCfg}")" = "0" ]]; then
                echo "${dpkgReCfg} locales --frontend noninteractive"
            else
                echo "locale-gen"
            fi
        )"

        if [[ "$(locale -a | grep -q "${en}.utf8" ; echo $?)" = "1" ]]; then
            echo
            echo -en "- Generating ${C_Y}${usLocale}${C_D} locale, this might take a while ... "

            {
                sudo cp /etc/locale.gen .
                sudo chown $(whoami) locale.gen
                echo "${usLocale} ${utf8}" >> locale.gen
                sudo chown root locale.gen
                sudo mv -f locale.gen /etc
                sudo ${localeGenCmd}
            } &> /dev/null

            echo "done."
        fi
}

function installDependencies() {
    local packages="curl gawk git"
    local packagesToInstall=""

    for package in $(echo ${packages}) ; do
        if [[ "$(helperExistsProgram "${package}")" = "1" ]]; then
            packagesToInstall="${packagesToInstall}${package} "
        fi
    done

    if [[ ! -z "${packagesToInstall}" ]]; then
        echo
        echo "- Installing dependencies: ${C_Y}${packagesToInstall}${C_D} ... "
        if [[ "$(helperExistsProgram yum)" = "0" ]]; then
            helperInstall "yum install -y" "epel-release"
            helperInstall "yum install -y" "${packagesToInstall}"
        elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
            helperInstall "apt update -y" "UPDATE"
            helperInstall "apt install -y" "${packagesToInstall}"
        elif [[ "$(helperExistsProgram pacman)" = "0" ]]; then
            helperInstall "pacman -Sy --noconfirm" "${packagesToInstall}"
        elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
            helperInstall "zypper -n in" "${packagesToInstall}"
        elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
            helperInstall "dnf install -y" "${packagesToInstall}"
        else
            echo
            echo "${C_R}[ ERROR ]${C_D} Can't install dependencies: ${C_Y}install system not known${C_D}"
            echo
            exit 1;
        fi
    fi
}

function installEwwDependencies() {
    local packages=""

    # Runtime deps for the widget scripts:
    #   - python3-gi + GTK3 typelibs (keyboard grab helpers)
    #   - xdotool               (menu positioning / cursor centering on X11)
    # NOTE: never name the helper files in this script: with the wget/curl
    # one-liner install this whole file IS the installer process command line,
    # and the pkill patterns in stop.sh must never match it.
    #   - xdg-utils             (xdg-open for the About window)
    #   - librsvg               (SVG loader for the panel charts)
    # qt6-tools provides qdbus6, used by workarea.py to query the KDE taskbar
    # frame for the panel gaps (optional: geometry falls back without it).
    if [[ "$(helperExistsProgram yum)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml python3-pillow python3-gobject gtk3 xdotool xdg-utils librsvg2 xorg-x11-utils xorg-x11-server-utils google-noto-sans-fonts qt6-tools"
    elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml python3-pillow python3-gi gir1.2-gtk-3.0 xdotool xdg-utils librsvg2-common x11-utils x11-xserver-utils fonts-noto-core qt6-tools"
    elif [[ "$(helperExistsProgram pacman)" = "0" ]]; then
        packages="python python-requests python-psutil python-yaml python-pillow python-gobject gtk3 xdotool xdg-utils librsvg xorg-xprop xorg-xrandr noto-fonts qt6-tools"
    elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-PyYAML python3-Pillow python3-gobject gtk3 xdotool xdg-utils librsvg2 xprop xrandr google-noto-sans-fonts qt6-tools"
    elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml python3-pillow python3-gobject gtk3 xdotool xdg-utils librsvg2 xorg-x11-utils xorg-x11-server-utils google-noto-sans-fonts qt6-tools"
    else
        echo
        echo "${C_R}[ ERROR ]${C_D} Can't install eww dependencies: ${C_Y}install system not known${C_D}"
        echo
        exit 1;
    fi

    echo
    echo "- Installing eww dependencies: ${C_Y}${packages}${C_D} ... "
    if [[ "$(helperExistsProgram yum)" = "0" ]]; then
        helperInstall "yum install -y" "${packages}"
    elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
        helperInstall "apt update -y" "UPDATE"
        helperInstall "apt install -y" "${packages}"
    elif [[ "$(helperExistsProgram pacman)" = "0" ]]; then
        helperInstall "pacman -Sy --noconfirm" "${packages}"
    elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
        helperInstall "zypper -n in" "${packages}"
    elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
        helperInstall "dnf install -y" "${packages}"
    fi
}

function ewwInstalledHash() {
    # 40-hex git hash reported by the installed eww binary ("" when missing).
    local ver=""
    if command -v eww &> /dev/null; then
        ver="$(eww --version 2> /dev/null)"
    fi
    if [[ "${ver}" =~ ([0-9a-f]{40}) ]]; then
        printf '%s' "${BASH_REMATCH[1]}"
    fi
}

function ensurePinnedEww() {
    # Prints what is installed and reconciles it with the pinned
    # ${EWW_REPO_REF}.
    #
    # IDENTITY RULE (deliberately loud): the ONLY reliable identifier of an
    # eww build is the 40-hex git hash embedded in `eww --version`. The
    # printed version NUMBER can be anything -- upstream tagged v0.6.0 while
    # its Cargo string still said "eww 0.5.0", and later master commits print
    # "eww 0.6.0". Every message below therefore leads with an explicit
    # "Identity:" line built from the hash, never from the number.
    local ver="" inst_hash="" exp_sha="" ans="" new_hash="" ident=""
    if command -v eww &> /dev/null; then
        ver="$(eww --version 2> /dev/null)"
    fi

    echo "- Installed eww: ${ver:-NOT FOUND}"

    if [[ -z "${ver}" ]]; then
        echo "  ${C_R}Identity: NONE${C_D} -- eww is not runnable; the widget will not start."
        return
    fi

    inst_hash="$(ewwInstalledHash)"
    if [[ -z "${inst_hash}" ]]; then
        echo "  ${C_Y}Identity: UNKNOWN${C_D} (no embedded git hash). Treated as a modern build; it cannot be verified against ${C_Y}${EWW_REPO_REF}${C_D}."
        return
    fi

    exp_sha="$(helperGetEwwRefSha)"
    if [[ -z "${exp_sha}" ]]; then
        echo "  ${C_Y}Identity: build ${C_Y}${inst_hash:0:7}${C_D} (GitHub unreachable -- comparison with ${C_Y}${EWW_REPO_REF}${C_D} skipped)."
        return
    fi

    if [[ "${inst_hash}" = "${exp_sha}" ]]; then
        echo "  ${C_G}Identity: build ${C_Y}${inst_hash:0:7}${C_G} == pinned ${EWW_REPO_REF}.${C_D}"
        echo "  NOTE: this tag's binaries print a stale 'eww 0.5.0' label -- the NUMBER is cosmetic, the HASH above is what matters."
        return
    fi

    echo "  ${C_Y}Identity: build ${C_Y}${inst_hash:0:7}${C_Y} != pinned ${EWW_REPO_REF} (${exp_sha:0:7})${C_D}. Only the hash counts -- the printed number does not."
    ans="$(helperPrompt \
        "  == Build & install the pinned ${C_Y}${EWW_REPO_REF}${C_D} now? ${C_Y}[y or n]${C_D}: " \
        "y" "y n")"

    if [[ "${ans}" != "y" ]]; then
        echo "  Keeping the installed build; the widget detects its transform order automatically."
        return
    fi

    helperBuildEwwFromSource "force"
    new_hash="$(ewwInstalledHash)"
    echo "- Installed eww now: $(eww --version 2> /dev/null || echo 'NOT FOUND')"
    if [[ -n "${new_hash}" && "${new_hash}" = "${exp_sha}" ]]; then
        echo "  ${C_G}Identity: build ${C_Y}${new_hash:0:7}${C_G} == pinned ${EWW_REPO_REF}.${C_D}"
    elif [[ -n "${new_hash}" ]]; then
        echo "  ${C_Y}Identity: fresh build reports ${C_Y}${new_hash:0:7}${C_Y} != pinned ref${C_D}; leaving it in place."
    fi
}

function installEww() {
    echo
    echo "- Installing: ${C_Y}eww${C_D} ... "

    if [[ "$(helperExistsProgram pacman)" = "0" ]]; then
        echo -n "  == Installing ${C_Y}eww${C_D} ... "
        sudo pacman -Sy --noconfirm eww &> /dev/null

        if [[ "$(helperExistsProgram eww)" = "0" ]]; then
            echo "done."
            ensurePinnedEww
            return
        fi

        echo "not found in the official repos;"
        helperBuildEwwFromSource
    else
        helperBuildEwwFromSource
    fi

    ensurePinnedEww
}

function installWidgetFromGitHub() {
    local repo_dir="${REPO_DIR}"
    local backup_file="${BASE_DIR}/${REPO}-config.local.yaml.bak"

    # Default behaviour: remove any existing widget directory before cloning.
    # The git-ignored config.local.yaml is backed up first and restored into
    # the freshly cloned directory afterwards.
    rm -f "${backup_file}"

    if [[ "$(helperCheckDir "${repo_dir}")" = "0" ]]; then
        echo
        echo -n "- Deleting the existing ${C_Y}'${repo_dir}'${C_D} ... "
        killall eww &> /dev/null

        if [[ -f "${repo_dir}/config.local.yaml" ]]; then
            cp "${repo_dir}/config.local.yaml" "${backup_file}"
        fi

        rm -rf "${repo_dir}"
        echo "done."
    fi

    helperCloneAndCheckout

    if [[ -f "${backup_file}" ]]; then
        cp "${backup_file}" "${repo_dir}/config.local.yaml"
        rm -f "${backup_file}"
        echo "- The ${C_Y}'config.local.yaml'${C_D} backup restored."
    fi
}

function installFont() {
    local font="NotoSans-Regular.ttf"

    mkdir -p /home/"$(whoami)"/.local/share/fonts
    cp "${EWW_DIR}"/assets/fonts/"${font}" /home/"$(whoami)"/.local/share/fonts

    echo -e "- The ${C_Y}'${font}'${C_D} font installed."
}
function installSourceSetup() {
    source "${EWW_DIR}/scripts/bin/setup.sh" --from-install true --city "${DEFAULT_CITY}"
}

function main() {
    clear

    installPrintLogo
    installProceed
    installCheckOS
    installSetRootPassword
    installUsLocale
    installDependencies
    installEwwDependencies
    installEww
    installWidgetFromGitHub
    installFont

    installSourceSetup

    setupApiKey
    setupWeatherDetails
    setupAppearance
    setupHourFormat
    setupWindowSettings
    setupWriteConfig
    setupIconSettings
    setupCreateStartIcons
    setupCreateSetupIcons
    setupStartApplication
}

main
