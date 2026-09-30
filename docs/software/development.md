# Development on a Laptop

You can run the complete briefcase software on a Linux laptop with Docker. You do not need a Raspberry Pi. The laptop mode replaces the reed switch and the arm switch with buttons in the web app. The player shows the video in a window on your desktop.

## Requirements

- Linux with Wayland or X11, and PulseAudio or PipeWire
- Docker with the Compose plugin, version 2.24 or later
- your user in the `docker` group

## Start the Briefcase

1. Write the user and group IDs to `.env`, and make the `data/` directories.

   ```bash
   ./scripts/write_env.sh
   ```

2. Make a test video.

   ```bash
   ./tools/make_test_video.sh
   ```

3. Start the containers.

   ```bash
   docker compose -f compose.yml -f compose.dev.yml up --build
   ```

4. Open <http://localhost:8080>.
5. Push "Open lid". The test video plays from `00:00:30.000` in a window.

Push "Close lid" to stop the video. The player loads the video again, paused at the start position, so that the next "Open lid" is immediate.

## Compose Files

| File               | Use                                                                        |
| ------------------ | -------------------------------------------------------------------------- |
| `compose.yml`      | the Pi system: GPIO inputs and full-screen DRM output                      |
| `compose.dev.yml`  | an override for a laptop: simulated inputs and a desktop window            |
| `compose.test.yml` | the controller tests and linters                                           |

To run without a window, for example on a server, set the player output to `null`:

```bash
BRIEFCASE_PLAYER_OUTPUT=null docker compose -f compose.yml -f compose.dev.yml up --build
```

## Tests

```bash
docker compose -f compose.test.yml run --rm --build test
```

The test container runs `ruff check`, `ruff format --check` and `pytest`. The tests use a fake player and simulated inputs. They do not need a display, a GPIO chip or a network.

To format the code and fix lint problems in place, build the test image first with the command above, then run:

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/controller:/app" -w /app \
  rickroll_briefcase-test sh -c "ruff format . && ruff check --fix ."
```

## Useful Commands

Show the logs:

```bash
docker compose logs -f controller player
```

Restart the player. The controller connects again and loads the video again without user action:

```bash
docker compose restart player
```

Read the status as JSON:

```bash
curl -s http://localhost:8080/api/status
```

## Troubleshooting

| Problem                                   | Cause and fix                                                                                             |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| The player log shows `Failed initializing any suitable GPU context` | The container cannot open `/dev/dri/renderD128`. Run `./scripts/write_env.sh` again, then restart the containers. |
| There is no sound                         | The container cannot find the PulseAudio socket. Make sure that `$XDG_RUNTIME_DIR/pulse/native` exists.   |
| The web app shows "No video"              | `data/videos/` is empty. Run `./tools/make_test_video.sh` or upload a video.                              |
| The web app shows "Player offline"        | The player container does not run. Read `docker compose logs player`.                                     |

## See also

- [Architecture](architecture.md)
- [Configuration](configuration.md)
- [Video tools](../../tools/README.md)
