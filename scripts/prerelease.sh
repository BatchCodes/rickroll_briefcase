#! /bin/bash
set -euo pipefail

# Make the next pre-release, for example v0.2.0-rc.3. Refer to release.sh --help.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
exec "${SCRIPT_DIR}/release.sh" --pre "$@"
