"""Local HTTP server for DMD packed-frame and bitplane previews."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dmd_preview_render import (
    BITPLANE_LABELS,
    LiveFrameStore,
    render_png_bytes,
    render_preview_png,
    render_view_image,
)
from paired_pattern_engine import PAIR_TESTS, STATIC_PAIR_TESTS
from pattern_modes import PATTERN_NAMES

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DMD Bitplane Preview</title>
  <style>
    :root {
      color-scheme: dark;
      --app: #171717;
      --app-2: #222327;
      --panel: #f8fafc;
      --panel-2: #ffffff;
      --ink: #101828;
      --muted: #667085;
      --muted-2: #98a2b3;
      --line: #d0d7e2;
      --line-strong: #98a2b3;
      --stage: #05070a;
      --accent: #0f766e;
      --accent-strong: #0b5f59;
      --blue: #175cd3;
      --amber: #b54708;
      --green: #087443;
      --red: #b42318;
      --control-h: 36px;
      --control-radius: 6px;
      --control-gap: 8px;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--app);
      overflow: hidden;
    }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    .topbar {
      height: 54px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 16px;
      color: #f8fafc;
      background: #202124;
      border-bottom: 1px solid #33353b;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .brand-mark {
      width: 12px;
      height: 28px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.18);
    }
    h1 {
      margin: 0;
      font-size: 17px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .subtitle {
      margin-top: 2px;
      color: var(--muted-2);
      font-size: 11px;
    }
    .top-badges {
      min-width: 0;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .badge,
    .status-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      padding: 3px 9px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 999px;
      color: #e4e7ec;
      background: rgba(255, 255, 255, 0.07);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .badge.green,
    .status-pill.green {
      color: #d3f8df;
      border-color: rgba(75, 222, 128, 0.28);
      background: rgba(22, 101, 52, 0.32);
    }
    .badge.blue,
    .status-pill.blue {
      color: #d1e9ff;
      border-color: rgba(83, 177, 253, 0.32);
      background: rgba(24, 73, 169, 0.34);
    }
    .badge.amber,
    .status-pill.amber {
      color: #fedf89;
      border-color: rgba(247, 144, 9, 0.35);
      background: rgba(122, 79, 1, 0.34);
    }
    .app-shell {
      height: 100vh;
      min-height: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      gap: 12px;
      padding: 12px 12px 0;
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
      grid-template-rows: auto minmax(0, 1fr);
      overflow: hidden;
      border: 1px solid #33353b;
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 18px 38px rgba(0, 0, 0, 0.26);
    }
    .preview-titlebar {
      min-width: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    .preview-kicker {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    h2 {
      margin: 2px 0 0;
      color: var(--ink);
      font-size: 16px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    .preview-badge-row {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 6px;
      flex-wrap: wrap;
    }
    .preview-badge-row .badge,
    .preview-status-strip .status-pill,
    .preview-status-strip .state-token,
    .preview-status-strip .route-token {
      color: #344054;
      border-color: var(--line);
      background: #f2f4f7;
    }
    .preview-badge-row .badge.route {
      color: #1849a9;
      border-color: #b2ddff;
      background: #eff8ff;
    }
    .preview-status-strip {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-bottom: 1px solid var(--line);
      background: #eef2f6;
      overflow: hidden;
    }
    .preview-status-strip .status-pill,
    .preview-status-strip .state-token,
    .preview-status-strip .route-token {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      padding: 3px 9px;
      border: 1px solid var(--line);
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      min-width: 0;
      max-width: 240px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .preview-status-strip .route-start {
      margin-left: auto;
    }
    .preview-status-strip .route-token {
      color: #1849a9;
      border-color: #b2ddff;
      background: #eff8ff;
    }
    .state-token.source-live {
      color: #1849a9;
      border-color: #b2ddff;
      background: #eff8ff;
    }
    .state-token.source-offline {
      color: #475467;
      border-color: var(--line);
      background: #fff;
    }
    .state-token.good {
      color: #067647;
      border-color: #abefc6;
      background: #ecfdf3;
    }
    .state-token.muted {
      color: #475467;
      border-color: var(--line);
      background: #fff;
    }
    .image-wrap {
      min-height: 0;
      margin: 10px;
      border: 1px solid #24272d;
      border-radius: 6px;
      background: var(--stage);
      display: grid;
      place-items: center;
      overflow: auto;
    }
    img {
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      image-rendering: pixelated;
      display: block;
    }
    .bottom-panel {
      margin: 0 -12px;
      padding: 10px 12px 12px;
      border-top: 1px solid #33353b;
      background: #202124;
      box-shadow: 0 -16px 34px rgba(0, 0, 0, 0.28);
    }
    .command-deck {
      display: grid;
    }
    .control-surface {
      min-width: 0;
      min-height: 112px;
      display: grid;
      grid-template-columns: 216px minmax(0, 1fr) 156px;
      border: 1px solid #d0d7e2;
      border-radius: 8px;
      background: var(--panel-2);
      box-shadow: 0 10px 22px rgba(0, 0, 0, 0.14);
      overflow: hidden;
    }
    .control-section {
      min-width: 0;
      display: grid;
      align-content: start;
      gap: var(--control-gap);
      padding: 12px;
      border-left: 1px solid var(--line);
    }
    .control-section:first-child {
      border-left: 0;
    }
    .source-section,
    .refresh-section,
    .live-section {
      min-width: 0;
    }
    .card-title,
    .source-label,
    .field-label,
    .plane-title {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .card-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: #344054;
    }
    .source-toggle {
      position: relative;
      display: grid;
      grid-template-columns: 1fr 1fr;
      width: 100%;
      min-height: var(--control-h);
      padding: 3px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      background: #eef2f6;
      color: #475467;
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
      border-radius: 999px;
      background: #fff;
      box-shadow: 0 2px 6px rgba(16, 24, 40, 0.22);
      transition: transform 140ms ease;
    }
    .source-toggle input:checked + .thumb {
      transform: translateX(100%);
    }
    .source-toggle .option {
      position: relative;
      z-index: 1;
      display: grid;
      place-items: center;
      min-width: 0;
      font-size: 13px;
      font-weight: 700;
    }
    .source-toggle input:not(:checked) ~ .offline-option,
    .source-toggle input:checked ~ .live-option {
      color: var(--ink);
    }
    .source-meta,
    .live-copy,
    .status {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .offline-controls {
      min-width: 0;
      display: grid;
      grid-template-columns: minmax(360px, 1.05fr) minmax(420px, 0.95fr);
      gap: 0;
    }
    .offline-controls[hidden],
    .live-section[hidden],
    .plane-panel[hidden] {
      display: none;
    }
    .offline-controls .control-section {
      border-left: 1px solid var(--line);
    }
    .control-group {
      min-width: 0;
    }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(96px, 1fr));
      gap: 8px;
    }
    .view-grid {
      display: grid;
      grid-template-columns: minmax(160px, 0.8fr) minmax(96px, 0.5fr);
      gap: 8px;
      align-items: end;
    }
    label {
      min-width: 0;
      display: grid;
      gap: 5px;
    }
    select,
    input[type="number"] {
      width: 100%;
      min-width: 0;
      height: var(--control-h);
      border: 1px solid var(--line);
      border-radius: var(--control-radius);
      background: #fff;
      color: var(--ink);
      font-size: 13px;
      padding: 6px 8px;
      outline: none;
    }
    select:focus,
    input[type="number"]:focus,
    button:focus-visible {
      border-color: #53b1fd;
      box-shadow: 0 0 0 3px rgba(83, 177, 253, 0.24);
    }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 3px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef2f6;
    }
    .segmented button {
      min-height: calc(var(--control-h) - 8px);
      border: 0;
      border-radius: var(--control-radius);
      background: transparent;
      color: #475467;
      font-size: 13px;
      font-weight: 700;
    }
    .segmented button.active {
      background: #fff;
      color: var(--ink);
      box-shadow: 0 1px 4px rgba(16, 24, 40, 0.18);
    }
    .plane-panel {
      min-width: 0;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
      gap: 8px;
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
      border-radius: var(--control-radius);
      background: #fff;
      color: #344054;
      font-size: 12px;
      font-weight: 700;
      padding: 0 4px;
    }
    .plane-chip[data-channel="G"].active {
      border-color: var(--green);
      background: #dcfae6;
      color: #074d31;
    }
    .plane-chip[data-channel="R"].active {
      border-color: var(--red);
      background: #fee4e2;
      color: #7a271a;
    }
    .plane-chip[data-channel="B"].active {
      border-color: var(--blue);
      background: #d1e9ff;
      color: #1849a9;
    }
    .live-section {
      grid-template-columns: auto minmax(0, 1fr);
      align-items: start;
    }
    .live-dot {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: var(--amber);
      box-shadow: 0 0 0 5px rgba(181, 71, 8, 0.12);
    }
    .live-section.available .live-dot {
      background: var(--blue);
      box-shadow: 0 0 0 5px rgba(23, 92, 211, 0.14);
    }
    .live-title {
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
    }
    .live-info {
      min-width: 0;
      display: grid;
      gap: 6px;
    }
    .lut-summary {
      color: #344054;
      font-size: 12px;
      line-height: 1.35;
    }
    .lut-grid {
      min-width: 0;
      max-height: 62px;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      overflow: auto;
    }
    .lut-entry {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      min-width: 52px;
      padding: 2px 6px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #344054;
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }
    .lut-entry[data-channel="G"] {
      color: #074d31;
      border-color: #abefc6;
      background: #ecfdf3;
    }
    .lut-entry[data-channel="R"] {
      color: #7a271a;
      border-color: #fecdca;
      background: #fef3f2;
    }
    .lut-entry[data-channel="B"] {
      color: #1849a9;
      border-color: #b2ddff;
      background: #eff8ff;
    }
    .refresh-section {
      align-content: center;
    }
    .refresh-button {
      width: 100%;
      height: var(--control-h);
      border: 1px solid var(--accent-strong);
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      padding: 0 16px;
    }
    .refresh-button:hover {
      background: var(--accent-strong);
    }
    .status {
      min-height: 16px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    @media (max-width: 1220px) {
      body { overflow: auto; }
      .app-shell { height: auto; min-height: calc(100vh - 54px); }
      .stage { min-height: 420px; }
      .control-surface { grid-template-columns: 1fr; }
      .control-section,
      .offline-controls .control-section { border-left: 0; border-top: 1px solid var(--line); }
      .control-section:first-child { border-top: 0; }
      .offline-controls { grid-template-columns: 1fr; }
      .field-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    }
    @media (max-width: 680px) {
      .topbar { height: auto; min-height: 54px; align-items: flex-start; padding: 10px 12px; }
      .top-badges { justify-content: flex-start; }
      .preview-titlebar { align-items: flex-start; flex-direction: column; }
      .preview-status-strip { flex-wrap: wrap; }
      .field-grid,
      .view-grid,
      .plane-panel { grid-template-columns: 1fr; }
      .plane-grid { grid-template-columns: repeat(4, minmax(44px, 1fr)); }
    }
  </style>
</head>
<body>
  <main class="app-shell">
    <section class="stage">
      <article class="preview-card">
        <div class="preview-status-strip">
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
    <section class="bottom-panel">
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
            <div class="live-title">Live mirror</div>
            <div class="live-copy" id="liveCopy">Waiting for posted frames</div>
            <div class="lut-summary" id="lutSummary">No LUT metadata yet</div>
            <div class="lut-grid" id="lutEntries" aria-label="Live LUT entries"></div>
          </div>
        </section>
        <section class="control-section refresh-section">
          <button class="refresh-button" id="refresh" type="button">Refresh</button>
          <div class="status" id="status"></div>
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
      els.liveCopy.textContent = available ? "Showing latest posted packed frame" : "No live frame has been posted";
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
    loadConfig().catch(error => { els.status.textContent = error.message; });
  </script>
</body>
</html>
"""


class DmdPreviewHandler(BaseHTTPRequestHandler):
    server_version = "DmdPreview/1.0"

    def log_message(self, _format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/config":
                self._send_json(self._config_payload())
            elif parsed.path == "/api/frame.png":
                self._send_offline_frame(params)
            elif parsed.path == "/api/live-frame.png":
                self._send_live_frame(params)
            else:
                self.send_error(404, "not found")
        except ValueError as exc:
            self.send_error(400, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/live-frame":
            self.send_error(404, "not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        metadata = {}
        raw_metadata = self.headers.get("X-DMD-Metadata")
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                metadata = {}
        try:
            self.server.live_store.set_png(body, metadata=metadata)
        except Exception as exc:
            self.send_error(400, str(exc))
            return
        self.send_response(204)
        self.end_headers()

    def _config_payload(self):
        metadata, updated_at = self.server.live_store.get_metadata()
        return {
            "default_layout": "pair",
            "single_tests": list(PATTERN_NAMES),
            "pair_tests": list(PAIR_TESTS),
            "static_pair_tests": list(STATIC_PAIR_TESTS),
            "bitplanes": list(BITPLANE_LABELS),
            "live_frame_available": self.server.live_store.has_frame(),
            "live_metadata": metadata,
            "live_updated_at": updated_at,
        }

    def _send_offline_frame(self, params):
        layout = _query_value(params, "layout", "pair")
        test = _query_value(params, "test", "coarse-grid")
        test_a = _query_value(params, "test_a", None)
        test_b = _query_value(params, "test_b", None)
        frame_index = _query_int(params, "frame", 0)
        view = _query_value(params, "view", "packed")
        plane = _query_plane(params, "plane", 0)
        png = render_preview_png(
            layout=layout,
            test=test,
            test_a=test_a,
            test_b=test_b,
            frame_index=frame_index,
            view=view,
            plane=plane,
        )
        self._send_bytes(png, "image/png")

    def _send_live_frame(self, params):
        frame, _metadata, _updated_at = self.server.live_store.get_frame()
        if frame is None:
            self.send_error(404, "no live frame")
            return
        view = _query_value(params, "view", "packed")
        plane = _query_plane(params, "plane", 0)
        png = render_png_bytes(render_view_image(frame, view=view, plane=plane))
        self._send_bytes(png, "image/png")

    def _send_json(self, payload):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self._send_bytes(body, "application/json")

    def _send_bytes(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DmdPreviewServer(ThreadingHTTPServer):
    def __init__(self, server_address):
        super().__init__(server_address, DmdPreviewHandler)
        self.live_store = LiveFrameStore()


def _query_value(params, name, default):
    values = params.get(name)
    if not values:
        return default
    return values[0] or default


def _query_int(params, name, default):
    value = _query_value(params, name, None)
    if value is None:
        return default
    return int(value)


def _query_plane(params, name, default):
    value = _query_value(params, name, None)
    if value is None:
        return default
    if value in BITPLANE_LABELS:
        return BITPLANE_LABELS.index(value)
    plane = int(value)
    if plane < 0 or plane >= len(BITPLANE_LABELS):
        raise ValueError(f"plane must be in [0, {len(BITPLANE_LABELS) - 1}]")
    return plane


def create_server(host="127.0.0.1", port=8080):
    return DmdPreviewServer((host, int(port)))


def _build_parser():
    parser = argparse.ArgumentParser(description="Serve DMD bitplane preview UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    server = create_server(args.host, args.port)
    host, port = server.server_address
    print(f"Serving DMD preview at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
