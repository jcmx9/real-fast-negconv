#!/usr/bin/env bash
# rffilmlab.command — double-click launcher (macOS).
# Processes everything in the configured Negative folder once.
set -euo pipefail
status=0
if command -v rffilmlab >/dev/null 2>&1; then
    rffilmlab run || status="${?}"
else
    "${HOME}/.local/bin/rffilmlab" run || status="${?}"
fi
if [ "${status}" -eq 0 ]; then
    message="Fertig."
else
    message="Es gab ein Problem – siehe oben."
fi
read -r -p "${message} Enter drücken zum Schließen." _
