#! /bin/bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
TIMEOUT_SEC=30

usage() {
  cat <<USAGE
Usage: $(basename "$0") [BASE_URL]

Check a running briefcase in laptop mode (simulated inputs):
the lid must start and stop the video.

  BASE_URL  the web app address, for example http://localhost:8080 (default)
USAGE
}

state() {
  curl -fsS "${BASE_URL}/api/status" | python3 -c 'import json, sys; print(json.load(sys.stdin)["state"])'
}

simulate() {
  local body="$1"

  curl -fsS \
    -X POST \
    -H 'Content-Type: application/json' \
    -d "${body}" \
    "${BASE_URL}/api/simulate" >/dev/null
}

wait_for_state() {
  local wanted="$1"
  local waited=0
  local current=""

  while [[ "${waited}" -lt "${TIMEOUT_SEC}" ]]; do
    current="$(state || true)"
    if [[ "${current}" == "${wanted}" ]]; then
      printf 'ok: state is %s\n' "${wanted}"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  printf 'error: the state is %s, not %s, after %d s.\n' "${current}" "${wanted}" "${TIMEOUT_SEC}" >&2
  return 1
}

main() {
  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    return 0
  fi

  simulate '{"lid_open": false, "armed": true}'
  wait_for_state ready

  simulate '{"lid_open": true}'
  wait_for_state playing

  simulate '{"lid_open": false}'
  wait_for_state ready

  simulate '{"armed": false, "lid_open": true}'
  wait_for_state disarmed

  simulate '{"armed": true}'
  wait_for_state playing

  simulate '{"lid_open": false}'
  wait_for_state ready

  printf 'The smoke test passed.\n'
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
