#! /bin/bash
set -euo pipefail

# mpv runs this script after it releases the video output. The kernel keeps the
# last mode active, so the monitor would stay awake with a black picture. DPMS
# "off" stops the HDMI signal, and the monitor goes into power saving.

DRM_MODULE="${BRIEFCASE_DRM_MODULE:-vc4}"
DRM_SYS_DIR="/sys/class/drm"
EXTRA_ARGS="${BRIEFCASE_PLAYER_EXTRA_ARGS:-}"
DPMS_OFF=3
ATTEMPTS=30
RETRY_DELAY_SEC=0.1

connector_name() {
  local status_file
  local connector_dir

  if [[ "${EXTRA_ARGS}" =~ --drm-connector=([^[:space:]]+) ]]; then
    printf '%s\n' "${BASH_REMATCH[1]#*.}"
    return 0
  fi
  for status_file in "${DRM_SYS_DIR}"/card*-HDMI-A-*/status; do
    if [[ "$(cat "${status_file}" 2>/dev/null)" != "connected" ]]; then
      continue
    fi
    connector_dir="$(basename -- "$(dirname -- "${status_file}")")"
    printf '%s\n' "${connector_dir#card*-}"
    return 0
  done
  return 1
}

connector_id() {
  local name="$1"

  modetest -M "${DRM_MODULE}" -c 2>/dev/null | awk -v name="${name}" '$4 == name { print $1; exit }'
}

dpms_state() {
  local name="$1"
  local dpms_file

  for dpms_file in "${DRM_SYS_DIR}"/card*-"${name}"/dpms; do
    cat "${dpms_file}" 2>/dev/null
    return 0
  done
}

main() {
  local name
  local id
  local attempt

  if ! name="$(connector_name)"; then
    printf 'error: no connected HDMI port, so there is no screen to turn off.\n' >&2
    return 1
  fi

  # mpv must close the device first. Until then, it is the DRM master, and the
  # DPMS change fails.
  for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
    id="$(connector_id "${name}")"
    if [[ -n "${id}" ]]; then
      modetest -M "${DRM_MODULE}" -w "${id}:DPMS:${DPMS_OFF}" >/dev/null 2>&1 || true
      if [[ "$(dpms_state "${name}")" == "Off" ]]; then
        printf 'The screen on %s is off.\n' "${name}"
        return 0
      fi
    fi
    sleep "${RETRY_DELAY_SEC}"
  done

  printf 'error: could not turn off the screen on %s. Another program may still hold the screen.\n' "${name}" >&2
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
