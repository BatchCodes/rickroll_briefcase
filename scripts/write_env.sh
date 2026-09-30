#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
ENV_FILE="${REPO_DIR}/.env"
DATA_DIR="${REPO_DIR}/data"

usage() {
  cat <<USAGE
Usage: $(basename "$0")

Write the user and group IDs of this computer to .env, and make the data
directories. Docker Compose reads .env. The containers then run as your user
and can open the display, sound and GPIO devices.

Run it once after you clone the repository, on a laptop or on the Pi.
USAGE
}

target_user() {
  if [[ -n "${SUDO_USER:-}" ]] && [[ "${SUDO_USER}" != "root" ]]; then
    printf '%s\n' "${SUDO_USER}"
    return 0
  fi
  id -un
}

group_id() {
  local group_name="$1"
  local fallback="$2"
  local entry

  if ! entry="$(getent group "${group_name}")"; then
    printf '%s\n' "${fallback}"
    return 0
  fi
  printf '%s\n' "${entry}" | cut -d: -f3
}

set_env_value() {
  local key="$1"
  local value="$2"
  local temp_file

  temp_file="$(mktemp)"
  if [[ -f "${ENV_FILE}" ]]; then
    grep -v "^${key}=" "${ENV_FILE}" >"${temp_file}" || true
  fi
  printf '%s=%s\n' "${key}" "${value}" >>"${temp_file}"
  mv "${temp_file}" "${ENV_FILE}"
}

write_env() {
  local user_name
  local user_id
  local group_id_value

  user_name="$(target_user)"
  user_id="$(id -u "${user_name}")"
  group_id_value="$(id -g "${user_name}")"

  set_env_value BRIEFCASE_UID "${user_id}"
  set_env_value BRIEFCASE_GID "${group_id_value}"
  set_env_value VIDEO_GID "$(group_id video 44)"
  set_env_value RENDER_GID "$(group_id render 105)"
  set_env_value AUDIO_GID "$(group_id audio 29)"
  set_env_value GPIO_GID "$(group_id gpio 993)"

  install -d -o "${user_id}" -g "${group_id_value}" \
    "${DATA_DIR}" \
    "${DATA_DIR}/videos" \
    "${DATA_DIR}/config"

  chown "${user_id}:${group_id_value}" "${ENV_FILE}"
  printf 'Wrote %s for the user %s.\n' "${ENV_FILE}" "${user_name}"
}

main() {
  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    return 0
  fi
  write_env
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
