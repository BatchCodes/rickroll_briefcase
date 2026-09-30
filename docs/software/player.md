# Player Notes and Pi Tests

This document records the player tests on real Raspberry Pi hardware. The laptop mode cannot test these items: the DRM output in a container, HDMI audio, the display-off method, the boot time and the behaviour after a power loss.

**Status: not tested on a Pi yet.** The results tables below are empty. Fill them in when you do the tests.

## Before the Tests

1. Install the briefcase on the Pi. Refer to the [README](../../README.md).
2. Copy the test video to the Pi.

   ```bash
   ./tools/make_test_video.sh
   scp data/videos/test_pattern.mp4 <user>@<pi-address>:rickroll_briefcase/data/videos/
   ```

3. Connect the monitor, the reed switch and the arm switch.

## Test 1: Player Output

This test checks that `mpv` shows the video full screen on HDMI from a container, with HDMI audio.

1. Turn on the arm switch. Open the lid.
2. Look at the monitor. The video must fill the screen. No desktop, cursor or text must show.
3. Listen. The beep must come from the monitor speakers.
4. Look at the timecode. It must start at `00:00:30.000`.
5. Run the measurement script.

   ```bash
   ./scripts/pi_check.sh
   ```

If there is no picture, try the other DRM output in `.env`, then restart the containers with `docker compose up -d`:

```bash
BRIEFCASE_PLAYER_EXTRA_ARGS=--vo=drm --audio-device=alsa/sysdefault:CARD=vc4hdmi0
```

| Item                               | Result |
| ---------------------------------- | ------ |
| Board and RAM                      |        |
| `current-vo`                       |        |
| `hwdec-current`                    |        |
| `audio-device`                     |        |
| Picture fills the screen           |        |
| Sound from the monitor             |        |
| Frame drops after 60 s of playback |        |

## Test 2: Start Delay

This test measures the time from "lid open" to the first moving frame.

1. Record the monitor and the lid with a phone camera at 60 fps or more.
2. Open the lid 5 times. Close it between each test.
3. In the recording, count the frames from the moment the magnet moves away to the first moving picture. Divide by the frame rate.

| Try     | Delay (ms) |
| ------- | ---------- |
| 1       |            |
| 2       |            |
| 3       |            |
| 4       |            |
| 5       |            |
| Average |            |

A delay of less than 300 ms feels instant.

## Test 3: Display Off

While the lid is closed, the monitor shows a paused frame and its backlight stays on. This uses power. Try these methods in the order below. Use the first method that turns the backlight off and turns it on again in less than 1 s.

| Method                                 | "Off" command                           | "On" command                                  | Result |
| -------------------------------------- | --------------------------------------- | --------------------------------------------- | ------ |
| HDMI-CEC standby                       | `cec-ctl -d /dev/cec0 --to 0 --standby` | `cec-ctl -d /dev/cec0 --to 0 --image-view-on` |        |
| USB power switch on the monitor supply | a GPIO-controlled load switch           | the same switch                               |        |
| None (paused frame)                    | none                                    | none                                          |        |

Measure the power of the complete briefcase for each method with the Anker 737 display, with the lid closed:

| Method              | Power, lid closed (W) | Power, playing (W) |
| ------------------- | --------------------- | ------------------ |
| None (paused frame) |                       |                    |
| Best method         |                       |                    |

To use a command method, set these variables in `.env`. The controller container then runs the commands:

```bash
BRIEFCASE_DISPLAY_BACKEND=command
BRIEFCASE_DISPLAY_OFF_COMMAND=<off command>
BRIEFCASE_DISPLAY_ON_COMMAND=<on command>
```

N.B., a CEC command needs `/dev/cec0` and the `cec-ctl` tool in the controller container. Add them in the same change that selects this method.

## Test 4: Zero-Touch Acceptance

This test checks the zero-touch rule: the briefcase must operate with no keyboard, no mouse and no user action.

1. Disconnect the keyboard and the mouse.
2. Turn on the arm switch. Keep the lid open.
3. Disconnect the power, then connect it again.
4. Measure the time until the video plays. Run `./scripts/pi_check.sh` over SSH to read the boot-to-ready time. The target is 30 s or less.
5. Open and close the lid 20 times. Turn the arm switch off and on 20 times. The video must start and stop each time, with no wrong state.
6. Disconnect the power while the video plays. Connect it again. The briefcase must start normally, and the web app must show the same settings as before.

| Item                                  | Result |
| ------------------------------------- | ------ |
| Boot to ready (s)                     |        |
| Power on to first video, lid open (s) |        |
| 20 lid cycles without a fault         |        |
| 20 arm cycles without a fault         |        |
| Settings kept after a power loss      |        |

## Results Log

| Date | Board | Tester | Notes |
| ---- | ----- | ------ | ----- |

## See also

- [Architecture](architecture.md)
- [Configuration](configuration.md)
- [Video tools](../../tools/README.md)
