#!/usr/bin/env bash
# Release helper for real-fast-filmlab: sets the version in every file that
# carries it and checks the result. It commits, tags and pushes nothing.
# Usage: ./scripts/release.sh <version>     e.g. 26.12.0 or 26.12.0.dev1
set -euo pipefail

version="${1:-}"

usage() {
    echo "Usage: ${0} <version>   (YY.M.MICRO, optionally .devN)" >&2
    exit 2
}

valid_version() {
    printf '%s\n' "${1}" | grep -Eq '^[0-9]{2}\.[0-9]{1,2}\.[0-9]+(\.dev[0-9]+)?$'
}

[ "${#}" -eq 1 ] || usage
valid_version "${version}" || usage

cd "$(dirname "${0}")/.."

if [ -n "$(git status --porcelain)" ]; then
    echo "Error: the working tree has uncommitted changes." >&2
    exit 1
fi

uv run bump-my-version bump --new-version "${version}" --no-commit --no-tag --allow-dirty micro
sh scripts/check_release.sh

echo "Version ${version} is set. Next: move the CHANGELOG entries from"
echo "[Unreleased] to [${version}], then commit (release: ${version}) and tag (v${version})."
