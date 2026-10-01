#! /bin/bash
set -euo pipefail

# The release workflow sets this URL to the install.sh of the same release.
INSTALL_SCRIPT_URL="${BRIEFCASE_INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/BatchCodes/rickroll_briefcase/main/install.sh}"

main() {
  local script

  script="$(curl -fsSL "${INSTALL_SCRIPT_URL}")"
  bash -c "${script}" install.sh --full "$@"
}

main "$@"
