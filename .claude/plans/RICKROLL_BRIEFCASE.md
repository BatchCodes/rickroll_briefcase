---
slug: RICKROLL_BRIEFCASE
status: implementing
created: 2026-09-30
epic: rickroll_briefcase-679
---

# Rickroll Briefcase

## Current State

The repository was empty at the start. It contained only a `.claude/` directory with plan skills and some general rules. Step 1.1 removed the plans, rules and settings that are not related to the briefcase. Refer to the Q5 decision.

### Brief

The brief comes from the shared ChatGPT conversation "Build Rickroll Briefcase". The user asked for these features:

- The briefcase plays "Never Gonna Give You Up" when a person opens it.
- It stops immediately when a person closes it.
- It runs on a battery.
- It has a screen of approximately 13 inches, with sound.
- The battery lasts a few hours or more while the case is closed.
- It has an external on/off switch and possibly an external charging port.
- When a person turns it on, it starts playback at 00:30 in the video.
- It can play different videos. A web app on the phone selects the video. There is no physical video selector.

### Hardware decisions from the conversation

| Item                   | Part                                                              | Notes                                                                                                                   |
| ---------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Computer               | Raspberry Pi 4 (2 GB is sufficient)                               | The user has a Pi 4. The conversation dropped the ESP32. The Pi Zero 2 W is a supported lower-power target.             |
| Display                | Kenowa 13.3" 1080p portable monitor, HDMI input, USB-C power      | It has built-in speakers. Test these speakers first.                                                                    |
| Battery                | Anker 737 PowerCore 24K (A1289), 24,000 mAh, approximately 86 Wh  | Two USB-C outputs: one for the Pi, one for the monitor. It has a low-current mode. It is below the 100 Wh flight limit. |
| Lid sensor             | KY-021 reed switch module and a neodymium magnet                  | One GPIO input.                                                                                                         |
| External switch        | Goobay 10013 on/off switch (prototype)                            | It is a GPIO input for "armed" and "disarmed". It is not in the USB-C PD power path.                                    |
| Audio (optional)       | PAM8403 amplifier and 2× 4 Ω 3 W 40 mm speakers                   | Buy these only if the monitor speakers are too weak.                                                                    |
| Cables and prototyping | HDMI cable, 2× USB-C cable, GPIO header, Dupont wires, breadboard | The Pi 4 has micro-HDMI outputs. Use a micro-HDMI to HDMI cable.                                                        |

Estimated power is 10 W to 13 W while the video plays. The usable battery energy is approximately 70 Wh to 75 Wh. Thus the run time is approximately 5 to 7 hours while the video plays. While the case is closed, the Pi idles at approximately 3 W. The monitor can then be off.

### Software decisions from the conversation

- Keep the Pi on while the case is closed. This gives an instant start when a person opens the case.
- Store the videos on the SD card. Do not use YouTube or the internet.
- Keep the video player separate from the briefcase controller. The controller sends a command, for example "play video 3 from 00:30".
- Each video has its own start position.
- The Pi makes its own Wi-Fi access point, `RICKROLL-BRIEFCASE`. A phone connects to it and opens the web app in a browser. No app installation is necessary.
- Encode the videos as 1920×1080 H.264 with AAC audio.

### Legal constraint

The repository must not contain the "Never Gonna Give You Up" video or its audio. The music and video are copyright material. The README must tell users to supply a legally obtained copy. Development and CI use a generated test video (for example, the `ffmpeg` `testsrc` source).

### Technical risks

- Instant start: stopping and starting `mpv` for each lid event is too slow. The better method is to keep `mpv` running with the selected file loaded and paused at the start position. Then an open event only unpauses it. Step 2.2 must confirm this method.
- Display off: with the full KMS driver on Raspberry Pi OS Bookworm, `vcgencmd display_power` does not operate. Some monitors do not go into standby from DPMS. A black screen with the backlight on uses power. Step 2.2 must find a method that works on the Kenowa monitor.
- Docker access to hardware: the player container needs `/dev/dri`, `/dev/snd` and the DRM master. The controller container needs `/dev/gpiochip0`. Step 2.2 must confirm that `mpv --vo=drm` operates in a container.
- Docker start time: Docker adds a few seconds to the boot time. This is not important, because the switch does not cut the power.
- Power bank auto-off: some power banks turn off at a low load. Use the Anker 737 low-current mode, and test it with the case closed.

## Goal

A public, open-source GitHub repository that a stranger can use to build the briefcase. The repository contains the software, the hardware guide and the build instructions. The Pi software runs in Docker containers. A developer can run the full system on a laptop with Docker, without a Pi.

## Architecture

```text
Raspberry Pi 4 (Raspberry Pi OS Lite 64-bit, Docker)
├── host
│   ├── NetworkManager Wi-Fi access point "RICKROLL-BRIEFCASE"
│   └── systemd starts Docker Compose at boot
└── docker compose
    ├── player      mpv, --vo=drm, HDMI audio, JSON IPC socket
    ├── controller  Python: lid GPIO, state machine, FastAPI web app, mpv IPC client
    └── volumes     videos/, config/ (selected video, start positions, volume), shared IPC socket
```

The controller has one hardware abstraction for the lid. The Pi uses `gpiozero` with `lgpio`. The laptop uses a simulated lid, which a button in the web app toggles.

The web app is server-rendered HTML with a small amount of vanilla JavaScript. It has no frontend build step.

### Repository layout

```text
README.md
LICENSE
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
compose.yml              # Pi runtime
compose.dev.yml          # laptop override: simulated lid, windowed mpv
controller/              # Python package, Dockerfile, tests
player/                  # Dockerfile, mpv config, entrypoint
tools/                   # transcode and test-video scripts (run in a Docker ffmpeg image)
scripts/install.sh       # Pi host set-up
docs/hardware/           # parts list, wiring diagram, power, assembly
docs/software/           # architecture, configuration, API
.github/workflows/       # lint, test, multi-arch image build
```

## Open Questions

- [x] Q1: Which licence, which copyright holder name, and which GitHub owner and repository name?
- [x] Q2: What does the external switch do?
- [x] Q3: Which component makes the Wi-Fi access point? Must the web app have a PIN?
- [x] Q4: Which boards must the project support?
- [x] Q5: What happens to `.claude/` in the public repository? Which Python style applies?

## Decisions

- Hardware and software choices from the ChatGPT conversation -> accepted as the baseline. Refer to Current State. The user made these choices in the conversation.
- Video files -> not in the repository, because of copyright. Use generated test videos for development and CI.
- Web app frontend -> server-rendered HTML and vanilla JavaScript, served by FastAPI. This avoids a Node.js build step on the Pi and in CI.
- Player and controller -> two containers from two images, with a shared `mpv` IPC socket. This follows the conversation's separation of the player and the controller.
- Q1 licence -> MIT. The copyright holder is "The rickroll_briefcase contributors". The user had no preference.
- Q1 repository name -> `rickroll_briefcase`. GitHub and GHCR accept underscores. The image paths are `ghcr.io/<owner>/rickroll_briefcase-controller` and `ghcr.io/<owner>/rickroll_briefcase-player`. CI gets `<owner>` from `github.repository_owner`. `compose.yml` reads it from the `BRIEFCASE_IMAGE_OWNER` variable in `.env`. Thus the plan does not need the owner name now.
- Q2 external switch -> option A. The switch is a GPIO input for "armed" and "disarmed". The Pi stays on. When the case is armed and a person opens the lid, the video plays immediately. If a person arms the case while the lid is open, the video plays immediately from the start position. The switch does not cut the power.
- Q3 access point -> the host NetworkManager makes the access point. `scripts/install.sh` configures it. The web app has no PIN or login for now. Interpretation: the Wi-Fi network keeps a WPA2 password, which `install.sh` asks for. An open network lets any person nearby upload or delete videos. Change this decision if you want an open network.
- Q4 boards -> Pi 4 is the primary target and the test board. The Pi Zero 2 W is a supported target for lower power. Both use one `linux/arm64` image on 64-bit Raspberry Pi OS Lite. Rules for the Zero 2 W: use H.264 only (the Zero 2 W has no HEVC decoder), keep 1080p30 or less, keep the memory use of each container small, and document the mini-HDMI and micro-USB power differences. Only the Pi 4 gets hardware tests now.
- Q5 `.claude/` -> keep the `mdbd-plan` and `md-plan` skills and this plan. Remove all plans, rules and settings that are not related to the briefcase. Remove the references to other projects from the rules that stay (Markdown, shell, YAML, JSON).
- Q5 Python style -> PEP 8 with `ruff` (lint and format). Replace `.claude/rules/code-style-python.md` with a PEP 8 rule.
- Multiple videos and start points (user note) -> the web app configures all of these items. Each item has a default, so the briefcase operates correctly with no configuration:

  | Setting                | Scope     | Values                                                         | Default                           |
  | ---------------------- | --------- | -------------------------------------------------------------- | --------------------------------- |
  | Selection mode         | global    | `single` (the armed video), `cycle`, `shuffle`                 | `single`                          |
  | Armed video            | global    | any video in the library                                       | the first video in the library    |
  | Start mode             | per video | `fixed`, `beginning`, `random` (from the cue points), `resume` | `fixed`                           |
  | Start position         | per video | a time, for example `00:30`                                    | the global default start position |
  | Cue points             | per video | a list of times for the `random` start mode                    | empty                             |
  | Default start position | global    | a time                                                         | `00:30`, from the brief           |
  | End of video           | per video | `loop`, `stop` (black screen)                                  | `loop`                            |
  | Volume                 | global    | 0 to 100                                                       | 80                                |

- Zero-touch operation (user note) -> the briefcase is an appliance. No step needs a keyboard, a mouse, a login, a desktop or a window. Rules:
  - The Pi has no desktop. The player writes full screen directly to HDMI with `mpv --vo=drm`. There are no windows to maximise.
  - Arm switch on, while the Pi is on: the briefcase is ready immediately. The video is already loaded and paused.
  - Power applied (cold boot): systemd starts Docker Compose. The controller reads the positions of the arm switch and the lid at start. It then goes into the correct state with no user action. If the switch is on and the lid is open at the end of the boot, the video plays.
  - Crash or power loss: Docker restarts a failed container. The settings file is written atomically, so a power loss does not corrupt it.
  - Target: boot to ready in 30 s or less on a Pi 4. Step 2.2 measures it.
- Uploaded videos -> the controller runs `ffprobe` on each upload. The web app shows a warning if the codec, resolution or frame rate is not suitable for the Pi Zero 2 W. The Pi does not transcode videos, because this is too slow on a Zero 2 W. Users transcode on a laptop with the `tools/` script.

## Phase 1: Open-Source Repository and Development Environment

### Implementation Steps

1.1. [x] (bd: rickroll_briefcase-679.1) Clean `.claude/` according to the Q5 decisions. Replace the Python rule with a PEP 8 and `ruff` rule. Add `.gitignore`, `.editorconfig`, `.dockerignore` and `cspell.json`. Make the first commit.
1.2. [x] (bd: rickroll_briefcase-679.2) Add `LICENSE` (MIT, "The rickroll_briefcase contributors"), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant), `SECURITY.md` and GitHub issue and pull request templates.
1.3. [x] (bd: rickroll_briefcase-679.3) Add the first `README.md`: what the project is, a photo or diagram placeholder, the feature list, the copyright note about the video, a quick start for the laptop and a quick start for the Pi, and links to `docs/`.
1.4. [x] (bd: rickroll_briefcase-679.4) Add `tools/`: a Docker `ffmpeg` script that makes a test video with a visible timecode, and a script that transcodes any user video to 1080p30 H.264 with AAC.

## Phase 2: Briefcase Software

### Implementation Steps

2.1. [x] (bd: rickroll_briefcase-679.5) Make the `controller/` Python package skeleton: `pyproject.toml`, `ruff`, `pytest`, the configuration model (videos directory, config file, lid and arm GPIO pins, and the settings with their defaults from the Decisions table), and the `Dockerfile`.
2.2. [ ] (bd: rickroll_briefcase-679.6) Spike on a real Pi 4: `mpv --vo=drm` in a container with HDMI audio. Measure the time from unpause to the first frame. Find a display-off method that the Kenowa monitor accepts. Measure the cold-boot time from power on to ready with Docker. Record the results in `docs/software/player.md`. If a result invalidates the architecture, stop and add an open question.
2.3. [x] (bd: rickroll_briefcase-679.7) Make the `player/` image: `mpv` with JSON IPC, idle mode, a black background, and an entrypoint that selects full-screen `--vo=drm` on the Pi and a window on a laptop. The Pi path needs no user action.
2.4. [x] (bd: rickroll_briefcase-679.8) Implement the input abstraction for the lid reed switch and the arm switch: `gpiozero` inputs with debounce, and simulated inputs for development. Add unit tests.
2.5. [x] (bd: rickroll_briefcase-679.9) Implement the `mpv` IPC client and the state machine. States: disarmed, armed-closed, playing. On close or disarm: pause, mute, display off, then preload the next video (selection mode) at its start position (start mode). On open while armed, or on arm while open: display on, unmute, unpause. At start, read the current switch and lid positions and go into the matching state. Apply the end-of-video setting. Write the settings file atomically. Add unit tests with a fake `mpv`.
2.6. [x] (bd: rickroll_briefcase-679.10) Implement the FastAPI web app: video library, upload with the `ffprobe` check, rename, delete, test play, all settings in the Decisions table, and the lid and armed status. Store the settings in `config/settings.json`. Add a "reset to defaults" action. Make the page usable on a phone. Add API tests.
2.7. [x] (bd: rickroll_briefcase-679.11) Add `compose.yml` for the Pi and `compose.dev.yml` for a laptop. Health checks, restart policies, device mappings and volumes. Confirm that `docker compose -f compose.yml -f compose.dev.yml up` plays the test video on a laptop and that the web app toggles the simulated lid.

## Phase 3: Pi Deployment and CI

### Implementation Steps

3.1. [x] (bd: rickroll_briefcase-679.12) Write `scripts/install.sh` for Raspberry Pi OS Lite 64-bit: install Docker, add the user to the `docker` and `gpio` groups, configure the NetworkManager Wi-Fi access point with a WPA2 password that the script asks for, set HDMI and audio options in `config.txt`, disable the console login prompt and cursor on the HDMI output, install a systemd unit that starts Docker Compose at boot, and optionally disable Bluetooth and the LEDs to decrease power.
3.2. [x] (bd: rickroll_briefcase-679.13) Add GitHub Actions: `ruff` and `pytest` in Docker, `shellcheck`, a Markdown lint and spell check, and a `docker buildx` build for `linux/arm64` and `linux/amd64`. Push the images to GHCR on a tag.
3.3. [x] (bd: rickroll_briefcase-679.14) Make `compose.yml` pull the GHCR images by default, with a local build as an option. Add release notes and a version tag procedure to `CONTRIBUTING.md`.
3.4. [ ] (bd: rickroll_briefcase-679.15) Acceptance test on the Pi 4: with no keyboard or mouse, remove and apply power, then confirm that the briefcase is ready within the boot target and plays when a person opens the lid. Toggle the arm switch and the lid 20 times. Pull the power during playback and confirm a clean restart. Record the results in `docs/software/player.md`.

## Phase 4: Hardware and Build Guide

### Implementation Steps

4.1. [ ] (bd: none) Write `docs/hardware/parts.md`: the parts list with EU purchase links, approximate prices and optional audio parts.
4.2. [ ] (bd: none) Write `docs/hardware/wiring.md` with an SVG diagram: reed switch to the GPIO pin with its pull-up, the arm switch to a second GPIO pin, USB-C power to the Pi and the monitor, HDMI, the optional amplifier, and an external charging port (panel-mount USB-C extension to the power bank input).
4.3. [ ] (bd: none) Write `docs/hardware/assembly.md` and `docs/hardware/power.md`: the layout in a 13" briefcase, magnet position, mounting, weight, battery-life measurement with the Anker display, the low-current-mode test, and the Pi Zero 2 W differences (mini-HDMI, micro-USB power, H.264 only).
4.4. [ ] (bd: none) Finish `README.md` and `docs/software/`: architecture, configuration reference, API reference, troubleshooting and a "See also" section. Confirm that each document agrees with the code.

## Phase 5: Future Work

Not started. Candidate items: an ESP32 power controller for a long standby time, a physical video selector, a separate amplifier, a web app PIN or login, a read-only root file system (overlay) for safer power loss, and a pre-built SD card image with `pi-gen`.

## Findings

- bd has no database in this repository yet. The first `--implement` call must run `bd init` before it creates the epic.
- The git top level was a parent directory, not this directory. Step 1.1 ran `git init` in this directory to make it a separate repository.
- bd was initialised with the prefix `rickroll_briefcase`. `.beads/` is in `.gitignore`, so the public repository does not contain the private task list.
- The committed `.claude/settings.json` runs `bd prime` only if `bd` and `.beads/` exist, so contributors without bd get no hook error. `settings.local.json` stays local and is ignored by git.
- The README links to the phase 4 hardware documents (`docs/hardware/*.md`). These links stay broken until phase 4 is implemented.
- Step 2.6 uses `mediainfo` instead of `ffprobe` for the upload check. The `mediainfo` package is much smaller than `ffmpeg` in the controller image.
- Step 2.3 uses `mpv --vo=gpu --gpu-context=drm` on the Pi instead of `--vo=drm`. This output supports hardware decoding better. `BRIEFCASE_PLAYER_EXTRA_ARGS` can change it after the spike in step 2.2.
- Step 2.7 found that a failed video load left the controller in a wrong state. The controller now has an `error` state and tries again after 5 s. This supports the zero-touch rule.
- Step 2.7 found that the default start position (00:30) is after the end of a short video. The controller now starts such a video at 00:00.
- Step 2.7 added `scripts/write_env.sh`. It writes the user ID and the `video`, `render`, `audio` and `gpio` group IDs to `.env`, because these IDs differ between computers.
- Step 2.7 also wrote `docs/software/architecture.md`, `configuration.md` and `development.md`, because the README and `CONTRIBUTING.md` link to them. Step 4.4 must still check them.
- Step 3.1: `scripts/install.sh` passes `shellcheck`, and its boot-file edits were tested on copies of `config.txt` and `cmdline.txt`. It has not run on a real Pi yet. Step 3.4 covers this. On the Pi, the web app uses port 80, so the phone address is `http://10.42.0.1`.
- Step 3.2: the workflows were not run on GitHub, because the repository has no remote yet. The same checks pass locally in Docker: tests, `shellcheck`, `markdownlint-cli2`, `cspell` and `scripts/smoke_test.sh`.
- Steps 2.2 and 3.4 stay open, because they need the real Pi 4 and the Kenowa monitor. `docs/software/player.md` has the test procedures and empty results tables. `scripts/pi_check.sh` prints the boot-to-ready time and the player properties.
