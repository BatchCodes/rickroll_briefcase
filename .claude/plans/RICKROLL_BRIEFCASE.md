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

## Phase 5: Pre-Pi Improvements and Wi-Fi Mode

These steps come from a review after phase 3, before the first Pi test.

### Open Questions

- [x] Q6: In client mode, the Pi connects to the Wi-Fi networks that it already knows (NetworkManager connections, for example from Raspberry Pi Imager). Must the web page also let a user add a new network (name and password)? Recommendation: yes, with a "Add a Wi-Fi network" form in the Wi-Fi section. Without it, a user needs SSH or a keyboard to add a network.

### Decisions

- Wi-Fi mode switch (user request) -> a button on the web page, not a physical switch. Rules:
  - The Pi always starts in hotspot mode at boot. Client mode is temporary.
  - In client mode, if no known network connects within 60 s, or the connection drops for 60 s, the Pi goes back to hotspot mode by itself. Thus a user cannot be locked out.
  - In client mode, the web page is at `http://<hostname>.local` on the home network. It has a "Back to hotspot" button.
  - The page shows the current mode, the network name and the address before and after a switch.
- Wi-Fi control -> the controller container controls the host NetworkManager through the system D-Bus socket with `nmcli`. `install.sh` adds a polkit rule that lets the briefcase user control NetworkManager. The web app has no login, so any device on the hotspot can switch the mode. This is the same trust level as upload and delete.
- Arm64 image check -> run the `Images` workflow on GitHub with QEMU, instead of a local build. The workflow also publishes the first images, so the Pi can download them.
- Not now: a shutdown button, video thumbnails. They stay in future work.
- Q6 add-network form -> yes. The user confirmed it. Without the form, a user needs SSH or a keyboard to add a network.

### Implementation Steps

5.1. [x] (bd: rickroll_briefcase-679.16) Fix the Pi set-up path: add `sudo apt install -y git` and the `BatchCodes` clone command to the README, add `video=HDMI-A-1:1920x1080@60D` to the `install.sh` kernel parameters so that the HDMI output is active if the monitor starts late, and add an "Updating" section (Ethernet on a Pi 4, or Wi-Fi client mode from step 5.4).
5.2. [ ] (bd: rickroll_briefcase-679.17) Run the `Images` workflow for `linux/arm64` and `linux/amd64`, fix any build failure, and make the GHCR packages public. Tag `v0.1.0` and write the first release notes.
5.3. [x] (bd: rickroll_briefcase-679.18) Show the playback position in the web app status, and add a "Use current position as start" button for the current video. Add a "Pause" action for test play, so that a user can stop at the correct frame. Add tests.
5.4. [x] (bd: rickroll_briefcase-679.19) Implement the Wi-Fi mode switch: a `network.py` module that runs `nmcli` against the host D-Bus, the 60 s fallback timer, hotspot mode at boot, API endpoints and a Wi-Fi section in the web page with the current mode, network name and address and the add-network form. Mount the D-Bus socket in `compose.yml`, add `network-manager` to the controller image and add the polkit rule to `install.sh`. Use a fake `nmcli` in tests and in laptop mode.
5.5. [x] (bd: rickroll_briefcase-679.20) Small web app items: a friendly address `http://briefcase.lan` through the NetworkManager `dnsmasq-shared.d` configuration, the free SD card space in the video section, multi-file upload, and a note in the README about the Android "no internet" prompt.

## Phase 6: Power Switch and Power Latch

The user re-stated the switch requirements after phase 5. The outside of the briefcase gets two switches, and the lid has the reed switch:

| Switch          | Location                            | Function                                                                                                         |
| --------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Power switch    | outside, usable with the lid closed | turns the Pi and the monitor on and off. "On" can take one to two minutes. "Off" must have a very low power draw |
| Arm switch      | outside, usable with the lid closed | arms the briefcase, as now (GPIO 27)                                                                             |
| Lid reed switch | inside                              | starts the video immediately when a person opens the armed briefcase, as now (GPIO 17)                           |

### Decisions

- Power switch -> a self-holding power latch with a MOSFET power switch. Switch on: the latch turns on the power, the Pi boots and the briefcase is ready. Switch off: the Pi sees the change, shuts down cleanly, then signals the latch, and the latch disconnects the power. The off-state draw is approximately 0.
- Latch part -> the Pololu Big Pushbutton Power Switch MP. It switches the positive supply (high side), operates from 4.5 V to 40 V, carries approximately 8 A, draws approximately 0.01 µA when off, and has `ON`, `OFF` and `CTRL` inputs. Pololu states that the `OFF` input allows "the target device to shut off its own power". Do not use the Mini LV: its documentation does not clearly state the switched side. A low-side switch is not suitable, because the HDMI cable connects the grounds of the Pi and the monitor.
- Test without MOSFETs -> the power switch connects GPIO 3 to ground when it is on. A halted Pi wakes when GPIO 3 goes low. Without the latch hardware, "off" therefore halts the Pi, and "on" wakes it. This has a higher off-state draw, but it tests the full software. When the latch arrives, the same switch and the same software also cut the power.
- Pins -> GPIO 3 (pin 5) for the power switch input, GPIO 26 (pin 37) for the "power off" signal to the latch `OFF` inputs. I2C on GPIO 2 and 3 is turned off.
- Default -> the power switch is off in the software until `.env` enables it, so an installation without a power switch does not change.
- Debounce -> the switch must be off for 2 s before the shutdown starts. Switching it on again in that time cancels the shutdown.

### Candidate parts (Germany)

| Part                                           | Quantity                     | Where                                                                                                                                                                                            | Notes                                                                                                                       |
| ---------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Pololu Big Pushbutton Power Switch MP          | 2 (Pi line and monitor line) | [BerryBase, about 5.30 €](https://www.berrybase.de/en/pololu-big-pushbutton-power-switch-mit-verpolungsschutz-mp) or [Eckstein (Pololu distributor)](https://www.pololu.com/distributors/0J101)  | product page: [pololu.com/product/2812](https://www.pololu.com/product/2812)                                                |
| Pololu USB 2.0 Type-C Connector Breakout Board | 4 (in and out for each line) | [Eckstein, about 5.90 €](https://eckstein-shop.de/PololuUSB20Type-CConnectorBreakoutBoardEN)                                                                                                     | passes CC through unchanged. Do not use a "downstream" breakout with a fixed CC resistor                                    |
| 2-pole toggle switch (DPDT, 2xUM)              | 1                            | for example [musikding.de, about 0.90 €](https://www.musikding.de/Mini-Kippschalter-DPDT-2x-UM) or [henri.de](https://www.henri.de/bauelemente/schalter/kippschalter/miniatur-kippschalter.html) | pole 1: GPIO 3 sense, pole 2: latch `ON` pulse. Do not use an illuminated 230 V switch: its neon lamp does not light at 5 V |
| Capacitor and resistors for the `ON` pulse     | a few                        | any electronics shop, for example [Reichelt](https://www.reichelt.de/)                                                                                                                           | values come from step 6.5                                                                                                   |

### Implementation Steps

6.1. [ ] (bd: none) Power bank test (needs the Anker 737): check whether the Anker turns its USB-C output off at a load near 0, after how long, and whether it turns the output on again without a button press when a load connects again, and when only VBUS returns. Record the results in `docs/hardware/power.md`. The result decides the latch wiring in step 6.5.
6.2. [ ] (bd: none) Power switch software: a power switch input (GPIO 3, enabled by `BRIEFCASE_POWER_SWITCH_PIN`) with the 2 s debounce and cancel, a clean shutdown through the host `logind` over the system D-Bus, the power switch state in the web app status, and a simulated power switch in laptop mode that only logs "would shut down". Add tests.
6.3. [ ] (bd: none) `scripts/setup.sh` option `--power-switch`: turn off I2C on GPIO 2 and 3, add `dtoverlay=gpio-poweroff,gpiopin=26` (the "power off" signal for the latch), check the bootloader `WAKE_ON_GPIO` setting for the halt-and-wake fallback, add a polkit rule for the `logind` power-off action, and write `BRIEFCASE_POWER_SWITCH_PIN=3` to `.env`.
6.4. [ ] (bd: none) Test without the latch: wire only the power switch to GPIO 3 and ground. Measure the time from "on" to "ready", the shutdown time, and the halt power draw with the Anker display. Toggle the switch 20 times. Record the results in `docs/software/player.md`.
6.5. [ ] (bd: none) Latch wiring design and documentation with an SVG diagram in `docs/hardware/wiring.md`: two Pololu switches in the VBUS lines of the Pi and monitor USB-C cables, with CC passed through, the 2-pole power switch (GPIO 3 sense and the RC pulse to the `ON` inputs), and GPIO 26 to both `OFF` inputs. Adapt the design to the step 6.1 result. Add the parts to the parts list.
6.6. [ ] (bd: none) Test with the latch (after the parts arrive): an off-state draw of approximately 0, a clean shutdown before the power cut, the monitor power-up and USB-C PD negotiation after "on", and 20 power cycles. Record the results.

## Phase 7: Future Work

Not started. Candidate items: an ESP32 power controller for a long standby time, a physical video selector, a separate amplifier, a web app PIN or login, a shutdown button, video thumbnails, a read-only root file system (overlay) for safer power loss, and a pre-built SD card image with `pi-gen`.

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
- After the push to `github.com/BatchCodes/rickroll_briefcase`, CI passed on GitHub. The action versions were updated to remove the Node.js 20 warnings. The newer markdownlint added rule MD060 (table alignment). Prettier fixed the table, and `.claude/skills/` is now excluded from markdownlint, because those files come from outside the project.
- Step 5.1 added the "Never Gonna Give You Up" GIF at the top of the README (user request). The README links to the GIF on GIPHY. The repository does not contain the GIF file, because of the copyright rule.
- Step 5.4: the `nmcli` backend was tested read-only against the NetworkManager of the development laptop, through the D-Bus socket from the container. The mode switch was tested only with the simulated backend. The polkit rule and a real switch need the Pi test.
- Step 5.2: the `Images` workflow built and pushed both images for `linux/amd64` and `linux/arm64` on the first run (controller 3 min 27 s, player 4 min 17 s). The computer suspended at midnight, as the user asked, before the `v0.1.0` tag and the package visibility change. GHCR packages are private by default. Only the GitHub web page can make them public.
- Step 5.2: the image workflow tagged `latest` only for a release tag, but the Pi pulls `latest` by default. Each push to `main` now builds the images and tags them `latest`. Both images are public and can be pulled without a login, for `amd64` and `arm64`. The user asked to wait for the Pi test before the `v0.1.0` tag.
- After phase 5, the user asked for a stand-alone repository. All references to other projects were removed from the plan, the rules and the skill examples. The Markdown rule no longer depends on an external skill.
- After phase 5, the user asked for a one-line `curl | bash` install without git. `scripts/bootstrap.sh` downloads the GitHub archive, so it needs no git and no login, and `--build` still works because the archive has the full source. On an update it keeps `.env` and `data/`, and it never moves them. `install.sh` now reads the Wi-Fi password from `/dev/tty`, and it uses the default image owner `batchcodes` when there is no git remote. The script was tested in a Debian container: download, unpack, update with kept data, and the refusal cases.
- The user asked for two installers. `scripts/install.sh` is now `scripts/setup.sh` (the system set-up). `install.sh` at the repository root installs only the runtime files (`compose.yml`, `LICENSE`, `README.md`, `scripts/setup.sh`, `scripts/write_env.sh`, `scripts/pi_check.sh`) and pulls the images. `full_install.sh` runs `install.sh --full`: it installs the complete source and builds the images. Both use the same GitHub archive, so no separate archive needs a release. A container test found that `tar | head` stopped the script under `pipefail`. `awk` now reads the full listing.
- The user asked for release archives and a pre-release. `install.sh` now installs a release (`--version`, or the release copy of the installer with the version built in), a commit (`--ref <hash>`, with the `sha-<hash>` images) or `main` (the `latest` images). `scripts/setup.sh --image-tag` writes the image tag to `.env`. The `Release` workflow attaches the runtime archive, the full archive, both installers and `SHA256SUMS`. All modes were tested in a Debian container with local archives.
- After phase 5, the user re-stated the switch requirements: a power switch and an arm switch outside, and the lid reed switch inside. Phase 6 adds the power switch and the power latch. Part research: the Pololu Big Pushbutton Power Switch MP is high side. The Mini LV documentation does not state the side.
