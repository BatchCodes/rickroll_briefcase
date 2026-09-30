#! /bin/bash

TOOLS_IMAGE="rickroll_briefcase-tools"

build_tools_image() {
  local tools_dir
  tools_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

  if ! command -v docker >/dev/null 2>&1; then
    printf 'error: docker is not installed. The video tools run ffmpeg in a Docker container.\n' >&2
    return 1
  fi

  docker build --quiet --tag "${TOOLS_IMAGE}" "${tools_dir}" >/dev/null
}

run_ffmpeg() {
  local work_dir="$1"
  shift

  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "${work_dir}:/work" \
    "${TOOLS_IMAGE}" \
    "$@"
}
