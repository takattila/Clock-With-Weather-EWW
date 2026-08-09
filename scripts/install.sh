#!/bin/bash

# --- Standalone widget repo -------------------------------------------------
# The eww widget is its own repository; the repo root IS the widget directory.
GITHUB_USER="takattila"
REPO="Clock-With-Weather-Conky"
REPO_BRANCH="${REPO_BRANCH:-feature/wayland}"
# ----------------------------------------------------------------------------

EWW_REPO="elkowar/eww"
BASE_DIR="${HOME}/.eww"
REPO_DIR="${BASE_DIR}/${REPO}"
EWW_DIR="${REPO_DIR}"
EWW_BUILD_DIR="${EWW_BUILD_DIR:-/tmp/eww-src}"
EWW_INSTALL_BIN="${EWW_INSTALL_BIN:-/usr/local/bin/eww}"

C_D=$(echo -en "\e[0m")    # COLOR: DEFAULT
C_Y=$(echo -en "\e[1;93m") # COLOR: YELLOW
C_R=$(echo -en "\e[1;31m") # COLOR: RED
C_U=$(echo -en "\e[1;4m")  # UNDERLINED

echo -ne '\e]11;#000000\e\\' # set default foreground to black
echo -ne '\e]10;#ffffff\e\\' # set default background to #abcdef

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

    read -p "${printHelperText}" answer

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
    local eww_features="x11"
    [[ -n "${WAYLAND_DISPLAY}" ]] && eww_features="wayland"
    local eww_bin="${EWW_INSTALL_BIN}"
    local rebuild_eww="n"

    echo
    echo "- Building ${C_Y}eww${C_D} from source (feature: ${eww_features}) ... "

    if [[ -x "${eww_bin}" ]]; then
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

    echo -n "  == Cloning: ${C_Y}https://github.com/${EWW_REPO}${C_D} ... "
    git clone --depth 1 https://github.com/"${EWW_REPO}".git "${EWW_BUILD_DIR}" &> /dev/null
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

    if [[ "$(helperExistsProgram yum)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml xorg-x11-utils xorg-x11-server-utils google-noto-sans-fonts"
    elif [[ "$(helperExistsProgram apt)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml x11-utils x11-xserver-utils fonts-noto-core"
    elif [[ "$(helperExistsProgram pacman)" = "0" ]]; then
        packages="python python-requests python-psutil python-yaml xorg-xprop xorg-xrandr noto-fonts"
    elif [[ "$(helperExistsProgram zypper)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-PyYAML xprop xrandr google-noto-sans-fonts"
    elif [[ "$(helperExistsProgram dnf)" = "0" ]]; then
        packages="python3 python3-requests python3-psutil python3-yaml xorg-x11-utils xorg-x11-server-utils google-noto-sans-fonts"
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

function installEww() {
    echo
    echo "- Installing: ${C_Y}eww${C_D} ... "

    if [[ "$(helperExistsProgram pacman)" = "0" ]]; then
        echo -n "  == Installing ${C_Y}eww${C_D} ... "
        sudo pacman -Sy --noconfirm eww &> /dev/null

        if [[ "$(helperExistsProgram eww)" = "0" ]]; then
            echo "done."
            return
        fi

        echo "not found in the official repos;"
        helperBuildEwwFromSource
    else
        helperBuildEwwFromSource
    fi
}

function installWidgetFromGitHub() {
    local repo_dir="${REPO_DIR}"
    local delete_repo_dir

    if [[ "$(helperCheckDir "${repo_dir}")" = "0" ]]; then
        echo
        echo "- The ${C_Y}'${repo_dir}'${C_D} already exists."
        delete_repo_dir="$(
            helperPrompt "  Do you want to delete it? ${C_Y}[y or n]${C_D}: " "n" "y n"
        )"

        if [[ "${delete_repo_dir}" = "y" ]]; then
            killall eww &> /dev/null
            rm -rf "${repo_dir}"
            helperCloneAndCheckout

            return
        fi

        helperCheckout

        return
    fi

    helperCloneAndCheckout
}

function installFont() {
    local font="NotoSans-Regular.ttf"

    mkdir -p /home/"$(whoami)"/.local/share/fonts
    cp "${EWW_DIR}"/fonts/"${font}" /home/"$(whoami)"/.local/share/fonts

    echo -e "- The ${C_Y}'${font}'${C_D} font installed."
}
function installSourceSetup() {
    source "${EWW_DIR}/scripts/setup.sh" --from-install true
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
    setupAppearance
    setupWeather
    setupHourFormat
    setupWindowSettings
    setupWriteConfig
    setupIconSettings
    setupCreateStartIcons
    setupCreateSetupIcons
    setupStartApplication
}

main
