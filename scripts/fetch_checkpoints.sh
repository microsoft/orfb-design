#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

# Fetch and stage the model checkpoints the orfb-design Docker build bakes in.
#
# The graphormer and retrochimera server images run real CPU inference and
# expect their checkpoints staged into the Docker build context under
# ``model-assets/`` (git-ignored) so the Dockerfiles can ``COPY`` them into the
# image. This script is the single, reproducible way to populate that directory.
#
#   model-assets/
#     graphormer/
#       reduction_checkpoint_best.pt
#       oxidation_checkpoint_best.pt
#     retrochimera/
#       pistachio/            (unpacked RetroChimera model directory)
#
# Graphormer artifacts are downloaded from a pinned public Hugging Face
# revision and verified against their LFS SHA-256 values. Caller-supplied local
# paths remain available as optional overrides. The RetroChimera Pistachio
# checkpoint is downloaded from the public upstream Figshare release and
# verified against its published MD5.
#
# Usage:
#   scripts/fetch_checkpoints.sh all          # stage everything (default)
#   scripts/fetch_checkpoints.sh graphormer   # public Hugging Face artifacts
#   scripts/fetch_checkpoints.sh retrochimera # public Figshare artifact only
#   FORCE=1 scripts/fetch_checkpoints.sh all  # re-download even if present
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment)
# ---------------------------------------------------------------------------
COMPONENT="${1:-all}"
if [ "$#" -gt 1 ]; then
  printf 'Usage: %s [all|graphormer|retrochimera]\n' "$0" >&2
  exit 2
fi
case "${COMPONENT}" in
  all | graphormer | retrochimera) ;;
  *)
    printf 'Usage: %s [all|graphormer|retrochimera]\n' "$0" >&2
    exit 2
    ;;
esac

REDUCTION_CKPT="reduction_checkpoint_best.pt"
OXIDATION_CKPT="oxidation_checkpoint_best.pt"
REDUCTION_SOURCE="${GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE:-}"
OXIDATION_SOURCE="${GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE:-}"
GRAPHORMER_HF_REVISION="${GRAPHORMER_HF_REVISION:-83946163d6575dd35a6a030d9bea7460e0bc2252}"
GRAPHORMER_HF_BASE_URL="https://huggingface.co/microsoft/Graphormer/resolve/${GRAPHORMER_HF_REVISION}/orfb-design/checkpoints"
REDUCTION_REMOTE="graphormer_reduction.pt"
OXIDATION_REMOTE="graphormer_oxidation.pt"
REDUCTION_URL="${GRAPHORMER_REDUCTION_CHECKPOINT_URL:-${GRAPHORMER_HF_BASE_URL}/${REDUCTION_REMOTE}}"
OXIDATION_URL="${GRAPHORMER_OXIDATION_CHECKPOINT_URL:-${GRAPHORMER_HF_BASE_URL}/${OXIDATION_REMOTE}}"
REDUCTION_SHA256="${GRAPHORMER_REDUCTION_CHECKPOINT_SHA256:-8893ba5b4de6dd541f59a070e517119f9828073f227bbe5082e25ea6d8e3bc8a}"
OXIDATION_SHA256="${GRAPHORMER_OXIDATION_CHECKPOINT_SHA256:-2961e45c906a177c398aa61b9c3b2d28259e88e1f88aae787e77e8b72f21c8f5}"
RETRO_ZIP="retrochimera_pistachio.zip"
RETRO_FIGSHARE_FILE_ID="59468882"
RETRO_FIGSHARE_DOI="10.6084/m9.figshare.30591107.v1"
RETRO_URL="${RETROCHIMERA_CHECKPOINT_URL:-https://ndownloader.figshare.com/files/${RETRO_FIGSHARE_FILE_ID}}"
RETRO_MD5="${RETROCHIMERA_CHECKPOINT_MD5:-50406d29b96b165a68fef73fa31448e3}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS_DIR="${ORFB_MODEL_ASSETS_DIR:-${REPO_ROOT}/model-assets}"
GRAPHORMER_DIR="${ASSETS_DIR}/graphormer"
RETRO_DIR="${ASSETS_DIR}/retrochimera"
RETRO_MODEL_DIR="${RETRO_DIR}/pistachio"
CACHE_DIR="${ORFB_CHECKPOINT_CACHE_DIR:-${REPO_ROOT}/.cache/checkpoints}"

FORCE="${FORCE:-0}"

log() { printf '[fetch-checkpoints] %s\n' "$*"; }
die() { printf '[fetch-checkpoints] ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
if [ "${COMPONENT}" = "all" ] || [ "${COMPONENT}" = "graphormer" ] \
  || [ "${COMPONENT}" = "retrochimera" ]; then
  command -v curl >/dev/null 2>&1 || die "'curl' is not installed."
fi
if [ "${COMPONENT}" = "all" ] || [ "${COMPONENT}" = "graphormer" ]; then
  command -v sha256sum >/dev/null 2>&1 || die "'sha256sum' is not installed."
fi
if [ "${COMPONENT}" = "all" ] || [ "${COMPONENT}" = "retrochimera" ]; then
  command -v md5sum >/dev/null 2>&1 || die "'md5sum' is not installed."
  command -v unzip >/dev/null 2>&1 || die "'unzip' is not installed."
fi

mkdir -p "${GRAPHORMER_DIR}" "${RETRO_DIR}" "${CACHE_DIR}"

# stage_local <label> <source> <dest> <source-env-name>
stage_local() {
  local label="$1" source="$2" dest="$3" source_env="$4"
  local partial

  if [ "${FORCE}" != "1" ] && [ -s "${dest}" ]; then
    if [ -z "${source}" ]; then
      log "skip ${label} (already staged)"
      return 0
    fi
    [ -f "${source}" ] || die "${source_env} does not point to a file: ${source}"
    if cmp --silent "${source}" "${dest}"; then
      log "skip ${label} (already staged, contents match)"
      return 0
    fi
  fi

  [ -n "${source}" ] || die "set ${source_env} to the local ${label} checkpoint"
  [ -f "${source}" ] || die "${source_env} does not point to a file: ${source}"
  [ -s "${source}" ] || die "${source_env} points to an empty file: ${source}"

  partial="${dest}.part"
  rm -f "${partial}"
  log "copying ${label} checkpoint -> ${dest}"
  cp --reflink=auto "${source}" "${partial}"
  mv "${partial}" "${dest}"
}

# verify_sha256 <file> <expected>
verify_sha256() {
  local file="$1" expected="$2" actual
  actual="$(sha256sum "${file}" | awk '{print $1}')"
  [ "${actual}" = "${expected}" ]
}

# download_http_sha256 <url> <dest> <expected-sha256>
download_http_sha256() {
  local url="$1" dest="$2" expected_sha256="$3"
  local partial="${dest}.part"

  if [ "${FORCE}" != "1" ] && [ -f "${dest}" ]; then
    if verify_sha256 "${dest}" "${expected_sha256}"; then
      log "skip $(basename "${dest}") (checksum verified)"
      return 0
    fi
    log "re-downloading $(basename "${dest}") (checksum mismatch)"
    rm -f "${dest}"
  fi

  if [ "${FORCE}" = "1" ]; then
    rm -f "${dest}" "${partial}"
  fi

  log "downloading ${url} -> ${dest}"
  curl --fail --location --retry 3 --retry-delay 5 \
    --continue-at - --output "${partial}" "${url}"

  if ! verify_sha256 "${partial}" "${expected_sha256}"; then
    rm -f "${partial}"
    die "checksum mismatch for $(basename "${dest}"); expected SHA-256 ${expected_sha256}"
  fi
  mv "${partial}" "${dest}"
}

# stage_graphormer <label> <local-source> <url> <sha256> <cache-name> <dest>
stage_graphormer() {
  local label="$1" source="$2" url="$3" expected_sha256="$4" cache_name="$5" dest="$6"
  local cached="${CACHE_DIR}/${cache_name}"

  if [ -n "${source}" ]; then
    stage_local "${label}" "${source}" "${dest}" \
      "GRAPHORMER_${label^^}_CHECKPOINT_SOURCE"
    return
  fi

  if [ "${FORCE}" != "1" ] && [ -f "${dest}" ] \
    && verify_sha256 "${dest}" "${expected_sha256}"; then
    log "skip ${label} (already staged, checksum verified)"
    return
  fi

  download_http_sha256 "${url}" "${cached}" "${expected_sha256}"
  stage_local "${label}" "${cached}" "${dest}" \
    "GRAPHORMER_${label^^}_CHECKPOINT_SOURCE"
}

# verify_md5 <file> <expected>
verify_md5() {
  local file="$1" expected="$2" actual
  actual="$(md5sum "${file}" | awk '{print $1}')"
  [ "${actual}" = "${expected}" ]
}

# download_http <url> <dest> <expected-md5>
download_http() {
  local url="$1" dest="$2" expected_md5="$3"
  local partial="${dest}.part"

  if [ "${FORCE}" != "1" ] && [ -f "${dest}" ]; then
    if verify_md5 "${dest}" "${expected_md5}"; then
      log "skip $(basename "${dest}") (checksum verified)"
      return 0
    fi
    log "re-downloading $(basename "${dest}") (checksum mismatch)"
    rm -f "${dest}"
  fi

  if [ "${FORCE}" = "1" ]; then
    rm -f "${dest}" "${partial}"
  fi

  log "downloading ${url} -> ${dest}"
  curl --fail --location --retry 3 --retry-delay 5 \
    --continue-at - --output "${partial}" "${url}"

  if ! verify_md5 "${partial}" "${expected_md5}"; then
    rm -f "${partial}"
    die "checksum mismatch for $(basename "${dest}"); expected MD5 ${expected_md5}"
  fi
  mv "${partial}" "${dest}"
}

# ---------------------------------------------------------------------------
# Graphormer redox checkpoints
# ---------------------------------------------------------------------------
if [ "${COMPONENT}" = "all" ] || [ "${COMPONENT}" = "graphormer" ]; then
  log "== graphormer redox checkpoints (pinned Hugging Face release) =="
  stage_graphormer "reduction" "${REDUCTION_SOURCE}" "${REDUCTION_URL}" \
    "${REDUCTION_SHA256}" "${REDUCTION_REMOTE}" "${GRAPHORMER_DIR}/${REDUCTION_CKPT}"
  stage_graphormer "oxidation" "${OXIDATION_SOURCE}" "${OXIDATION_URL}" \
    "${OXIDATION_SHA256}" "${OXIDATION_REMOTE}" "${GRAPHORMER_DIR}/${OXIDATION_CKPT}"
fi

# ---------------------------------------------------------------------------
# RetroChimera Pistachio model directory (public upstream Figshare release)
# ---------------------------------------------------------------------------
if [ "${COMPONENT}" = "all" ] || [ "${COMPONENT}" = "retrochimera" ]; then
  log "== retrochimera pistachio checkpoint (public Figshare release) =="
  if [ "${FORCE}" != "1" ] \
    && [ -f "${RETRO_MODEL_DIR}/models.json" ] \
    && [ -f "${RETRO_MODEL_DIR}/smiles_transformer/combined.ckpt" ] \
    && [ -f "${RETRO_MODEL_DIR}/template_localization/combined.ckpt" ]; then
    log "skip ${RETRO_ZIP} (already unpacked at ${RETRO_MODEL_DIR})"
  else
    download_http "${RETRO_URL}" "${CACHE_DIR}/${RETRO_ZIP}" "${RETRO_MD5}"

    log "unpacking ${RETRO_ZIP} -> ${RETRO_MODEL_DIR}"
    tmp_extract="$(mktemp -d "${CACHE_DIR}/pistachio.XXXXXX")"
    unzip -q -o "${CACHE_DIR}/${RETRO_ZIP}" -d "${tmp_extract}"

    # Normalize layout: the model files must land directly under
    # model-assets/retrochimera/pistachio/. If the archive wraps everything in
    # one top-level folder, unwrap it.
    shopt -s nullglob
    entries=("${tmp_extract}"/*)
    shopt -u nullglob
    candidate="${tmp_extract}"
    if [ "${#entries[@]}" -eq 1 ] && [ -d "${entries[0]}" ]; then
      candidate="${entries[0]}"
    fi

    [ -f "${candidate}/models.json" ] \
      || die "${RETRO_ZIP} does not contain models.json at the expected level"
    [ -f "${candidate}/smiles_transformer/combined.ckpt" ] \
      || die "${RETRO_ZIP} is missing smiles_transformer/combined.ckpt"
    [ -f "${candidate}/template_localization/combined.ckpt" ] \
      || die "${RETRO_ZIP} is missing template_localization/combined.ckpt"

    rm -rf "${RETRO_MODEL_DIR}"
    mv "${candidate}" "${RETRO_MODEL_DIR}"
    if [ -d "${tmp_extract}" ]; then
      rm -rf "${tmp_extract}"
    fi

    cat >"${RETRO_MODEL_DIR}/checkpoint-source.txt" <<EOF
source=${RETRO_URL}
figshare_file_id=${RETRO_FIGSHARE_FILE_ID}
doi=${RETRO_FIGSHARE_DOI}
md5=${RETRO_MD5}
EOF
    log "retrochimera model staged: $(ls -1 "${RETRO_MODEL_DIR}" | wc -l) entries"
  fi
fi

log "done. requested checkpoint assets are staged."
