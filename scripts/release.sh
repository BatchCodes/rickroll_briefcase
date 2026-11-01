#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
PYPROJECT="${REPO_DIR}/controller/pyproject.toml"
INIT_FILE="${REPO_DIR}/controller/src/briefcase/__init__.py"
MAIN_BRANCH="main"
REMOTE="origin"
CI_WORKFLOW="ci.yml"
RELEASE_URL_BASE="https://github.com/BatchCodes/rickroll_briefcase/releases/tag"
VERSION_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+$'

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options] [VERSION]

Make a release or a pre-release of the briefcase. The script checks the
repository, sets the version, makes the tag and pushes it after you confirm.
The Images and Release workflows on GitHub then build the images, the APK and
the release files.

  VERSION          the release version, for example 0.2.0 (default: the
                   version in controller/pyproject.toml)
  --pre            make the next pre-release of VERSION, for example
                   v0.2.0-rc.3 after v0.2.0-rc.2
  --dry-run        show the steps, but change nothing
  --yes            do not ask for a confirmation before the push
  --no-ci-check    do not require a successful CI run for the commit
  --watch          follow the Release and Images workflows after the push
  -h, --help       show this help

Examples:
  $(basename "$0") --pre              the next pre-release of the current version
  $(basename "$0") --pre 0.2.0        v0.2.0-rc.1, and set the version to 0.2.0
  $(basename "$0") 0.2.0              the release v0.2.0
USAGE
}

parse_args() {
  VERSION=""
  PRERELEASE=0
  DRY_RUN=0
  ASSUME_YES=0
  CI_CHECK=1
  WATCH=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pre)
        PRERELEASE=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --yes)
        ASSUME_YES=1
        shift
        ;;
      --no-ci-check)
        CI_CHECK=0
        shift
        ;;
      --watch)
        WATCH=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      -*)
        printf 'error: unknown option %s\n' "$1" >&2
        usage >&2
        exit 1
        ;;
      *)
        VERSION="${1#v}"
        shift
        ;;
    esac
  done
}

git_repo() {
  git -C "${REPO_DIR}" "$@"
}

file_version() {
  sed -n 's/^version = "\(.*\)"$/\1/p' "${PYPROJECT}" | head -n 1
}

next_patch() {
  local version="$1"

  printf '%s.%s\n' "${version%.*}" "$((${version##*.} + 1))"
}

tag_exists() {
  git_repo rev-parse -q --verify "refs/tags/$1" >/dev/null
}

next_rc_number() {
  local base="$1"
  local highest

  highest="$(git_repo tag -l "v${base}-rc.*" | sed -n "s/^v${base//./\\.}-rc\.\([0-9]*\)$/\1/p" | sort -n | tail -n 1)"
  printf '%s\n' "$((${highest:-0} + 1))"
}

check_repository() {
  local branch
  local local_head
  local remote_head

  branch="$(git_repo rev-parse --abbrev-ref HEAD)"
  if [[ "${branch}" != "${MAIN_BRANCH}" ]]; then
    printf 'error: you are on the branch %s. Releases come from %s, so switch to it first.\n' "${branch}" "${MAIN_BRANCH}" >&2
    return 1
  fi

  if ! git_repo diff --quiet || ! git_repo diff --cached --quiet; then
    printf 'error: tracked files have uncommitted changes. Commit or stash them first, because the release must match a pushed commit.\n' >&2
    return 1
  fi

  git_repo fetch --quiet --tags "${REMOTE}"
  local_head="$(git_repo rev-parse HEAD)"
  remote_head="$(git_repo rev-parse "${REMOTE}/${MAIN_BRANCH}")"
  if [[ "${local_head}" != "${remote_head}" ]]; then
    printf 'error: your %s differs from %s/%s. Pull or push first, so that the release has the tested commit.\n' "${MAIN_BRANCH}" "${REMOTE}" "${MAIN_BRANCH}" >&2
    return 1
  fi
}

check_ci() {
  local commit="$1"
  local conclusion

  if [[ "${CI_CHECK}" -eq 0 ]]; then
    printf 'CI check: skipped (--no-ci-check).\n'
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    printf 'error: the gh command is not installed, so the script cannot check CI. Install gh, or use --no-ci-check.\n' >&2
    return 1
  fi
  conclusion="$(gh run list --workflow "${CI_WORKFLOW}" --commit "${commit}" --limit 1 --json conclusion --jq '.[0].conclusion // "none"')"
  if [[ "${conclusion}" != "success" ]]; then
    printf 'error: CI for %s is "%s", not "success". Wait for CI, or use --no-ci-check.\n' "${commit:0:7}" "${conclusion:-none}" >&2
    return 1
  fi
  printf 'CI check: success for %s.\n' "${commit:0:7}"
}

set_file_version() {
  local version="$1"

  sed -i "s/^version = \".*\"$/version = \"${version}\"/" "${PYPROJECT}"
  sed -i "s/^__version__ = \".*\"$/__version__ = \"${version}\"/" "${INIT_FILE}"
}

confirm() {
  local answer

  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    return 0
  fi
  read -r -p "Push ${TAG} to ${REMOTE}? This publishes the release. [y/N] (for example y) " answer
  [[ "${answer}" == "y" || "${answer}" == "Y" ]]
}

choose_tag() {
  local current
  local latest_release

  current="$(file_version)"
  VERSION="${VERSION:-${current}}"
  if ! [[ "${VERSION}" =~ ${VERSION_PATTERN} ]]; then
    printf 'error: %s is not a version such as 0.2.0.\n' "${VERSION}" >&2
    return 1
  fi
  if tag_exists "v${VERSION}"; then
    printf 'error: the release v%s exists. Give a newer version, for example: %s %s\n' "${VERSION}" "$(basename "$0")" "$(next_patch "${VERSION}")" >&2
    return 1
  fi

  latest_release="$(git_repo tag -l 'v*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1 || true)"
  if [[ -n "${latest_release}" ]] && [[ "$(printf '%s\nv%s\n' "${latest_release}" "${VERSION}" | sort -V | tail -n 1)" != "v${VERSION}" ]]; then
    printf 'error: v%s is older than the newest release %s.\n' "${VERSION}" "${latest_release}" >&2
    return 1
  fi

  if [[ "${PRERELEASE}" -eq 1 ]]; then
    TAG="v${VERSION}-rc.$(next_rc_number "${VERSION}")"
  else
    TAG="v${VERSION}"
  fi
  NEEDS_VERSION_COMMIT=0
  if [[ "${VERSION}" != "${current}" ]]; then
    NEEDS_VERSION_COMMIT=1
  fi
}

show_plan() {
  printf '\nRelease plan:\n'
  printf '  tag:            %s (%s)\n' "${TAG}" "$([[ "${PRERELEASE}" -eq 1 ]] && printf 'pre-release' || printf 'release')"
  printf '  commit:         %s %s\n' "$(git_repo rev-parse --short HEAD)" "$(git_repo log -1 --format=%s)"
  if [[ "${NEEDS_VERSION_COMMIT}" -eq 1 ]]; then
    printf '  version commit: set the version from %s to %s\n' "$(file_version)" "${VERSION}"
  fi
  printf '  release page:   %s/%s\n\n' "${RELEASE_URL_BASE}" "${TAG}"
}

make_release() {
  if [[ "${NEEDS_VERSION_COMMIT}" -eq 1 ]]; then
    set_file_version "${VERSION}"
    git_repo add "${PYPROJECT}" "${INIT_FILE}"
    git_repo commit -q -m "version: set the briefcase version to ${VERSION}"
  fi
  git_repo tag -a "${TAG}" -m "${TAG}"

  if ! confirm; then
    printf 'Stopped before the push. Undo the local changes with:\n'
    printf '  git tag -d %s\n' "${TAG}"
    if [[ "${NEEDS_VERSION_COMMIT}" -eq 1 ]]; then
      printf '  git reset --hard HEAD~1\n'
    fi
    return 1
  fi

  if [[ "${NEEDS_VERSION_COMMIT}" -eq 1 ]]; then
    git_repo push -q "${REMOTE}" "${MAIN_BRANCH}"
  fi
  git_repo push -q "${REMOTE}" "${TAG}"
  printf 'Pushed %s. GitHub now builds the release: %s/%s\n' "${TAG}" "${RELEASE_URL_BASE}" "${TAG}"
}

watch_workflows() {
  local workflow
  local run_id

  if [[ "${WATCH}" -eq 0 ]]; then
    return 0
  fi
  sleep 10
  for workflow in release.yml images.yml; do
    run_id="$(gh run list --workflow "${workflow}" --branch "${TAG}" --limit 1 --json databaseId --jq '.[0].databaseId')"
    if [[ -z "${run_id}" ]]; then
      printf 'warning: no %s run for %s yet. Check it on GitHub.\n' "${workflow}" "${TAG}" >&2
      continue
    fi
    gh run watch "${run_id}" --exit-status
  done
}

main() {
  parse_args "$@"
  check_repository
  check_ci "$(git_repo rev-parse HEAD)"
  choose_tag
  show_plan
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'Dry run: nothing changed.\n'
    return 0
  fi
  make_release
  watch_workflows
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
