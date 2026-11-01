#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
DEVICE_MODEL_FILE="/proc/device-tree/model"
ENV_FILE="${REPO_DIR}/.env"
BOOT_DIR="/boot/firmware"
CONFIG_TXT="${BOOT_DIR}/config.txt"
CMDLINE_TXT="${BOOT_DIR}/cmdline.txt"
DRM_SYS_DIR="/sys/class/drm"
ASOUND_CARDS_FILE="/proc/asound/cards"
DEFAULT_HDMI_CONNECTOR="HDMI-A-1"
HDMI_MODE="1920x1080@60D"
SERVICE_NAME="rickroll-briefcase"
POWER_SWITCH_PIN=3
POWER_LATCH_PIN=26
KNOB_CLK_PIN=22
KNOB_DT_PIN=23
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
HOTSPOT_COMMAND="/usr/local/bin/briefcase-hotspot"
UPDATE_SERVICE_NAME="rickroll-briefcase-update"
UPDATE_SERVICE_FILE="/etc/systemd/system/${UPDATE_SERVICE_NAME}.service"
UPDATE_PATH_FILE="/etc/systemd/system/${UPDATE_SERVICE_NAME}.path"
HOTSPOT_CONNECTION="briefcase-hotspot"
POLKIT_RULE="/etc/polkit-1/rules.d/50-rickroll-briefcase.rules"
DNSMASQ_SHARED_CONF="/etc/NetworkManager/dnsmasq-shared.d/rickroll-briefcase.conf"
FRIENDLY_NAME="briefcase.lan"
DEFAULT_IMAGE_OWNER="batchcodes"
HOTSPOT_ADDRESS="10.42.0.1"
DOCKER_INSTALL_URL="https://get.docker.com"
# Tools for maintenance over SSH: tmux, Neovim and magic-wormhole (file copy).
TOOL_PACKAGES=(tmux neovim magic-wormhole)
CONFIG_BEGIN="# rickroll_briefcase begin"
CONFIG_END="# rickroll_briefcase end"
CMDLINE_PARAMS=(
  "consoleblank=0"
  "logo.nologo"
  "quiet"
  "loglevel=3"
  "vt.global_cursor_default=0"
)
# Without a kernel console on HDMI, the screen can turn off while the lid is
# closed. drm_client_lib is in kernel 6.15 and newer, drm_kms_helper in older ones.
SCREEN_OFF_PARAMS=(
  "drm_client_lib.active=none"
  "drm_kms_helper.fbdev_emulation=0"
)

usage() {
  cat <<USAGE
Usage: sudo $(basename "$0") [options]

Set up a Raspberry Pi (Raspberry Pi OS Lite, 64-bit) as a Rickroll Briefcase.
The script is safe to run again.

  --ssid NAME          Wi-Fi network name, for example BRIEFCASE (default)
  --password TEXT      WPA2 password, 8 to 63 characters, for example 'never-gonna-9'
                       (the script asks for it if you do not give it)
  --country CODE       Wi-Fi country code, for example DE or GB
  --no-hotspot         do not make the Wi-Fi access point (--hotspot: make it)
  --power-save         turn off Bluetooth and the board LEDs to decrease power
                       (--no-power-save: keep them on)
  --keep-console       keep the login prompt on the HDMI screen. The screen then
                       does not turn off while the lid is closed
                       (--hide-console: remove it)
  --no-tools           do not install the maintenance tools (tmux, nvim and
                       magic-wormhole) (--tools: install them)
  --non-interactive    never ask a question. Fail if an answer is necessary,
                       for example the Wi-Fi password of a new access point
  --power-switch       use a power switch on GPIO 3 (pin 5) to ground: "off"
                       shuts the Pi down cleanly, "on" wakes the halted Pi.
                       Use this before the power latch hardware is fitted
  --power-latch        as --power-switch, and the Pi also signals the power
                       latch on GPIO 26 (pin 37) at the end of a shutdown, so
                       the latch can disconnect the power
  --no-power-switch    remove the power switch configuration
  --knob               use a KY-040 video selector knob: CLK on GPIO 22 (pin 15),
                       DT on GPIO 23 (pin 16), + on 3.3 V (pin 17), GND (pin 20)
  --no-knob            remove the knob configuration
  --lid-closed-when-high
                       for a lid sensor that is open (off) when the magnet is
                       near, so the GPIO pin is high when the lid is closed
  --lid-closed-when-low
                       for a lid sensor that is closed (on) when the magnet is
                       near (the default wiring)
  --image-tag TAG      the image version to download, for example 0.1.0,
                       sha-3f2a1c9 or latest (default: latest)
  --build              build the images on the Pi instead of downloading them
                       (slow: approximately 10 to 20 minutes on a Pi 4)
                       (--no-build: download them)
  -h, --help           show this help

The script stores the options in .env. A later run without an option uses
the stored value. An existing access point keeps its password, unless you
give --password.

The access point starts at the next boot. If you use SSH over Wi-Fi now, the
Pi leaves that network at the next boot. Connect to the briefcase network then.
USAGE
}

parse_args() {
  # Empty means "not given": resolve_options uses the stored value or the default.
  SSID=""
  PASSWORD=""
  COUNTRY=""
  MAKE_HOTSPOT=""
  POWER_SAVE=""
  KEEP_CONSOLE=""
  INSTALL_TOOLS=""
  BUILD_LOCALLY=""
  NON_INTERACTIVE=0
  IMAGE_TAG="latest"
  POWER_MODE=""
  LID_CLOSED_WHEN_LOW=""
  KNOB_MODE=""

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
      --hotspot)
        MAKE_HOTSPOT=1
        shift
        ;;
      --no-tools)
        INSTALL_TOOLS=0
        shift
        ;;
      --tools)
        INSTALL_TOOLS=1
        shift
        ;;
      --power-save)
        POWER_SAVE=1
        shift
        ;;
      --no-power-save)
        POWER_SAVE=0
        shift
        ;;
      --keep-console)
        KEEP_CONSOLE=1
        shift
        ;;
      --hide-console)
        KEEP_CONSOLE=0
        shift
        ;;
      --build)
        BUILD_LOCALLY=1
        shift
        ;;
      --no-build)
        BUILD_LOCALLY=0
        shift
        ;;
      --non-interactive)
        NON_INTERACTIVE=1
        shift
        ;;
      --power-switch)
        POWER_MODE="switch"
        shift
        ;;
      --power-latch)
        POWER_MODE="latch"
        shift
        ;;
      --knob)
        KNOB_MODE="on"
        shift
        ;;
      --no-knob)
        KNOB_MODE="off"
        shift
        ;;
      --lid-closed-when-high)
        LID_CLOSED_WHEN_LOW="false"
        shift
        ;;
      --lid-closed-when-low)
        LID_CLOSED_WHEN_LOW="true"
        shift
        ;;
      --no-power-switch)
        POWER_MODE="none"
        shift
        ;;
      --image-tag)
        IMAGE_TAG="$2"
        shift 2
        ;;
      --image-tag=*)
        IMAGE_TAG="${1#*=}"
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

stored_value() {
  local key="$1"

  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi
  sed -n "s/^${key}=//p" "${ENV_FILE}" | tail -n 1
}

resolve_options() {
  SSID="${SSID:-$(stored_value BRIEFCASE_SETUP_SSID)}"
  SSID="${SSID:-BRIEFCASE}"
  COUNTRY="${COUNTRY:-$(stored_value BRIEFCASE_SETUP_COUNTRY)}"
  MAKE_HOTSPOT="${MAKE_HOTSPOT:-$(stored_value BRIEFCASE_SETUP_HOTSPOT)}"
  MAKE_HOTSPOT="${MAKE_HOTSPOT:-1}"
  POWER_SAVE="${POWER_SAVE:-$(stored_value BRIEFCASE_SETUP_POWER_SAVE)}"
  POWER_SAVE="${POWER_SAVE:-0}"
  KEEP_CONSOLE="${KEEP_CONSOLE:-$(stored_value BRIEFCASE_SETUP_KEEP_CONSOLE)}"
  KEEP_CONSOLE="${KEEP_CONSOLE:-0}"
  INSTALL_TOOLS="${INSTALL_TOOLS:-$(stored_value BRIEFCASE_SETUP_TOOLS)}"
  INSTALL_TOOLS="${INSTALL_TOOLS:-1}"
  BUILD_LOCALLY="${BUILD_LOCALLY:-$(stored_value BRIEFCASE_SETUP_BUILD)}"
  BUILD_LOCALLY="${BUILD_LOCALLY:-0}"
}

store_options() {
  set_env_value BRIEFCASE_SETUP_SSID "${SSID}"
  set_env_value BRIEFCASE_SETUP_COUNTRY "${COUNTRY}"
  set_env_value BRIEFCASE_SETUP_HOTSPOT "${MAKE_HOTSPOT}"
  set_env_value BRIEFCASE_SETUP_POWER_SAVE "${POWER_SAVE}"
  set_env_value BRIEFCASE_SETUP_KEEP_CONSOLE "${KEEP_CONSOLE}"
  set_env_value BRIEFCASE_SETUP_TOOLS "${INSTALL_TOOLS}"
  set_env_value BRIEFCASE_SETUP_BUILD "${BUILD_LOCALLY}"
}

hotspot_exists() {
  if ! command -v nmcli >/dev/null 2>&1; then
    return 1
  fi
  nmcli -t -f NAME connection show | grep -qx "${HOTSPOT_CONNECTION}"
}

read_password() {
  if [[ "${MAKE_HOTSPOT}" -eq 0 ]] || [[ -n "${PASSWORD}" ]]; then
    return 0
  fi
  if hotspot_exists; then
    return 0
  fi
  if [[ "${NON_INTERACTIVE}" -eq 1 ]]; then
    printf 'error: there is no access point yet, so the script needs a Wi-Fi password. Give it with --password.\n' >&2
    exit 1
  fi

  if [[ ! -r /dev/tty ]]; then
    printf 'error: there is no terminal for the password prompt. Give the password with --password.\n' >&2
    exit 1
  fi

  while true; do
    read -r -s -p "Wi-Fi password for ${SSID} (8 to 63 characters, for example never-gonna-9): " PASSWORD </dev/tty
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
  if [[ -z "${PASSWORD}" ]] && hotspot_exists; then
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

install_tools() {
  if [[ "${INSTALL_TOOLS}" -eq 0 ]]; then
    return
  fi
  log_step "Maintenance tools"
  apt-get update
  apt-get install -y "${TOOL_PACKAGES[@]}"
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

is_pi5_or_later() {
  local model=""

  if [[ -r "${DEVICE_MODEL_FILE}" ]]; then
    model="$(tr -d '\0' <"${DEVICE_MODEL_FILE}")"
  fi
  [[ "${model}" =~ Raspberry\ Pi\ ([5-9]|[1-9][0-9]) ]]
}

check_power_mode() {
  if [[ "${POWER_MODE}" != "switch" ]]; then
    return 0
  fi
  if ! is_pi5_or_later; then
    return 0
  fi
  printf 'error: --power-switch does not work on a Raspberry Pi 5. A Pi 5 does not wake from halt on GPIO 3, so the switch could shut the Pi down but not start it again. Use --power-latch when the power latch is fitted, or use --no-power-switch.\n' >&2
  exit 1
}

resolve_power_mode() {
  local stored_mode=""

  if [[ -n "${POWER_MODE}" ]]; then
    return 0
  fi
  if [[ -f "${ENV_FILE}" ]]; then
    stored_mode="$(sed -n 's/^BRIEFCASE_POWER_MODE=//p' "${ENV_FILE}" | tail -n 1)"
  fi
  POWER_MODE="${stored_mode:-none}"
}

write_env() {
  log_step "Environment file"
  "${SCRIPT_DIR}/write_env.sh"
  set_env_value BRIEFCASE_INPUT_BACKEND gpio
  set_env_value BRIEFCASE_PLAYER_OUTPUT drm
  set_env_value BRIEFCASE_HTTP_PORT 80
  set_env_value BRIEFCASE_PLAYER_EXTRA_ARGS "$(hdmi_player_args)"
  set_env_value BRIEFCASE_POWER_MODE "${POWER_MODE}"
  set_display_backend
  if [[ "${KNOB_MODE}" == "on" ]]; then
    set_env_value BRIEFCASE_KNOB_CLK_PIN "${KNOB_CLK_PIN}"
    set_env_value BRIEFCASE_KNOB_DT_PIN "${KNOB_DT_PIN}"
  elif [[ "${KNOB_MODE}" == "off" ]]; then
    set_env_value BRIEFCASE_KNOB_CLK_PIN ""
    set_env_value BRIEFCASE_KNOB_DT_PIN ""
  fi
  if [[ -n "${LID_CLOSED_WHEN_LOW}" ]]; then
    set_env_value BRIEFCASE_LID_CLOSED_WHEN_LOW "${LID_CLOSED_WHEN_LOW}"
  fi
  if [[ "${POWER_MODE}" == "none" ]]; then
    set_env_value BRIEFCASE_POWER_SWITCH_PIN ""
  else
    set_env_value BRIEFCASE_POWER_SWITCH_PIN "${POWER_SWITCH_PIN}"
  fi
  choose_images
}

set_display_backend() {
  local current_backend=""

  if [[ -f "${ENV_FILE}" ]]; then
    current_backend="$(sed -n 's/^BRIEFCASE_DISPLAY_BACKEND=//p' "${ENV_FILE}" | tail -n 1)"
  fi
  # Keep a "command" backend that the user set by hand.
  if [[ "${current_backend}" == "command" ]]; then
    return 0
  fi
  # The player backend turns the screen off while the lid is closed. It needs the
  # HDMI console off, so it does not work with --keep-console.
  if [[ "${KEEP_CONSOLE}" -eq 1 ]]; then
    set_env_value BRIEFCASE_DISPLAY_BACKEND none
  else
    set_env_value BRIEFCASE_DISPLAY_BACKEND player
  fi
}

image_owner() {
  local remote_url
  local owner

  if ! command -v git >/dev/null 2>&1; then
    return 1
  fi
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
  local owner="${DEFAULT_IMAGE_OWNER}"
  local remote_owner

  if [[ "${BUILD_LOCALLY}" -eq 1 ]]; then
    if [[ ! -f "${REPO_DIR}/controller/Dockerfile" ]] || [[ ! -f "${REPO_DIR}/compose.build.yml" ]]; then
      printf 'error: --build needs the complete source, but this is a normal install. Use full_install.sh instead.\n' >&2
      exit 1
    fi
    set_env_value COMPOSE_FILE "${REPO_DIR}/compose.yml:${REPO_DIR}/compose.build.yml"
    printf 'The Pi builds the images itself.\n'
    return 0
  fi

  if remote_owner="$(image_owner)"; then
    owner="${remote_owner}"
  fi
  set_env_value BRIEFCASE_IMAGE_OWNER "${owner}"
  set_env_value BRIEFCASE_VERSION "${IMAGE_TAG}"
  set_env_value COMPOSE_FILE "${REPO_DIR}/compose.yml"
  printf 'The Pi downloads the images ghcr.io/%s/...:%s.\n' "${owner}" "${IMAGE_TAG}"
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

connected_hdmi_connector() {
  local status_file
  local connector_dir
  local connector_name

  for status_file in "${DRM_SYS_DIR}"/card*-HDMI-A-*/status; do
    if [[ ! -f "${status_file}" ]] || [[ "$(cat "${status_file}")" != "connected" ]]; then
      continue
    fi
    connector_dir="$(dirname -- "${status_file}")"
    # A port that cmdline.txt forces on reports "connected" with no monitor, but it has no EDID.
    if [[ "$(wc -c <"${connector_dir}/edid" 2>/dev/null || printf '0')" -eq 0 ]]; then
      continue
    fi
    connector_name="$(basename -- "${connector_dir}")"
    printf '%s\n' "${connector_name#card*-}"
    return 0
  done
  return 1
}

choose_hdmi_connector() {
  local forced_connector=""

  log_step "HDMI port"
  if HDMI_CONNECTOR="$(connected_hdmi_connector)"; then
    printf 'The screen is on %s.\n' "${HDMI_CONNECTOR}"
    return 0
  fi

  if [[ -f "${CMDLINE_TXT}" ]]; then
    forced_connector="$(grep -o 'video=HDMI-A-[0-9]*' "${CMDLINE_TXT}" | head -n 1 || true)"
  fi
  HDMI_CONNECTOR="${forced_connector#video=}"
  HDMI_CONNECTOR="${HDMI_CONNECTOR:-${DEFAULT_HDMI_CONNECTOR}}"
  printf 'warning: no screen answers on an HDMI port, so the player uses %s. Connect the screen and run this script again to find its port.\n' "${HDMI_CONNECTOR}" >&2
}

hdmi_audio_card() {
  local wanted_card
  local card_names

  # HDMI-A-1 is HDMI 0 with the sound card vc4hdmi0, HDMI-A-2 is HDMI 1 with vc4hdmi1.
  wanted_card="vc4hdmi$((${HDMI_CONNECTOR##*-} - 1))"
  card_names="$(awk -F'[][]' '/vc4hdmi/ { gsub(/ /, "", $2); print $2 }' "${ASOUND_CARDS_FILE}" 2>/dev/null || true)"
  if grep -qx -- "${wanted_card}" <<<"${card_names}"; then
    printf '%s\n' "${wanted_card}"
    return 0
  fi
  # A Pi with one HDMI port has a single card, for example vc4hdmi.
  head -n 1 <<<"${card_names}"
}

hdmi_player_args() {
  local card_name

  card_name="$(hdmi_audio_card)"
  if [[ -z "${card_name}" ]]; then
    printf -- '--drm-connector=%s\n' "${HDMI_CONNECTOR}"
    return 0
  fi
  printf -- '--drm-connector=%s --audio-device=alsa/sysdefault:CARD=%s\n' "${HDMI_CONNECTOR}" "${card_name}"
}

configure_boot() {
  local block
  local -a wanted_params
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
  if [[ "${POWER_MODE}" != "none" ]]; then
    block+="
dtparam=i2c_arm=off"
  fi
  if [[ "${POWER_MODE}" == "latch" ]]; then
    block+="
dtoverlay=gpio-poweroff,gpiopin=${POWER_LATCH_PIN}"
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

  # Remove the forced mode of an earlier port, so that only one port reports "connected".
  sed -i -E '1 s/ ?video=HDMI-A-[0-9]+:[^ ]*//g' "${CMDLINE_TXT}"
  wanted_params=("${CMDLINE_PARAMS[@]}" "video=${HDMI_CONNECTOR}:${HDMI_MODE}")
  if [[ "${KEEP_CONSOLE}" -eq 1 ]]; then
    for param in "${SCREEN_OFF_PARAMS[@]}"; do
      sed -i "1 s/ ${param}//g" "${CMDLINE_TXT}"
    done
  else
    wanted_params+=("${SCREEN_OFF_PARAMS[@]}")
  fi
  for param in "${wanted_params[@]}"; do
    if ! grep -qw -- "${param}" "${CMDLINE_TXT}"; then
      sed -i "1 s/\$/ ${param}/" "${CMDLINE_TXT}"
    fi
  done
  printf 'Updated %s and %s.\n' "${CONFIG_TXT}" "${CMDLINE_TXT}"
}

disable_desktop() {
  local default_target

  default_target="$(systemctl get-default 2>/dev/null || true)"
  if [[ "${default_target}" != "graphical.target" ]]; then
    return 0
  fi

  log_step "Desktop"
  printf 'This Pi starts a desktop. The desktop takes the HDMI screen, so the player cannot use it.\n'
  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_boot_behaviour B1
  else
    systemctl set-default multi-user.target
  fi
  printf 'The Pi now starts to the console, without the desktop. The change takes effect at the next boot.\n'
}

configure_console() {
  if [[ "${KEEP_CONSOLE}" -eq 1 ]]; then
    return 0
  fi
  log_step "HDMI console"
  systemctl disable getty@tty1.service
  printf 'The login prompt no longer shows on the HDMI screen. SSH still works.\n'
}

create_hotspot() {
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

  if hotspot_exists; then
    # Keep the existing access point, so that an unattended update needs no
    # password. Apply a new network name or password if one was given.
    nmcli connection modify "${HOTSPOT_CONNECTION}" 802-11-wireless.ssid "${SSID}"
    if [[ -n "${PASSWORD}" ]]; then
      nmcli connection modify "${HOTSPOT_CONNECTION}" wifi-sec.psk "${PASSWORD}"
    fi
    printf 'The access point %s exists. The script kept it.\n' "${SSID}"
  else
    create_hotspot
  fi
  apt-get install -y dnsmasq-base
  install -d -m 0755 "$(dirname -- "${DNSMASQ_SHARED_CONF}")"
  printf 'address=/%s/%s\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}" >"${DNSMASQ_SHARED_CONF}"
  chmod 0644 "${DNSMASQ_SHARED_CONF}"
  printf 'The access point starts at the next boot. Open http://%s or http://%s on it.\n' "${FRIENDLY_NAME}" "${HOTSPOT_ADDRESS}"
}

install_permissions() {
  local power_rule=""

  log_step "Permissions for the controller container"
  if [[ "${POWER_MODE}" != "none" ]]; then
    power_rule="
  // Let the controller power off the Pi when the power switch goes off.
  if ((action.id === \"org.freedesktop.login1.power-off\" ||
       action.id === \"org.freedesktop.login1.power-off-multiple-sessions\") &&
      subject.user === \"${SUDO_USER}\") {
    return polkit.Result.YES;
  }"
  fi
  install -d -m 0755 "$(dirname -- "${POLKIT_RULE}")"
  cat >"${POLKIT_RULE}" <<RULE
polkit.addRule(function (action, subject) {
  // Let the briefcase controller container change the Wi-Fi mode.
  if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
      subject.user === "${SUDO_USER}") {
    return polkit.Result.YES;
  }${power_rule}
});
RULE
  chmod 0644 "${POLKIT_RULE}"
  printf 'The user %s can now control NetworkManager.\n' "${SUDO_USER}"
  if [[ "${POWER_MODE}" != "none" ]]; then
    printf 'The user %s can now power off the Pi.\n' "${SUDO_USER}"
  fi
}

check_wake_setting() {
  local eeprom_config

  if [[ "${POWER_MODE}" != "switch" ]]; then
    return 0
  fi
  log_step "Wake on GPIO 3"
  if ! command -v rpi-eeprom-config >/dev/null 2>&1; then
    printf 'This board has no bootloader EEPROM (for example a Pi Zero 2 W). A halted Pi wakes on GPIO 3 by default.\n'
    return 0
  fi
  eeprom_config="$(rpi-eeprom-config 2>/dev/null || true)"
  if printf '%s\n' "${eeprom_config}" | grep -q '^WAKE_ON_GPIO=0'; then
    printf 'warning: the bootloader setting WAKE_ON_GPIO=0 stops the power switch from waking the Pi. Run "sudo rpi-eeprom-config --edit" and set WAKE_ON_GPIO=1.\n' >&2
  fi
  if printf '%s\n' "${eeprom_config}" | grep -q '^POWER_OFF_ON_HALT=1'; then
    printf 'warning: the bootloader setting POWER_OFF_ON_HALT=1 can stop the power switch from waking the Pi. Run "sudo rpi-eeprom-config --edit" and set POWER_OFF_ON_HALT=0.\n' >&2
  fi
  printf 'The power switch wakes the halted Pi on GPIO 3 (pin 5).\n'
}

install_commands() {
  log_step "Commands"
  ln -sfn "${REPO_DIR}/scripts/hotspot.sh" "${HOTSPOT_COMMAND}"
  printf 'Run briefcase-hotspot to switch the Pi from a known Wi-Fi network back to the hotspot.\n'
}

install_update_units() {
  local owner_group

  log_step "Updates from the web app"
  owner_group="$(id -g "${SUDO_USER}")"
  install -d -o "${SUDO_USER}" -g "${owner_group}" -m 0755 "${REPO_DIR}/data/update"
  cat >"${UPDATE_PATH_FILE}" <<UNIT
[Unit]
Description=Start a Rickroll Briefcase update when the web app asks for one

[Path]
PathExists=${REPO_DIR}/data/update/request.json
Unit=${UPDATE_SERVICE_NAME}.service

[Install]
WantedBy=multi-user.target
UNIT
  cat >"${UPDATE_SERVICE_FILE}" <<UNIT
[Unit]
Description=Update the Rickroll Briefcase software
After=network.target

[Service]
Type=oneshot
ExecStart=${REPO_DIR}/scripts/update.sh
TimeoutStartSec=30min
UNIT
  systemctl daemon-reload
  systemctl enable --now "${UPDATE_SERVICE_NAME}.path"
  printf 'The web app can start updates. Log: journalctl -u %s\n' "${UPDATE_SERVICE_NAME}"
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
  resolve_options
  resolve_power_mode
  check_power_mode
  read_password
  check_password
  install_docker
  install_tools
  add_user_to_groups
  choose_hdmi_connector
  write_env
  store_options
  configure_boot
  disable_desktop
  configure_console
  configure_hotspot
  install_permissions
  check_wake_setting
  install_service
  install_update_units
  install_commands
  start_containers
  print_summary
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
