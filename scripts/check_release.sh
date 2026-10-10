#!/usr/bin/env sh
# Release consistency checks (CI and before a release).
#
#   sh scripts/check_release.sh
#
# 1. The version in src/real_fast_negconv/__init__.py, pyproject.toml
#    (bump-my-version), install.sh, install.ps1 and both README headers agree.
# 2. constraints.txt (the library versions the installers use) matches
#    uv.lock; regenerate it with the command in its first lines.
#
# Exit codes: 0 consistent, 1 a check failed.
set -eu

repo="$(cd "$(dirname "$0")/.." && pwd)"
status=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    status=1
}

version_in() {
    # version_in FILE SED_EXPRESSION – first match of SED_EXPRESSION in FILE
    sed -n "$2" "${repo}/$1" | head -n 1
}

expected="$(version_in src/real_fast_negconv/__init__.py 's/^__version__ = "\(.*\)"$/\1/p')"
if [ -z "${expected}" ]; then
    fail "no __version__ in src/real_fast_negconv/__init__.py"
fi
check_version() {
    # check_version FILE SED_EXPRESSION
    found="$(version_in "$1" "$2")"
    if [ "${found}" != "${expected}" ]; then
        fail "$1 says '${found}', __init__.py says '${expected}'"
    fi
}
check_version pyproject.toml 's/^current_version = "\(.*\)"$/\1/p'
check_version install.sh 's/^RFNEGCONV_VERSION="\(.*\)"$/\1/p'
check_version install.ps1 "s/^\$script:Version = '\(.*\)'\$/\1/p"
check_version README.md 's/.*\*\*Version \([^*]*\)\*\*.*/\1/p'
check_version README.en.md 's/.*\*\*Version \([^*]*\)\*\*.*/\1/p'

tmp="$(mktemp "${TMPDIR:-/tmp}/constraints.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
if ! (cd "${repo}" && uv export --locked --no-hashes --no-dev --no-emit-project \
    --format requirements-txt --no-header --quiet) >"${tmp}"; then
    fail "uv.lock is not up to date with pyproject.toml"
elif ! sed '/^#/d' "${repo}/constraints.txt" | cmp -s - "${tmp}"; then
    fail "constraints.txt does not match uv.lock (regenerate it, see its first lines)"
fi

if [ "${status}" -eq 0 ]; then
    printf 'release checks passed (version %s)\n' "${expected}"
fi
exit "${status}"
