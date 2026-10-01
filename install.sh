#! /bin/bash
set -euo pipefail

REPO_OWNER="BatchCodes"
REPO_NAME="rickroll_briefcase"
DEFAULT_DIR="${HOME}/rickroll_briefcase"
DEFAULT_REF="main"
# The release workflow sets this in the copy of install.sh that it attaches
# to a release, so that the release installer installs its own release.
DEFAULT_VERSION=""
GITHUB_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"
RAW_URL_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main"
SOURCE_ARCHIVE_URL_BASE="${BRIEFCASE_ARCHIVE_URL_BASE:-https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz}"
RELEASE_URL_BASE="${BRIEFCASE_RELEASE_URL_BASE:-${GITHUB_URL}/releases/download}"
KEEP_ENTRIES=(".env" "data")
RUNTIME_FILES=(
  "compose.yml"
  "LICENSE"
  "README.md"
  "scripts/setup.sh"
  "scripts/write_env.sh"
  "scripts/pi_check.sh"
)

usage() {
  cat <<USAGE
Install or update the Rickroll Briefcase on a Raspberry Pi with one command.

Normal install (downloads the ready-made container images):

  curl -fsSL ${RAW_URL_BASE}/install.sh | bash -s -- --country DE

Full install (the complete source, and the Pi builds the images itself):

  curl -fsSL ${RAW_URL_BASE}/full_install.sh | bash -s -- --country DE

What to install:
  (default)        the newest commit on main, with the "latest" images
  --version TAG    a release or pre-release, for example v0.1.0. The script
                   downloads the archives that are attached to the release,
                   and uses the images with the same version
  --ref REF        a commit hash or a branch, for example 3f2a1c9 or main.
                   The script downloads the source archive of that commit. A
                   commit on main uses the images of that commit (sha-<hash>)

Other options for this script:
  --full           install the complete source and build the images on the Pi
  --dir PATH       where to put the files, for example ~/rickroll_briefcase (default)

The script needs no git and no GitHub login. A normal install keeps only the
files that it needs to run the images. A full install keeps everything. Then
the script runs scripts/setup.sh with sudo. On an update, it replaces the
files and keeps .env and data/ (your settings and videos). Run it as your
normal user, not as root.

All other options go to setup.sh, for example --country DE or --power-save.
Refer to scripts/setup.sh --help.
USAGE
}

parse_args() {
  INSTALL_DIR="${DEFAULT_DIR}"
  VERSION="${DEFAULT_VERSION}"
  REF=""
  FULL_INSTALL=0
  SETUP_ARGS=()

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
      --version)
        VERSION="$2"
        shift 2
        ;;
      --version=*)
        VERSION="${1#*=}"
        shift
        ;;
      --ref | --branch)
        REF="$2"
        shift 2
        ;;
      --ref=* | --branch=*)
        REF="${1#*=}"
        shift
        ;;
      --full)
        FULL_INSTALL=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        SETUP_ARGS+=("$1")
        shift
        ;;
    esac
  done

  if [[ -n "${REF}" ]]; then
    VERSION=""
  fi
  if [[ -z "${VERSION}" ]] && [[ -z "${REF}" ]]; then
    REF="${DEFAULT_REF}"
  fi
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

is_commit_hash() {
  [[ "$1" =~ ^[0-9a-f]{7,40}$ ]]
}

kind_name() {
  if [[ "${FULL_INSTALL}" -eq 1 ]]; then
    printf 'full\n'
    return 0
  fi
  printf 'runtime\n'
}

choose_source() {
  local kind

  kind="$(kind_name)"
  if [[ -n "${VERSION}" ]]; then
    ARCHIVE_URL="${RELEASE_URL_BASE}/${VERSION}/${REPO_NAME}-${kind}-${VERSION}.tar.gz"
    ARCHIVE_IS_FILTERED=1
    IMAGE_TAG="${VERSION#v}"
    SOURCE_LABEL="release ${VERSION}, ${kind} archive"
    return 0
  fi

  ARCHIVE_URL="${SOURCE_ARCHIVE_URL_BASE}/${REF}"
  ARCHIVE_IS_FILTERED=0
  SOURCE_LABEL="${REF}, source archive"
  if is_commit_hash "${REF}"; then
    IMAGE_TAG="sha-${REF:0:7}"
    return 0
  fi
  if [[ "${REF}" == "${DEFAULT_REF}" ]]; then
    IMAGE_TAG="latest"
    return 0
  fi

  if [[ "${FULL_INSTALL}" -eq 0 ]]; then
    printf 'error: CI publishes images only for %s, not for the branch %s. Use full_install.sh to build this branch on the Pi.\n' "${DEFAULT_REF}" "${REF}" >&2
    exit 1
  fi
  IMAGE_TAG="latest"
}

unpack_archive() {
  local archive="$1"
  local target="$2"
  local prefix
  local member
  local -a members=()

  prefix="$(tar -tzf "${archive}" | awk -F/ 'NR == 1 { print $1 }')"
  if [[ -z "${prefix}" ]]; then
    printf 'error: the downloaded archive is empty.\n' >&2
    exit 1
  fi

  mkdir -p "${target}"
  if [[ "${FULL_INSTALL}" -eq 1 ]] || [[ "${ARCHIVE_IS_FILTERED}" -eq 1 ]]; then
    tar -xzf "${archive}" -C "${target}" --strip-components=1
    return 0
  fi

  for member in "${RUNTIME_FILES[@]}"; do
    members+=("${prefix}/${member}")
  done
  tar -xzf "${archive}" -C "${target}" --strip-components=1 "${members[@]}"
}

download_files() {
  local entry

  WORK_DIR="$(mktemp -d)"
  trap 'rm -rf "${WORK_DIR}"' EXIT

  printf '==> Downloading %s/%s (%s)\n' "${REPO_OWNER}" "${REPO_NAME}" "${SOURCE_LABEL}"
  if ! curl -fsSL "${ARCHIVE_URL}" -o "${WORK_DIR}/source.tar.gz"; then
    printf 'error: cannot download %s. Check the version or the commit.\n' "${ARCHIVE_URL}" >&2
    exit 1
  fi
  unpack_archive "${WORK_DIR}/source.tar.gz" "${WORK_DIR}/source"

  if [[ ! -f "${WORK_DIR}/source/compose.yml" ]]; then
    printf 'error: the downloaded archive does not contain compose.yml.\n' >&2
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

run_setup() {
  local -a extra_args=("--image-tag" "${IMAGE_TAG}")

  if [[ "${FULL_INSTALL}" -eq 1 ]]; then
    extra_args+=("--build")
  fi

  printf '==> Running the setup\n'
  sudo "${INSTALL_DIR}/scripts/setup.sh" "${extra_args[@]}" "${SETUP_ARGS[@]}"
}

main() {
  parse_args "$@"
  require_system
  check_install_dir
  choose_source
  download_files
  run_setup
}

if [[ "${BRIEFCASE_INSTALL_SOURCED:-0}" != "1" ]]; then
  main "$@"
fi
