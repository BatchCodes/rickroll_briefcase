#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
UPDATE_SCRIPT="${SCRIPT_DIR}/../update.sh"
FAILURES=0

check() {
  local name="$1"
  local expected="$2"
  local actual="$3"

  if [[ "${expected}" == "${actual}" ]]; then
    printf 'ok: %s\n' "${name}"
    return 0
  fi
  printf 'FAIL: %s: expected %q, got %q\n' "${name}" "${expected}" "${actual}" >&2
  FAILURES=$((FAILURES + 1))
}

main() {
  local releases_json

  # shellcheck source=scripts/update.sh
  source "${UPDATE_SCRIPT}"
  set +e

  WORK_DIR="$(mktemp -d)"
  trap 'rm -rf "${WORK_DIR}"' EXIT
  REPO_DIR="${WORK_DIR}"
  UPDATE_DIR="${WORK_DIR}/data/update"
  REQUEST_FILE="${UPDATE_DIR}/request.json"
  TAKEN_FILE="${UPDATE_DIR}/request.taken.json"
  STATUS_FILE="${UPDATE_DIR}/status.json"
  mkdir -p "${UPDATE_DIR}"

  releases_json='[
    {"tag_name": "v0.3.0", "draft": true, "prerelease": false},
    {"tag_name": "v0.2.0-rc.1", "draft": false, "prerelease": true},
    {"tag_name": "v0.1.0", "draft": false, "prerelease": false}
  ]'
  check "release skips drafts and pre-releases" "v0.1.0" "$(select_tag "${releases_json}" 0)"
  check "prerelease includes pre-releases" "v0.2.0-rc.1" "$(select_tag "${releases_json}" 1)"
  check "no release" "" "$(select_tag '[]' 0)"

  printf '{"target": "main"}' >"${REQUEST_FILE}"
  check "target from the request file" "main" "$(read_target)"
  check "request file is taken" "no" "$([[ -f "${REQUEST_FILE}" ]] && echo yes || echo no)"
  check "default target" "release" "$(read_target)"
  check "argument target" "prerelease" "$(read_target prerelease)"
  check "bad target fails" "1" "$(read_target nightly >/dev/null 2>&1; echo $?)"

  TARGET="release"
  FROM_VERSION="0.1.0"
  TO_VERSION="v0.2.0"
  write_status "installing" "Installing v0.2.0." >/dev/null
  check "status state" "installing" "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["state"])' "${STATUS_FILE}")"
  check "status to version" "v0.2.0" "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["to_version"])' "${STATUS_FILE}")"

  if [[ "${FAILURES}" -ne 0 ]]; then
    printf '%d checks failed.\n' "${FAILURES}" >&2
    return 1
  fi
  printf 'All update checks passed.\n'
}

main "$@"
