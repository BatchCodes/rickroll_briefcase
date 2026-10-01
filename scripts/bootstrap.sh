#! /bin/bash
set -euo pipefail

REPO_OWNER="BatchCodes"
REPO_NAME="rickroll_briefcase"
DEFAULT_DIR="${HOME}/rickroll_briefcase"
DEFAULT_BRANCH="main"
ARCHIVE_URL_BASE="${BRIEFCASE_ARCHIVE_URL_BASE:-https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads}"
KEEP_ENTRIES=(".env" "data")

usage() {
  cat <<USAGE
Install or update the Rickroll Briefcase on a Raspberry Pi with one command:

  curl -fsSL https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/scripts/bootstrap.sh | bash -s -- --country DE

The script downloads the repository as an archive (no git and no GitHub
login), unpacks it, and runs scripts/install.sh with sudo. On an update, it
replaces the files and keeps .env and data/ (your settings and videos).
Run it as your normal user, not as root.

Options for this script:
  --dir PATH      where to put the files, for example ~/rickroll_briefcase (default)
  --branch NAME   the branch to install, for example main (default)

All other options go to install.sh, for example --country DE, --power-save or
--build. Refer to scripts/install.sh --help.
USAGE
}

parse_args() {
  INSTALL_DIR="${DEFAULT_DIR}"
  BRANCH="${DEFAULT_BRANCH}"
  INSTALL_ARGS=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir)
        INSTALL_DIR="$2"
        shift 2
        ;;
      --dir=*)
        INSTALL_DIR="${1#*=}"
        shift
        ;;
      --branch)
        BRANCH="$2"
        shift 2
        ;;
      --branch=*)
        BRANCH="${1#*=}"
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        INSTALL_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

require_system() {
  local command_name

  if [[ "${EUID}" -eq 0 ]]; then
    printf 'error: run this script as your normal user, not with sudo or as root. It asks for sudo when it needs it, and the briefcase runs as your user.\n' >&2
    exit 1
  fi

  for command_name in sudo curl tar; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
      printf 'error: %s is not installed. The installer needs it.\n' "${command_name}" >&2
      exit 1
    fi
  done
}

check_install_dir() {
  if [[ ! -e "${INSTALL_DIR}" ]]; then
    return 0
  fi

  if [[ ! -d "${INSTALL_DIR}" ]]; then
    printf 'error: %s exists and is not a directory. Use --dir with another path.\n' "${INSTALL_DIR}" >&2
    exit 1
  fi

  if [[ -z "$(ls -A "${INSTALL_DIR}")" ]] || [[ -f "${INSTALL_DIR}/compose.yml" ]]; then
    return 0
  fi

  printf 'error: %s exists and does not contain a briefcase installation. Move it, or use --dir with another path.\n' "${INSTALL_DIR}" >&2
  exit 1
}

download_files() {
  local entry

  WORK_DIR="$(mktemp -d)"
  trap 'rm -rf "${WORK_DIR}"' EXIT

  printf '==> Downloading %s/%s (%s)\n' "${REPO_OWNER}" "${REPO_NAME}" "${BRANCH}"
  curl -fsSL "${ARCHIVE_URL_BASE}/${BRANCH}" -o "${WORK_DIR}/source.tar.gz"
  mkdir -p "${WORK_DIR}/source"
  tar -xzf "${WORK_DIR}/source.tar.gz" -C "${WORK_DIR}/source" --strip-components=1

  if [[ ! -f "${WORK_DIR}/source/compose.yml" ]]; then
    printf 'error: the downloaded archive does not contain compose.yml. Check the branch name %s.\n' "${BRANCH}" >&2
    exit 1
  fi

  for entry in "${KEEP_ENTRIES[@]}"; do
    rm -rf "${WORK_DIR:?}/source/${entry}"
  done

  printf '==> Installing the files in %s\n' "${INSTALL_DIR}"
  mkdir -p "${INSTALL_DIR}"
  find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 \
    ! -name .env \
    ! -name data \
    -exec rm -rf {} +
  cp -a "${WORK_DIR}/source/." "${INSTALL_DIR}/"
}

run_installer() {
  printf '==> Running the installer\n'
  sudo "${INSTALL_DIR}/scripts/install.sh" "${INSTALL_ARGS[@]}"
}

main() {
  parse_args "$@"
  require_system
  check_install_dir
  download_files
  run_installer
}

main "$@"
