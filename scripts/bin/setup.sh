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

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"
API_KEY_FILE="${DIR}/.api_key"
LOCAL_CONFIG_FILE="${DIR}/config.local.yaml"

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

# ----------------------------------------------------------------------------
# Minimal YAML helpers (pure bash, no python/pyyaml). The config files are
# two-space-indented mappings of scalars; that is everything the wizard needs
# to read the defaults and to save EVERY machine-local setting into the
# git-ignored config.local.yaml.
# ----------------------------------------------------------------------------

# helperYamlLeaves <file>
# Prints every scalar leaf of a simple YAML mapping as "<dotted.path>|<value>"
# (surrounding quotes stripped). Comments, blank lines and sub-maps are skipped.
function helperYamlLeaves() {
    local file=$1
    local line rest key value path indent depth i
    local -a stack=()

    [[ -f "${file}" ]] || return 0

    while IFS= read -r line || [[ -n "${line}" ]] ; do
        rest="${line#"${line%%[! ]*}"}"
        [[ -z "${rest}" || "${rest:0:1}" = "#" ]] && continue
        indent=$(( ${#line} - ${#rest} ))
        [[ "${rest}" =~ ^([^:]+):[[:space:]]*(.*)$ ]] || continue
        key="${BASH_REMATCH[1]}"
        key="${key%%*[[:space:]]}"
        value="${BASH_REMATCH[2]}"

        depth=$(( indent / 2 ))
        stack=("${stack[@]:0:depth}")
        stack[depth]="${key}"

        [[ -z "${value//[[:space:]]/}" ]] && continue
        value="${value%%' #'*}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ ${#value} -ge 2 && "${value:0:1}" = "'" && "${value: -1}" = "'" ]] ; then
            value="${value:1:$(( ${#value} - 2 ))}"
        elif [[ ${#value} -ge 2 && "${value:0:1}" = '"' && "${value: -1}" = '"' ]] ; then
            value="${value:1:$(( ${#value} - 2 ))}"
        fi

        path="${stack[0]}"
        for (( i = 1 ; i < ${#stack[@]} ; i++ )) ; do
            path+=".${stack[${i}]}"
        done
        printf '%s|%s\n' "${path}" "${value}"
    done < "${file}"
}

# helperYamlGet <file> <dotted.key> [<default>]
function helperYamlGet() {
    local file=$1
    local key=$2
    local default="${3-}"
    local entry

    while IFS= read -r entry ; do
        if [[ "${entry%%|*}" = "${key}" ]] ; then
            printf '%s\n' "${entry#*|}"
            return 0
        fi
    done < <(helperYamlLeaves "${file}")

    printf '%s\n' "${default}"
    return 1
}

# helperYamlEmitChain <matched-depth> <parent-indent> <quoted-value>
# Prints the missing "<segment>:" chain (the final line carries the value);
# used by helperYamlSet. Reads `segments` from the caller scope.
function helperYamlEmitChain() {
    local fromDepth=$1
    local parentIndent=$2
    local quoted=$3

    local indent="${parentIndent}"
    if (( fromDepth < 0 )) ; then
        indent=$(( indent - 2 ))
    fi

    local first=$(( fromDepth < 0 ? 0 : fromDepth ))
    local last=$(( ${#segments[@]} - 1 ))
    local d
    for (( d = first ; d <= last ; d++ )) ; do
        indent=$(( indent + 2 ))
        if (( d == last )) ; then
            printf '%*s%s: %s\n' "${indent}" '' "${segments[${d}]}" "${quoted}"
        else
            printf '%*s%s:\n' "${indent}" '' "${segments[${d}]}"
        fi
    done
}

# helperYamlSet <file> <dotted.key> <value>
# Creates or updates a single leaf key; every other line of the file is kept
# verbatim (comments included). Missing sections are appended.
function helperYamlSet() {
    local file=$1
    local key=$2
    local value=$3

    local -a segments=()
    local oldIFS="${IFS}"
    IFS='.'
    read -r -a segments <<< "${key}"
    IFS="${oldIFS}"

    local quoted="${value}"
    if ! [[ "${value}" =~ ^[A-Za-z0-9_./+:-]+$ ]] ; then
        quoted="'${value//\'/\'\\\'\'}'"
    fi

    [[ -f "${file}" ]] || : > "${file}"

    local -a lines=()
    mapfile -t lines < "${file}"

    local line rest k v indent depth i j match
    local -a stack=()
    local bestDepth=-1
    local bestLine=-1
    local bestIndent=0
    local bestScalar=false

    for i in "${!lines[@]}" ; do
        line="${lines[${i}]}"
        rest="${line#"${line%%[! ]*}"}"
        [[ -z "${rest}" || "${rest:0:1}" = "#" ]] && continue
        indent=$(( ${#line} - ${#rest} ))
        [[ "${rest}" =~ ^([^:]+):[[:space:]]*(.*)$ ]] || continue
        k="${BASH_REMATCH[1]}"
        k="${k%%*[[:space:]]}"
        v="${BASH_REMATCH[2]}"

        depth=$(( indent / 2 ))
        stack=("${stack[@]:0:depth}")
        stack[depth]="${k}"

        match=0
        for j in "${!segments[@]}" ; do
            [[ -z "${stack[${j}]-}" ]] && break
            [[ "${stack[${j}]}" = "${segments[${j}]}" ]] || break
            match=$(( j + 1 ))
        done

        if (( match > bestDepth )) ; then
            bestDepth="${match}"
            bestLine="${i}"
            bestIndent="${indent}"
            bestScalar=false
            [[ -n "${v//[[:space:]]/}" ]] && bestScalar=true
        fi
    done

    local replaceMode=false
    if (( bestDepth == ${#segments[@]} )) && [[ "${bestScalar}" = true ]] ; then
        replaceMode=true
    fi

    local insertAt=${#lines[@]}
    if [[ "${replaceMode}" = false && ${bestLine} -ge 0 ]] ; then
        for (( i = bestLine + 1 ; i < ${#lines[@]} ; i++ )) ; do
            line="${lines[${i}]}"
            rest="${line#"${line%%[! ]*}"}"
            [[ -z "${rest}" || "${rest:0:1}" = "#" ]] && continue
            indent=$(( ${#line} - ${#rest} ))
            if (( indent <= bestIndent )) ; then
                insertAt="${i}"
                break
            fi
        done
    fi

    # No matching ancestor at all (bestDepth 0): the whole chain is appended
    # at the end of the file, starting at column 0.
    if [[ "${replaceMode}" = false && ${bestDepth} -eq 0 ]] ; then
        bestLine=-1
        bestIndent=-2
        insertAt=${#lines[@]}
    fi

    local tmpFile="${file}.$$"
    local emitted=false
    {
        for i in "${!lines[@]}" ; do
            if [[ "${replaceMode}" = true && "${i}" = "${bestLine}" ]] ; then
                printf '%*s%s: %s\n' "${bestIndent}" '' \
                    "${segments[${#segments[@]}-1]}" "${quoted}"
                continue
            fi
            if [[ "${replaceMode}" = false && "${i}" = "${insertAt}" ]] ; then
                helperYamlEmitChain "${bestDepth}" "${bestIndent}" "${quoted}"
                emitted=true
            fi
            printf '%s\n' "${lines[${i}]}"
        done
        if [[ "${replaceMode}" = false && "${emitted}" = false ]] ; then
            helperYamlEmitChain "${bestDepth}" "${bestIndent}" "${quoted}"
        fi
    } > "${tmpFile}" && mv -f "${tmpFile}" "${file}"
}

# helperConfigGet <key> [<monitor>]
# Resolves a setting the same way the runtime does (scripts/core/config.py):
# config.local.yaml wins over config.yaml; the weather keys fall back to the
# selected theme (assets/themes/weather/<name>/weather.yaml); positions are
# per-monitor only.
function helperConfigGet() {
    local key=$1
    local monitor="${2:-}"
    local value=""

    case "${key}" in
        city|language_code|lang|units|api_url)
            local basePath="weather.${key}"
            value="$(helperYamlGet "${LOCAL_CONFIG_FILE}" "${basePath}")"
            [[ -z "${value}" ]] && value="$(helperYamlGet "${DIR}/config.yaml" "${basePath}")"

            # Theme baseline: assets/themes/weather/<name>/weather.yaml
            local name themeValue
            name="$(helperYamlGet "${LOCAL_CONFIG_FILE}" "weather.name")"
            [[ -z "${name}" ]] && name="$(helperYamlGet "${DIR}/config.yaml" "weather.name")"
            if [[ -n "${name}" ]] ; then
                themeValue="$(helperYamlGet "${DIR}/assets/themes/weather/${name}/weather.yaml" "weather.${key}")"
                value="${value:-${themeValue}}"
            fi
            printf '%s\n' "${value}"
            return 0
            ;;
        position_x|position_y)
            local m="${monitor:-0}"
            local perMonitorPath="weather.window.per_monitor.${m}.${key}"
            value="$(helperYamlGet "${LOCAL_CONFIG_FILE}" "${perMonitorPath}")"
            [[ -z "${value}" ]] && value="$(helperYamlGet "${DIR}/config.yaml" "${perMonitorPath}")"
            [[ -z "${value}" ]] && value="0"
            printf '%s\n' "${value}"
            return 0
            ;;
        hour_format)
            local path="system.hour_format"
            local default="24"
            ;;
        alignment)
            local path="weather.window.alignment"
            local default="middle_middle"
            ;;
        panel_enabled)
            local path="panel.enabled"
            local default="true"
            ;;
        *)
            local path="${key}"
            local default=""
            ;;
    esac

    value="$(helperYamlGet "${LOCAL_CONFIG_FILE}" "${path}")"
    [[ -z "${value}" ]] && value="$(helperYamlGet "${DIR}/config.yaml" "${path}")"
    [[ -z "${value}" ]] && value="${default}"

    printf '%s\n' "${value}"
}

# helperThemeNumber <theme-name> -> 1-based index (same order as setupListThemes)
function helperThemeNumber() {
    local name="${1:-light}"
    local i=0 t

    for t in $(ls -A "${DIR}/assets/themes/appearance") ; do
        i=$(( i + 1 ))
        if [[ "${t}" = "${name}" ]] ; then
            printf '%s\n' "${i}"
            return 0
        fi
    done

    i=0
    for t in $(ls -A "${DIR}/assets/themes/appearance") ; do
        i=$(( i + 1 ))
        if [[ "${t}" = "light" ]] ; then
            printf '%s\n' "${i}"
            return 0
        fi
    done

    printf '1\n'
}

# helperAlignmentNumber <alignment-name> -> 1-based index (default: 9)
function helperAlignmentNumber() {
    local name="${1:-middle_middle}"
    local i=0 a

    for a in "${ALIGNMENTS_ARRAY[@]}" ; do
        i=$(( i + 1 ))
        if [[ "${a}" = "${name}" ]] ; then
            printf '%s\n' "${i}"
            return 0
        fi
    done

    printf '9\n'
}

DEFAULT_OPENWEATHER_API_KEY="$(  [[ -n "${ARG_API_KEY}" ]]           && echo "${ARG_API_KEY}"           || echo "${OPENWEATHER_API_KEY}" )"
DEFAULT_CITY="$(                 [[ -n "${ARG_CITY}" ]]              && echo "${ARG_CITY}"              || helperConfigGet city )"
DEFAULT_LANGUAGE_CODE="$(        [[ -n "${ARG_LANGUAGE_CODE}" ]]     && echo "${ARG_LANGUAGE_CODE}"     || helperConfigGet language_code )"
DEFAULT_LANG="$(                 [[ -n "${ARG_LANG}" ]]              && echo "${ARG_LANG}"              || helperConfigGet lang )"
DEFAULT_UNITS_NUMBER="$(         [[ -n "${ARG_UNITS_NUMBER}" ]]      && echo "${ARG_UNITS_NUMBER}"      || { [[ "$(helperConfigGet units)" = "imperial" ]] && echo "2" || echo "1" ; } )"
DEFAULT_THEME_NUMBER="$(         [[ -n "${ARG_THEME_NUMBER}" ]]      && echo "${ARG_THEME_NUMBER}"      || helperThemeNumber "$(helperConfigGet appearance)" )"
DEFAULT_HOUR_FORMAT="$(          [[ -n "${ARG_HOUR_FORMAT}" ]]       && echo "${ARG_HOUR_FORMAT}"       || helperConfigGet hour_format )"
DEFAULT_ALIGNMENT_NUMBER="$(     [[ -n "${ARG_ALIGNMENT_NUMBER}" ]]  && echo "${ARG_ALIGNMENT_NUMBER}"  || helperAlignmentNumber "$(helperConfigGet alignment)" )"
DEFAULT_POSITION_X="$(           [[ -n "${ARG_POSITION_X}" ]]        && echo "${ARG_POSITION_X}"        || helperConfigGet position_x 0 )"
DEFAULT_POSITION_Y="$(           [[ -n "${ARG_POSITION_Y}" ]]        && echo "${ARG_POSITION_Y}"        || helperConfigGet position_y 0 )"
DEFAULT_START_PANEL="$(          [[ -n "${ARG_START_PANEL}" ]]       && echo "${ARG_START_PANEL}"       || echo "1" )"
DEFAULT_CREATE_DESKTOP_ICONS="$( [[ -n "${ARG_CREATE_DESKTOP_ICONS}" ]] && echo "${ARG_CREATE_DESKTOP_ICONS}" || echo "2" )"

DESKTOP_LAUNCHER='
[Desktop Entry]
Comment=Start - Clock with Weather EWW widget
Terminal=false
Name=[ Start ] Clock with Weather EWW widget
Exec=bash -c "REPLACE_APP_DIR/scripts/bin/start.sh"
Type=Application
Categories=Utility;
GenericName[en_GB.UTF-8]=Clock with Weather EWW widget
Icon=REPLACE_APP_DIR/assets/icons-src/light/weather/dovora/01d.png
'

DESKTOP_LAUNCHER_SETUP='
[Desktop Entry]
Comment=Setup - Clock with Weather EWW widget
Terminal=true
Name=[ Setup ] Clock with Weather EWW widget
Exec=bash -c "REPLACE_APP_DIR/scripts/bin/setup.sh"
Type=Application
Categories=Settings;Utility;
GenericName[en_GB.UTF-8]=Clock with Weather EWW widget setup
Icon=REPLACE_APP_DIR/assets/icons-src/light/elements/temperature.png
'

C_D=$(echo -en "\e[0m")    # COLOR: DEFAULT
C_Y=$(echo -en "\e[1;93m") # COLOR: YELLOW
C_R=$(echo -en "\e[1;31m") # COLOR: RED
C_U=$(echo -en "\e[1;4m")  # UNDERLINED

# --- Terminal colors ---------------------------------------------------------
# Save the terminal's current default fg/bg colors (OSC 10/11 query) before
# switching to the setup palette, and restore the saved colors when this script
# exits (normally, on Ctrl+C or on SIGTERM). When sourced from install.sh, it
# has already saved the original colors; in that case they are kept here and
# only the setup palette is re-applied.
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

function terminalSetSetupColors() {
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
    terminalSetSetupColors
else
    terminalSetSetupColors
fi

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

    echo
    city="$(
        helperPrompt "- Please enter your ${C_Y}city${C_D} name ${C_Y}[e.g.: budapest, wien or london]${C_D}: " "${DEFAULT_CITY}" "NO_VALIDATE"
    )"
    city="${city,,}"   # lowercase
    city="${city^}"    # capitalize the first letter
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

    # Machine-local values go into the git-ignored config.local.yaml (deep
    # merged over the committed config, local keys win), so running setup
    # never produces changes in git. The city is NEVER written into the
    # committed theme files (assets/themes/weather/*/weather.yaml).
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.city" "${city}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.language_code" "${country}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.lang" "${lang}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.units" "${units}"
    echo "- Local weather settings saved to '${LOCAL_CONFIG_FILE}'."
}

function setupListThemes() {
    local printWithoutNames=$1
    local i=0

    for t in $(ls -A "${DIR}/assets/themes/appearance") ; do
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

    for t in $(ls -A "${DIR}/assets/themes/appearance") ; do
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

    # Every wizard choice is machine-local: it lands in the git-ignored
    # config.local.yaml (deep-merged over config.yaml, local keys win), so
    # running setup never produces changes in git.
    helperYamlSet "${LOCAL_CONFIG_FILE}" "appearance" "${DEFAULT_APPEARANCE}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "system.hour_format" "${DEFAULT_HOUR_FORMAT}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.window.alignment" "${alignment}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "panel.enabled" "${panelEnabled}"

    # The clock position is stored per monitor only (there are no global
    # position_x/position_y keys anymore); the wizard writes monitor 0's entry.
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.window.per_monitor.0.position_x" "${DEFAULT_POSITION_X}"
    helperYamlSet "${LOCAL_CONFIG_FILE}" "weather.window.per_monitor.0.position_y" "${DEFAULT_POSITION_Y}"

    echo "- Local overrides saved to '${LOCAL_CONFIG_FILE}'."
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
    local startLog="${DIR}/logs/start.log"
    mkdir -p "${DIR}/logs"
    local count

    if [[ -z "${apiKey}" ]] && [[ -f "${DIR}/.api_key" ]]; then
        apiKey="$(head -n 1 "${DIR}/.api_key")"
    fi

    echo
    echo -n "- Starting widgets ... "
    if [[ -n "${apiKey}" ]]; then
        nohup bash "${DIR}/scripts/bin/start.sh" "${apiKey}" > "${startLog}" 2>&1 &
    else
        nohup bash "${DIR}/scripts/bin/start.sh" > "${startLog}" 2>&1 &
    fi

    sleep 2
    count="$(eww --config "${DIR}/eww" active-windows 2>/dev/null | wc -l)"

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
