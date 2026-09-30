#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
MAX_WIDTH=1920
MAX_HEIGHT=1080
FRAME_RATE=30

# shellcheck source=tools/ffmpeg_lib.sh
source "${SCRIPT_DIR}/ffmpeg_lib.sh"

usage() {
  cat <<USAGE
Usage: $(basename "$0") INPUT [OUTPUT]

Convert a video to a format that every supported Pi plays smoothly:
H.264 High profile, ${MAX_WIDTH}x${MAX_HEIGHT} or smaller, ${FRAME_RATE} fps, AAC stereo audio.

  INPUT   the source video, for example ~/Videos/my_video.mkv
  OUTPUT  the converted file (default: INPUT with the suffix _briefcase.mp4)

The input and the output must be in the same directory or below the current directory.
USAGE
}

transcode() {
  local input_path="$1"
  local output_path="$2"
  local work_dir
  local input_rel
  local output_rel
  local scale_filter

  if [[ ! -f "${input_path}" ]]; then
    printf 'error: the input file %s does not exist.\n' "${input_path}" >&2
    return 1
  fi

  work_dir="$(pwd)"
  input_rel="$(realpath --relative-to="${work_dir}" "${input_path}")"
  output_rel="$(realpath --relative-to="${work_dir}" --canonicalize-missing "${output_path}")"

  if [[ "${input_rel}" == ../* ]] || [[ "${output_rel}" == ../* ]]; then
    printf 'error: the input and the output must be below the current directory, because only this directory is mounted in the container.\n' >&2
    return 1
  fi

  scale_filter="scale=w=${MAX_WIDTH}:h=${MAX_HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2"
  scale_filter+=",fps=${FRAME_RATE}"

  build_tools_image

  run_ffmpeg "${work_dir}" \
    -y \
    -i "/work/${input_rel}" \
    -map 0:v:0 \
    -map 0:a:0? \
    -vf "${scale_filter}" \
    -c:v libx264 \
    -profile:v high \
    -level:v 4.1 \
    -pix_fmt yuv420p \
    -preset medium \
    -crf 20 \
    -c:a aac \
    -b:a 160k \
    -ac 2 \
    -ar 48000 \
    -movflags +faststart \
    "/work/${output_rel}"

  printf 'Converted video written to %s\n' "${output_path}"
}

main() {
  local input_path
  local output_path

  if [[ $# -lt 1 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
    return 0
  fi

  input_path="$1"
  output_path="${2:-${input_path%.*}_briefcase.mp4}"

  transcode "${input_path}" "${output_path}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
