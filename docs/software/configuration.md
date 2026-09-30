# Briefcase Configuration

The briefcase has two types of configuration:

- **Installation settings** describe the hardware: GPIO pins, user IDs and the display method. They are environment variables in the `.env` file next to `compose.yml`. Change them only when you change the hardware.
- **Playback settings** describe what the briefcase plays. The web app changes them. The controller stores them in `data/config/settings.json`.

## Installation Settings (`.env`)

`scripts/write_env.sh` writes the user and group IDs. You can add the other variables by hand. Restart the containers after a change:

```bash
docker compose up -d
```

| Variable                        | Default              | Description                                                                                          |
| ------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------- |
| `BRIEFCASE_UID`                 | `1000`               | the user ID that the containers use                                                                  |
| `BRIEFCASE_GID`                 | `1000`               | the group ID that the containers use                                                                 |
| `VIDEO_GID`                     | `44`                 | the host `video` group, for `/dev/dri/card*`                                                         |
| `RENDER_GID`                    | `105`                | the host `render` group, for `/dev/dri/renderD*`                                                     |
| `AUDIO_GID`                     | `29`                 | the host `audio` group, for `/dev/snd`                                                               |
| `GPIO_GID`                      | `993`                | the host `gpio` group, for `/dev/gpiochip0`                                                          |
| `COMPOSE_FILE`                  | `compose.yml`        | the Compose files. `install.sh` adds `compose.build.yml` when the Pi builds the images itself        |
| `BRIEFCASE_IMAGE_OWNER`         | `batchcodes` | the GitHub owner of the GHCR images, in lower case. `install.sh` gets it from the git remote         |
| `BRIEFCASE_VERSION`             | `latest`             | the image tag, for example `0.1.0`                                                                   |
| `BRIEFCASE_DATA_DIR`            | `./data`             | the directory for `videos/` and `config/`                                                            |
| `BRIEFCASE_HTTP_PORT`           | `8080`               | the web app port on the host                                                                         |
| `BRIEFCASE_INPUT_BACKEND`       | `gpio`               | `gpio` on a Pi, `simulated` on a laptop                                                              |
| `BRIEFCASE_LID_PIN`             | `17`                 | the BCM GPIO number of the reed switch                                                               |
| `BRIEFCASE_ARM_PIN`             | `27`                 | the BCM GPIO number of the arm switch                                                                |
| `BRIEFCASE_LID_CLOSED_WHEN_LOW` | `true`               | `true` if a low lid pin means "lid closed"                                                           |
| `BRIEFCASE_ARMED_WHEN_LOW`      | `true`               | `true` if a low arm pin means "armed"                                                                |
| `BRIEFCASE_PLAYER_OUTPUT`       | `drm`                | `drm` (full screen on HDMI, no desktop), `window` (a desktop window) or `null` (no picture or sound) |
| `BRIEFCASE_PLAYER_EXTRA_ARGS`   | empty                | more `mpv` options, for example `--audio-device=alsa/hdmi:CARD=vc4hdmi0`                             |
| `BRIEFCASE_DISPLAY_BACKEND`     | `none`               | `none` (the monitor stays on) or `command` (run the commands below)                                  |
| `BRIEFCASE_DISPLAY_ON_COMMAND`  | empty                | the shell command that turns the monitor on, in the controller container                             |
| `BRIEFCASE_DISPLAY_OFF_COMMAND` | empty                | the shell command that turns the monitor off, in the controller container                            |
| `BRIEFCASE_LOG_LEVEL`           | `INFO`               | `DEBUG`, `INFO`, `WARNING` or `ERROR`                                                                |

Both switches connect their GPIO pin to ground when they are closed. The controller uses the internal pull-up resistors. With the default wiring, the lid is closed when the lid pin is low, and the briefcase is armed when the arm pin is low. To invert a switch, set `BRIEFCASE_LID_CLOSED_WHEN_LOW=false` or `BRIEFCASE_ARMED_WHEN_LOW=false` in `.env`.

## Playback Settings (Web App)

Each setting has a default. The briefcase operates correctly with no configuration.

| Setting                | Scope     | Values                                                                                                        | Default                   |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------------- | ------------------------- |
| Video to play          | global    | a video in the library                                                                                        | the first video (by name) |
| Selection mode         | global    | `single` (always the video to play), `cycle` (the next video each time), `shuffle` (a random video each time) | `single`                  |
| Default start position | global    | a time, for example `00:30`                                                                                   | `00:30`                   |
| Volume                 | global    | 0 to 100                                                                                                      | 80                        |
| Start mode             | per video | `fixed`, `beginning`, `random` (one of the cue points), `resume`                                              | `fixed`                   |
| Start position         | per video | a time, or empty for the default start position                                                               | empty                     |
| Cue points             | per video | a list of times, for example `00:30, 01:12`                                                                   | empty                     |
| At the end             | per video | `loop` or `stop` (black screen until the lid closes)                                                          | `loop`                    |

If a start position is after the end of a short video, the video starts at `00:00`.

In the `cycle` and `shuffle` modes, the briefcase changes to the next video when the lid closes. The `shuffle` mode does not play the same video two times in sequence.

The web app button "Reset to defaults" resets all playback settings. It does not delete videos.

## Settings File

`data/config/settings.json` holds the playback settings. The controller writes it atomically: it writes a temporary file, then replaces the old file. A power loss cannot leave a partial file. If the file is damaged, the controller renames it to `settings.json.broken` and uses the defaults.

## See also

- [Architecture](architecture.md)
- [Development](development.md)
