"use strict";

const STATUS_POLL_MS = 1000;

const STATE_LABELS = {
  starting: "Starting",
  no_video: "No video",
  player_offline: "Player offline",
  disarmed: "Disarmed",
  ready: "Ready",
  playing: "Playing",
  finished: "Finished",
  error: "Error, retrying",
};

const $ = (selector, root = document) => root.querySelector(selector);

let lastStatus = null;
let videos = [];

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

function formatBytes(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(bytes / 1024 ** 2)} MB`;
}

function formatTime(seconds) {
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function showError(message) {
  const element = $("#status-error");
  element.textContent = message || "";
  element.hidden = !message;
}

function renderStatus(status) {
  lastStatus = status;
  const badge = $("#state-badge");
  badge.textContent = STATE_LABELS[status.state] || status.state;
  badge.className = "badge";
  if (status.state === "playing") badge.classList.add("playing");
  if (status.state === "ready") badge.classList.add("ready");
  if (["no_video", "player_offline", "error"].includes(status.state)) {
    badge.classList.add("warn");
  }

  $("#now-video").textContent = status.current_video
    ? `${status.current_video} from ${formatTime(status.start_sec || 0)}`
    : "";
  $("#lid-state").textContent = status.lid_open ? "Open" : "Closed";
  $("#arm-state").textContent = status.armed ? "Armed" : "Disarmed";
  $("#player-state").textContent = status.player_connected ? "Connected" : "Offline";

  const playing = status.state === "playing";
  const position = status.position_sec;
  const duration = status.duration_sec;
  $("#position-text").textContent =
    position === null || position === undefined
      ? "--:-- / --:--"
      : `${formatTime(position)} / ${duration ? formatTime(duration) : "--:--"}`;
  const bar = $("#position-bar");
  bar.max = duration || 1;
  bar.value = position && duration ? Math.min(position, duration) : 0;
  $("#pause-button").textContent = status.paused ? "Resume" : "Pause";
  $("#pause-button").disabled = !playing;
  for (const button of document.querySelectorAll("#position-tools button")) {
    button.disabled = !playing;
  }
  showError(status.error);

  $("#simulate").hidden = !status.simulated_inputs;
  $("#sim-lid").textContent = status.lid_open ? "Close lid" : "Open lid";
  $("#sim-arm").textContent = status.armed ? "Disarm" : "Arm";
}

async function refreshStatus() {
  try {
    renderStatus(await api("GET", "/api/status"));
  } catch (error) {
    showError(`The briefcase does not answer: ${error.message}`);
  }
}

function renderSettings(settings) {
  const form = $("#settings-form");
  const select = $("#armed-video");
  select.replaceChildren(
    ...videos.map((video) => new Option(video.name, video.name)),
  );
  select.value = settings.armed_video || (videos[0] && videos[0].name) || "";
  form.selection_mode.value = settings.selection_mode;
  form.default_start.value = settings.default_start;
  form.volume.value = settings.volume;
  $("#volume-value").textContent = settings.volume;
}

function renderVideos() {
  const list = $("#video-list");
  const template = $("#video-template");
  $("#no-videos").hidden = videos.length > 0;
  list.replaceChildren(
    ...videos.map((video) => {
      const item = template.content.firstElementChild.cloneNode(true);
      $(".video-name", item).textContent = video.name;
      const meta = [formatBytes(video.size_bytes), `starts at ${video.effective_start}`];
      if (video.info && video.info.duration_sec) {
        meta.unshift(formatTime(video.info.duration_sec));
      }
      $(".video-meta", item).textContent = meta.join(" · ");

      const warnings = $(".warnings", item);
      for (const warning of (video.info && video.info.warnings) || []) {
        const line = document.createElement("li");
        line.textContent = warning;
        warnings.append(line);
      }

      const form = $(".video-form", item);
      const settings = video.settings;
      form.start_mode.value = settings.start_mode;
      form.start_sec.value =
        settings.start_sec === null ? "" : formatTime(settings.start_sec);
      form.cue_points_sec.value = settings.cue_points_sec.map(formatTime).join(", ");
      form.end_action.value = settings.end_action;

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await run(() =>
          api("PUT", `/api/videos/${encodeURIComponent(video.name)}/settings`, {
            start_mode: form.start_mode.value,
            start_sec: form.start_sec.value.trim() || null,
            cue_points_sec: form.cue_points_sec.value,
            end_action: form.end_action.value,
          }),
        );
        await refreshAll();
      });
      $(".rename", item).addEventListener("click", async () => {
        const newName = prompt("New name, for example my_video.mp4", video.name);
        if (!newName || newName === video.name) return;
        await run(() =>
          api("PATCH", `/api/videos/${encodeURIComponent(video.name)}`, {
            new_name: newName,
          }),
        );
        await refreshAll();
      });
      $(".delete", item).addEventListener("click", async () => {
        if (!confirm(`Delete ${video.name}? You cannot undo this.`)) return;
        await run(() => api("DELETE", `/api/videos/${encodeURIComponent(video.name)}`));
        await refreshAll();
      });
      return item;
    }),
  );
}

async function run(action) {
  try {
    return await action();
  } catch (error) {
    alert(error.message);
    return null;
  }
}

async function refreshAll() {
  const [videoList, settings] = await Promise.all([
    api("GET", "/api/videos"),
    api("GET", "/api/settings"),
  ]);
  videos = videoList;
  renderVideos();
  renderSettings(settings);
  await refreshStatus();
}

function upload(file) {
  const progress = $("#upload-progress");
  const message = $("#upload-message");
  progress.hidden = false;
  progress.value = 0;
  message.hidden = false;
  message.textContent = `Uploading ${file.name}…`;

  const request = new XMLHttpRequest();
  request.open("PUT", `/api/videos/${encodeURIComponent(file.name)}`);
  request.upload.addEventListener("progress", (event) => {
    if (event.lengthComputable) progress.value = (event.loaded / event.total) * 100;
  });
  request.addEventListener("load", async () => {
    progress.hidden = true;
    let data = {};
    try {
      data = JSON.parse(request.responseText);
    } catch (error) {
      data = {};
    }
    if (request.status >= 400) {
      message.textContent = `Upload failed: ${data.detail || request.status}`;
      return;
    }
    const warnings = (data.info && data.info.warnings) || [];
    message.textContent = warnings.length
      ? `Uploaded ${data.name}. Warning: ${warnings.join(" ")}`
      : `Uploaded ${data.name}.`;
    await refreshAll();
  });
  request.addEventListener("error", () => {
    progress.hidden = true;
    message.textContent = "Upload failed: the connection broke.";
  });
  request.send(file);
}

function bindEvents() {
  $("#play-button").addEventListener("click", () =>
    run(async () => renderStatus(await api("POST", "/api/play", { active: true }))),
  );
  $("#stop-button").addEventListener("click", () =>
    run(async () => renderStatus(await api("POST", "/api/play", { active: false }))),
  );
  $("#pause-button").addEventListener("click", () =>
    run(async () =>
      renderStatus(await api("POST", "/api/pause", { paused: !lastStatus.paused })),
    ),
  );
  for (const button of document.querySelectorAll(".seek")) {
    button.addEventListener("click", () =>
      run(async () =>
        renderStatus(
          await api("POST", "/api/seek", { offset_sec: Number(button.dataset.offset) }),
        ),
      ),
    );
  }
  const usePosition = async (target) => {
    const result = await run(() => api("POST", "/api/use-position", { target }));
    if (!result) return;
    const label = target === "cue" ? "Added the cue point" : "The start position is now";
    $("#position-message").hidden = false;
    $("#position-message").textContent = `${label} ${result.position}.`;
    await refreshAll();
  };
  $("#use-start-button").addEventListener("click", () => usePosition("start"));
  $("#use-cue-button").addEventListener("click", () => usePosition("cue"));
  $("#sim-lid").addEventListener("click", () =>
    run(async () =>
      renderStatus(await api("POST", "/api/simulate", { lid_open: !lastStatus.lid_open })),
    ),
  );
  $("#sim-arm").addEventListener("click", () =>
    run(async () =>
      renderStatus(await api("POST", "/api/simulate", { armed: !lastStatus.armed })),
    ),
  );

  const form = $("#settings-form");
  form.volume.addEventListener("input", () => {
    $("#volume-value").textContent = form.volume.value;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      selection_mode: form.selection_mode.value,
      default_start: form.default_start.value.trim() || "00:30",
      volume: Number(form.volume.value),
    };
    if (form.armed_video.value) body.armed_video = form.armed_video.value;
    const settings = await run(() => api("PUT", "/api/settings", body));
    if (settings) await refreshAll();
  });
  $("#reset-button").addEventListener("click", async () => {
    if (!confirm("Reset all playback settings to the defaults?")) return;
    await run(() => api("POST", "/api/settings/reset"));
    await refreshAll();
  });

  $("#upload-input").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (file) upload(file);
    event.target.value = "";
  });
}

bindEvents();
refreshAll().catch((error) => showError(error.message));
setInterval(refreshStatus, STATUS_POLL_MS);
