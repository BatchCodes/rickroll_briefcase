#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
MPV_PROPERTIES=(
  current-vo
  hwdec-current
  current-ao
  audio-device
  video-params
  frame-drop-count
  decoder-frame-drop-count
)

usage() {
  cat <<USAGE
Usage: $(basename "$0")

Print the measurements for the Pi tests in docs/software/player.md:
the boot-to-ready time, the player output and decoder, and the frame drops.
Run it on the Pi after a boot, when the web app shows "Ready".
USAGE
}

boot_epoch() {
  awk '/^btime/ { print $2 }' /proc/stat
}

ready_epoch() {
  local ready_line
  local ready_time

  ready_line="$(docker compose --project-directory "${REPO_DIR}" logs --no-color --timestamps controller 2>/dev/null | grep -m 1 'Ready:' || true)"
  if [[ -z "${ready_line}" ]]; then
    return 1
  fi
  ready_time="$(printf '%s\n' "${ready_line}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z' | head -n 1)"
  date -d "${ready_time}" +%s
}

print_boot_time() {
  local boot
  local ready

  boot="$(boot_epoch)"
  if ! ready="$(ready_epoch)"; then
    printf 'Boot to ready: the controller log has no "Ready:" line yet.\n'
    return 0
  fi
  printf 'Boot to ready: %d s\n' "$((ready - boot))"
}

print_player_properties() {
  local property

  printf '\nPlayer properties:\n'
  for property in "${MPV_PROPERTIES[@]}"; do
    docker compose --project-directory "${REPO_DIR}" exec -T controller python - "${property}" <<'PYTHON'
import json
import socket
import sys

name = sys.argv[1]
client = socket.socket(socket.AF_UNIX)
client.connect("/run/briefcase/mpv.sock")
client.sendall((json.dumps({"command": ["get_property", name], "request_id": 1}) + "\n").encode())
buffer = b""
while True:
    buffer += client.recv(65536)
    for line in buffer.splitlines():
        message = json.loads(line)
        if message.get("request_id") == 1:
            print(f"  {name}: {message.get('data', message.get('error'))}")
            sys.exit(0)
PYTHON
  done
}

print_system() {
  local model="unknown"

  printf '\nSystem:\n'

  if [[ -r /proc/device-tree/model ]]; then
    model="$(tr -d '\0' </proc/device-tree/model)"
  fi
  printf '  model: %s\n' "${model}"
  printf '  kernel: %s\n' "$(uname -r)"
  if command -v vcgencmd >/dev/null 2>&1; then
    printf '  temperature: %s\n' "$(vcgencmd measure_temp)"
    printf '  throttled: %s\n' "$(vcgencmd get_throttled)"
  fi
}

main() {
  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    return 0
  fi
  print_boot_time
  print_player_properties
  print_system
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
