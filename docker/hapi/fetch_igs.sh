#!/usr/bin/env bash
# fetch_igs.sh — download IG package tarballs into docker/hapi/igs/
# Run once before `make fhir-up` on a fresh checkout.
# Requires: curl, sha256sum (or shasum -a 256 on macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IGS_DIR="${SCRIPT_DIR}/igs"
mkdir -p "${IGS_DIR}"

declare -A URLS
declare -A CHECKSUMS

URLS["hl7.fhir.us.core-6.1.0.tgz"]="https://packages.fhir.org/hl7.fhir.us.core/6.1.0"
CHECKSUMS["hl7.fhir.us.core-6.1.0.tgz"]=""   # fill in after first verified download

URLS["hl7.fhir.us.davinci-pas-2.0.1.tgz"]="https://packages.fhir.org/hl7.fhir.us.davinci-pas/2.0.1"
CHECKSUMS["hl7.fhir.us.davinci-pas-2.0.1.tgz"]=""   # fill in after first verified download

for FILE in "${!URLS[@]}"; do
    DEST="${IGS_DIR}/${FILE}"
    if [[ -f "${DEST}" ]]; then
        echo "[skip] ${FILE} already present"
        continue
    fi
    echo "[fetch] ${FILE} ..."
    curl -fSL "${URLS[$FILE]}" -o "${DEST}"
    echo "[ok]   ${FILE}"
done

echo "All IGs present in ${IGS_DIR}"
