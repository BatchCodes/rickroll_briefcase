#! /bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(dirname -- "${SCRIPT_DIR}")"
DEFAULT_OUTPUT="${REPO_DIR}/data/videos/test_pattern.mp4"
DEFAULT_DURATION_SEC=120
FONT_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# shellcheck source=tools/ffmpeg_lib.sh
source "${SCRIPT_DIR}/ffmpeg_lib.sh"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--duration SECONDS] [--output PATH]

Make a 1920x1080, 30 fps H.264 and AAC test video with a visible timecode.
The timecode lets you check the start position of the player.

  --duration SECONDS  length of the video, for example 120 (default: ${DEFAULT_DURATION_SEC})
  --output PATH       output file, for example data/videos/test.mp4
                      (default: data/videos/test_pattern.mp4)
USAGE
}

parse_args() {
  DURATION_SEC="${DEFAULT_DURATION_SEC}"
  OUTPUT_PATH="${DEFAULT_OUTPUT}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --duration)
        DURATION_SEC="$2"
        shift 2
        ;;
      --duration=*)
        DURATION_SEC="${1#*=}"
        shift
        ;;
      --output)
        OUTPUT_PATH="$2"
        shift 2
        ;;
      --output=*)
        OUTPUT_PATH="${1#*=}"
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

  if ! [[ "${DURATION_SEC}" =~ ^[0-9]+$ ]] || [[ "${DURATION_SEC}" -lt 1 ]]; then
    printf 'error: --duration must be a whole number of seconds, for example 120.\n' >&2
    exit 1
  fi
}

make_test_video() {
  local output_dir
  local output_name
  local overlay

  mkdir -p "$(dirname -- "${OUTPUT_PATH}")"
  output_dir="$(cd -- "$(dirname -- "${OUTPUT_PATH}")" && pwd)"
  output_name="$(basename -- "${OUTPUT_PATH}")"

  overlay="drawtext=fontfile=${FONT_PATH}:fontsize=120:fontcolor=white"
  overlay+=":box=1:boxcolor=black@0.6:boxborderw=20"
  overlay+=":x=(w-text_w)/2:y=(h-text_h)/2"
  overlay+=":text='%{pts\\:hms}'"

  build_tools_image

  run_ffmpeg "${output_dir}" \
    -y \
    -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=${DURATION_SEC}" \
    -f lavfi -i "sine=frequency=440:beep_factor=4:duration=${DURATION_SEC}" \
    -vf "${overlay}" \
    -c:v libx264 \
    -profile:v high \
    -level:v 4.1 \
    -pix_fmt yuv420p \
    -preset veryfast \
    -crf 30 \
    -c:a aac \
    -b:a 128k \
    -ar 48000 \
    -movflags +faststart \
    "/work/${output_name}"

  printf 'Test video written to %s\n' "${OUTPUT_PATH}"
}

main() {
  parse_args "$@"
  make_test_video
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
