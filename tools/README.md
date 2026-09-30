# Video Tools

These scripts make test videos and convert your own videos for the briefcase. They run `ffmpeg` in a Docker container, so you need only Docker. The scripts build the small `rickroll_briefcase-tools` image the first time that you run them.

## Make a Test Video

The repository does not contain copyright videos. Use a generated test video for development and for hardware tests.

```bash
./tools/make_test_video.sh
```

The script writes `data/videos/test_pattern.mp4`. The video shows colour bars, a large timecode and a beep each second. Use the timecode to check that the player starts at the correct start position, for example `00:00:30.000`.

Options:

| Option               | Default                        | Description                        |
| -------------------- | ------------------------------ | ---------------------------------- |
| `--duration SECONDS` | `120`                          | the length of the video in seconds |
| `--output PATH`      | `data/videos/test_pattern.mp4` | the output file                    |

## Convert Your Own Video

Convert each video before you upload it to the briefcase:

```bash
./tools/transcode.sh my_video.mkv
```

The script writes `my_video_briefcase.mp4` next to the input file. The output has these properties:

- H.264 High profile, level 4.1
- 1920×1080 or smaller, with the original aspect ratio
- 30 fps
- AAC stereo audio at 48 kHz

The Pi 4 and the Pi Zero 2 W both decode this format in hardware. The Pi Zero 2 W cannot decode HEVC (H.265). The web app shows a warning if an uploaded video does not match this format.

The input file and the output file must be below the current directory, because the script mounts only the current directory in the container.

## See also

- [README](../README.md)
- [Player notes](../docs/software/player.md)
