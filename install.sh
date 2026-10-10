#!/usr/bin/env sh
# shellcheck disable=SC1111 # German typographic quotes in messages are intended
# Installer for real-fast-negconv (rfnegconv) on macOS and Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh
#   curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --ohne-dienst
#   curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --uninstall
#
# Besides the background service it creates the program "Negative entwickeln"
# (macOS: ~/Applications, Linux: application menu) that processes the Negative
# folder once and shows the result. --ohne-dienst installs no service (an
# existing one is removed); a run without it installs the service again.
#
# Running it again updates the program. Existing config, folders and images
# are never changed or deleted. No admin rights needed.
#
# Environment (tests/CI):
#   RFNEGCONV_SOURCE        local path or uv source spec instead of the release
#   RFNEGCONV_NO_SERVICE=1  do not install/remove the background service
#   RFNEGCONV_PICTURES_DIR  base folder instead of the Pictures folder
#   RFNEGCONV_DESKTOP_DIR   folder for the shortcuts instead of the Desktop
#   RFNEGCONV_EXIFTOOL_SITE download site for exiftool instead of exiftool.org
#
# Exit codes: 0 ok, 1 general error, 2 wrong usage, 3 unsupported system,
#             4 uv could not be installed, 5 program could not be installed,
#             6 unsafe environment (HOME empty or "/").
set -eu

RFNEGCONV_VERSION="26.10.7"
APP_NAME="real-fast-negconv"
REPO_URL="https://github.com/jcmx9/real-fast-negconv"
RAW_URL="https://raw.githubusercontent.com/jcmx9/real-fast-negconv"
EXIFTOOL_SITE="${RFNEGCONV_EXIFTOOL_SITE:-https://exiftool.org}"
EXIFTOOL_MIRROR="https://sourceforge.net/projects/exiftool/files"  # linked from exiftool.org

TMP_DIR=""
UV=""
OS=""
DATA_DIR=""
STATE_FILE=""
EXIFTOOL_DIR=""
WITHOUT_SERVICE=0
SERVICE_REMOVED=0
LAUNCHER_NAME="Negative entwickeln"
LAUNCHER_ID="io.github.jcmx9.rfnegconv.launcher"
LAUNCHER_MARKER="X-Rfnegconv-Launcher=true"
LAUNCHER_PLACE=""

say() {
    printf '%s\n' "$*"
}

hint() {
    printf 'Hinweis: %s\n' "$*" >&2
}

die() {
    printf 'Fehler: %s\n' "$1" >&2
    exit "${2:-1}"
}

cleanup() {
    if [ -n "${TMP_DIR}" ] && [ -d "${TMP_DIR}" ]; then
        rm -rf "${TMP_DIR}"
    fi
}

usage() {
    say "Aufruf: install.sh [--ohne-dienst | --uninstall]"
    say "  ohne Option    installieren oder aktualisieren (mit Hintergrunddienst)"
    say "  --ohne-dienst  ohne Hintergrunddienst: umwandeln nur über „${LAUNCHER_NAME}“"
    say "  --uninstall    Programm entfernen (Ordner, Bilder und Einstellungen bleiben)"
}

detect_system() {
    case "${HOME:-}" in
        '' | /)
            die "Der Benutzerordner (HOME) ist nicht gesetzt oder ist „/“. Bitte als normaler Benutzer in einem Terminal ausführen." 6
            ;;
    esac
    case "$(uname -s)" in
        Darwin)
            OS="macos"
            DATA_DIR="${HOME}/Library/Application Support/${APP_NAME}"
            ;;
        Linux)
            OS="linux"
            DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/${APP_NAME}"
            ;;
        *)
            die "Dieses System wird nicht unterstützt (nur macOS und Linux; für Windows gibt es install.ps1)." 3
            ;;
    esac
    STATE_FILE="${DATA_DIR}/installer-state"
    EXIFTOOL_DIR="${DATA_DIR}/exiftool"
}

# --- state file: which parts this installer set up itself -------------------

state_get() {
    if [ -f "${STATE_FILE}" ]; then
        sed -n "s/^${1}=//p" "${STATE_FILE}" | head -n 1
    fi
}

state_set() {
    mkdir -p "${DATA_DIR}"
    if [ -f "${STATE_FILE}" ]; then
        grep -v "^${1}=" "${STATE_FILE}" >"${STATE_FILE}.tmp" || true
    else
        : >"${STATE_FILE}.tmp"
    fi
    printf '%s=%s\n' "${1}" "${2}" >>"${STATE_FILE}.tmp"
    mv "${STATE_FILE}.tmp" "${STATE_FILE}"
}

state_unset() {
    if [ -f "${STATE_FILE}" ]; then
        grep -v "^${1}=" "${STATE_FILE}" >"${STATE_FILE}.tmp" || true
        mv "${STATE_FILE}.tmp" "${STATE_FILE}"
    fi
}

# --- helpers ----------------------------------------------------------------

fetch() {
    # fetch URL FILE [MAX_SECONDS] – an unreachable host fails within seconds,
    # a download (retry included) takes about MAX_SECONDS at most (default 120)
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL \
            --connect-timeout 10 --max-time "$((${3:-120} / 2))" --retry 1 -o "${2}" "${1}"
    elif command -v wget >/dev/null 2>&1; then
        wget --https-only -q --timeout=10 --tries=2 -O "${2}" "${1}"
    else
        return 1
    fi
}

http_status() {
    # http_status URL – HTTP status code of URL (e.g. 404), empty if unknown
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --tlsv1.2 -sS -o /dev/null -w '%{http_code}' \
            --connect-timeout 10 --max-time 30 "${1}" 2>/dev/null || true
    elif command -v wget >/dev/null 2>&1; then
        wget --https-only -q --timeout=10 --tries=1 --spider -S "${1}" 2>&1 \
            | sed -n 's/^ *HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p' | tail -n 1
    fi
}

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${1}" | cut -d ' ' -f 1
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${1}" | cut -d ' ' -f 1
    else
        return 1
    fi
}

make_tmp_dir() {
    if [ -z "${TMP_DIR}" ]; then
        TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rfnegconv-install.XXXXXX")"
    fi
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        UV="$(command -v uv)"
        return 0
    fi
    for dir in "${XDG_BIN_HOME:-${HOME}/.local/bin}" "${HOME}/.local/bin" "${HOME}/.cargo/bin"; do
        if [ -x "${dir}/uv" ]; then
            PATH="${dir}:${PATH}"
            export PATH
            UV="${dir}/uv"
            return 0
        fi
    done
    return 1
}

add_tool_bin_to_path() {
    bin_dir="$("${UV}" tool dir --bin 2>/dev/null || true)"
    if [ -n "${bin_dir}" ]; then
        PATH="${bin_dir}:${PATH}"
        export PATH
    fi
}

app_installed() {
    "${UV}" tool list 2>/dev/null | grep -q "^${1} "
}

# --- install steps ----------------------------------------------------------

ensure_uv() {
    if find_uv; then
        say "✓ uv ist schon da."
        return 0
    fi
    say "→ Installiere uv (Programm-Verwaltung) …"
    make_tmp_dir
    fetch "https://astral.sh/uv/install.sh" "${TMP_DIR}/uv-install.sh" \
        || die "uv konnte nicht geladen werden. Bitte Internetverbindung prüfen." 4
    sh "${TMP_DIR}/uv-install.sh" --quiet </dev/null \
        || die "uv konnte nicht installiert werden." 4
    find_uv || die "uv wurde installiert, ist aber nicht auffindbar." 4
    state_set uv "${UV}"
    say "✓ uv installiert."
}

install_app() {
    say "→ Installiere rfnegconv ${RFNEGCONV_VERSION} (das kann ein paar Minuten dauern) …"
    # the library versions fixed for this release (constraints.txt, exported
    # from uv.lock): every install of a version gets the same libraries
    if [ -n "${RFNEGCONV_SOURCE:-}" ]; then
        if [ -d "${RFNEGCONV_SOURCE}" ]; then
            source_spec="$(cd "${RFNEGCONV_SOURCE}" && pwd)"
            set -- --reinstall-package "${APP_NAME}"
            if [ -f "${source_spec}/constraints.txt" ]; then
                set -- "$@" --constraints "${source_spec}/constraints.txt"
            fi
        else
            source_spec="${RFNEGCONV_SOURCE}"
            set --
        fi
    else
        source_spec="${APP_NAME} @ ${REPO_URL}/archive/refs/tags/v${RFNEGCONV_VERSION}.tar.gz"
        make_tmp_dir
        constraints_url="${RAW_URL}/v${RFNEGCONV_VERSION}/constraints.txt"
        if ! fetch "${constraints_url}" "${TMP_DIR}/constraints.txt"; then
            if [ "$(http_status "${constraints_url}")" = "404" ]; then
                die "Version ${RFNEGCONV_VERSION} wurde auf dem Server nicht gefunden. Bitte den Installationsbefehl von der Projektseite verwenden." 5
            fi
            die "rfnegconv konnte nicht geladen werden. Bitte Internetverbindung prüfen." 5
        fi
        set -- --constraints "${TMP_DIR}/constraints.txt"
    fi
    "${UV}" tool install --quiet --force --python 3.13 "$@" "${source_spec}" </dev/null \
        || die "rfnegconv konnte nicht installiert werden." 5
    add_tool_bin_to_path
    command -v rfnegconv >/dev/null 2>&1 \
        || die "rfnegconv wurde installiert, ist aber nicht auffindbar." 5
    # put the tool bin dir on PATH for new terminals, however uv was installed
    "${UV}" tool update-shell </dev/null >/dev/null 2>&1 || true
    say "✓ rfnegconv installiert."
}

private_exiftool_works() {
    [ -x "${EXIFTOOL_DIR}/exiftool" ] \
        && "${EXIFTOOL_DIR}/exiftool" -ver </dev/null >/dev/null 2>&1
}

install_exiftool_private() {
    command -v perl >/dev/null 2>&1 || return 2
    make_tmp_dir
    fetch "${EXIFTOOL_SITE}/ver.txt" "${TMP_DIR}/ver.txt" || return 1
    version="$(tr -d ' \r\n' <"${TMP_DIR}/ver.txt")"
    case "${version}" in
        '' | *[!0-9.]*) return 1 ;;
    esac
    archive="Image-ExifTool-${version}.tar.gz"
    fetch "${EXIFTOOL_SITE}/${archive}" "${TMP_DIR}/${archive}" 600 2>/dev/null \
        || fetch "${EXIFTOOL_MIRROR}/${archive}/download" "${TMP_DIR}/${archive}" 600 \
        || return 1
    fetch "${EXIFTOOL_SITE}/checksums.txt" "${TMP_DIR}/checksums.txt" || return 1
    expected="$(sed -n "s/^SHA2-256(${archive})= *//p" "${TMP_DIR}/checksums.txt" | tr -d ' \r')"
    actual="$(sha256_of "${TMP_DIR}/${archive}")" || return 1
    if [ -z "${expected}" ] || [ "${expected}" != "${actual}" ]; then
        return 1
    fi
    tar -xzf "${TMP_DIR}/${archive}" -C "${TMP_DIR}" || return 1
    mkdir -p "${DATA_DIR}" || return 1
    rm -rf "${EXIFTOOL_DIR}"
    if ! mv "${TMP_DIR}/Image-ExifTool-${version}" "${EXIFTOOL_DIR}" \
        || ! private_exiftool_works; then
        rm -rf "${EXIFTOOL_DIR}"  # never leave a broken copy behind; a re-run retries
        return 1
    fi
    state_set exiftool private
    return 0
}

ensure_exiftool() {
    if command -v exiftool >/dev/null 2>&1; then
        say "✓ exiftool ist schon da."
        return 0
    fi
    if private_exiftool_works; then
        say "✓ exiftool ist schon da."
        return 0
    fi
    say "→ Installiere exiftool (überträgt Kameradaten in die Fotos; dauert meist höchstens etwa eine Minute) …"
    if [ "${OS}" = "macos" ] && command -v brew >/dev/null 2>&1; then
        if NONINTERACTIVE=1 HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1 brew install --quiet exiftool </dev/null; then
            state_set exiftool brew
            say "✓ exiftool installiert."
            return 0
        fi
        hint "brew konnte exiftool nicht installieren – versuche den Download."
    fi
    status=0
    install_exiftool_private || status=$?
    if [ "${status}" -eq 0 ]; then
        say "✓ exiftool installiert."
    elif [ "${status}" -eq 2 ]; then
        hint "exiftool braucht Perl, das hier fehlt. Das Programm funktioniert trotzdem, nur ohne Kameradaten in den Fotos. Abhilfe: Paket „perl“ bzw. „libimage-exiftool-perl“ installieren."
    else
        hint "exiftool konnte nicht installiert werden. Das Programm funktioniert trotzdem, nur ohne Kameradaten in den Fotos."
    fi
}

xdg_dir() {
    # xdg_dir NAME FALLBACK – XDG user dir (e.g. PICTURES) or the fallback
    if [ "${OS}" = "linux" ] && command -v xdg-user-dir >/dev/null 2>&1; then
        dir="$(xdg-user-dir "${1}" 2>/dev/null || true)"
        if [ -n "${dir}" ] && [ "${dir}" != "${HOME}" ]; then
            printf '%s\n' "${dir}"
            return 0
        fi
    fi
    printf '%s\n' "${2}"
}

setup_folders() {
    pictures="${RFNEGCONV_PICTURES_DIR:-$(xdg_dir PICTURES "${HOME}/Pictures")}"
    base="${pictures}/rfnegconv"
    say "→ Richte Ordner und Einstellungen ein …"
    if ! output="$(rfnegconv config init --negative "${base}/Negative" \
        --photos "${base}/Fotos" --archive "${base}/Archiv")"; then
        hint "Die Einstellungen konnten nicht eingerichtet werden (siehe Meldung oben). Bitte die Datei config.toml prüfen."
        return 1
    fi
    NEGATIVE_DIR="$(printf '%s\n' "${output}" | sed -n 's/^negative=//p')"
    PHOTOS_DIR="$(printf '%s\n' "${output}" | sed -n 's/^photos=//p')"
    ARCHIVE_DIR="$(printf '%s\n' "${output}" | sed -n 's/^archive=//p')"
    CONFIG_FILE="$(printf '%s\n' "${output}" | sed -n 's/^config=//p')"
    state_set negative_dir "${NEGATIVE_DIR}"
    if [ "$(printf '%s\n' "${output}" | sed -n 's/^status=//p')" = "kept" ]; then
        say "✓ Vorhandene Einstellungen übernommen."
    else
        say "✓ Ordner angelegt."
    fi
}

setup_service() {
    if [ "${WITHOUT_SERVICE}" = "1" ]; then
        remove_service
        return 0
    fi
    if [ "${RFNEGCONV_NO_SERVICE:-}" = "1" ]; then
        say "(Test) Hintergrunddienst übersprungen – würde ausführen: rfnegconv service install"
        return 0
    fi
    say "→ Starte den Hintergrunddienst …"
    if rfnegconv service install </dev/null; then
        say "✓ Hintergrunddienst läuft."
    else
        hint "Der Hintergrunddienst konnte nicht gestartet werden. Bilder lassen sich trotzdem mit „rfnegconv“ umwandeln."
    fi
}

remove_service() {
    # --ohne-dienst: an installed service is stopped and removed
    if [ "${RFNEGCONV_NO_SERVICE:-}" = "1" ]; then
        say "(Test) Hintergrunddienst übersprungen – würde ausführen: rfnegconv service uninstall"
        SERVICE_REMOVED=1
        return 0
    fi
    if rfnegconv service uninstall </dev/null >/dev/null 2>&1; then
        SERVICE_REMOVED=1
        say "✓ Kein Hintergrunddienst (umwandeln über „${LAUNCHER_NAME}“)."
    else
        hint "Der Hintergrunddienst konnte nicht entfernt werden und bleibt eingerichtet. Bitte den Befehl später noch einmal ausführen."
    fi
}

desktop_dir() {
    printf '%s\n' "${RFNEGCONV_DESKTOP_DIR:-$(xdg_dir DESKTOP "${HOME}/Desktop")}"
}

add_shortcut() {
    # add_shortcut DESKTOP NAME TARGET KEY – only links this installer created
    # (recorded in the state file) are ever replaced or removed
    link="${1}/${2}"
    if [ -L "${link}" ] && [ "$(state_get "${4}")" = "${link}" ] \
        && [ "$(readlink "${link}")" = "$(state_get "${4}_target")" ]; then
        rm -f "${link}"  # ours and unchanged: refresh (the folder may have changed)
    elif [ -e "${link}" ] || [ -L "${link}" ]; then
        if [ "$(state_get "${4}")" = "${link}" ]; then
            state_unset "${4}"
            state_unset "${4}_target"
        fi
        hint "Auf dem Schreibtisch gibt es schon „${2}“ – nicht verändert."
        return 0
    fi
    ln -s "${3}" "${link}"
    state_set "${4}" "${link}"
    state_set "${4}_target" "${3}"
    say "✓ Verknüpfung „${2}“ auf dem Schreibtisch."
}

setup_shortcuts() {
    desktop="$(desktop_dir)"
    if [ ! -d "${desktop}" ]; then
        return 0
    fi
    add_shortcut "${desktop}" "Negative" "${NEGATIVE_DIR}" shortcut_negative
    add_shortcut "${desktop}" "Fotos" "${PHOTOS_DIR}" shortcut_photos
}

# --- launcher "Negative entwickeln": one processing run, then a dialog ------

sh_quote() {
    # sh_quote VALUE – VALUE as one single-quoted sh word
    printf "'%s'" "$(printf '%s' "${1}" | sed "s/'/'\\\\''/g")"
}

launcher_path() {
    if [ "${OS}" = "macos" ]; then
        printf '%s\n' "${HOME}/Applications/${LAUNCHER_NAME}.app"
    else
        printf '%s\n' "${XDG_DATA_HOME:-${HOME}/.local/share}/applications/negative-entwickeln.desktop"
    fi
}

launcher_is_ours() {
    # launcher_is_ours PATH – recorded by this installer and still ours
    [ "$(state_get launcher)" = "${1}" ] || return 1
    if [ "${OS}" = "macos" ]; then
        grep -q "<string>${LAUNCHER_ID}</string>" "${1}/Contents/Info.plist" 2>/dev/null
    else
        grep -qx "${LAUNCHER_MARKER}" "${1}" 2>/dev/null
    fi
}

write_launcher_script() {
    # write_launcher_script FILE APP – sh script: run APP once, show the result
    {
        printf '#!/bin/sh\n'
        printf '# „%s“ – created by the rfnegconv installer.\n' "${LAUNCHER_NAME}"
        printf '# Processes the Negative folder once and shows the result.\n'
        printf 'PATH=%s\n' "$(sh_quote "${PATH}")"
        printf 'export PATH\n'
        printf 'RFNEGCONV=%s\n' "$(sh_quote "${2}")"
        printf 'TITLE=%s\n' "$(sh_quote "${LAUNCHER_NAME}")"
        if [ "${OS}" = "macos" ]; then
            cat <<'EOF'

show_notice() {
    osascript -e 'on run argv' \
        -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
        -e 'end run' "${1}" "${TITLE}" >/dev/null 2>&1 || true
}

show_message() {
    osascript -e 'on run argv' -e 'activate' \
        -e 'display dialog (item 1 of argv) with title (item 2 of argv) buttons {"OK"} default button "OK"' \
        -e 'end run' "${1}" "${TITLE}" >/dev/null 2>&1 || printf '%s\n' "${1}"
}
EOF
        else
            cat <<'EOF'

show_notice() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -- "${TITLE}" "${1}" >/dev/null 2>&1 || true
    fi
}

show_message() {
    if command -v zenity >/dev/null 2>&1; then
        markup="$(printf '%s' "${1}" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')"
        zenity --info --title="${TITLE}" --text="${markup}" >/dev/null 2>&1 || true
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title "${TITLE}" --msgbox "${1}" >/dev/null 2>&1 || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send -- "${TITLE}" "${1}" >/dev/null 2>&1 || true
    else
        printf '%s\n' "${1}"
    fi
}
EOF
        fi
        cat <<'EOF'

field() {
    # field NAME LINE – value of NAME=<digits> in the summary line
    printf '%s\n' "${2}" | sed -n "s/.*${1}=\([0-9]*\).*/\1/p"
}

result_text() {
    # result_text OUTPUT STATUS – German result for the dialog
    line="$(printf '%s\n' "${1}" | grep '^processed=' | tail -n 1)"
    if [ "${2}" -ne 0 ] || [ -z "${line}" ]; then
        detail="$(printf '%s\n' "${1}" | sed -n 's/^Error: //p' | head -n 1)"
        printf 'Die Negative konnten nicht entwickelt werden.\n\n%s' \
            "${detail:-Das Programm rfnegconv wurde nicht gefunden oder ist abgebrochen.}"
        return 0
    fi
    processed="$(field processed "${line}")"
    failed="$(field failed "${line}")"
    photos="Fotos"
    if [ "${processed}" = "1" ]; then
        photos="Foto"
    fi
    if [ "$(field busy "${line}")" = "1" ]; then
        printf 'Wird gerade im Hintergrund verarbeitet.'
    elif [ "${failed:-0}" -gt 0 ]; then
        printf '%s %s fertig, %s Fehler – Details in Negative/_Fehler.' "${processed}" "${photos}" "${failed}"
    elif [ "${processed:-0}" -gt 0 ]; then
        printf '%s %s fertig.' "${processed}" "${photos}"
    else
        printf 'Keine neuen Negative gefunden.'
    fi
}

show_notice 'Negative werden entwickelt …'
status=0
output="$("${RFNEGCONV}" -Q run --summary 2>&1)" || status=$?
show_message "$(result_text "${output}" "${status}")"
exit 0
EOF
    } >"${1}"
    chmod 755 "${1}"
}

desktop_exec_quote() {
    # desktop_exec_quote PATH – PATH as a quoted Exec argument (desktop entry
    # spec): backslash before " ` $ \ inside the quotes, then every backslash
    # doubled because the Exec value is also a string with \\ escapes
    printf '"%s"' "$(printf '%s' "${1}" | sed 's/[\\"`$]/\\&/g; s/\\/\\\\/g; s/%/%%/g')"
}

write_launcher() {
    # write_launcher PATH APP
    if [ "${OS}" = "macos" ]; then
        mkdir -p "${1}/Contents/MacOS"
        cat >"${1}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>de</string>
	<key>CFBundleDisplayName</key>
	<string>${LAUNCHER_NAME}</string>
	<key>CFBundleExecutable</key>
	<string>negative-entwickeln</string>
	<key>CFBundleIdentifier</key>
	<string>${LAUNCHER_ID}</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>${LAUNCHER_NAME}</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>${RFNEGCONV_VERSION}</string>
	<key>CFBundleVersion</key>
	<string>${RFNEGCONV_VERSION}</string>
</dict>
</plist>
EOF
        write_launcher_script "${1}/Contents/MacOS/negative-entwickeln" "${2}"
        LAUNCHER_PLACE="Programme"
    else
        script="${DATA_DIR}/negative-entwickeln.sh"
        mkdir -p "${DATA_DIR}" "$(dirname "${1}")"
        write_launcher_script "${script}" "${2}"
        state_set launcher_script "${script}"
        cat >"${1}" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=${LAUNCHER_NAME}
Comment=Negative im Ordner „Negative“ jetzt umwandeln
Exec=$(desktop_exec_quote "${script}")
Icon=camera-photo
Terminal=false
Categories=Graphics;Photography;
${LAUNCHER_MARKER}
EOF
        LAUNCHER_PLACE="Anwendungen"
    fi
}

setup_launcher() {
    # only a launcher this installer created (state file) is ever replaced
    launcher="$(launcher_path)"
    app_path="$(command -v rfnegconv)"
    if [ -e "${launcher}" ] || [ -L "${launcher}" ]; then
        if ! launcher_is_ours "${launcher}"; then
            if [ "$(state_get launcher)" = "${launcher}" ]; then
                state_unset launcher
            fi
            hint "„${LAUNCHER_NAME}“ gibt es schon – nicht verändert."
            return 0
        fi
        remove_private_dir "${launcher}"  # ours: refresh (paths may have changed)
    fi
    write_launcher "${launcher}" "${app_path}"
    state_set launcher "${launcher}"
    say "✓ Programm „${LAUNCHER_NAME}“ (in ${LAUNCHER_PLACE})."
}

remove_launcher() {
    launcher="$(state_get launcher)"
    if [ -n "${launcher}" ] && launcher_is_ours "${launcher}"; then
        remove_private_dir "${launcher}"
    fi
    script="$(state_get launcher_script)"
    if [ -n "${script}" ] && [ "${script}" = "${DATA_DIR}/negative-entwickeln.sh" ]; then
        rm -f "${script}"
    fi
}

final_check() {
    say ""
    version_line="$(rfnegconv --version 2>/dev/null || true)"
    say "Installiert: ${version_line:-rfnegconv (Version unbekannt)}"
    status_text="$(rfnegconv service status </dev/null 2>/dev/null || true)"
    case "${status_text}" in
        *"installed and running"*) service_de="läuft" ;;
        *"installed but not running"*) service_de="eingerichtet, läuft aber gerade nicht" ;;
        *"starts at login"*) service_de="eingerichtet (startet bei der Anmeldung)" ;;
        *"not installed"*) service_de="nicht eingerichtet" ;;
        *) service_de="unbekannt" ;;
    esac
    say "Hintergrunddienst: ${service_de}"
    case "${status_text}" in
        *"exiftool: not found"*) say "exiftool: nicht gefunden (Fotos ohne Kameradaten)" ;;
        *"exiftool: "*) say "exiftool: vorhanden" ;;
    esac
}

summary() {
    say ""
    say "Fertig!"
    if [ -n "${NEGATIVE_DIR}" ]; then
        say "  Negative (hier Scans hineinlegen): ${NEGATIVE_DIR}"
        say "  Fotos (hier erscheinen die Bilder): ${PHOTOS_DIR}"
        say "  Archiv (fertige Scans):            ${ARCHIVE_DIR}"
        say "  Einstellungen:                     ${CONFIG_FILE}"
    fi
    if [ "${SERVICE_REMOVED}" = "1" ]; then
        say "Ohne Hintergrunddienst: Die Umwandlung startet nur über das Programm „${LAUNCHER_NAME}“${LAUNCHER_PLACE:+ (in ${LAUNCHER_PLACE})}."
    else
        say "Dateien im Ordner „Negative“ werden automatisch umgewandelt."
        if [ -n "${LAUNCHER_PLACE}" ]; then
            say "Sofort umwandeln: Programm „${LAUNCHER_NAME}“ (in ${LAUNCHER_PLACE})."
        fi
    fi
    if [ "${WITHOUT_SERVICE}" = "1" ]; then
        say "Aktualisieren: curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --ohne-dienst"
    else
        say "Aktualisieren: denselben Befehl noch einmal ausführen."
    fi
    say "Wird „rfnegconv“ im Terminal nicht gefunden: ein neues Terminalfenster öffnen."
    say "Entfernen:     curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --uninstall"
}

do_install() {
    NEGATIVE_DIR=""
    PHOTOS_DIR=""
    ARCHIVE_DIR=""
    CONFIG_FILE=""
    say "rfnegconv – Installation"
    ensure_uv
    install_app  # exits on failure: the old program and its service keep working
    if setup_folders; then
        setup_service
        setup_shortcuts
        setup_launcher
    fi
    ensure_exiftool  # optional and online: last, so an abort here loses nothing else
    final_check
    summary
}

# --- uninstall --------------------------------------------------------------

remove_shortcuts() {
    for key in shortcut_negative shortcut_photos; do
        link="$(state_get "${key}")"
        target="$(state_get "${key}_target")"
        if [ -n "${link}" ] && [ -L "${link}" ] && [ -n "${target}" ] \
            && [ "$(readlink "${link}")" = "${target}" ]; then
            rm -f "${link}"
        fi
    done
}

remove_private_dir() {
    # remove_private_dir DIR – rm -rf only inside the home directory
    case "${1}" in
        "${HOME}"/?*) rm -rf "${1}" ;;
        *) hint "Nicht entfernt (liegt nicht im Benutzerordner): ${1}" ;;
    esac
}

remove_uv() {
    uv_path="$(state_get uv)"
    if [ -z "${uv_path}" ]; then
        return 0
    fi
    say "→ Entferne uv (wurde von diesem Installer eingerichtet) …"
    if [ -x "${uv_path}" ]; then
        "${uv_path}" cache clean </dev/null >/dev/null 2>&1 || true
        # only a successful, empty listing allows removing uv's data
        # ("No tools installed" goes to stderr); a failed one proves nothing
        if tools="$("${uv_path}" tool list 2>/dev/null)" && [ -z "${tools}" ]; then
            python_dir="$("${uv_path}" python dir 2>/dev/null || true)"
            tool_dir="$("${uv_path}" tool dir 2>/dev/null || true)"
            if [ -n "${python_dir}" ]; then remove_private_dir "${python_dir}"; fi
            if [ -n "${tool_dir}" ]; then remove_private_dir "${tool_dir}"; fi
        fi
    fi
    uv_dir="$(dirname "${uv_path}")"
    rm -f "${uv_dir}/uv" "${uv_dir}/uvx"
    receipt_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/uv"
    rm -f "${receipt_dir}/uv-receipt.json"
    rmdir "${receipt_dir}" "${XDG_DATA_HOME:-${HOME}/.local/share}/uv" 2>/dev/null || true
    if [ -e "${uv_dir}/uv" ]; then
        hint "uv konnte nicht entfernt werden: ${uv_dir}/uv"
    else
        say "✓ uv entfernt."
    fi
}

do_uninstall() {
    say "rfnegconv – Entfernen"
    negative_dir="$(state_get negative_dir)"
    if find_uv; then
        add_tool_bin_to_path
        if command -v rfnegconv >/dev/null 2>&1; then
            if [ "${RFNEGCONV_NO_SERVICE:-}" = "1" ]; then
                say "(Test) Hintergrunddienst übersprungen – würde ausführen: rfnegconv service uninstall"
            else
                rfnegconv service uninstall </dev/null || hint "Der Hintergrunddienst konnte nicht entfernt werden."
            fi
        fi
        removed=1
        if app_installed "${APP_NAME}" \
            && ! "${UV}" tool uninstall "${APP_NAME}" </dev/null >/dev/null 2>&1; then
            hint "${APP_NAME} konnte nicht entfernt werden."
            removed=0
        fi
        if [ "${removed}" -eq 1 ]; then
            say "✓ Programm entfernt."
        fi
    else
        hint "uv nicht gefunden – das Programm ist wohl schon entfernt."
    fi
    remove_shortcuts
    remove_launcher
    case "$(state_get exiftool)" in
        brew)
            say "→ Entferne exiftool …"
            if brew uninstall --quiet exiftool </dev/null >/dev/null 2>&1; then
                say "✓ exiftool entfernt."
            else
                hint "exiftool konnte nicht entfernt werden."
            fi
            ;;
        private)
            remove_private_dir "${EXIFTOOL_DIR}"
            if [ -e "${EXIFTOOL_DIR}" ]; then
                hint "exiftool konnte nicht entfernt werden: ${EXIFTOOL_DIR}"
            else
                say "✓ exiftool entfernt."
            fi
            ;;
    esac
    remove_uv
    rm -f "${STATE_FILE}"
    rmdir "${DATA_DIR}" 2>/dev/null || true
    say ""
    say "Fertig. Deine Ordner, Bilder und Einstellungen wurden NICHT gelöscht."
    if [ -n "${negative_dir}" ]; then
        say "  Sie liegen weiterhin in: $(dirname "${negative_dir}")"
    fi
}

main() {
    mode="install"
    for arg in "$@"; do
        case "${arg}" in
            --uninstall) mode="uninstall" ;;
            --ohne-dienst) WITHOUT_SERVICE=1 ;;
            -h | --help)
                usage
                exit 0
                ;;
            *)
                usage >&2
                exit 2
                ;;
        esac
    done
    trap cleanup EXIT
    detect_system
    if [ "${mode}" = "uninstall" ]; then
        do_uninstall
    else
        do_install
    fi
}

main "$@"
