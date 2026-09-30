#! /bin/bash
set -euo pipefail

MPV_SOCKET="${BRIEFCASE_MPV_SOCKET:-/run/briefcase/mpv.sock}"
PLAYER_OUTPUT="${BRIEFCASE_PLAYER_OUTPUT:-drm}"
EXTRA_ARGS="${BRIEFCASE_PLAYER_EXTRA_ARGS:-}"

output_args() {
  case "${PLAYER_OUTPUT}" in
    drm)
      printf '%s\n' \
        --vo=gpu \
        --gpu-context=drm \
        --ao=alsa
      ;;
    window)
      printf '%s\n' \
        --vo=gpu \
        --ao=pulse,alsa,null
      ;;
    null)
      printf '%s\n' \
        --vo=null \
        --ao=null
      ;;
    *)
      printf 'error: BRIEFCASE_PLAYER_OUTPUT must be drm, window or null, not %s.\n' "${PLAYER_OUTPUT}" >&2
      return 1
      ;;
  esac
}

main() {
  local -a mpv_args
  local -a extra_args

  if [[ $# -gt 0 ]]; then
    exec "$@"
  fi

  mkdir -p "$(dirname -- "${MPV_SOCKET}")"
  rm -f "${MPV_SOCKET}"

  mapfile -t mpv_args < <(output_args)
  read -r -a extra_args <<<"${EXTRA_ARGS}"

  exec mpv \
    --input-ipc-server="${MPV_SOCKET}" \
    "${mpv_args[@]}" \
    "${extra_args[@]}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
