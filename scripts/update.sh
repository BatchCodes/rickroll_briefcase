#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
ENV_FILE="${REPO_DIR}/.env"
UPDATE_DIR="${REPO_DIR}/data/update"
REQUEST_FILE="${UPDATE_DIR}/request.json"
TAKEN_FILE="${UPDATE_DIR}/request.taken.json"
STATUS_FILE="${UPDATE_DIR}/status.json"
HOTSPOT_CONNECTION="briefcase-hotspot"
WIFI_INTERFACE="wlan0"
GITHUB_API="https://api.github.com/repos/BatchCodes/rickroll_briefcase"
RAW_INSTALL_URL="https://raw.githubusercontent.com/BatchCodes/rickroll_briefcase/main/install.sh"
CONNECT_WAIT_SEC=20

usage() {
  cat <<USAGE
Usage: sudo $(basename "$0") [release|prerelease|main]

Update the briefcase software, then go back to the hotspot. The systemd unit
rickroll-briefcase-update.path starts this script when the web app writes
${REQUEST_FILE}. Without an argument, the script reads the target from that
file.

  release     the newest release (default)
  prerelease  the newest release or pre-release
  main        the newest commit on main, with the "latest" images

The script writes its progress to ${STATUS_FILE}. The full log is in the
journal: journalctl -u rickroll-briefcase-update.
USAGE
}

stored_value() {
  local key="$1"

  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi
  sed -n "s/^${key}=//p" "${ENV_FILE}" | tail -n 1
}

owner_name() {
  stat -c %U "${REPO_DIR}"
}

write_status() {
  local state="$1"
  local message="$2"
  local temp_file

  printf 'update: %s: %s\n' "${state}" "${message}"
  install -d -o "$(owner_name)" -m 0755 "${UPDATE_DIR}"
  temp_file="$(mktemp "${UPDATE_DIR}/.status.XXXXXX")"
  STATE="${state}" MESSAGE="${message}" TARGET="${TARGET:-}" \
    FROM_VERSION="${FROM_VERSION:-}" TO_VERSION="${TO_VERSION:-}" \
    STARTED_AT="${STARTED_AT:-}" \
    python3 - >"${temp_file}" <<'PYTHON'
import json
import os
import time

print(json.dumps({
    "state": os.environ["STATE"],
    "message": os.environ["MESSAGE"],
    "target": os.environ["TARGET"],
    "from_version": os.environ["FROM_VERSION"],
    "to_version": os.environ["TO_VERSION"],
    "started_at": os.environ["STARTED_AT"],
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}, indent=2))
PYTHON
  chown "$(owner_name)" "${temp_file}"
  chmod 0644 "${temp_file}"
  mv "${temp_file}" "${STATUS_FILE}"
}

read_target() {
  local requested="${1:-}"

  if [[ -z "${requested}" ]] && [[ -f "${REQUEST_FILE}" ]]; then
    mv "${REQUEST_FILE}" "${TAKEN_FILE}"
    requested="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("target", "release"))' "${TAKEN_FILE}")"
  fi
  case "${requested:-release}" in
    release | prerelease | main)
      printf '%s\n' "${requested:-release}"
      ;;
    *)
      printf 'error: the update target %s is not release, prerelease or main.\n' "${requested}" >&2
      return 1
      ;;
  esac
}

select_tag() {
  local releases_json="$1"
  local include_prereleases="$2"

  INCLUDE_PRERELEASES="${include_prereleases}" python3 -c '
import json
import os
import sys

releases = json.loads(sys.stdin.read())
include = os.environ["INCLUDE_PRERELEASES"] == "1"
for release in releases:
    if release.get("draft"):
        continue
    if release.get("prerelease") and not include:
        continue
    print(release["tag_name"])
    break
' <<<"${releases_json}"
}

has_internet() {
  curl -fsS --max-time 8 -o /dev/null "${GITHUB_API}"
}

known_networks() {
  nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY connection show |
    awk -F: -v hotspot="${HOTSPOT_CONNECTION}" '$2 == "802-11-wireless" && $1 != hotspot { print $3 "\t" $1 }' |
    sort -rn |
    cut -f2
}

connect_to_internet() {
  local name

  if has_internet; then
    return 0
  fi

  write_status "connecting" "Leaving the hotspot to connect to a known Wi-Fi network."
  LEFT_HOTSPOT=1
  nmcli connection down "${HOTSPOT_CONNECTION}" >/dev/null 2>&1 || true
  nmcli device wifi rescan ifname "${WIFI_INTERFACE}" >/dev/null 2>&1 || true
  sleep 3

  while IFS= read -r name; do
    if [[ -z "${name}" ]]; then
      continue
    fi
    printf 'update: trying the Wi-Fi network %s\n' "${name}"
    if ! nmcli --wait "${CONNECT_WAIT_SEC}" connection up "${name}" ifname "${WIFI_INTERFACE}" >/dev/null 2>&1; then
      continue
    fi
    if has_internet; then
      CONNECTED_NETWORK="${name}"
      return 0
    fi
  done < <(known_networks)

  return 1
}

restore_hotspot() {
  if [[ "${LEFT_HOTSPOT:-0}" -eq 0 ]]; then
    return 0
  fi
  if [[ -n "${CONNECTED_NETWORK:-}" ]]; then
    nmcli connection down "${CONNECTED_NETWORK}" >/dev/null 2>&1 || true
  fi
  if ! nmcli connection up "${HOTSPOT_CONNECTION}" >/dev/null 2>&1; then
    printf 'update: warning: the hotspot did not start. It starts at the next boot.\n' >&2
  fi
}

finish() {
  local exit_code=$?

  restore_hotspot
  if [[ "${exit_code}" -ne 0 ]] && [[ "${STATUS_WRITTEN_FINAL:-0}" -eq 0 ]]; then
    write_status "failed" "The update stopped with an error. Read: journalctl -u rickroll-briefcase-update."
  fi
}

run_update() {
  local owner
  local install_url
  local release_json
  local include_prereleases
  local install_script
  local image_tag
  local -a install_args=(--files-only --dir "${REPO_DIR}")

  owner="$(owner_name)"
  FROM_VERSION="$(stored_value BRIEFCASE_VERSION)"
  STARTED_AT="$(date +%Y-%m-%dT%H:%M:%S%z)"
  write_status "starting" "The update starts (target: ${TARGET})."

  trap finish EXIT
  if ! connect_to_internet; then
    STATUS_WRITTEN_FINAL=1
    write_status "failed" "No known Wi-Fi network with internet is in range. Add one on the Wi-Fi tab, or connect an Ethernet cable."
    return 1
  fi

  write_status "checking" "Finding the newest version on GitHub."
  case "${TARGET}" in
    main)
      TO_VERSION="latest"
      install_url="${RAW_INSTALL_URL}"
      install_args+=(--ref main)
      ;;
    release | prerelease)
      release_json="$(curl -fsS --max-time 20 "${GITHUB_API}/releases?per_page=20")"
      include_prereleases=0
      if [[ "${TARGET}" == "prerelease" ]]; then
        include_prereleases=1
      fi
      TO_VERSION="$(select_tag "${release_json}" "${include_prereleases}")"
      if [[ -z "${TO_VERSION}" ]]; then
        STATUS_WRITTEN_FINAL=1
        write_status "failed" "GitHub has no release for the target ${TARGET}."
        return 1
      fi
      if [[ "${TO_VERSION#v}" == "${FROM_VERSION}" ]]; then
        STATUS_WRITTEN_FINAL=1
        write_status "done" "The briefcase already has version ${TO_VERSION}."
        return 0
      fi
      install_url="https://github.com/BatchCodes/rickroll_briefcase/releases/download/${TO_VERSION}/install.sh"
      install_args+=(--version "${TO_VERSION}")
      ;;
  esac
  if [[ "$(stored_value BRIEFCASE_SETUP_BUILD)" == "1" ]]; then
    install_args+=(--full)
  fi

  write_status "downloading" "Downloading the files of ${TO_VERSION}."
  install_script="$(mktemp)"
  curl -fsSL "${install_url}" -o "${install_script}"
  chmod 0755 "${install_script}"
  image_tag="$(runuser -u "${owner}" -- bash "${install_script}" "${install_args[@]}" | sed -n 's/^IMAGE_TAG=//p' | tail -n 1)"
  rm -f "${install_script}"

  write_status "installing" "Installing ${TO_VERSION}. The web app restarts during this step."
  SUDO_USER="${owner}" "${SCRIPT_DIR}/setup.sh" --non-interactive --image-tag "${image_tag:-latest}"

  STATUS_WRITTEN_FINAL=1
  write_status "done" "The briefcase now has version ${TO_VERSION}."
}

main() {
  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    return 0
  fi
  if [[ "${EUID}" -ne 0 ]]; then
    printf 'error: run this script as root, because it changes the network and runs setup.sh.\n' >&2
    return 1
  fi
  TARGET="$(read_target "${1:-}")"
  run_update
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
