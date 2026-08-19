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
        --city | -c)
            shift
            ARG_CITY=$1
            ;;
        --language-code | -lc)
            shift
            ARG_LANGUAGE_CODE=$1
            ;;
        --lang | -la)
            shift
            ARG_LANG=$1
            ;;
        --units-number | -u)
            shift
            ARG_UNITS_NUMBER=$1
            ;;
        --theme-number | -t)
            shift
            ARG_THEME_NUMBER=$1
            ;;
        --hour-format | -hf)
            shift
            ARG_HOUR_FORMAT=$1
            ;;
        --window-alignment-number | -wa)
            shift
            ARG_ALIGNMENT_NUMBER=$1
            ;;
        --window-position-x-number | -wx)
            shift
            ARG_POSITION_X=$1
            ;;
        --window-position-y-number | -wy)
            shift
            ARG_POSITION_Y=$1
            ;;
        --start-panel | -sp)
            shift
            ARG_START_PANEL=$1
            ;;
        --create-desktop-icons | -cdi)
            shift
            ARG_CREATE_DESKTOP_ICONS=$1
            ;;
    esac
    shift
done

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
API_KEY_FILE="${DIR}/.api_key"
CONFIG_FILE="${DIR}/config.yaml"

LANGUAGE_CODES="af al ar az bg ca cz da de el en eu fa fi fr gl he hi hr hu id it ja kr la lt mk no nl pl pt pt_br ro ru sv sk sl sp sr th tr ua vi zh_cn zh_tw zu"
COUNTRY_CODES="ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw"

ALIGNMENTS_ARRAY=(
    "top_left"
    "top_right"
    "top_middle"
    "bottom_left"
    "bottom_right"
    "bottom_middle"
    "middle_left"
    "middle_right"
    "middle_middle"
)

DEFAULT_OPENWEATHER_API_KEY="$(  [[ -n "${ARG_API_KEY}" ]]          && echo "${ARG_API_KEY}"          || echo "${OPENWEATHER_API_KEY}" )"
DEFAULT_CITY="$(                 [[ -n "${ARG_CITY}" ]]              && echo "${ARG_CITY}"              || python3 "${DIR}/scripts/config.py" --key city )"
DEFAULT_LANGUAGE_CODE="$(        [[ -n "${ARG_LANGUAGE_CODE}" ]]     && echo "${ARG_LANGUAGE_CODE}"     || python3 "${DIR}/scripts/config.py" --key language_code )"
DEFAULT_LANG="$(                 [[ -n "${ARG_LANG}" ]]              && echo "${ARG_LANG}"              || python3 "${DIR}/scripts/config.py" --key lang )"
DEFAULT_UNITS_NUMBER="$(         [[ -n "${ARG_UNITS_NUMBER}" ]]      && echo "${ARG_UNITS_NUMBER}"      || python3 -c 'import sys; print(2 if sys.argv[1] == "imperial" else 1)' "$(python3 "${DIR}/scripts/config.py" --key units)" )"
DEFAULT_THEME_NUMBER="$(         [[ -n "${ARG_THEME_NUMBER}" ]]      && echo "${ARG_THEME_NUMBER}"      || python3 -c '
import os, sys
names = sorted(os.listdir(os.path.join(sys.argv[1], "themes", "appearance")))
try:
    print(names.index(sys.argv[2]) + 1)
except ValueError:
    print(11)
' "$DIR" "$(python3 "${DIR}/scripts/config.py" --key appearance)" )"
DEFAULT_HOUR_FORMAT="$(          [[ -n "${ARG_HOUR_FORMAT}" ]]       && echo "${ARG_HOUR_FORMAT}"       || python3 "${DIR}/scripts/config.py" --key hour_format )"
DEFAULT_ALIGNMENT_NUMBER="$(     [[ -n "${ARG_ALIGNMENT_NUMBER}" ]]  && echo "${ARG_ALIGNMENT_NUMBER}"  || python3 -c '
import sys
a = ["top_left", "top_right", "top_middle", "bottom_left", "bottom_right", "bottom_middle", "middle_left", "middle_right", "middle_middle"]
try:
    print(a.index(sys.argv[1]) + 1)
except ValueError:
    print(9)
' "$(python3 "${DIR}/scripts/config.py" --key alignment)" )"
DEFAULT_POSITION_X="$(           [[ -n "${ARG_POSITION_X}" ]]        && echo "${ARG_POSITION_X}"        || python3 "${DIR}/scripts/config.py" --key position_x --monitor 0 )"
DEFAULT_POSITION_Y="$(           [[ -n "${ARG_POSITION_Y}" ]]        && echo "${ARG_POSITION_Y}"        || python3 "${DIR}/scripts/config.py" --key position_y --monitor 0 )"
DEFAULT_START_PANEL="$(          [[ -n "${ARG_START_PANEL}" ]]       && echo "${ARG_START_PANEL}"       || python3 -c 'import sys; print(1 if sys.argv[1] == "true" else 2)' "$(python3 "${DIR}/scripts/config.py" --key panel_enabled)" )"
DEFAULT_CREATE_DESKTOP_ICONS="$( [[ -n "${ARG_CREATE_DESKTOP_ICONS}" ]] && echo "${ARG_CREATE_DESKTOP_ICONS}" || echo "1" )"

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

function setupWeatherDetails() {
    local city
    local country
    local lang
    local unitsNumber
    local units
    local weatherFile="${DIR}/themes/weather/default/weather.yaml"

    echo
    city="$(
        helperPrompt "- Please enter your ${C_Y}city${C_D} name ${C_Y}[e.g.: budapest, wien or london]${C_D}: " "${DEFAULT_CITY}" "NO_VALIDATE"
    )"
    city="$(python3 -c 'import sys; s = sys.argv[1].strip(); print((s[:1].upper() + s[1:].lower()) if s else s)' "${city}")"
    DEFAULT_CITY="${city}"

    echo
    echo "- Please enter your ${C_Y}country code${C_D}."
    echo "  This one is to specify in which country the given ${C_Y}city is located${C_D}."
    echo "  Check your country code here: ${C_U}https://www.iban.com/country-codes${C_D}"
    echo
    country="$(
        helperPrompt "  ${C_Y}[e.g.: hu, gb, us]${C_D}: " "${DEFAULT_LANGUAGE_CODE}" "${COUNTRY_CODES}"
    )"
    DEFAULT_LANGUAGE_CODE="${country}"

    echo
    echo "- Please enter your ${C_Y}language code${C_D}."
    echo "  In what language do you want to ${C_Y}display the weather details?${C_D}"
    echo "  Check your language code here: ${C_U}https://openweathermap.org/current#multi${C_D}"
    echo
    lang="$(
        helperPrompt "  ${C_Y}[e.g.: hu, en, fr]${C_D}: " "${DEFAULT_LANG}" "${LANGUAGE_CODES}"
    )"
    DEFAULT_LANG="${lang}"

    echo
    echo "- Please enter which temperature unit do you want to use: "
    echo -e "  ${C_Y}1.${C_D} metric (for displaying ${C_Y}Celsius${C_D})"
    echo -e "  ${C_Y}2.${C_D} imperial (for displaying ${C_Y}Fahrenheit${C_D})"
    echo
    unitsNumber="$(
        helperPrompt "  ${C_Y}[1 or 2]${C_D} ?: " "${DEFAULT_UNITS_NUMBER}" "1 2"
    )"
    [[ "${unitsNumber}" = "2" ]] && units="imperial" || units="metric"
    DEFAULT_UNITS_NUMBER="${unitsNumber}"

    sed -i "s/^  city: .*/  city: ${city}/" "${weatherFile}"
    sed -i "s/^  language_code: .*/  language_code: ${country}/" "${weatherFile}"
    sed -i "s/^  lang: .*/  lang: ${lang}/" "${weatherFile}"
    sed -i "s/^  units: .*/  units: ${units}/" "${weatherFile}"
}

function setupListThemes() {
    local printWithoutNames=$1
    local i=0

    for t in $(ls -A "${DIR}/themes/appearance") ; do
        i=$(( i + 1 ))
        if [[ "${printWithoutNames}" ]]; then
            echo "${i} "
        else
            echo "  ${C_Y}${i}.${C_D} ${t}"
        fi
    done
}

function setupGetThemeByNumber() {
    local number=$1
    local i=0

    for t in $(ls -A "${DIR}/themes/appearance") ; do
        i=$(( i + 1 ))
        if [[ "$i" = "$number" ]]; then
            echo "${t}"
            break
        fi
    done
}

function setupAppearance() {
    echo
    setupListThemes
    echo
    DEFAULT_THEME_NUMBER="$(
        helperPrompt "- Enter choosen ${C_Y}theme${C_D} number ${C_Y}[e.g.: 11]${C_D}: " "${DEFAULT_THEME_NUMBER}" "$(setupListThemes 1)"
    )"
    DEFAULT_APPEARANCE="$(setupGetThemeByNumber "${DEFAULT_THEME_NUMBER}")"
}

function setupHourFormat() {
    echo
    DEFAULT_HOUR_FORMAT="$(
        helperPrompt "- What type of ${C_Y}hour format${C_D} do you want to use ${C_Y}[12 or 24]${C_D} ?: " "${DEFAULT_HOUR_FORMAT}" "12 24"
    )"
}

function setupListConfigAlignments() {
    local printWithoutNames=$1
    local i=0

    for a in "${ALIGNMENTS_ARRAY[@]}" ; do
        i=$(( i + 1 ))
        if [[ "${printWithoutNames}" ]]; then
            echo "${i} "
        else
            echo -e "  ${C_Y}${i}.${C_D} ${a}"
        fi
    done
}

function setupGetConfigAlignmentByNumber() {
    local number=$1
    local i=0

    for a in "${ALIGNMENTS_ARRAY[@]}" ; do
        i=$(( i + 1 ))
        if [[ "$i" = "$number" ]]; then
            echo "${a}"
            break
        fi
    done
}

function setupWindowSettings() {
    echo
    echo "- Please enter the ${C_Y}number${C_D} of the choosen ${C_Y}window alignment${C_D}."
    echo
    setupListConfigAlignments
    echo
    DEFAULT_ALIGNMENT_NUMBER="$(
        helperPrompt "  ${C_Y}[e.g.: 9]${C_D} ?: " "${DEFAULT_ALIGNMENT_NUMBER}" "$(setupListConfigAlignments 1)"
    )"

    echo
    DEFAULT_POSITION_X="$(
        helperPrompt "- Please enter the '${C_Y}X${C_D}' position of the widget's window ${C_Y}[e.g.: 0]${C_D}: " "${DEFAULT_POSITION_X}" "VALIDATE_NUMBER"
    )"

    echo
    DEFAULT_POSITION_Y="$(
        helperPrompt "- Please enter the '${C_Y}Y${C_D}' position of the widget's window ${C_Y}[e.g.: 0]${C_D}: " "${DEFAULT_POSITION_Y}" "VALIDATE_NUMBER"
    )"

    echo
    echo "- Do you want to start the ${C_Y}System Monitor Panel${C_D} as well?"
    echo -e "  ${C_Y}1.${C_D} Yes (Recommended)"
    echo -e "  ${C_Y}2.${C_D} No"
    echo
    DEFAULT_START_PANEL="$(
        helperPrompt "  your choice ?: " "${DEFAULT_START_PANEL}" "1 2"
    )"
}

function setupWriteConfig() {
    local alignment
    local panelEnabled

    alignment="$(setupGetConfigAlignmentByNumber "${DEFAULT_ALIGNMENT_NUMBER}")"
    [[ "${DEFAULT_START_PANEL}" = "1" ]] && panelEnabled="true" || panelEnabled="false"

    python3 -c '
import re, sys
path, new = sys.argv[1], sys.argv[2]
text = open(path, "r", encoding="utf-8").read()
text = re.sub(r"^appearance:.*(?:\n[ \t]+.*)*", "appearance: " + new, text, count=1, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
' "${CONFIG_FILE}" "${DEFAULT_APPEARANCE}"
    sed -i "s/^  hour_format: .*/  hour_format: \"${DEFAULT_HOUR_FORMAT}\"/" "${CONFIG_FILE}"
    sed -i "s/^  alignment: .*/  alignment: ${alignment}/" "${CONFIG_FILE}"
    sed -i "s/^  enabled: .*/  enabled: ${panelEnabled}/" "${CONFIG_FILE}"

    # The clock position is stored per monitor only (there are no global
    # position_x/position_y keys anymore); the wizard writes monitor 0's entry.
    python3 "${DIR}/scripts/config_set.py" --widget clock --monitor 0 \
        --key position_x --value "${DEFAULT_POSITION_X}"
    python3 "${DIR}/scripts/config_set.py" --widget clock --monitor 0 \
        --key position_y --value "${DEFAULT_POSITION_Y}"
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

    local legacyLauncher
    for legacyLauncher in \
        "${menuDir}/start-clock-with-weather-conky-widget.desktop" \
        "${desktopDir}/start-clock-with-weather-conky-widget.desktop"; do
        if [[ -f "${legacyLauncher}" ]]; then
            rm -f "${legacyLauncher}"
            echo "- Removed obsolete launcher: ${C_Y}${legacyLauncher}${C_D}"
        fi
    done

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

    local legacyLauncher
    for legacyLauncher in \
        "${menuDir}/setup-clock-with-weather-conky-widget.desktop" \
        "${desktopDir}/setup-clock-with-weather-conky-widget.desktop"; do
        if [[ -f "${legacyLauncher}" ]]; then
            rm -f "${legacyLauncher}"
            echo "- Removed obsolete launcher: ${C_Y}${legacyLauncher}${C_D}"
        fi
    done

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
    local count

    if [[ -z "${apiKey}" ]] && [[ -f "${DIR}/.api_key" ]]; then
        apiKey="$(head -n 1 "${DIR}/.api_key")"
    fi

    echo
    echo -n "- Starting widgets ... "
    if [[ -n "${apiKey}" ]]; then
        nohup bash "${DIR}/scripts/start.sh" "${apiKey}" > "${startLog}" 2>&1 &
    else
        nohup bash "${DIR}/scripts/start.sh" > "${startLog}" 2>&1 &
    fi

    sleep 2
    count="$(eww --config "${DIR}" active-windows 2>/dev/null | wc -l)"

    if [[ "${count}" -gt 0 ]]; then
        echo -e "${C_Y}done${C_D} (${count} eww windows detected)."
    else
        echo -e "${C_R}failed or still starting...${C_D}"
    fi

    echo
    echo -e "- EWW widgets started. - ${C_Y}Bye! :-)${C_D}"
    echo
    echo "-------------------------------------------------------"
    read -n 1 -s -p "  Press any key to close this window..."
    echo
}

function main() {
    if [[ -n "${FROM_INSTALL}" ]]; then
        return
    fi

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
