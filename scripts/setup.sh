#!/bin/bash

# Arguments
while [[ ! $# -eq 0 ]]; do
    case "$1" in
        # Optional parameters
        --from-install | -f)
            shift
            FROM_INSTALL=$1
            ;;
        --api-key | -a)
            shift
            ARG_API_KEY=$1
            ;;
        --appearance | -ap)
            shift
            ARG_APPEARANCE=$1
            ;;
        --weather | -w)
            shift
            ARG_WEATHER=$1
            ;;
        --hour-format | -hf)
            shift
            ARG_HOUR_FORMAT=$1
            ;;
        --create-desktop-icons | -cdi)
            shift
            ARG_CREATE_DESKTOP_ICONS=$1
            ;;
        --corner-radius | -cr)
            shift
            ARG_CORNER_RADIUS=$1
            ;;
        --panel-gap | -pg)
            shift
            ARG_PANEL_GAP=$1
            ;;
    esac
    shift
done

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
API_KEY_FILE="${DIR}/.api_key"
CONFIG_FILE="${DIR}/config.yaml"

DEFAULT_OPENWEATHER_API_KEY="$( [[ -n "${ARG_API_KEY}" ]]      && echo "${ARG_API_KEY}"      || echo "${OPENWEATHER_API_KEY}" )"
DEFAULT_APPEARANCE="$(          [[ -n "${ARG_APPEARANCE}" ]]   && echo "${ARG_APPEARANCE}"   || echo "light" )"
DEFAULT_WEATHER="$(             [[ -n "${ARG_WEATHER}" ]]      && echo "${ARG_WEATHER}"      || echo "default" )"
DEFAULT_HOUR_FORMAT="$(         [[ -n "${ARG_HOUR_FORMAT}" ]]  && echo "${ARG_HOUR_FORMAT}"  || echo "24" )"
DEFAULT_CREATE_DESKTOP_ICONS="$( [[ -n "${ARG_CREATE_DESKTOP_ICONS}" ]] && echo "${ARG_CREATE_DESKTOP_ICONS}" || echo "1" )"
DEFAULT_CORNER_RADIUS="$(        [[ -n "${ARG_CORNER_RADIUS}" ]] && echo "${ARG_CORNER_RADIUS}" || grep -E '^  corner_radius: ' "${CONFIG_FILE}" 2>/dev/null | sed -E 's/^  corner_radius: //' )"
DEFAULT_CORNER_RADIUS="${DEFAULT_CORNER_RADIUS:-10}"
DEFAULT_PANEL_GAP="$(            [[ -n "${ARG_PANEL_GAP}" ]]     && echo "${ARG_PANEL_GAP}"     || grep -E '^  gap: ' "${CONFIG_FILE}" 2>/dev/null | sed -E 's/^  gap: //' )"
DEFAULT_PANEL_GAP="${DEFAULT_PANEL_GAP:-16}"

DESKTOP_LAUNCHER='
[Desktop Entry]
Comment=Start - Clock with Weather EWW widget
Terminal=false
Name=[ Start ] Clock with Weather EWW widget
Exec=bash -c "REPLACE_APP_DIR/scripts/start.sh"
Type=Application
Categories=Utility;
GenericName[en_GB.UTF-8]=Clock with Weather EWW widget
Icon=REPLACE_APP_DIR/images/theme/light/weather/dovora/01d.png
'

DESKTOP_LAUNCHER_SETUP='
[Desktop Entry]
Comment=Setup - Clock with Weather EWW widget
Terminal=true
Name=[ Setup ] Clock with Weather EWW widget
Exec=bash -c "REPLACE_APP_DIR/scripts/setup.sh"
Type=Application
Categories=Settings;Utility;
GenericName[en_GB.UTF-8]=Clock with Weather EWW widget setup
Icon=REPLACE_APP_DIR/images/theme/light/elements/temperature.png
'

C_D=$(echo -en "\e[0m")    # COLOR: DEFAULT
C_Y=$(echo -en "\e[1;93m") # COLOR: YELLOW
C_R=$(echo -en "\e[1;31m") # COLOR: RED
C_U=$(echo -en "\e[1;4m")  # UNDERLINED

echo -ne '\e]11;#000000\e\\' # set default foreground to black
echo -ne '\e]10;#ffffff\e\\' # set default background to #abcdef

function helperReplace() {
    local string=$1
    local from=$2
    local to=$3

    echo "${string//$from/$to}"
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

function setupApiKey() {
    local apiKey="${DEFAULT_OPENWEATHER_API_KEY}"

    if [[ -z "${apiKey}" ]]; then
        echo
        echo "- Please enter your ${C_Y}OpenWeatherMap API key${C_D}."
        echo "  If you don't have it yet, ${C_Y}you can get it from here${C_D}:"
        echo
        echo "  ${C_U}https://home.openweathermap.org/users/sign_up${C_D}"
        echo

        apiKey="$(
            helperPrompt "  your ${C_Y}API key${C_D}: " "EMPTY_ANSWER_NOT_ALLOWED" "NO_VALIDATE"
        )"
    fi

    echo "${apiKey}" > "${API_KEY_FILE}"
    chmod 600 "${API_KEY_FILE}"

    echo -e "- The ${C_Y}'${API_KEY_FILE}'${C_D} file saved (chmod 600)."
}

function setupAppearance() {
    local appearances
    appearances="$(ls "${DIR}/themes/appearance")"

    echo
    echo "- Choose the ${C_Y}appearance theme${C_D}:"
    local i=1
    local items=()
    for name in ${appearances} ; do
        echo -e "  ${C_Y}${i}.${C_D} ${name}"
        items+=("${name}")
        i=$((i + 1))
    done

    local number="$(
        helperPrompt "  your choice ?: " "1" "VALIDATE_NUMBER"
    )"

    if [[ -z "${number}" ]] || [[ ${number} -lt 1 ]] || [[ ${number} -gt ${#items[@]} ]]; then
        number=1
    fi

    DEFAULT_APPEARANCE="${items[$((number - 1))]}"
}

function setupWeather() {
    local weathers
    weathers="$(ls "${DIR}/themes/weather")"

    echo
    echo "- Choose the ${C_Y}weather theme${C_D} (city / language / units):"
    local i=1
    local items=()
    for name in ${weathers} ; do
        echo -e "  ${C_Y}${i}.${C_D} ${name}"
        items+=("${name}")
        i=$((i + 1))
    done

    local number="$(
        helperPrompt "  your choice ?: " "1" "VALIDATE_NUMBER"
    )"

    if [[ -z "${number}" ]] || [[ ${number} -lt 1 ]] || [[ ${number} -gt ${#items[@]} ]]; then
        number=1
    fi

    DEFAULT_WEATHER="${items[$((number - 1))]}"
}

function setupHourFormat() {
    echo
    echo "- Choose the ${C_Y}hour format${C_D}:"
    echo -e "  ${C_Y}1.${C_D} 24 (e.g. 14:05)"
    echo -e "  ${C_Y}2.${C_D} 12 (e.g. 02:05 PM)"
    echo
    DEFAULT_HOUR_FORMAT="$(
        helperPrompt "  your choice ?: " "1" "1 2"
    )"
    [[ "${DEFAULT_HOUR_FORMAT}" = "2" ]] && DEFAULT_HOUR_FORMAT="12" || DEFAULT_HOUR_FORMAT="24"
}

function setupWindowSettings() {
    echo
    echo "- Window settings:"
    echo "  corner_radius : window/panel background corner rounding in px (0 = square)."
    echo "  panel.gap     : symmetric spacing in px between the panel and the taskbar on one"
    echo "                  side and the opposite screen edge on the other side."
    echo
    DEFAULT_CORNER_RADIUS="$(
        helperPrompt "  ${C_Y}corner radius${C_D} in px [0-50] ?: " "${DEFAULT_CORNER_RADIUS}" "VALIDATE_NUMBER"
    )"
    [[ "${DEFAULT_CORNER_RADIUS}" -lt 0 ]] && DEFAULT_CORNER_RADIUS=0

    DEFAULT_PANEL_GAP="$(
        helperPrompt "  ${C_Y}panel gap${C_D} in px [0-100] ?: " "${DEFAULT_PANEL_GAP}" "VALIDATE_NUMBER"
    )"
    [[ "${DEFAULT_PANEL_GAP}" -lt 0 ]] && DEFAULT_PANEL_GAP=0
}

function setupWriteConfig() {
    sed -i "s/^appearance: .*/appearance: ${DEFAULT_APPEARANCE}/" "${CONFIG_FILE}"
    sed -i "s/^weather: .*/weather: ${DEFAULT_WEATHER}/" "${CONFIG_FILE}"
    sed -i "s/^  hour_format: .*/  hour_format: \"${DEFAULT_HOUR_FORMAT}\"/" "${CONFIG_FILE}"
    sed -i "s/^  corner_radius: .*/  corner_radius: ${DEFAULT_CORNER_RADIUS}/" "${CONFIG_FILE}"
    sed -i "s/^  gap: .*/  gap: ${DEFAULT_PANEL_GAP}/" "${CONFIG_FILE}"
    echo "- ${C_Y}'${CONFIG_FILE}'${C_D} updated (appearance: ${DEFAULT_APPEARANCE}, weather: ${DEFAULT_WEATHER}, hour_format: ${DEFAULT_HOUR_FORMAT}, corner_radius: ${DEFAULT_CORNER_RADIUS}, panel.gap: ${DEFAULT_PANEL_GAP})."
}

function setupIconSettings() {
    echo
    echo "- Do you want to create ${C_Y}Desktop icons${C_D} for starting/setup?"
    echo "  (Menu icons will be created automatically)"
    echo -e "  ${C_Y}1.${C_D} Yes"
    echo -e "  ${C_Y}2.${C_D} No"
    echo
    DEFAULT_CREATE_DESKTOP_ICONS="$(
        helperPrompt "  your choice ?: " "${DEFAULT_CREATE_DESKTOP_ICONS}" "1 2"
    )"
}

function setupCreateStartIcons() {
    local launcherPath
    local launcherMenuPath
    local launcher
    local menuDir="${HOME}/.local/share/applications"
    local desktopDir

    mkdir -p "${menuDir}"

    desktopDir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -z "${desktopDir}" ]]; then
        desktopDir="${HOME}/Desktop"
    fi

    launcherPath="${desktopDir}/start-clock-with-weather-eww.desktop"
    launcherMenuPath="${menuDir}/start-clock-with-weather-eww.desktop"

    launcher=$(helperReplace "${DESKTOP_LAUNCHER}" "REPLACE_APP_DIR" "${DIR}")

    # Always create menu icon
    echo "${launcher}" > "${launcherMenuPath}"
    chmod 755 "${launcherMenuPath}"
    echo "- Menu icon created: ${C_Y}${launcherMenuPath}${C_D}"

    # Conditionally create desktop icon
    if [[ "${DEFAULT_CREATE_DESKTOP_ICONS}" = "1" ]]; then
        echo "${launcher}" > "${launcherPath}"
        chmod 755 "${launcherPath}"
        echo "- Desktop icon created: ${C_Y}${launcherPath}${C_D}"
    fi
}

function setupCreateSetupIcons() {
    local launcherPath
    local launcherMenuPath
    local launcher
    local menuDir="${HOME}/.local/share/applications"
    local desktopDir

    mkdir -p "${menuDir}"

    desktopDir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -z "${desktopDir}" ]]; then
        desktopDir="${HOME}/Desktop"
    fi

    launcherPath="${desktopDir}/setup-clock-with-weather-eww.desktop"
    launcherMenuPath="${menuDir}/setup-clock-with-weather-eww.desktop"

    launcher=$(helperReplace "${DESKTOP_LAUNCHER_SETUP}" "REPLACE_APP_DIR" "${DIR}")

    # Always create menu icon
    echo "${launcher}" > "${launcherMenuPath}"
    chmod 755 "${launcherMenuPath}"
    echo "- Menu icon created: ${C_Y}${launcherMenuPath}${C_D}"

    # Conditionally create desktop icon
    if [[ "${DEFAULT_CREATE_DESKTOP_ICONS}" = "1" ]]; then
        echo "${launcher}" > "${launcherPath}"
        chmod 755 "${launcherPath}"
        echo "- Desktop icon created: ${C_Y}${launcherPath}${C_D}"
    fi
}

function setupStartApplication() {
    local apiKey="${DEFAULT_OPENWEATHER_API_KEY:-}"
    local startLog="${DIR}/start.log"

    if [[ -z "${apiKey}" ]] && [[ -f "${DIR}/.api_key" ]]; then
        apiKey="$(head -n 1 "${DIR}/.api_key")"
    fi

    echo
    echo "- Starting the ${C_Y}eww widgets${C_D} ... "
    if [[ -n "${apiKey}" ]]; then
        nohup bash "${DIR}/scripts/start.sh" "${apiKey}" > "${startLog}" 2>&1 &
    else
        nohup bash "${DIR}/scripts/start.sh" > "${startLog}" 2>&1 &
    fi
    echo
    echo "- The ${C_Y}eww widgets${C_D} are running."
}

function main() {
    if [[ -n "${FROM_INSTALL}" ]]; then
        return
    fi

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
