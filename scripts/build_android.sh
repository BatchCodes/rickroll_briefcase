#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
ANDROID_DIR="${REPO_DIR}/android"
BUILD_IMAGE="briefcase-android-build"
GRADLE_CACHE="${BRIEFCASE_GRADLE_CACHE:-${HOME}/.cache/briefcase-gradle}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") debug|release [OUTPUT]

Build the Briefcase Android app in Docker. You need only Docker.

  debug    run the unit tests and build a debug APK (signed with a debug key)
  release  run the unit tests and build a release APK. Set these variables
           first: BRIEFCASE_KEYSTORE_FILE (path to the .jks file),
           BRIEFCASE_KEYSTORE_PASSWORD, BRIEFCASE_KEY_ALIAS and
           BRIEFCASE_KEY_PASSWORD. BRIEFCASE_VERSION_NAME (for example 0.2.0)
           and BRIEFCASE_VERSION_CODE (a whole number that increases with
           each release) are optional
  OUTPUT   copy the APK to this path, for example dist/briefcase.apk
USAGE
}

run_gradle() {
  local -a docker_args=(
    --rm
    --user "$(id -u):$(id -g)"
    -e HOME=/tmp
    -e GRADLE_USER_HOME=/cache/gradle
    -v "${ANDROID_DIR}:/work"
    -v "${GRADLE_CACHE}:/cache/gradle"
  )
  local name

  for name in BRIEFCASE_VERSION_NAME BRIEFCASE_VERSION_CODE BRIEFCASE_KEYSTORE_PASSWORD BRIEFCASE_KEY_ALIAS BRIEFCASE_KEY_PASSWORD; do
    if [[ -n "${!name:-}" ]]; then
      docker_args+=(-e "${name}")
    fi
  done
  if [[ -n "${BRIEFCASE_KEYSTORE_FILE:-}" ]]; then
    docker_args+=(
      -v "$(realpath "${BRIEFCASE_KEYSTORE_FILE}"):/keystore/release.jks:ro"
      -e BRIEFCASE_KEYSTORE_FILE=/keystore/release.jks
    )
  fi

  docker run "${docker_args[@]}" "${BUILD_IMAGE}" ./gradlew --no-daemon "$@"
}

check_release_variables() {
  local name
  local missing=0

  for name in BRIEFCASE_KEYSTORE_FILE BRIEFCASE_KEYSTORE_PASSWORD BRIEFCASE_KEY_ALIAS BRIEFCASE_KEY_PASSWORD; do
    if [[ -z "${!name:-}" ]]; then
      printf 'error: %s is not set. A release APK needs the release key, so that updates install over the old app.\n' "${name}" >&2
      missing=1
    fi
  done
  return "${missing}"
}

main() {
  local build_type="${1:-}"
  local output="${2:-}"
  local apk

  case "${build_type}" in
    debug)
      apk="${ANDROID_DIR}/app/build/outputs/apk/debug/app-debug.apk"
      ;;
    release)
      check_release_variables
      apk="${ANDROID_DIR}/app/build/outputs/apk/release/app-release.apk"
      ;;
    *)
      usage
      return 1
      ;;
  esac

  mkdir -p "${GRADLE_CACHE}"
  docker build --quiet --tag "${BUILD_IMAGE}" "${ANDROID_DIR}" >/dev/null

  if [[ "${build_type}" == "debug" ]]; then
    run_gradle testDebugUnitTest assembleDebug
  else
    run_gradle testReleaseUnitTest assembleRelease
  fi

  if [[ ! -f "${apk}" ]]; then
    printf 'error: the build did not make %s.\n' "${apk}" >&2
    return 1
  fi
  if [[ -n "${output}" ]]; then
    mkdir -p "$(dirname -- "${output}")"
    cp "${apk}" "${output}"
    apk="${output}"
  fi
  printf 'APK: %s\n' "${apk}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
