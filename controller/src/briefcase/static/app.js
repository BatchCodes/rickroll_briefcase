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
  shutting_down: "Shutting down",
};

const WIFI_MODE_LABELS = {
  hotspot: "Hotspot",
  client: "Client",
  switching: "Switching…",
  offline: "Offline",
  unavailable: "Unavailable",
};

const POWER_LABELS = {
  on: "On",
  off_pending: "Off (waiting)",
  shutting_down: "Shutting down",
  simulated_off: "Off (simulated)",
};

const $ = (selector, root = document) => root.querySelector(selector);

const TAB_NAMES = ["status", "playback", "upload", "wifi"];
// Old fragments from bookmarks, mapped to the current tab names.
const TAB_ALIASES = { videos: "upload" };

function availableTabs() {
  return TAB_NAMES.filter((name) => {
    const button = $(`.tabs [data-tab="${name}"]`);
    return button && !button.hidden;
  });
}

function showTab(name) {
  const tabs = availableTabs();
  const selected = tabs.includes(name) ? name : "status";
  for (const button of document.querySelectorAll(".tabs [data-tab]")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === selected));
  }
  for (const section of document.querySelectorAll("main > section[data-tab]")) {
    section.classList.toggle("tab-hidden", section.dataset.tab !== selected);
  }
  // Keep a requested tab that is not available yet (for example "wifi"
  // before the first network status), so it opens when it becomes available.
  if (selected === name && location.hash !== `#${selected}`) {
    history.replaceState(null, "", `#${selected}`);
  }
}

function currentTab() {
  const name = location.hash.replace("#", "") || "status";
  return TAB_ALIASES[name] || name;
}

let lastStatus = null;
let lastArmedVideo = null;
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
  if (status.armed_video !== undefined && status.armed_video !== lastArmedVideo) {
    lastArmedVideo = status.armed_video;
    refreshAll().catch(() => {});
  }
  const badge = $("#state-badge");
  badge.textContent = STATE_LABELS[status.state] || status.state;
  badge.className = "badge";
  if (status.state === "playing") badge.classList.add("playing");
  if (status.state === "ready") badge.classList.add("ready");
  if (["no_video", "player_offline", "error"].includes(status.state)) {
    badge.classList.add("warn");
  }

  let nowText = status.current_video
    ? `${status.current_video} from ${formatTime(status.start_sec || 0)}`
    : "";
  if (status.resume_remaining_sec !== null && status.resume_remaining_sec !== undefined) {
    nowText = `${status.current_video}: continues if opened within ${Math.ceil(status.resume_remaining_sec)} s`;
  }
  $("#now-video").textContent = nowText;
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

  const power = status.power || { state: "no_switch" };
  const hasPower = power.state !== "no_switch";
  $("#power-fact").hidden = !hasPower;
  $("#power-state").textContent = POWER_LABELS[power.state] || power.state;
  const powerMessage = $("#power-message");
  let powerText = "";
  if (power.state === "off_pending") {
    powerText = `The power switch is off. The briefcase shuts down in ${power.delay_sec} s.`;
  } else if (power.state === "shutting_down") {
    powerText = "The briefcase is shutting down.";
  } else if (power.state === "simulated_off") {
    powerText = "Laptop mode: the Pi would be off now. Turn the power switch on again.";
  } else if (power.error) {
    powerText = `The shutdown failed: ${power.error}`;
  }
  powerMessage.hidden = !powerText;
  powerMessage.textContent = powerText;
  $("#sim-power").hidden = !hasPower;
  $("#sim-power").textContent = power.switch_on === false ? "Power on" : "Power off";

  const hasKnob = Boolean(status.knob && status.knob.enabled);
  $("#sim-knob-left").hidden = !hasKnob;
  $("#sim-knob-right").hidden = !hasKnob;

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

const START_MODE_NOTES = {
  beginning: "starts at 00:00",
  random: "random cue point",
  resume: "resumes",
};

function renderSettings(settings) {
  const form = $("#settings-form");
  form.selection_mode.value = settings.selection_mode;
  form.default_start.value = settings.default_start;
  form.resume_window.value = settings.resume_window_sec;
  form.volume.value = settings.volume;
  $("#volume-value").textContent = settings.volume;
  renderVideoTable(settings);
}

function renderVideoTable(settings) {
  const selected = settings.armed_video || (videos[0] && videos[0].name) || null;
  lastArmedVideo = selected;
  const body = $("#video-table tbody");
  if (!videos.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 2;
    cell.className = "muted";
    cell.textContent = "No videos yet. Upload one in the Upload tab.";
    row.append(cell);
    body.replaceChildren(row);
    return;
  }
  body.replaceChildren(
    ...videos.map((video) => {
      const row = document.createElement("tr");
      const isSelected = video.name === selected;
      row.classList.toggle("selected", isSelected);
      row.setAttribute("aria-selected", String(isSelected));
      row.tabIndex = 0;

      const nameCell = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "name-wrap";
      const mark = document.createElement("span");
      mark.className = "select-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = isSelected ? "▶" : "";
      const text = document.createElement("div");
      const name = document.createElement("span");
      name.className = "row-name";
      // A zero-width space after "_", "-" and "." lets long names wrap there.
      name.textContent = video.name.replace(/([_.-])/g, "$1\u200b");
      text.append(name);
      const note = START_MODE_NOTES[video.settings.start_mode];
      if (note) {
        const noteElement = document.createElement("span");
        noteElement.className = "mode-note";
        noteElement.textContent = note;
        text.append(noteElement);
      }
      wrap.append(mark, text);
      nameCell.append(wrap);

      const startCell = document.createElement("td");
      startCell.className = "start-cell";
      const input = document.createElement("input");
      input.inputMode = "decimal";
      input.setAttribute("aria-label", `Start position of ${video.name}`);
      input.placeholder =
        video.settings.start_mode === "fixed"
          ? settings.default_start
          : video.settings.start_mode === "beginning"
            ? "00:00"
            : "–";
      input.value =
        video.settings.start_sec === null ? "" : formatTime(video.settings.start_sec);
      const original = input.value;
      const save = async () => {
        if (input.value.trim() === original) return;
        const result = await run(() =>
          api("PUT", `/api/videos/${encodeURIComponent(video.name)}/settings`, {
            start_mode: "fixed",
            start_sec: input.value.trim() || null,
          }),
        );
        if (!result) input.value = original;
        await refreshAll();
      };
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          input.blur();
        }
      });
      input.addEventListener("change", save);
      input.addEventListener("click", (event) => event.stopPropagation());
      startCell.append(input);

      const select = async () => {
        if (isSelected) return;
        await run(() => api("PUT", "/api/settings", { armed_video: video.name }));
        await refreshAll();
      };
      row.addEventListener("click", select);
      row.addEventListener("keydown", (event) => {
        if (event.target === row && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          select();
        }
      });

      row.append(nameCell, startCell);
      return row;
    }),
  );
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
      form.cue_points_sec.value = settings.cue_points_sec.map(formatTime).join(", ");
      form.end_action.value = settings.end_action;

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await run(() =>
          api("PUT", `/api/videos/${encodeURIComponent(video.name)}/settings`, {
            start_mode: form.start_mode.value,
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

function renderNetwork(network) {
  const card = $("#wifi-card");
  card.hidden = !network.available;
  const tabButton = $('.tabs [data-tab="wifi"]');
  if (tabButton.hidden === network.available) {
    tabButton.hidden = !network.available;
    showTab(currentTab());
  }
  if (!network.available) return;

  $("#wifi-mode").textContent = WIFI_MODE_LABELS[network.mode] || network.mode;
  $("#wifi-network").textContent = network.connection || "–";
  $("#wifi-address").textContent = network.address || "–";
  const message = $("#wifi-message");
  message.hidden = !network.message;
  message.textContent = network.message || "";

  const switching = network.mode === "switching";
  $("#wifi-client-button").disabled = switching || network.mode === "client";
  $("#wifi-hotspot-button").disabled = switching || network.mode === "hotspot";

  const host = network.hostname ? `http://${network.hostname}.local` : "the Pi address";
  $("#wifi-help").textContent =
    network.mode === "client"
      ? `Client mode. On this network, open ${host}. After a reboot, the hotspot comes back.`
      : `"Connect to known Wi-Fi" disconnects your phone from the hotspot. ` +
        `Then open ${host} on your home network. If no known network connects ` +
        `in ${Math.round(network.fallback_sec)} s, the hotspot comes back.`;

  const list = $("#known-networks");
  list.replaceChildren(
    ...network.known_networks.map((name) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = name;
      const forget = document.createElement("button");
      forget.type = "button";
      forget.className = "secondary";
      forget.textContent = "Forget";
      forget.addEventListener("click", async () => {
        if (!confirm(`Forget the Wi-Fi network ${name}?`)) return;
        const result = await run(() =>
          api("DELETE", `/api/network/known/${encodeURIComponent(name)}`),
        );
        if (result) renderNetwork(result);
      });
      item.append(label, forget);
      return item;
    }),
  );
  if (!network.known_networks.length) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = "No known networks. Add one below.";
    list.append(item);
  }
}

async function refreshNetwork() {
  try {
    renderNetwork(await api("GET", "/api/network"));
  } catch (error) {
    $("#wifi-card").hidden = true;
    $('.tabs [data-tab="wifi"]').hidden = true;
    showTab(currentTab());
  }
}

async function refreshAll() {
  const [videoList, settings] = await Promise.all([
    api("GET", "/api/videos"),
    api("GET", "/api/settings"),
  ]);
  videos = videoList;
  refreshNetwork();
  refreshStorage();
  renderVideos();
  renderSettings(settings);
  await refreshStatus();
}

async function refreshStorage() {
  try {
    const storage = await api("GET", "/api/storage");
    $("#storage").textContent =
      `Free space: ${formatBytes(storage.free_bytes)} of ${formatBytes(storage.total_bytes)}`;
  } catch (error) {
    $("#storage").textContent = "";
  }
}

function upload(file, index, count) {
  const progress = $("#upload-progress");
  const message = $("#upload-message");
  const prefix = count > 1 ? `(${index + 1} of ${count}) ` : "";
  progress.hidden = false;
  progress.value = 0;
  message.hidden = false;
  message.textContent = `${prefix}Uploading ${file.name}…`;

  return new Promise((resolve) => {
    const request = new XMLHttpRequest();
    request.open("PUT", `/api/videos/${encodeURIComponent(file.name)}`);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) progress.value = (event.loaded / event.total) * 100;
    });
    request.addEventListener("load", () => {
      progress.hidden = true;
      let data = {};
      try {
        data = JSON.parse(request.responseText);
      } catch (error) {
        data = {};
      }
      if (request.status >= 400) {
        resolve(`${file.name}: upload failed: ${data.detail || request.status}`);
        return;
      }
      const warnings = (data.info && data.info.warnings) || [];
      resolve(
        warnings.length
          ? `Uploaded ${data.name}. Warning: ${warnings.join(" ")}`
          : `Uploaded ${data.name}.`,
      );
    });
    request.addEventListener("error", () => {
      progress.hidden = true;
      resolve(`${file.name}: upload failed: the connection broke.`);
    });
    request.send(file);
  });
}

async function uploadAll(files) {
  const results = [];
  for (const [index, file] of files.entries()) {
    results.push(await upload(file, index, files.length));
  }
  $("#upload-message").textContent = results.join(" ");
  await refreshAll();
}

function bindEvents() {
  for (const button of document.querySelectorAll(".tabs [data-tab]")) {
    button.addEventListener("click", () => {
      showTab(button.dataset.tab);
      window.scrollTo(0, 0);
    });
  }
  window.addEventListener("hashchange", () => showTab(currentTab()));

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
  $("#sim-power").addEventListener("click", () =>
    run(async () =>
      renderStatus(
        await api("POST", "/api/simulate", {
          power_on: lastStatus.power.switch_on === false,
        }),
      ),
    ),
  );
  for (const [id, step] of [
    ["#sim-knob-left", -1],
    ["#sim-knob-right", 1],
  ]) {
    $(id).addEventListener("click", () =>
      run(async () => renderStatus(await api("POST", "/api/simulate", { knob: step }))),
    );
  }
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
      resume_window: form.resume_window.value.trim() || "15",
      volume: Number(form.volume.value),
    };
    const settings = await run(() => api("PUT", "/api/settings", body));
    if (settings) await refreshAll();
  });
  $("#reset-button").addEventListener("click", async () => {
    if (!confirm("Reset all playback settings to the defaults?")) return;
    await run(() => api("POST", "/api/settings/reset"));
    await refreshAll();
  });

  $("#wifi-client-button").addEventListener("click", async () => {
    if (!confirm("Connect to a known Wi-Fi network? Your phone loses the hotspot.")) {
      return;
    }
    const result = await run(() => api("POST", "/api/network/mode", { mode: "client" }));
    if (result) renderNetwork(result);
  });
  $("#wifi-hotspot-button").addEventListener("click", async () => {
    const result = await run(() => api("POST", "/api/network/mode", { mode: "hotspot" }));
    if (result) renderNetwork(result);
  });
  $("#add-network-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const result = await run(() =>
      api("POST", "/api/network/known", {
        ssid: form.ssid.value,
        password: form.password.value,
      }),
    );
    if (!result) return;
    form.reset();
    renderNetwork(result);
  });

  $("#upload-input").addEventListener("change", (event) => {
    const files = Array.from(event.target.files);
    event.target.value = "";
    if (files.length) uploadAll(files);
  });
}

bindEvents();
showTab(currentTab());
refreshAll().catch((error) => showError(error.message));
setInterval(refreshStatus, STATUS_POLL_MS);
setInterval(refreshNetwork, 5000);
