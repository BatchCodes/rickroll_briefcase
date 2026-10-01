#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
REPO_NAME="rickroll_briefcase"
RELEASE_URL_BASE="https://github.com/BatchCodes/${REPO_NAME}/releases/download"

usage() {
  cat <<USAGE
Usage: $(basename "$0") TAG OUTPUT_DIR

Make the files for a GitHub release from the commit HEAD:

  ${REPO_NAME}-runtime-TAG.tar.gz  the files that a normal install needs
  ${REPO_NAME}-full-TAG.tar.gz     the complete source
  install.sh                       the installer, set to install TAG
  full_install.sh                  the full installer, set to install TAG
  SHA256SUMS                       the checksums of the files above

  TAG         the release tag, for example v0.1.0 or v0.1.0-rc.1
  OUTPUT_DIR  the directory for the files, for example dist
USAGE
}

runtime_files() {
  # shellcheck source=install.sh
  BRIEFCASE_INSTALL_SOURCED=1 source "${REPO_DIR}/install.sh"
  printf '%s\n' "${RUNTIME_FILES[@]}"
}

make_assets() {
  local tag="$1"
  local output_dir="$2"
  local prefix="${REPO_NAME}-${tag}/"
  local -a files=()

  mkdir -p "${output_dir}"
  mapfile -t files < <(runtime_files)

  git -C "${REPO_DIR}" archive \
    --format=tar.gz \
    --prefix="${prefix}" \
    --output="${output_dir}/${REPO_NAME}-full-${tag}.tar.gz" \
    HEAD

  git -C "${REPO_DIR}" archive \
    --format=tar.gz \
    --prefix="${prefix}" \
    --output="${output_dir}/${REPO_NAME}-runtime-${tag}.tar.gz" \
    HEAD \
    "${files[@]}"

  sed "s|^DEFAULT_VERSION=\"\"\$|DEFAULT_VERSION=\"${tag}\"|" \
    "${REPO_DIR}/install.sh" >"${output_dir}/install.sh"
  if ! grep -q "^DEFAULT_VERSION=\"${tag}\"\$" "${output_dir}/install.sh"; then
    printf 'error: cannot set DEFAULT_VERSION in install.sh. The release installer would install main.\n' >&2
    return 1
  fi

  sed "s|raw.githubusercontent.com/BatchCodes/${REPO_NAME}/main/install.sh|github.com/BatchCodes/${REPO_NAME}/releases/download/${tag}/install.sh|" \
    "${REPO_DIR}/full_install.sh" >"${output_dir}/full_install.sh"
  if ! grep -q "${RELEASE_URL_BASE}/${tag}/install.sh" "${output_dir}/full_install.sh"; then
    printf 'error: cannot set the install.sh URL in full_install.sh.\n' >&2
    return 1
  fi
  chmod +x "${output_dir}/install.sh" "${output_dir}/full_install.sh"

  (
    cd "${output_dir}"
    sha256sum ./*.tar.gz install.sh full_install.sh >SHA256SUMS
  )
  printf 'Release files written to %s\n' "${output_dir}"
}

main() {
  if [[ $# -ne 2 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
    return 0
  fi
  make_assets "$1" "$2"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
