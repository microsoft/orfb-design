#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${ROOT_DIR}/servers/ezbattery/ezbattery_tools/src/ezbattery_tools/_vendor/EZBattery"
LICENSE_FILE="${ROOT_DIR}/servers/ezbattery/EZBattery.LICENSE"
COMMIT_FILE="${ROOT_DIR}/servers/ezbattery/EZBattery.COMMIT"

EZBATTERY_REPOSITORY="https://github.com/pnnl/EZBattery.git"
EZBATTERY_COMMIT="$(tr -d '[:space:]' < "${COMMIT_FILE}")"
if [[ ! "${EZBATTERY_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Invalid EZBattery commit in ${COMMIT_FILE}: ${EZBATTERY_COMMIT}" >&2
    exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

checkout_dir="${tmp_dir}/repository"
git init --quiet "${checkout_dir}"
git -C "${checkout_dir}" remote add origin "${EZBATTERY_REPOSITORY}"
git -C "${checkout_dir}" sparse-checkout init --cone
git -C "${checkout_dir}" sparse-checkout set EZBattery
git -C "${checkout_dir}" fetch --quiet --depth 1 origin "${EZBATTERY_COMMIT}"

actual_commit="$(git -C "${checkout_dir}" rev-parse FETCH_HEAD)"
if [[ "${actual_commit}" != "${EZBATTERY_COMMIT}" ]]; then
    echo "Expected EZBattery commit ${EZBATTERY_COMMIT}, fetched ${actual_commit}" >&2
    exit 1
fi

git -C "${checkout_dir}" checkout --quiet --detach FETCH_HEAD
test -f "${checkout_dir}/EZBattery/__init__.py"
test -f "${LICENSE_FILE}"

rm -rf "${DEST_DIR}"
mkdir -p "${DEST_DIR}"
cp "${checkout_dir}"/EZBattery/*.py "${DEST_DIR}/"
cp "${LICENSE_FILE}" "${DEST_DIR}/LICENSE"
cp "${COMMIT_FILE}" "${DEST_DIR}/UPSTREAM_COMMIT"

echo "Staged pnnl/EZBattery@${EZBATTERY_COMMIT}"
