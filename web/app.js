// Media Harvester web UI. Talks to the local Python server in mediaharvester.py.
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="mh-token"]').content;
  const $ = (sel) => document.querySelector(sel);

  const els = {
    form: $("#linkForm"), input: $("#linkInput"), checkBtn: $("#checkBtn"),
    readyPanel: $("#readyPanel"), readyList: $("#readyList"), downloadAll: $("#downloadAll"),
    jobsPanel: $("#jobsPanel"), jobList: $("#jobList"), clearFinished: $("#clearFinished"),
    openFolder: $("#openFolder"), empty: $("#emptyState"),
    saveTo: $("#saveTo"), saveToPath: $("#saveToPath"),
    banner: $("#ffmpegBanner"), installFfmpeg: $("#installFfmpeg"),
    settings: $("#settingsDialog"), openSettings: $("#openSettings"),
    folderInput: $("#folderInput"), chooseFolder: $("#chooseFolder"), saveFolder: $("#saveFolder"),
    resetFolder: $("#resetFolder"), folderNote: $("#folderNote"),
    ytdlpVersion: $("#ytdlpVersion"), ffmpegStatus: $("#ffmpegStatus"),
    updateEngine: $("#updateEngine"), installFfmpeg2: $("#installFfmpeg2"), taskNote: $("#taskNote"),
    dropVeil: $("#dropVeil"), toast: $("#toast"),
    quitApp: $("#quitApp"), quitScreen: $("#quitScreen"),
    newGroup: $("#newGroup"), groupList: $("#groupList"),
    targetWrap: $("#targetWrap"), targetGroup: $("#targetGroup"),
  };

  let server = null;          // latest /api/state
  let ready = [];             // links checked (or being checked) but not yet downloaded
  let defaultMode = loadPref("mode", "video");
  let groups = [];            // { id, name }: links in a group download into a folder of that name
  let targetGroup = null;     // group id that newly pasted links join, or null
  const groupEls = new Map(); // group id -> its box, kept so typing in a name isn't interrupted
  const jobEls = new Map();   // job id -> <li>
  const seenDone = new Set(); // job ids we've already announced as finished

  // ---------------------------------------------------------------- helpers

  function loadPref(key, fallback) {
    try { return localStorage.getItem("mh:" + key) || fallback; } catch { return fallback; }
  }
  function savePref(key, value) {
    try { localStorage.setItem("mh:" + key, value); } catch { /* private mode */ }
  }

  async function api(path, body = {}) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Token": TOKEN },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
    return data;
  }

  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "text") el.textContent = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c != null && c !== false) el.append(c);
    return el;
  }

  function extractLinks(text) {
    const found = text.match(/https?:\/\/[^\s<>"'`]+/gi) || [];
    return [...new Set(found.map((u) => u.replace(/[),.;!]+$/, "")))];
  }

  function formatDuration(sec) {
    if (!sec && sec !== 0) return "";
    sec = Math.round(sec);
    const hrs = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return hrs ? `${hrs}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function formatBytes(n) {
    if (!n) return "";
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function formatEta(sec) {
    if (sec == null) return "";
    if (sec < 60) return `${Math.max(1, Math.round(sec))} sec left`;
    return `${Math.round(sec / 60)} min left`;
  }

  function heightLabel(hgt) {
    if (!hgt) return "Best quality";
    if (hgt >= 2160) return "4K (2160p)";
    if (hgt >= 1440) return "1440p";
    return `${hgt}p`;
  }

  function siteName(info) {
    const key = info.site || "";
    const names = { Youtube: "YouTube", YoutubeTab: "YouTube", TikTok: "TikTok", Instagram: "Instagram",
      Twitter: "X", Vimeo: "Vimeo", Reddit: "Reddit", Facebook: "Facebook", SoundcloudSet: "SoundCloud",
      Soundcloud: "SoundCloud", Twitch: "Twitch", TwitchVod: "Twitch", Generic: "" };
    return key in names ? names[key] : key;
  }

  let toastTimer = null;
  function toast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 3800);
  }

  const isMac = () => server && server.platform === "Darwin";

  // ---------------------------------------------------------------- adding links

  function addLinks(text) {
    const links = extractLinks(text);
    if (!links.length) {
      toast("That doesn’t look like a link. Links start with https://");
      return false;
    }
    for (const url of links) {
      const existing = ready.find((it) => it.url === url);
      if (existing) { flash(existing); continue; }
      const item = { key: Math.random().toString(36).slice(2), url, status: "checking",
                     mode: defaultMode, height: null, info: null, error: null, groupId: targetGroup };
      ready.unshift(item);
      inspect(item);
    }
    renderReady();
    return true;
  }

  async function inspect(item) {
    item.status = "checking";
    item.error = null;
    renderReady();
    try {
      item.info = await api("/api/inspect", { url: item.url });
      item.status = "ready";
      if (item.info.audio_only) item.mode = "audio";
    } catch (err) {
      item.status = "error";
      item.error = err.message;
    }
    renderReady();
  }

  function flash(item) {
    const el = els.readyList.querySelector(`[data-key="${item.key}"]`);
    if (!el) return;
    el.classList.remove("is-flash");
    void el.offsetWidth;
    el.classList.add("is-flash");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function removeReady(item) {
    ready = ready.filter((it) => it !== item);
    renderReady();
  }

  // ---------------------------------------------------------------- downloading

  function itemsFor(item) {
    const info = item.info;
    // A group's name becomes the folder; otherwise a playlist gets a folder of its own
    const group = groupOf(item);
    if (info.kind === "playlist") {
      return info.entries.map((e) => ({ url: e.url, title: e.title, thumbnail: e.thumbnail,
        mode: item.mode, height: item.height, folder: group ? group.name : info.title }));
    }
    return [{ url: info.url, title: info.title, thumbnail: info.thumbnail, mode: item.mode, height: item.height,
      folder: group ? group.name : null }];
  }

  async function startDownload(itemsToStart) {
    const payload = itemsToStart.flatMap(itemsFor);
    if (!payload.length) return;
    try {
      await api("/api/download", { items: payload });
      ready = ready.filter((it) => !itemsToStart.includes(it));
      renderReady();
      toast(payload.length === 1 ? "Download started." : `${payload.length} downloads started.`);
      poll();
    } catch (err) {
      toast(err.message);
    }
  }

  // ---------------------------------------------------------------- render: ready cards

  const PLAY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.5-2.5z"/></svg>';

  function thumbEl(src, badge) {
    const wrap = h("div", { class: "thumb" });
    const ph = h("div", { class: "placeholder" });
    ph.innerHTML = PLAY_ICON;
    wrap.append(ph);
    if (src) {
      const img = h("img", { src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
      img.addEventListener("error", () => img.remove());
      img.addEventListener("load", () => ph.remove());
      wrap.append(img);
    }
    if (badge) wrap.append(h("span", { class: "badge", text: badge }));
    return wrap;
  }

  function modeControl(item) {
    const group = h("div", { class: "segmented", role: "radiogroup", "aria-label": "Save as" });
    for (const [mode, label] of [["video", "Video"], ["audio", "Audio (MP3)"]]) {
      if (mode === "video" && item.info.audio_only) continue;
      group.append(h("button", {
        type: "button", role: "radio", "aria-checked": String(item.mode === mode), text: label,
        onclick: () => { item.mode = mode; renderReady(); },
      }));
    }
    return group;
  }

  function qualityControl(item) {
    if (item.mode !== "video") return null;
    const heights = item.info.kind === "playlist" ? [1080, 720, 480] : item.info.heights || [];
    if (!heights.length) return null;
    const select = h("select", { "aria-label": "Video quality",
      onchange: (e) => { item.height = Number(e.target.value) || null; } });
    select.append(h("option", { value: "", text: "Best quality" }));
    for (const hgt of heights) {
      select.append(h("option", { value: hgt, text: heightLabel(hgt), selected: item.height === hgt }));
    }
    return select;
  }

  function groupControl(item) {
    if (!groups.length) return null;
    const select = h("select", { "aria-label": "Group",
      onchange: (e) => { item.groupId = e.target.value || null; renderReady(); } });
    select.append(h("option", { value: "", text: "No group" }));
    for (const g of groups) {
      select.append(h("option", { value: g.id, text: g.name, selected: item.groupId === g.id }));
    }
    return select;
  }

  function readyCard(item) {
    const li = h("li", { class: "card", "data-key": item.key });

    if (item.status === "checking") {
      li.classList.add("is-checking");
      const thumb = thumbEl(null);
      thumb.append(h("div", { class: "shimmer" }));
      li.append(thumb, h("div", { class: "card-body" },
        h("p", { class: "card-title", text: "Checking link…" }),
        h("span", { class: "card-url", text: item.url }),
        h("div", { class: "card-controls" }, h("span", { class: "spacer" }),
          h("button", { class: "btn btn-small btn-quiet", type: "button", text: "Remove",
            onclick: () => removeReady(item) }))));
      return li;
    }

    if (item.status === "error") {
      li.append(thumbEl(null), h("div", { class: "card-body" },
        h("p", { class: "card-title", text: "Couldn’t use this link" }),
        h("p", { class: "card-error", text: item.error }),
        h("span", { class: "card-url", text: item.url }),
        h("div", { class: "card-controls" }, h("span", { class: "spacer" }),
          h("button", { class: "btn btn-small btn-quiet", type: "button", text: "Remove",
            onclick: () => removeReady(item) }),
          h("button", { class: "btn btn-small", type: "button", text: "Check again",
            onclick: () => inspect(item) }))));
      return li;
    }

    const info = item.info;
    const isList = info.kind === "playlist";
    const count = isList ? info.entries.length : 0;
    const meta = isList
      ? [`Playlist of ${count} ${count === 1 ? "video" : "videos"}`, info.uploader, siteName(info)]
      : [info.uploader, siteName(info)];

    const body = h("div", { class: "card-body" },
      h("p", { class: "card-title", text: info.title, title: info.title }),
      h("p", { class: "card-meta", text: meta.filter(Boolean).join(", ") }));

    if (isList) {
      const list = h("ol", { class: "playlist-list" },
        info.entries.map((e) => h("li", { text: e.title })));
      body.append(h("details", {}, h("summary", { text: "Show what’s included" }), list));
    }

    body.append(h("div", { class: "card-controls" },
      modeControl(item), qualityControl(item), groupControl(item), h("span", { class: "spacer" }),
      h("button", { class: "btn btn-small btn-quiet", type: "button", text: "Remove",
        onclick: () => removeReady(item) }),
      h("button", { class: "btn btn-small btn-primary", type: "button",
        text: isList ? `Download all ${count}` : "Download",
        onclick: () => startDownload([item]) })));

    li.append(thumbEl(info.thumbnail, isList ? `${count} videos` : formatDuration(info.duration)), body);
    return li;
  }

  function renderReady() {
    els.readyList.replaceChildren(...ready.filter((it) => !groupOf(it)).map(readyCard));
    renderGroups();
    const readyCount = ready.filter((it) => it.status === "ready").length;
    els.readyPanel.hidden = ready.length === 0 && groups.length === 0;
    els.downloadAll.hidden = readyCount < 2;
    els.downloadAll.textContent = `Download all ${readyCount}`;
    updateEmpty();
  }

  // ---------------------------------------------------------------- render: jobs

  function jobStatusText(job) {
    switch (job.status) {
      case "queued": return "Waiting for another download to finish";
      case "downloading": {
        const parts = [`${job.stage}: ${Math.round(job.progress * 100)}%`];
        if (job.speed) parts.push(`${formatBytes(job.speed)}/s`);
        if (job.eta != null) parts.push(formatEta(job.eta));
        return parts.join(", ");
      }
      case "processing":
        return job.progress > 0 && job.progress < 1
          ? `${job.stage}: ${Math.round(job.progress * 100)}%` : `${job.stage}…`;
      case "done": return `Saved ${job.filename}${job.folder ? ` in ${job.folder}` : ""}${job.size ? ` (${formatBytes(job.size)})` : ""}`;
      case "cancelled": return "Cancelled";
      default: return job.error || "Failed";
    }
  }

  function jobActions(job) {
    const btn = (text, onclick, cls = "btn btn-small btn-quiet") =>
      h("button", { class: cls, type: "button", text, onclick });
    const act = (path, extra = {}) => () => api(path, { id: job.id, ...extra }).then(poll).catch((e) => toast(e.message));

    if (["queued", "downloading", "processing"].includes(job.status)) {
      return [btn("Cancel", act("/api/cancel"))];
    }
    if (job.status === "done") {
      return [btn("Open", act("/api/open"), "btn btn-small"),
              server.can_share && btn("Share…", act("/api/open", { share: true })),
              btn(isMac() ? "Show in Finder" : "Show in folder", act("/api/open", { reveal: true }))];
    }
    return [btn("Remove", act("/api/remove")), btn("Try again", act("/api/retry"), "btn btn-small")];
  }

  function renderJob(job) {
    let li = jobEls.get(job.id);
    if (!li) {
      li = h("li", { class: "job" });
      li._thumb = thumbEl(job.thumbnail);
      li._fill = h("i");
      li._thumb.append(h("div", { class: "fill" }, li._fill));
      li._title = h("p", { class: "job-title", title: job.title });
      li._status = h("p", { class: "job-status" });
      li._actions = h("div", { class: "job-actions" });
      li.append(li._thumb, h("div", { class: "job-body" }, li._title, li._status), li._actions);
      jobEls.set(job.id, li);
    }
    li.className = `job is-${job.status}`;
    const tag = job.mode === "audio" ? "MP3" : job.height ? heightLabel(job.height) : "Video";
    li._title.replaceChildren(h("span", { class: "tag", text: tag }), job.title);
    li._status.textContent = jobStatusText(job);
    const pct = job.status === "done" ? 100 : job.status === "queued" ? 0 : Math.round(job.progress * 100);
    li._fill.style.width = `${pct}%`;

    // Only rebuild buttons when the status changes, so clicks aren't lost mid-poll
    if (li._lastStatus !== job.status) {
      li._actions.replaceChildren(...jobActions(job).filter(Boolean));
      li._lastStatus = job.status;
    }
    return li;
  }

  function renderJobs(jobs) {
    const ids = new Set(jobs.map((j) => j.id));
    for (const [id, el] of jobEls) if (!ids.has(id)) { el.remove(); jobEls.delete(id); }
    jobs.forEach((job, i) => {
      const li = renderJob(job);
      if (els.jobList.children[i] !== li) els.jobList.insertBefore(li, els.jobList.children[i] || null);

      if (job.status === "done" && !seenDone.has(job.id)) {
        if (server._initialised) toast(`Saved: ${job.title}`);
        seenDone.add(job.id);
      }
    });
    els.jobsPanel.hidden = jobs.length === 0;
    els.clearFinished.hidden = !jobs.some((j) => ["done", "error", "cancelled"].includes(j.status));

    const active = jobs.filter((j) => ["queued", "downloading", "processing"].includes(j.status)).length;
    document.title = active ? `(${active}) Media Harvester` : "Media Harvester";
    updateEmpty();
  }

  function updateEmpty() {
    els.empty.hidden = ready.length > 0 || groups.length > 0 || (server && server.jobs.length > 0);
  }

  // ---------------------------------------------------------------- groups

  const groupOf = (item) => groups.find((g) => g.id === item.groupId) || null;
  const groupName = (name) => name.replace(/[<>:"/\\|?*]/g, "").trim() || "New group";

  function newGroup() {
    const taken = new Set(groups.map((g) => g.name));
    let name = "New group";
    for (let n = 2; taken.has(name); n++) name = `New group ${n}`;
    const group = { id: Math.random().toString(36).slice(2), name };
    groups.push(group);
    targetGroup = group.id; // the next links pasted most likely belong here
    renderReady();
    const input = groupEls.get(group.id).name;
    input.focus();
    input.select();
  }

  function removeGroup(group) {
    groups = groups.filter((g) => g !== group);
    ready.forEach((it) => { if (it.groupId === group.id) it.groupId = null; });
    if (targetGroup === group.id) targetGroup = null;
    groupEls.get(group.id).box.remove();
    groupEls.delete(group.id);
    renderReady();
  }

  function groupBox(group) {
    let g = groupEls.get(group.id);
    if (g) return g;
    g = { box: h("section", { class: "group", "aria-label": `Group ${group.name}` }) };
    g.name = h("input", { class: "group-name", type: "text", value: group.name, spellcheck: "false",
      "aria-label": "Group name", maxlength: "80" });
    // Update the name as they type, but only rebuild the menus once they're done
    g.name.addEventListener("input", () => {
      group.name = groupName(g.name.value);
      g.path.textContent = folderFor(group);
    });
    g.name.addEventListener("change", () => { g.name.value = group.name; renderReady(); });
    g.name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); g.name.blur(); } });
    g.count = h("span", { class: "group-count" });
    g.download = h("button", { class: "btn btn-small btn-primary", type: "button", text: "Download group",
      onclick: () => startDownload(ready.filter((it) => it.groupId === group.id && it.status === "ready")) });
    g.path = h("p", { class: "group-path" });
    g.list = h("ul", { class: "cards" });
    g.empty = h("p", { class: "group-empty",
      text: "No links yet. Paste links while “Add new links to” is set to this group, or pick this group from the Group menu on a link." });
    const icon = h("span", { class: "group-icon", "aria-hidden": "true" });
    icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
    g.box.append(
      h("div", { class: "group-head" }, icon, g.name, g.count, h("span", { class: "spacer" }),
        h("button", { class: "btn btn-small btn-quiet", type: "button", text: "Remove group",
          onclick: () => removeGroup(group) }),
        g.download),
      g.path, g.list, g.empty);
    groupEls.set(group.id, g);
    return g;
  }

  function folderFor(group) {
    const base = server ? server.settings.download_dir_display : "your downloads folder";
    return `Saves to ${base}/${group.name}`;
  }

  function renderGroups() {
    groups.forEach((group, i) => {
      const g = groupBox(group);
      const items = ready.filter((it) => it.groupId === group.id);
      const readyHere = items.filter((it) => it.status === "ready").length;
      g.list.replaceChildren(...items.map(readyCard));
      g.list.hidden = items.length === 0;
      g.empty.hidden = items.length > 0;
      g.count.textContent = `${items.length} ${items.length === 1 ? "link" : "links"}`;
      g.download.hidden = readyHere === 0;
      g.download.textContent = readyHere === items.length ? "Download group" : `Download ${readyHere} ready`;
      g.path.textContent = folderFor(group);
      if (document.activeElement !== g.name) g.name.value = group.name;
      if (els.groupList.children[i] !== g.box) els.groupList.insertBefore(g.box, els.groupList.children[i] || null);
    });

    // "Add new links to": only useful once a group exists
    els.targetWrap.hidden = groups.length === 0;
    els.targetGroup.replaceChildren(h("option", { value: "", text: "No group" }),
      ...groups.map((g) => h("option", { value: g.id, text: g.name, selected: g.id === targetGroup })));
  }

  // ---------------------------------------------------------------- server state

  function renderState() {
    els.saveToPath.textContent = server.settings.download_dir_display;
    els.saveTo.title = `Downloads are saved to ${server.settings.download_dir}. Click to change.`;
    els.banner.hidden = server.ffmpeg;
    els.installFfmpeg2.hidden = server.ffmpeg;
    els.ytdlpVersion.textContent = server.yt_dlp_version;
    els.ffmpegStatus.textContent = server.ffmpeg ? "installed" : "not installed";

    const task = server.task;
    const busy = task.running;
    els.installFfmpeg.disabled = els.installFfmpeg2.disabled = els.updateEngine.disabled = busy;
    if (busy && task.name === "ffmpeg") {
      els.installFfmpeg.textContent = "Installing…";
      els.taskNote.textContent = "Installing FFmpeg. This can take a minute or two.";
    } else if (busy) {
      els.taskNote.textContent = "Updating the download engine…";
    } else {
      els.installFfmpeg.textContent = "Install FFmpeg";
      if (task.message) {
        els.taskNote.textContent = task.message;
        els.taskNote.classList.toggle("is-error", task.ok === false);
      }
    }
    if (server._lastTaskMessage !== undefined && task.message && task.message !== server._lastTaskMessage) {
      toast(task.message);
    }

    renderJobs(server.jobs);
  }

  let pollTimer = null;
  let quitting = false;
  let lastTaskMessage;
  async function poll() {
    clearTimeout(pollTimer);
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      const next = await res.json();
      next._initialised = !!server;
      next._lastTaskMessage = lastTaskMessage;
      server = next;
      lastTaskMessage = next.task.message;
      renderState();
    } catch {
      if (quitting) return;
      toast("Lost connection to Media Harvester. Open it again to keep going.");
    }
    const busy = server && (server.task.running ||
      server.jobs.some((j) => ["queued", "downloading", "processing"].includes(j.status)));
    if (!quitting) pollTimer = setTimeout(poll, busy ? 700 : 3000);
  }

  // ---------------------------------------------------------------- events: hopper

  function autosize() {
    els.input.style.height = "auto";
    els.input.style.height = `${Math.min(els.input.scrollHeight, 220)}px`;
  }

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!els.input.value.trim()) { els.input.focus(); return; }
    if (addLinks(els.input.value)) { els.input.value = ""; autosize(); }
  });

  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); els.form.requestSubmit(); }
  });
  els.input.addEventListener("input", autosize);
  els.input.addEventListener("paste", () => {
    // Check pasted links right away; no need to press the button
    setTimeout(() => {
      if (extractLinks(els.input.value).length) els.form.requestSubmit();
    }, 0);
  });

  // Paste anywhere on the page
  document.addEventListener("paste", (e) => {
    const t = e.target;
    if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || els.settings.open) return;
    const text = e.clipboardData && e.clipboardData.getData("text");
    if (text && extractLinks(text).length) { e.preventDefault(); addLinks(text); }
  });

  // Drag a link from another tab onto the page
  let dragDepth = 0;
  const hasLink = (e) => [...(e.dataTransfer?.types || [])].some((t) => t === "text/uri-list" || t === "text/plain");
  document.addEventListener("dragenter", (e) => { if (hasLink(e)) { dragDepth++; els.dropVeil.hidden = false; } });
  document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; els.dropVeil.hidden = true; } });
  document.addEventListener("dragover", (e) => { if (hasLink(e)) e.preventDefault(); });
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    els.dropVeil.hidden = true;
    const text = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
    if (text) addLinks(text);
  });

  // Default "save as" choice for newly added links
  document.querySelectorAll("[data-default-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      defaultMode = btn.dataset.defaultMode;
      savePref("mode", defaultMode);
      syncDefaultMode();
      // Apply to links that are waiting, so the switch does what it looks like it does
      ready.forEach((it) => { if (!(it.info && it.info.audio_only)) it.mode = defaultMode; });
      renderReady();
    });
  });
  function syncDefaultMode() {
    document.querySelectorAll("[data-default-mode]").forEach((btn) => {
      btn.setAttribute("aria-checked", String(btn.dataset.defaultMode === defaultMode));
    });
  }

  els.newGroup.addEventListener("click", newGroup);
  els.targetGroup.addEventListener("change", () => { targetGroup = els.targetGroup.value || null; });

  els.downloadAll.addEventListener("click", () => startDownload(ready.filter((it) => it.status === "ready")));
  els.clearFinished.addEventListener("click", () => api("/api/clear").then(poll).catch((e) => toast(e.message)));
  els.openFolder.addEventListener("click", () => api("/api/open-folder").catch((e) => toast(e.message)));

  // ---------------------------------------------------------------- events: folder & settings

  async function chooseFolder() {
    try {
      const res = await api("/api/choose-folder");
      if (res.changed) {
        server.settings = res.settings;
        els.folderInput.value = res.settings.download_dir;
        renderState();
        toast(`Downloads will be saved to ${res.settings.download_dir_display}`);
      }
      return res.changed;
    } catch (err) {
      toast(err.message);
      return false;
    }
  }

  els.saveTo.addEventListener("click", chooseFolder);
  els.chooseFolder.addEventListener("click", chooseFolder);

  els.openSettings.addEventListener("click", () => {
    if (server) els.folderInput.value = server.settings.download_dir;
    els.folderNote.textContent = "";
    els.settings.showModal();
  });

  async function saveFolder(body) {
    els.folderNote.classList.remove("is-error");
    try {
      const res = await api("/api/settings", body);
      server.settings = res.settings;
      els.folderInput.value = res.settings.download_dir;
      els.folderNote.textContent = "Saved.";
      renderState();
    } catch (err) {
      els.folderNote.textContent = err.message;
      els.folderNote.classList.add("is-error");
    }
  }
  els.saveFolder.addEventListener("click", () => saveFolder({ download_dir: els.folderInput.value }));
  els.folderInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); saveFolder({ download_dir: els.folderInput.value }); }
  });
  els.resetFolder.addEventListener("click", () => saveFolder({ reset: true }));

  const runTask = (path) => () => api(path).then(poll).catch((e) => toast(e.message));
  els.installFfmpeg.addEventListener("click", runTask("/api/install-ffmpeg"));
  els.installFfmpeg2.addEventListener("click", runTask("/api/install-ffmpeg"));
  els.updateEngine.addEventListener("click", runTask("/api/update-ytdlp"));

  // Quitting asks twice when downloads are still running, since they'd be stopped
  els.quitApp.addEventListener("click", async () => {
    const active = server ? server.jobs.filter((j) => ["queued", "downloading", "processing"].includes(j.status)).length : 0;
    if (active && els.quitApp.dataset.armed !== "1") {
      els.quitApp.dataset.armed = "1";
      els.quitApp.textContent = `Stop ${active} ${active === 1 ? "download" : "downloads"} and quit`;
      return;
    }
    try {
      await api("/api/quit");
    } catch { /* already gone */ }
    quitting = true;
    clearTimeout(pollTimer);
    els.settings.close();
    els.quitScreen.hidden = false;
    document.title = "Media Harvester";
  });
  els.settings.addEventListener("close", () => {
    delete els.quitApp.dataset.armed;
    els.quitApp.textContent = "Quit Media Harvester";
  });

  // ---------------------------------------------------------------- go

  syncDefaultMode();
  poll();
  els.input.focus();
})();
