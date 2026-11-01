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

ready_uptime() {
  docker compose --project-directory "${REPO_DIR}" logs --no-color controller 2>/dev/null |
    sed -n 's/.*First ready: \([0-9]*\) s after the boot.*/\1/p' |
    tail -n 1
}

print_boot_time() {
  local seconds

  seconds="$(ready_uptime)"
  if [[ -z "${seconds}" ]]; then
    printf 'Boot to ready: the controller log has no "First ready" line yet.\n'
    return 0
  fi
  printf 'Boot to ready: %s s (the Pi uptime when the controller was first ready)\n' "${seconds}"
}

print_throttled() {
  local value
  local flags

  value="$(vcgencmd get_throttled | sed 's/.*=//')"
  printf '  throttled: %s\n' "${value}"
  flags=$((value))
  if (( flags & 0x1 )); then printf '    now: under-voltage\n'; fi
  if (( flags & 0x4 )); then printf '    now: throttled\n'; fi
  if (( flags & 0x10000 )); then printf '    since the boot: under-voltage occurred (the power supply gives too little)\n'; fi
  if (( flags & 0x40000 )); then printf '    since the boot: throttling occurred\n'; fi
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
    print_throttled
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
