#!/usr/bin/env bash
# rffilmlab.command — double-click launcher (macOS).
# Processes everything in the configured Negative folder once.
set -euo pipefail
if command -v rffilmlab >/dev/null 2>&1; then
    rffilmlab run || true
else
    "${HOME}/.local/bin/rffilmlab" run || true
fi
read -r -p "Fertig. Enter drücken zum Schließen." _
