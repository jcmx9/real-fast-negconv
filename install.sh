#!/usr/bin/env sh
# shellcheck disable=SC1111 # German typographic quotes in messages are intended
# Installer for real-fast-negconv (rfnegconv) on macOS and Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh
#   curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --uninstall
#
# Running it again updates the program. Existing config, folders and images
# are never changed or deleted. No admin rights needed.
#
# Environment (tests/CI):
#   RFNEGCONV_SOURCE        local path or uv source spec instead of the release
#   RFNEGCONV_NO_SERVICE=1  do not install/remove the background service
#   RFNEGCONV_PICTURES_DIR  base folder instead of the Pictures folder
#   RFNEGCONV_DESKTOP_DIR   folder for the shortcuts instead of the Desktop
#
# Exit codes: 0 ok, 1 general error, 2 wrong usage, 3 unsupported system,
#             4 uv could not be installed, 5 program could not be installed,
#             6 unsafe environment (HOME empty or "/").
set -eu

RFNEGCONV_VERSION="26.10.6"
APP_NAME="real-fast-negconv"
REPO_URL="https://github.com/jcmx9/real-fast-negconv"
EXIFTOOL_SITE="https://exiftool.org"
EXIFTOOL_MIRROR="https://sourceforge.net/projects/exiftool/files"  # linked from exiftool.org

TMP_DIR=""
UV=""
OS=""
DATA_DIR=""
STATE_FILE=""
EXIFTOOL_DIR=""

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
    say "Aufruf: install.sh [--uninstall]"
    say "  ohne Option   installieren oder aktualisieren"
    say "  --uninstall   Programm entfernen (Ordner, Bilder und Einstellungen bleiben)"
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
    # fetch URL FILE
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL --retry 2 -o "${2}" "${1}"
    elif command -v wget >/dev/null 2>&1; then
        wget --https-only -q -O "${2}" "${1}"
    else
        return 1
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
    if [ -n "${RFNEGCONV_SOURCE:-}" ]; then
        if [ -d "${RFNEGCONV_SOURCE}" ]; then
            source_spec="$(cd "${RFNEGCONV_SOURCE}" && pwd)"
            set -- --reinstall-package "${APP_NAME}"
        else
            source_spec="${RFNEGCONV_SOURCE}"
            set --
        fi
    else
        source_spec="${APP_NAME} @ ${REPO_URL}/archive/refs/tags/v${RFNEGCONV_VERSION}.tar.gz"
        set --
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
    fetch "${EXIFTOOL_SITE}/${archive}" "${TMP_DIR}/${archive}" 2>/dev/null \
        || fetch "${EXIFTOOL_MIRROR}/${archive}/download" "${TMP_DIR}/${archive}" \
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
    say "→ Installiere exiftool (überträgt Kameradaten in die Fotos) …"
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
    say "Dateien im Ordner „Negative“ werden automatisch umgewandelt."
    say "Aktualisieren: denselben Befehl noch einmal ausführen."
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
    ensure_exiftool
    if setup_folders; then
        setup_service
        setup_shortcuts
    fi
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
        if [ -z "$("${uv_path}" tool list 2>/dev/null)" ]; then
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
