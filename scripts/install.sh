#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
ENV_FILE="${REPO_DIR}/.env"
BOOT_DIR="/boot/firmware"
CONFIG_TXT="${BOOT_DIR}/config.txt"
CMDLINE_TXT="${BOOT_DIR}/cmdline.txt"
SERVICE_NAME="rickroll-briefcase"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
HOTSPOT_CONNECTION="briefcase-hotspot"
POLKIT_RULE="/etc/polkit-1/rules.d/50-rickroll-briefcase.rules"
DNSMASQ_SHARED_CONF="/etc/NetworkManager/dnsmasq-shared.d/rickroll-briefcase.conf"
FRIENDLY_NAME="briefcase.lan"
HOTSPOT_ADDRESS="10.42.0.1"
DOCKER_INSTALL_URL="https://get.docker.com"
CONFIG_BEGIN="# rickroll_briefcase begin"
CONFIG_END="# rickroll_briefcase end"
CMDLINE_PARAMS=(
  "video=HDMI-A-1:1920x1080@60D"
  "consoleblank=0"
  "logo.nologo"
  "quiet"
  "loglevel=3"
  "vt.global_cursor_default=0"
)

usage() {
  cat <<USAGE
Usage: sudo $(basename "$0") [options]

Set up a Raspberry Pi (Raspberry Pi OS Lite, 64-bit) as a Rickroll Briefcase.
The script is safe to run again.

  --ssid NAME          Wi-Fi network name, for example RICKROLL-BRIEFCASE (default)
  --password TEXT      WPA2 password, 8 to 63 characters, for example 'never-gonna-9'
                       (the script asks for it if you do not give it)
  --country CODE       Wi-Fi country code, for example DE or GB
  --no-hotspot         do not make the Wi-Fi access point
  --power-save         turn off Bluetooth and the board LEDs to decrease power
  --keep-console       keep the login prompt on the HDMI screen
  --build              build the images on the Pi instead of downloading them
                       (slow: approximately 10 to 20 minutes on a Pi 4)
  -h, --help           show this help

The access point starts at the next boot. If you use SSH over Wi-Fi now, the
Pi leaves that network at the next boot. Connect to the briefcase network then.
USAGE
}

parse_args() {
  SSID="RICKROLL-BRIEFCASE"
  PASSWORD=""
  COUNTRY=""
  MAKE_HOTSPOT=1
  POWER_SAVE=0
  KEEP_CONSOLE=0
  BUILD_LOCALLY=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --ssid)
        SSID="$2"
        shift 2
        ;;
      --ssid=*)
        SSID="${1#*=}"
        shift
        ;;
      --password)
        PASSWORD="$2"
        shift 2
        ;;
      --password=*)
        PASSWORD="${1#*=}"
        shift
        ;;
      --country)
        COUNTRY="$2"
        shift 2
        ;;
      --country=*)
        COUNTRY="${1#*=}"
        shift
        ;;
      --no-hotspot)
        MAKE_HOTSPOT=0
        shift
        ;;
      --power-save)
        POWER_SAVE=1
        shift
        ;;
      --keep-console)
        KEEP_CONSOLE=1
        shift
        ;;
      --build)
        BUILD_LOCALLY=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        printf 'error: unknown argument %s\n' "$1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

log_step() {
  printf '\n==> %s\n' "$1"
}

require_system() {
  if [[ "${EUID}" -ne 0 ]]; then
    printf 'error: run this script with sudo, because it changes system files.\n' >&2
    exit 1
  fi

  if [[ -z "${SUDO_USER:-}" ]] || [[ "${SUDO_USER}" == "root" ]]; then
    printf 'error: run this script with sudo from your normal user, not as root. The containers run as that user.\n' >&2
    exit 1
  fi

  if [[ "$(uname -m)" != "aarch64" ]]; then
    printf 'error: this is not a 64-bit ARM system (uname -m is %s). Install Raspberry Pi OS Lite (64-bit).\n' "$(uname -m)" >&2
    exit 1
  fi

  if [[ ! -f "${CONFIG_TXT}" ]]; then
    printf 'error: %s does not exist. The script needs Raspberry Pi OS Bookworm or later.\n' "${CONFIG_TXT}" >&2
    exit 1
  fi
}

read_password() {
  if [[ "${MAKE_HOTSPOT}" -eq 0 ]] || [[ -n "${PASSWORD}" ]]; then
    return 0
  fi

  while true; do
    read -r -s -p "Wi-Fi password for ${SSID} (8 to 63 characters, for example never-gonna-9): " PASSWORD
    printf '\n'
    if [[ "${#PASSWORD}" -ge 8 ]] && [[ "${#PASSWORD}" -le 63 ]]; then
      return 0
    fi
    printf 'The password must have 8 to 63 characters. Try again.\n'
  done
}

check_password() {
  if [[ "${MAKE_HOTSPOT}" -eq 0 ]]; then
    return 0
  fi
  if [[ "${#PASSWORD}" -lt 8 ]] || [[ "${#PASSWORD}" -gt 63 ]]; then
    printf 'error: the Wi-Fi password must have 8 to 63 characters, because WPA2 requires it.\n' >&2
    exit 1
  fi
}

install_docker() {
  log_step "Docker"
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    printf 'Docker and the Compose plugin are already installed.\n'
  else
    apt-get update
    apt-get install -y curl ca-certificates
    curl -fsSL "${DOCKER_INSTALL_URL}" | sh
  fi
  systemctl enable --now docker
}

add_user_to_groups() {
  local group_name

  log_step "User groups for ${SUDO_USER}"
  for group_name in docker gpio video render audio; do
    if getent group "${group_name}" >/dev/null; then
      usermod -aG "${group_name}" "${SUDO_USER}"
    fi
  done
}

write_env() {
  log_step "Environment file"
  "${SCRIPT_DIR}/write_env.sh"
  set_env_value BRIEFCASE_INPUT_BACKEND gpio
  set_env_value BRIEFCASE_PLAYER_OUTPUT drm
  set_env_value BRIEFCASE_HTTP_PORT 80
  set_env_value BRIEFCASE_PLAYER_EXTRA_ARGS "$(hdmi_audio_args)"
  choose_images
}

image_owner() {
  local remote_url
  local owner

  if ! remote_url="$(git -C "${REPO_DIR}" remote get-url origin 2>/dev/null)"; then
    return 1
  fi
  owner="$(printf '%s\n' "${remote_url}" | sed -nE 's#^(https://|git@)github\.com[:/]([^/]+)/.*#\2#p')"
  if [[ -z "${owner}" ]]; then
    return 1
  fi
  printf '%s\n' "${owner}" | tr '[:upper:]' '[:lower:]'
}

choose_images() {
  local owner

  if [[ "${BUILD_LOCALLY}" -eq 0 ]] && owner="$(image_owner)"; then
    set_env_value BRIEFCASE_IMAGE_OWNER "${owner}"
    set_env_value COMPOSE_FILE "${REPO_DIR}/compose.yml"
    printf 'The Pi downloads the images from ghcr.io/%s.\n' "${owner}"
    return 0
  fi

  if [[ "${BUILD_LOCALLY}" -eq 0 ]]; then
    printf 'The git remote is not on GitHub, so the Pi builds the images itself.\n'
    BUILD_LOCALLY=1
  fi
  set_env_value COMPOSE_FILE "${REPO_DIR}/compose.yml:${REPO_DIR}/compose.build.yml"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local temp_file

  temp_file="$(mktemp)"
  grep -v "^${key}=" "${ENV_FILE}" >"${temp_file}" || true
  printf '%s=%s\n' "${key}" "${value}" >>"${temp_file}"
  install -o "${SUDO_USER}" -g "$(id -g "${SUDO_USER}")" -m 0644 "${temp_file}" "${ENV_FILE}"
  rm -f "${temp_file}"
}

hdmi_audio_args() {
  local card_name

  card_name="$(awk -F'[][]' '/vc4hdmi/ { gsub(/ /, "", $2); print $2; exit }' /proc/asound/cards 2>/dev/null || true)"
  if [[ -z "${card_name}" ]]; then
    printf '\n'
    return 0
  fi
  printf -- '--audio-device=alsa/sysdefault:CARD=%s\n' "${card_name}"
}

configure_boot() {
  local block
  local temp_file
  local param

  log_step "Boot configuration"
  block="${CONFIG_BEGIN}
[all]
disable_splash=1
hdmi_force_hotplug=1
hdmi_drive=2"
  if [[ "${POWER_SAVE}" -eq 1 ]]; then
    block+="
dtoverlay=disable-bt
dtparam=act_led_trigger=none
dtparam=act_led_activelow=off
dtparam=pwr_led_trigger=none
dtparam=pwr_led_activelow=off"
  fi
  block+="
${CONFIG_END}"

  temp_file="$(mktemp)"
  awk -v begin="${CONFIG_BEGIN}" -v end="${CONFIG_END}" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { lines[++count] = $0 }
    END {
      while (count > 0 && lines[count] == "") count--
      for (index_line = 1; index_line <= count; index_line++) print lines[index_line]
    }
  ' "${CONFIG_TXT}" >"${temp_file}"
  printf '\n%s\n' "${block}" >>"${temp_file}"
  install -m 0755 "${temp_file}" "${CONFIG_TXT}"
  rm -f "${temp_file}"

  for param in "${CMDLINE_PARAMS[@]}"; do
    if ! grep -qw -- "${param}" "${CMDLINE_TXT}"; then
      sed -i "1 s/\$/ ${param}/" "${CMDLINE_TXT}"
    fi
  done
  printf 'Updated %s and %s.\n' "${CONFIG_TXT}" "${CMDLINE_TXT}"
}

configure_console() {
  if [[ "${KEEP_CONSOLE}" -eq 1 ]]; then
    return 0
  fi
  log_step "HDMI console"
  systemctl disable getty@tty1.service
  printf 'The login prompt no longer shows on the HDMI screen. SSH still works.\n'
}

configure_hotspot() {
  if [[ "${MAKE_HOTSPOT}" -eq 0 ]]; then
    return 0
  fi
  log_step "Wi-Fi access point ${SSID}"

  if ! command -v nmcli >/dev/null 2>&1; then
    printf 'error: nmcli is not installed. Raspberry Pi OS Bookworm uses NetworkManager. Install it, or use --no-hotspot.\n' >&2
    exit 1
  fi

  if [[ -n "${COUNTRY}" ]]; then
    raspi-config nonint do_wifi_country "${COUNTRY}"
  fi
  rfkill unblock wifi || true

  if nmcli -t -f NAME connection show | grep -qx "${HOTSPOT_CONNECTION}"; then
    nmcli connection delete "${HOTSPOT_CONNECTION}"
  fi

  nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name "${HOTSPOT_CONNECTION}" \
    autoconnect yes \
    ssid "${SSID}" \
    connection.autoconnect-priority 100 \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    ipv6.method disabled \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.pairwise ccmp \
    wifi-sec.psk "${PASSWORD}"
  apt-get install -y dnsmasq-base
  install -d -m 0755 "$(dirname -- "${DNSMASQ_SHARED_CONF}")"
  printf 'address=/%s/%s\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}" >"${DNSMASQ_SHARED_CONF}"
  chmod 0644 "${DNSMASQ_SHARED_CONF}"
  printf 'The access point starts at the next boot. Open http://%s or http://%s on it.\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}"
}

install_network_permission() {
  log_step "Wi-Fi control from the web app"
  install -d -m 0755 "$(dirname -- "${POLKIT_RULE}")"
  cat >"${POLKIT_RULE}" <<RULE
// Let the briefcase controller container change the Wi-Fi mode.
polkit.addRule(function (action, subject) {
  if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
      subject.user === "${SUDO_USER}") {
    return polkit.Result.YES;
  }
});
RULE
  chmod 0644 "${POLKIT_RULE}"
  printf 'The user %s can now control NetworkManager.\n' "${SUDO_USER}"
}

install_service() {
  log_step "Start at boot"
  cat >"${SERVICE_FILE}" <<SERVICE
[Unit]
Description=Rickroll Briefcase containers
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${REPO_DIR}
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
SERVICE
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}.service"
}

start_containers() {
  log_step "Containers"
  if [[ "${BUILD_LOCALLY}" -eq 1 ]]; then
    docker compose --project-directory "${REPO_DIR}" build
  else
    docker compose --project-directory "${REPO_DIR}" pull
  fi
  docker compose --project-directory "${REPO_DIR}" up -d --remove-orphans
}

print_summary() {
  cat <<SUMMARY

The Rickroll Briefcase is installed.

Next steps:
  1. Reboot the Pi: sudo reboot
  2. Connect your phone to the Wi-Fi network ${SSID}.
  3. Open http://${FRIENDLY_NAME} (or http://${HOTSPOT_ADDRESS}) in the phone browser.
  4. Upload a video, then turn on the arm switch.
SUMMARY
}

main() {
  parse_args "$@"
  require_system
  read_password
  check_password
  install_docker
  add_user_to_groups
  write_env
  configure_boot
  configure_console
  configure_hotspot
  install_network_permission
  install_service
  start_containers
  print_summary
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
