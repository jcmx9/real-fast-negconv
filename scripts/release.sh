#!/usr/bin/env bash
# Release helper for real-fast-negconv.
# Usage: ./scripts/release.sh dev | prod [--new-month]
set -euo pipefail

mode="${1:-}"
flag="${2:-}"

case "$mode" in
    dev)
        git checkout dev
        git pull origin dev
        uv run bump-my-version bump dev
        git push origin dev --follow-tags
        ;;
    prod)
        git checkout dev
        git pull origin dev
        if [[ "$flag" == "--new-month" ]]; then
            uv run bump-my-version bump month
        else
            uv run bump-my-version bump micro
        fi
        git push origin dev --follow-tags
        echo "Now open a PR from dev → main."
        ;;
    *)
        echo "Usage: $0 dev | prod [--new-month]" >&2
        exit 1
        ;;
esac
