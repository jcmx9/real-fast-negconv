#!/usr/bin/env bash
# rfnegconv.command — double-click launcher (macOS).
# Processes everything in the configured Negative folder once.
set -euo pipefail
if command -v rfnegconv >/dev/null 2>&1; then
    rfnegconv run || true
else
    "${HOME}/.local/bin/rfnegconv" run || true
fi
read -r -p "Fertig. Enter drücken zum Schließen." _
