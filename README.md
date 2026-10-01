# Rickroll Briefcase

![Rick Astley dances in the "Never Gonna Give You Up" music video](https://media.giphy.com/media/Vuw9m5wXviFIQ/giphy.gif)

A briefcase that plays a video when a person opens it. The classic video is "Never Gonna Give You Up" by Rick Astley. Close the lid and the video stops. Open it again and the video starts again, immediately.

![Diagram of the briefcase system: the lid sensor and the arm switch connect to a Raspberry Pi, which shows the video on a 13.3 inch monitor](docs/images/system_overview.svg)

The briefcase contains a Raspberry Pi, a 13.3" portable monitor and a USB-C power bank. A reed switch and a magnet detect the lid. An external switch arms the briefcase. The Pi makes its own Wi-Fi network. You use a phone browser to select the videos and change the settings. The briefcase needs no internet connection.

## Features

- instant start when a person opens the lid, because the video is already loaded and paused
- instant stop when a person closes the lid
- external arm switch: switch it on and the briefcase is ready
- zero-touch operation: no keyboard, no mouse, no desktop and no windows
- a video library with upload, rename and delete in a phone web app
- a start position for each video, for example 00:30, with fixed, beginning, random and resume start modes
- single, cycle and shuffle selection modes
- loop or stop at the end of a video
- battery power for approximately 5 to 7 hours of playback
- all software in Docker containers, with a laptop mode for development without a Pi

## Important: Supply Your Own Video

This repository does **not** contain "Never Gonna Give You Up" or any other copyright music or video. You must supply a legally obtained copy of each video that you use. Do not download videos from streaming services if their terms do not permit it.

For development, the repository makes a generated test video with a visible timecode. Refer to [tools/README.md](tools/README.md).

## Quick Start on a Laptop

You need Docker with the Compose plugin.

```bash
git clone https://github.com/BatchCodes/rickroll_briefcase.git
cd rickroll_briefcase
./scripts/write_env.sh
./tools/make_test_video.sh
docker compose -f compose.yml -f compose.dev.yml up --build
```

Open <http://localhost:8080>. Use the "Lid" and "Arm" buttons to simulate the briefcase. The video plays in a window on your desktop.

## Quick Start on a Raspberry Pi

You need a Raspberry Pi 4 or a Raspberry Pi Zero 2 W with Raspberry Pi OS Lite (64-bit). Build the hardware first. Refer to the [hardware guide](docs/hardware/parts.md).

Run this command on the Pi as your normal user, for example over SSH:

```bash
curl -fsSL https://raw.githubusercontent.com/BatchCodes/rickroll_briefcase/main/install.sh | bash -s -- --country DE
```

Use your own Wi-Fi country code instead of `DE`. The command downloads the files that the Pi needs to `~/rickroll_briefcase`. It needs no git and no GitHub login. Then it runs `scripts/setup.sh` with `sudo`. The setup asks for a Wi-Fi password. It installs Docker, sets up the `RICKROLL-BRIEFCASE` access point, downloads the container images and starts the briefcase at each boot.

To install the complete source and build the images on the Pi instead, use `full_install.sh`. The build takes approximately 10 to 20 minutes on a Pi 4.

```bash
curl -fsSL https://raw.githubusercontent.com/BatchCodes/rickroll_briefcase/main/full_install.sh | bash -s -- --country DE
```

### Install a Release or a Commit

The commands above install the newest commit on `main`. To install a release or a pre-release, use the installer that is attached to it. It installs the files and the images of that release:

```bash
curl -fsSL https://github.com/BatchCodes/rickroll_briefcase/releases/download/v0.1.0/install.sh | bash -s -- --country DE
```

Use `full_install.sh` from the same release for a full install. To install one commit, add `--ref` with the commit hash, for example `--ref 3f2a1c9`. A commit on `main` uses the images of that commit.

For all options, run `curl -fsSL https://raw.githubusercontent.com/BatchCodes/rickroll_briefcase/main/install.sh | bash -s -- --help` and `~/rickroll_briefcase/scripts/setup.sh --help`.

Then do these steps:

1. Connect your phone to the `RICKROLL-BRIEFCASE` Wi-Fi network.
2. Open <http://briefcase.lan> in the phone browser. If the name does not work, open <http://10.42.0.1>. Android can show "This network has no internet access". Select "Stay connected", because the briefcase needs no internet.
3. Upload a video.
4. Turn on the arm switch and close the lid.
5. Give the briefcase to a friend.

## Updating

An update needs an internet connection. The briefcase Wi-Fi is an access point, so it has no internet. Use one of these methods:

- On a Pi 4, connect an Ethernet cable to your router.
- On the web page, push "Connect to known Wi-Fi". The Pi then connects to a Wi-Fi network that it knows. If it cannot connect in 60 s, it goes back to the access point. After a reboot, the Pi is always an access point again.

To update the briefcase software, run these commands on the Pi, for example over SSH:

```bash
cd ~/rickroll_briefcase
docker compose pull
docker compose up -d
```

The code is in the container images, so this is the complete update. If you used `full_install.sh`, run that `curl` command again instead. It also updates the installer and `compose.yml`. It keeps your settings and videos, and it is safe to run more than one time.

## Documentation

| Document                                        | Content                                              |
| ----------------------------------------------- | ---------------------------------------------------- |
| [Parts list](docs/hardware/parts.md)            | the parts to buy, with prices                        |
| [Wiring](docs/hardware/wiring.md)               | how to connect the reed switch, arm switch and power |
| [Assembly](docs/hardware/assembly.md)           | how to put the parts in the briefcase                |
| [Power](docs/hardware/power.md)                 | battery life and power measurements                  |
| [Architecture](docs/software/architecture.md)   | how the software parts work together                 |
| [Configuration](docs/software/configuration.md) | all settings and their defaults                      |
| [Development](docs/software/development.md)     | how to run and test the software on a laptop         |
| [Player notes](docs/software/player.md)         | player and hardware test results                     |
| [Video tools](tools/README.md)                  | how to make test videos and convert your own videos  |

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## Licence

The software and the documentation use the [MIT licence](LICENSE). The licence does not cover videos that you add to the briefcase. The GIF at the top of this page comes from [GIPHY](https://giphy.com/gifs/Vuw9m5wXviFIQ) and is not part of this repository.
