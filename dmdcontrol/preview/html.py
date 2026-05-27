"""HTML assets for the local DMD preview server."""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DMD Bitplane Preview</title>
  <style>
    :root {
      color-scheme: dark;
      --black: #050505;
      --offwhite: #f2efe8;
      --paper: #e9e2d6;
      --muted: #a49f94;
      --line: rgba(242, 239, 232, 0.18);
      --line-strong: rgba(242, 239, 232, 0.34);
      --panel: rgba(242, 239, 232, 0.035);
      --panel-2: rgba(242, 239, 232, 0.065);
      --orange: #ff4401;
      --orange-dim: rgba(255, 68, 1, 0.12);
      --stage: #000000;
      --green: #61d394;
      --blue: #7ab7ff;
      --red: #ff7a6f;
      --amber: #ffb84d;
      --font-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --font-mono: "SFMono-Regular", "Cascadia Code", "Roboto Mono", Consolas, "Liberation Mono", monospace;
      --page-pad: clamp(8px, 1vw, 14px);
      --control-h: 36px;
      --control-radius: 2px;
      --transition-speed: 160ms ease;
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    html {
      background: var(--black);
      color: var(--offwhite);
      font-family: var(--font-sans);
      font-size: 16px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    body {
      margin: 0;
      background:
        linear-gradient(rgba(255, 68, 1, 0.018) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 68, 1, 0.018) 1px, transparent 1px),
        radial-gradient(circle at 78% 24%, rgba(255, 68, 1, 0.055), transparent 34vw),
        var(--black);
      background-size: 44px 44px, 44px 44px, auto, auto;
      overflow: hidden;
    }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    button, select, input { color-scheme: dark; }

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--black); }
    ::-webkit-scrollbar-thumb { background: var(--line-strong); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

    .dashboard {
      width: 100vw;
      height: 100vh;
      min-height: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      gap: var(--page-pad);
      padding: var(--page-pad);
    }

    .stage {
      min-width: 0;
      min-height: 0;
      display: grid;
    }
    .preview-card {
      min-width: 0;
      min-height: 0;
      display: grid;
      overflow: hidden;
      border: 1px solid var(--line);
      background: rgba(0, 0, 0, 0.82);
      box-shadow: inset 0 0 0 1px rgba(255, 68, 1, 0.035), 0 24px 60px rgba(0, 0, 0, 0.42);
    }
    .state-cache { display: none; }
    .image-wrap {
      min-width: 0;
      min-height: 0;
      width: 100%;
      height: 100%;
      background: var(--stage);
      background-size: 24px 24px, 24px 24px, auto;
      display: grid;
      place-items: center;
      overflow: auto;
    }
    img {
      display: block;
      width: auto;
      height: auto;
      max-width: 100%;
      max-height: 100%;
      image-rendering: pixelated;
    }

    .control-panel {
      min-width: 0;
      display: grid;
    }
    .command-deck { min-width: 0; display: grid; }
    .control-surface {
      min-width: 0;
      min-height: 114px;
      display: grid;
      grid-template-columns: 190px minmax(0, 1fr) 218px;
      border: 1px solid var(--line);
      background: rgba(5, 5, 5, 0.92);
      overflow: hidden;
    }
    .control-section {
      min-width: 0;
      display: grid;
      align-content: start;
      gap: 0.7rem;
      padding: 0.82rem;
      border-left: 1px solid var(--line);
      background: rgba(242, 239, 232, 0.025);
    }
    .control-section:first-child { border-left: 0; }
    .source-section, .refresh-section, .live-section { min-width: 0; }

    .card-title,
    .field-label,
    .plane-title,
    .source-toggle .option,
    .segmented button,
    .auto-toggle,
    .refresh-button,
    .status,
    .lut-entry,
    .live-title,
    .state-token,
    .route-token {
      font-family: var(--font-mono);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .card-title,
    .field-label,
    .plane-title {
      color: var(--orange);
      font-size: 0.68rem;
      font-weight: 700;
      line-height: 1;
    }
    .card-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--line);
    }

    label {
      min-width: 0;
      display: grid;
      gap: 0.35rem;
    }
    select,
    input[type="number"] {
      width: 100%;
      min-width: 0;
      height: var(--control-h);
      border: 1px solid var(--line);
      border-radius: var(--control-radius);
      background: rgba(242, 239, 232, 0.045);
      color: var(--offwhite);
      font-size: 0.82rem;
      padding: 0.42rem 0.55rem;
      outline: none;
    }
    select option { background: #111; color: var(--offwhite); }
    select:focus,
    input[type="number"]:focus,
    button:focus-visible {
      border-color: var(--orange);
      box-shadow: 0 0 0 3px rgba(255, 68, 1, 0.18);
      outline: none;
    }

    .source-toggle {
      position: relative;
      display: grid;
      grid-template-columns: 1fr 1fr;
      width: 100%;
      min-height: var(--control-h);
      padding: 3px;
      border: 1px solid var(--line-strong);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.04);
      color: var(--muted);
      user-select: none;
    }
    .source-toggle input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }
    .source-toggle .thumb {
      position: absolute;
      inset: 3px auto 3px 3px;
      width: calc(50% - 3px);
      border-radius: 1px;
      background: var(--orange);
      transition: transform var(--transition-speed);
    }
    .source-toggle input:checked + .thumb { transform: translateX(100%); }
    .source-toggle .option {
      position: relative;
      z-index: 1;
      display: grid;
      place-items: center;
      min-width: 0;
      font-size: 0.74rem;
      font-weight: 700;
    }
    .source-toggle input:not(:checked) ~ .offline-option,
    .source-toggle input:checked ~ .live-option {
      color: var(--black);
    }
    .source-meta { display: none; }

    .offline-controls {
      min-width: 0;
      display: grid;
      grid-template-columns: minmax(360px, 1.05fr) minmax(390px, 0.95fr);
      gap: 0;
    }
    .offline-controls[hidden],
    .live-section[hidden],
    .plane-panel[hidden] { display: none; }
    .offline-controls .control-section { border-left: 1px solid var(--line); }
    .control-group { min-width: 0; }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(96px, 1fr));
      gap: 0.55rem;
    }
    .view-grid {
      display: grid;
      grid-template-columns: minmax(160px, 0.8fr) minmax(96px, 0.5fr);
      gap: 0.55rem;
      align-items: end;
    }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 3px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.04);
    }
    .segmented button {
      min-height: calc(var(--control-h) - 8px);
      border: 0;
      border-radius: 1px;
      background: transparent;
      color: var(--muted);
      font-size: 0.74rem;
      font-weight: 700;
    }
    .segmented button.active {
      background: var(--offwhite);
      color: var(--black);
    }
    .plane-panel {
      min-width: 0;
      padding: 0.5rem;
      border: 1px solid var(--line);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.035);
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
      gap: 0.55rem;
    }
    .plane-grid {
      min-width: 0;
      display: grid;
      grid-template-columns: repeat(8, minmax(34px, 1fr));
      gap: 4px;
    }
    .plane-chip {
      min-width: 0;
      min-height: 28px;
      border: 1px solid var(--line);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.035);
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0 4px;
    }
    .plane-chip.active {
      border-color: var(--orange);
      background: var(--orange-dim);
      color: var(--orange);
    }
    .plane-chip[data-channel="G"].active { border-color: var(--green); color: var(--green); background: rgba(97, 211, 148, 0.10); }
    .plane-chip[data-channel="R"].active { border-color: var(--red); color: var(--red); background: rgba(255, 122, 111, 0.10); }
    .plane-chip[data-channel="B"].active { border-color: var(--blue); color: var(--blue); background: rgba(122, 183, 255, 0.10); }

    .live-section {
      grid-template-columns: auto minmax(0, 1fr);
      align-items: start;
    }
    .live-dot {
      width: 10px;
      height: 10px;
      margin-top: 0.2rem;
      border-radius: 999px;
      background: var(--amber);
      box-shadow: 0 0 0 5px rgba(255, 184, 77, 0.12);
    }
    .live-section.available .live-dot {
      background: var(--orange);
      box-shadow: 0 0 0 5px var(--orange-dim);
    }
    .live-title {
      color: var(--offwhite);
      font-size: 0.88rem;
      font-weight: 700;
    }
    .live-info {
      min-width: 0;
      display: grid;
      gap: 0.4rem;
    }
    .live-copy,
    .lut-summary {
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.35;
    }
    .lut-grid {
      min-width: 0;
      max-height: 62px;
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem;
      overflow: auto;
    }
    .lut-entry {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 23px;
      min-width: 52px;
      padding: 0.12rem 0.35rem;
      border: 1px solid var(--line);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.035);
      color: var(--muted);
      font-size: 0.66rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .lut-entry[data-channel="G"] { color: var(--green); border-color: rgba(97, 211, 148, 0.5); background: rgba(97, 211, 148, 0.08); }
    .lut-entry[data-channel="R"] { color: var(--red); border-color: rgba(255, 122, 111, 0.5); background: rgba(255, 122, 111, 0.08); }
    .lut-entry[data-channel="B"] { color: var(--blue); border-color: rgba(122, 183, 255, 0.5); background: rgba(122, 183, 255, 0.08); }

    .refresh-section { align-content: start; }
    .refresh-actions {
      min-width: 0;
      display: grid;
      gap: 0.55rem;
    }
    .auto-refresh-controls {
      min-width: 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 92px;
      gap: 0.55rem;
      align-items: end;
    }
    .auto-toggle {
      min-width: 0;
      min-height: var(--control-h);
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.42rem 0.55rem;
      border: 1px solid var(--line);
      border-radius: 2px;
      background: rgba(242, 239, 232, 0.035);
      color: var(--offwhite);
      font-size: 0.74rem;
      font-weight: 700;
      user-select: none;
    }
    .auto-toggle input {
      width: 15px;
      height: 15px;
      accent-color: var(--orange);
    }
    .refresh-button {
      width: 100%;
      height: var(--control-h);
      border: 1px solid var(--orange);
      border-radius: 2px;
      background: var(--orange);
      color: var(--black);
      font-size: 0.78rem;
      font-weight: 800;
      padding: 0 1rem;
      transition: background var(--transition-speed), color var(--transition-speed), border-color var(--transition-speed);
    }
    .refresh-button:hover {
      background: var(--offwhite);
      border-color: var(--offwhite);
      color: var(--black);
    }
    .status {
      min-height: 16px;
      color: var(--muted);
      font-size: 0.7rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    @media (max-width: 1180px) {
      body { overflow: auto; }
      .dashboard { height: auto; min-height: 100vh; }
      .stage { min-height: 60vh; }
      .control-surface { grid-template-columns: 1fr; }
      .control-section,
      .offline-controls .control-section { border-left: 0; border-top: 1px solid var(--line); }
      .control-section:first-child { border-top: 0; }
      .offline-controls { grid-template-columns: 1fr; }
      .field-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    }
    @media (max-width: 680px) {
      .dashboard { padding: 8px; gap: 8px; }
      .stage { min-height: 52vh; }
      .field-grid,
      .view-grid,
      .plane-panel,
      .auto-refresh-controls { grid-template-columns: 1fr; }
      .plane-grid { grid-template-columns: repeat(4, minmax(44px, 1fr)); }
    }
  </style>
</head>
<body>
  <main class="dashboard">
    <section class="stage" aria-label="DMD preview viewport">
      <article class="preview-card">
        <div class="state-cache" aria-hidden="true">
          <span class="state-token source-offline" id="sourceBadge">offline</span>
          <span class="state-token" id="layoutBadge">paired</span>
          <span class="state-token" id="testBadge">coarse-grid</span>
          <span class="state-token" id="viewBadge">packed frame</span>
          <span class="state-token" id="frameBadge">frame 0</span>
          <span class="route-token route-start">B DP-0 left</span>
          <span class="route-token">A DP-2 right</span>
          <span class="state-token muted" id="liveStatus">no live frame</span>
        </div>
        <div class="image-wrap">
          <img id="preview" alt="DMD preview">
        </div>
      </article>
    </section>

    <section class="control-panel" aria-label="DMD preview controls">
      <div class="command-deck">
        <div class="control-surface">
          <section class="control-section source-section">
            <div class="card-title">Source</div>
            <label class="source-toggle" for="sourceSwitch">
              <input id="sourceSwitch" type="checkbox">
              <span class="thumb"></span>
              <span class="option offline-option">Offline</span>
              <span class="option live-option">Live</span>
            </label>
            <div class="source-meta" id="sourceMeta">Offline simulated frames</div>
          </section>

          <div class="offline-controls" id="offlineControls">
            <section class="control-section control-group">
              <div class="card-title">Pattern</div>
              <div class="field-grid">
                <label><span class="field-label">Layout</span>
                  <select id="layout">
                    <option value="pair">Paired</option>
                    <option value="single">Single</option>
                  </select>
                </label>
                <label><span class="field-label">Test</span>
                  <select id="test"></select>
                </label>
                <label><span class="field-label">A</span>
                  <select id="testA"></select>
                </label>
                <label><span class="field-label">B</span>
                  <select id="testB"></select>
                </label>
              </div>
            </section>

            <section class="control-section control-group">
              <div class="card-title">Render</div>
              <div class="view-grid">
                <label><span class="field-label">View</span>
                  <div class="segmented" id="viewControl">
                    <button type="button" data-view="packed">Packed</button>
                    <button type="button" data-view="bitplane">Bitplane</button>
                  </div>
                </label>
                <label><span class="field-label">Frame</span>
                  <input id="frame" type="number" min="0" step="1" value="0">
                </label>
              </div>
              <div class="plane-panel" id="planePanel" hidden>
                <div class="plane-title">Plane</div>
                <div class="plane-grid" id="planeButtons"></div>
              </div>
            </section>
          </div>

          <section class="control-section live-section" id="liveControls" hidden>
            <span class="live-dot" aria-hidden="true"></span>
            <div class="live-info">
              <div class="live-title">Live</div>
              <div class="live-copy" id="liveCopy">Waiting for posted frames</div>
              <div class="lut-summary" id="lutSummary">No LUT metadata yet</div>
              <div class="lut-grid" id="lutEntries" aria-label="Live LUT entries"></div>
            </div>
          </section>

          <section class="control-section refresh-section">
            <div class="card-title">Refresh</div>
            <div class="refresh-actions">
              <button class="refresh-button" id="refresh" type="button">Refresh</button>
              <div class="auto-refresh-controls">
                <label class="auto-toggle">
                  <input id="autoRefresh" type="checkbox">
                  <span>Auto</span>
                </label>
                <label><span class="field-label">Every</span>
                  <select id="autoInterval">
                    <option value="1">1 sec</option>
                    <option value="5" selected>5 sec</option>
                    <option value="10">10 sec</option>
                    <option value="60">60 sec</option>
                  </select>
                </label>
              </div>
              <div class="status" id="status"></div>
            </div>
          </section>
        </div>
      </div>
    </section>
  </main>
  <script>
    const els = {
      sourceSwitch: document.getElementById("sourceSwitch"),
      offlineControls: document.getElementById("offlineControls"),
      liveControls: document.getElementById("liveControls"),
      liveCopy: document.getElementById("liveCopy"),
      lutSummary: document.getElementById("lutSummary"),
      lutEntries: document.getElementById("lutEntries"),
      layout: document.getElementById("layout"),
      test: document.getElementById("test"),
      testA: document.getElementById("testA"),
      testB: document.getElementById("testB"),
      viewButtons: Array.from(document.querySelectorAll("[data-view]")),
      planePanel: document.getElementById("planePanel"),
      planeButtons: document.getElementById("planeButtons"),
      frame: document.getElementById("frame"),
      refresh: document.getElementById("refresh"),
      autoRefresh: document.getElementById("autoRefresh"),
      autoInterval: document.getElementById("autoInterval"),
      preview: document.getElementById("preview"),
      status: document.getElementById("status"),
      liveStatus: document.getElementById("liveStatus"),
      sourceBadge: document.getElementById("sourceBadge"),
      sourceMeta: document.getElementById("sourceMeta"),
      layoutBadge: document.getElementById("layoutBadge"),
      testBadge: document.getElementById("testBadge"),
      viewBadge: document.getElementById("viewBadge"),
      frameBadge: document.getElementById("frameBadge")
    };
    let config = null;
    let currentView = "packed";
    let currentPlane = "G0";
    let autoRefreshTimer = null;
    let autoRefreshRunning = false;

    function fillSelect(select, values, includeAuto) {
      select.innerHTML = "";
      if (includeAuto) {
        const auto = document.createElement("option");
        auto.value = "";
        auto.textContent = "(default)";
        select.appendChild(auto);
      }
      values.forEach(value => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
    }

    function activeTests() {
      return els.layout.value === "pair" ? config.pair_tests : config.single_tests;
    }

    function refreshModeOptions() {
      const current = els.test.value;
      const tests = activeTests();
      fillSelect(els.test, tests, false);
      els.test.value = tests.includes(current) ? current : (tests.includes("coarse-grid") ? "coarse-grid" : tests[0]);
      const paired = els.layout.value === "pair";
      els.testA.disabled = !paired;
      els.testB.disabled = !paired;
    }

    function buildPlaneButtons() {
      els.planeButtons.innerHTML = "";
      config.bitplanes.forEach(label => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "plane-chip";
        button.dataset.plane = label;
        button.dataset.channel = label[0];
        button.textContent = label;
        button.addEventListener("click", () => {
          currentPlane = label;
          syncPlaneButtons();
          refreshImage();
        });
        els.planeButtons.appendChild(button);
      });
      syncPlaneButtons();
    }

    function syncPlaneButtons() {
      Array.from(els.planeButtons.children).forEach(button => {
        button.classList.toggle("active", button.dataset.plane === currentPlane);
      });
    }

    function setView(view) {
      currentView = view;
      els.viewButtons.forEach(button => {
        button.classList.toggle("active", button.dataset.view === currentView);
      });
      els.planePanel.hidden = currentView !== "bitplane";
      updateBadge();
    }

    function syncSourceMode() {
      const live = els.sourceSwitch.checked;
      els.offlineControls.hidden = live;
      els.liveControls.hidden = !live;
      els.sourceMeta.textContent = live ? "Latest posted packed frame" : "Offline simulated frames";
      updateBadge();
    }

    function formatUs(value) {
      if (value === undefined || value === null || value === "") return "?";
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return String(value);
      return numeric.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " us";
    }

    function formatHz(value) {
      if (value === undefined || value === null || value === "") return "?";
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return String(value);
      return numeric.toLocaleString(undefined, { maximumFractionDigits: 3 }) + " Hz";
    }

    function renderLutInfo(metadata) {
      const lut = metadata && metadata.lut;
      const entries = lut && Array.isArray(lut.entries) ? lut.entries : [];
      if (!entries.length) {
        els.lutSummary.textContent = "No LUT metadata posted by live run";
        els.lutEntries.innerHTML = "";
        return;
      }

      const timing = lut.timing || {};
      const first = entries[0] || {};
      const sequence = timing.total_sequence_us !== undefined
        ? " · sequence " + formatUs(timing.total_sequence_us)
        : "";
      const hz = timing.effective_frame_hz !== undefined
        ? " · VSYNC " + formatHz(timing.effective_frame_hz)
        : "";
      const source = timing.timing_source ? " · " + timing.timing_source : "";
      els.lutSummary.textContent =
        entries.length + " LUT entries · exposure " + formatUs(timing.exposure_us ?? first.exposure_us) +
        " · dark " + formatUs(timing.dark_us ?? first.dark_us) + sequence + hz + source;

      els.lutEntries.innerHTML = "";
      entries.forEach(entry => {
        const chip = document.createElement("span");
        chip.className = "lut-entry";
        chip.dataset.channel = (entry.plane_label || "?")[0] || "?";
        const start = formatUs(entry.start_us);
        const end = formatUs(entry.end_us);
        chip.textContent = String(entry.index).padStart(2, "0") + " " + entry.plane_label + " " + start + "-" + end;
        els.lutEntries.appendChild(chip);
      });
    }

    function updateLiveStatus(available, metadata) {
      const text = available ? "live frame available" : "no live frame";
      els.liveStatus.textContent = text;
      els.liveStatus.className = available ? "state-token good" : "state-token muted";
      els.liveCopy.textContent = available ? "latest posted packed frame" : "No live frame";
      els.liveControls.classList.toggle("available", Boolean(available));
      renderLutInfo(metadata || {});
    }

    function updateBadge() {
      if (els.sourceSwitch.checked) {
        els.sourceBadge.textContent = "live";
        els.sourceBadge.className = "state-token source-live";
        els.layoutBadge.textContent = "paired mirror";
        els.testBadge.textContent = "latest posted frame";
        els.viewBadge.textContent = "packed frame";
        els.frameBadge.textContent = "live";
        return;
      }
      const layout = els.layout.value === "pair" ? "Paired" : "Single";
      const view = currentView === "bitplane" ? currentPlane + " bitplane" : "packed frame";
      els.sourceBadge.textContent = "offline";
      els.sourceBadge.className = "state-token source-offline";
      els.layoutBadge.textContent = layout.toLowerCase();
      els.testBadge.textContent = els.test.value || "test";
      els.viewBadge.textContent = view;
      els.frameBadge.textContent = "frame " + (els.frame.value || "0");
    }

    function imageUrl() {
      const params = new URLSearchParams();
      if (els.sourceSwitch.checked) {
        params.set("view", "packed");
        params.set("_", String(Date.now()));
        return "/api/live-frame.png?" + params.toString();
      }
      params.set("layout", els.layout.value);
      params.set("test", els.test.value);
      params.set("frame", els.frame.value || "0");
      params.set("view", currentView);
      params.set("plane", currentPlane);
      if (els.layout.value === "pair") {
        if (els.testA.value) params.set("test_a", els.testA.value);
        if (els.testB.value) params.set("test_b", els.testB.value);
      }
      params.set("_", String(Date.now()));
      return "/api/frame.png?" + params.toString();
    }

    async function refreshLiveConfig() {
      const response = await fetch("/api/config");
      config = await response.json();
      updateLiveStatus(config.live_frame_available, config.live_metadata);
    }

    async function refreshImage() {
      syncSourceMode();
      els.status.textContent = "loading";
      if (els.sourceSwitch.checked) {
        await refreshLiveConfig();
      }
      els.preview.onload = () => { els.status.textContent = "ready"; };
      els.preview.onerror = () => { els.status.textContent = "image unavailable"; };
      els.preview.src = imageUrl();
    }

    function stopAutoRefreshTimer() {
      if (autoRefreshTimer !== null) {
        window.clearTimeout(autoRefreshTimer);
        autoRefreshTimer = null;
      }
    }

    function autoRefreshDelayMs() {
      const seconds = Number(els.autoInterval.value);
      return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : 5000;
    }

    function scheduleAutoRefresh() {
      stopAutoRefreshTimer();
      if (!els.autoRefresh.checked) return;
      autoRefreshTimer = window.setTimeout(runAutoRefresh, autoRefreshDelayMs());
    }

    async function runAutoRefresh() {
      if (!els.autoRefresh.checked) return;
      if (autoRefreshRunning) {
        scheduleAutoRefresh();
        return;
      }

      autoRefreshRunning = true;
      try {
        await refreshImage();
      } catch (error) {
        els.status.textContent = error.message;
      } finally {
        autoRefreshRunning = false;
        scheduleAutoRefresh();
      }
    }

    function syncAutoRefresh() {
      stopAutoRefreshTimer();
      if (els.autoRefresh.checked) {
        refreshImage().catch(error => { els.status.textContent = error.message; });
        scheduleAutoRefresh();
      }
    }

    async function loadConfig() {
      const response = await fetch("/api/config");
      config = await response.json();
      fillSelect(els.testA, config.static_pair_tests, true);
      fillSelect(els.testB, config.static_pair_tests, true);
      currentPlane = config.bitplanes[0] || "G0";
      updateLiveStatus(config.live_frame_available, config.live_metadata);
      refreshModeOptions();
      buildPlaneButtons();
      setView("packed");
      syncSourceMode();
      refreshImage();
    }

    els.layout.addEventListener("change", () => { refreshModeOptions(); refreshImage(); });
    [els.test, els.testA, els.testB, els.frame].forEach(el => {
      el.addEventListener("change", refreshImage);
    });
    els.viewButtons.forEach(button => {
      button.addEventListener("click", () => {
        setView(button.dataset.view);
        refreshImage();
      });
    });
    els.sourceSwitch.addEventListener("change", refreshImage);
    els.refresh.addEventListener("click", refreshImage);
    els.autoRefresh.addEventListener("change", syncAutoRefresh);
    els.autoInterval.addEventListener("change", scheduleAutoRefresh);
    window.addEventListener("beforeunload", stopAutoRefreshTimer);
    loadConfig().catch(error => { els.status.textContent = error.message; });
  </script>
</body>
</html>
"""
