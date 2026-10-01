# Contributing to the Rickroll Briefcase

Thank you for your help. This document tells you how to set up a development system, how to test a change and how to send it.

All contributors must follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development System

You need only Docker with the Compose plugin. You do not need a Raspberry Pi, Python or `ffmpeg` on your computer.

1. Clone the repository.

   ```bash
   git clone https://github.com/BatchCodes/rickroll_briefcase.git
   cd rickroll_briefcase
   ```

2. Write your user and group IDs to `.env`, and make the data directories.

   ```bash
   ./scripts/write_env.sh
   ```

3. Make a test video.

   ```bash
   ./tools/make_test_video.sh
   ```

4. Start the briefcase on your laptop.

   ```bash
   docker compose -f compose.yml -f compose.dev.yml up --build
   ```

5. Open <http://localhost:8080> in a browser.

The laptop version uses a simulated lid and a simulated arm switch. The web app shows buttons for them. The player opens a window on your desktop. Refer to [docs/software/development.md](docs/software/development.md) for more information.

## Tests and Linting

Run the full test suite and the linters in Docker:

```bash
docker compose -f compose.test.yml run --rm test
```

Run the shell script check:

```bash
docker run --rm -v "$PWD:/mnt" -w /mnt koalaman/shellcheck:stable *.sh scripts/*.sh tools/*.sh player/*.sh
```

CI runs the same checks on each pull request.

## Code Style

- Python follows PEP 8. `ruff` checks and formats the code.
- Shell scripts use `set -euo pipefail` and must pass `shellcheck`.
- Documentation uses British English and short, simple sentences.
- Hardware access stays behind the input and player abstractions. All other code must run on a laptop.

## Pull Requests

1. Make a branch from `main`.
2. Make one change per pull request.
3. Add or update tests for each change in behaviour.
4. Update the documentation in the same pull request.
5. Use a [Conventional Commits](https://www.conventionalcommits.org/) message, for example `feat: add shuffle mode`.

Do not add copyright material to the repository. This includes music, videos and images that you do not own.

## Releases

Maintainers make releases.

1. Update the `version` in [controller/pyproject.toml](controller/pyproject.toml).
2. Commit the change with the message `chore: release vX.Y.Z`.
3. Make a tag, for example `git tag v1.2.0`. For a pre-release, add a suffix, for example `v1.2.0-rc.1`.
4. Push the tag with `git push origin v1.2.0`.

Two workflows then run:

- `Images` builds the `linux/arm64` and `linux/amd64` images and pushes them to GHCR with the tag `X.Y.Z` (and `X.Y` for a full release).
- `Release` makes the GitHub release. A tag with a suffix makes a pre-release. [scripts/make_release_assets.sh](scripts/make_release_assets.sh) makes the attached files: the runtime archive, the full archive, an `install.sh` and a `full_install.sh` that install this release, and `SHA256SUMS`.

Each push to `main` also builds the images and pushes them with the tags `latest` and `sha-<commit>`. Edit the generated release notes on the GitHub release page. List the new features, the fixes and any change that needs user action.
