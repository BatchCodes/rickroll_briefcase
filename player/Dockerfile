FROM debian:bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    mpv \
    libgl1-mesa-dri \
    libpulse0 \
    tini \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --system --uid 1000 --create-home briefcase \
  && install -d -m 1777 /run/briefcase

COPY mpv.conf /etc/mpv/mpv.conf
COPY entrypoint.sh /usr/local/bin/player-entrypoint

USER briefcase
HEALTHCHECK --interval=10s --timeout=2s --start-period=10s --retries=3 \
  CMD ["sh", "-c", "test -S \"${BRIEFCASE_MPV_SOCKET:-/run/briefcase/mpv.sock}\""]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/player-entrypoint"]
