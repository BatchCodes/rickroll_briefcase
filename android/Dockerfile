FROM eclipse-temurin:17-jdk-noble

ARG CMDLINE_TOOLS_URL=https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
ENV ANDROID_HOME=/opt/android-sdk \
    GRADLE_USER_HOME=/cache/gradle

RUN apt-get update \
  && apt-get install -y --no-install-recommends unzip curl \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p "${ANDROID_HOME}/cmdline-tools" \
  && curl -fsSL "${CMDLINE_TOOLS_URL}" -o /tmp/tools.zip \
  && unzip -q /tmp/tools.zip -d "${ANDROID_HOME}/cmdline-tools" \
  && mv "${ANDROID_HOME}/cmdline-tools/cmdline-tools" "${ANDROID_HOME}/cmdline-tools/latest" \
  && rm /tmp/tools.zip \
  && yes | "${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager" --licenses >/dev/null \
  && "${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager" \
    "platforms;android-35" \
    "build-tools;35.0.0" \
    "platform-tools" >/dev/null \
  && mkdir -p /cache/gradle && chmod 1777 /cache /cache/gradle

WORKDIR /work
