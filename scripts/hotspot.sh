#! /bin/bash
set -euo pipefail

HOTSPOT_CONNECTION="briefcase-hotspot"
HOTSPOT_ADDRESS="10.42.0.1"
FRIENDLY_NAME="briefcase.lan"

usage() {
  cat <<USAGE
Usage: briefcase-hotspot

Switch the Pi from a known Wi-Fi network back to the briefcase hotspot.
NetworkManager leaves the other network and starts the hotspot in one step,
so the switch completes even if your SSH connection over Wi-Fi drops.
USAGE
}

active_wifi_connection() {
  nmcli -t -f NAME,TYPE connection show --active |
    awk -F: '$2 == "802-11-wireless" { print $1; exit }'
}

main() {
  local active

  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    return 0
  fi

  if [[ "${EUID}" -ne 0 ]]; then
    exec sudo "$0" "$@"
  fi

  if ! command -v nmcli >/dev/null 2>&1; then
    printf 'error: nmcli is not installed. The hotspot needs NetworkManager.\n' >&2
    return 1
  fi
  if ! nmcli -t -f NAME connection show | grep -qx "${HOTSPOT_CONNECTION}"; then
    printf 'error: the connection %s does not exist. Run scripts/setup.sh to make the hotspot.\n' "${HOTSPOT_CONNECTION}" >&2
    return 1
  fi

  active="$(active_wifi_connection)"
  if [[ "${active}" == "${HOTSPOT_CONNECTION}" ]]; then
    printf 'The hotspot is already on. Open http://%s or http://%s on it.\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}"
    return 0
  fi

  if [[ -n "${active}" ]]; then
    printf 'Leaving the Wi-Fi network %s.\n' "${active}"
  fi
  if [[ -n "${SSH_CONNECTION:-}" ]]; then
    printf 'If this SSH session uses that Wi-Fi network, it stops now. Connect to the briefcase hotspot to continue.\n'
  fi
  nmcli connection up "${HOTSPOT_CONNECTION}" >/dev/null
  printf 'The hotspot is on. Open http://%s or http://%s on it.\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
