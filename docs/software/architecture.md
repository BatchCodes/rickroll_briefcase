# Software Architecture

The briefcase software has two Docker containers. They run on Raspberry Pi OS Lite (64-bit) with no desktop.

```text
Raspberry Pi
├── host
│   ├── NetworkManager: Wi-Fi access point "RICKROLL-BRIEFCASE"
│   └── systemd: starts Docker Compose at boot
└── Docker Compose
    ├── player      mpv, full screen on HDMI, HDMI audio, JSON IPC socket
    ├── controller  Python: lid and arm inputs, state machine, web app
    └── volumes     data/videos, data/config, the shared mpv socket
```

## Player

The `player` container runs `mpv` in idle mode. `mpv` writes the picture directly to the HDMI output through DRM and KMS. There is no desktop and no window. `mpv` ignores the keyboard, the mouse and the terminal. It draws no on-screen controls. The controller sends all commands through the JSON IPC socket `/run/briefcase/mpv.sock`, in a volume that both containers share.

## Controller

The `controller` container runs one Python process with these parts:

| Module          | Function                                                                    |
| --------------- | --------------------------------------------------------------------------- |
| `inputs.py`     | reads the reed switch and the arm switch with `gpiozero`, or simulates them |
| `mpv.py`        | the `mpv` IPC client, with automatic reconnection                           |
| `controller.py` | the state machine                                                           |
| `library.py`    | the video files: list, upload, rename, delete and format check              |
| `settings.py`   | the playback settings, their defaults and the atomic settings file          |
| `display.py`    | optional monitor power commands                                             |
| `web.py`        | the FastAPI JSON API and the phone web page                                 |

## Instant Start

A cold start of a video player takes too long for the gag. Thus the controller always keeps the next video loaded in `mpv`, **paused at its start position and muted**. When a person opens the lid, the controller only has to unmute and unpause. When the lid closes, the controller pauses, mutes, and loads the next video again at its start position.

## States

| State            | Meaning                                                                   |
| ---------------- | ------------------------------------------------------------------------- |
| `starting`       | the controller has not finished its first check                           |
| `player_offline` | the controller cannot connect to `mpv`. It tries again each second        |
| `no_video`       | the library is empty                                                      |
| `disarmed`       | the arm switch is off. The video is loaded, but the lid does not start it |
| `ready`          | armed, lid closed, video loaded and paused                                |
| `playing`        | armed and lid open, or a test play from the web app                       |
| `finished`       | the video ended with the `stop` end action. The screen is black           |
| `error`          | a command failed. The controller tries again after 5 s                    |

The video plays when the briefcase is armed **and** the lid is open. At start, the controller reads the positions of both switches. Thus, if the arm switch is on and the lid is open at the end of a boot, the video plays with no user action.

All events (switch changes, player events and web requests) go through one lock, so two transitions never overlap. Each event handler reads the latest switch positions, so switch bounce cannot leave a wrong state.

## Recovery

- If the `mpv` connection breaks, the controller connects again and loads the video again.
- If a command fails, the controller goes into the `error` state and tries again after 5 s.
- Docker restarts a container that stops (`restart: unless-stopped`).
- A power loss cannot damage the settings file, because the controller writes it atomically.

## See also

- [Configuration](configuration.md)
- [Development](development.md)
- [Player notes](player.md)
