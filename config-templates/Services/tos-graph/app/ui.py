from __future__ import annotations

import json
from html import escape

from .config import TosGraphSettings
from .neo4j_store import Neo4jStoreStatus


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>tos-graph</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f2ec;
        --ink: #17231e;
        --muted: #65736b;
        --line: rgba(23, 35, 30, 0.16);
        --panel: rgba(255, 255, 255, 0.78);
        --accent: #2e7d66;
        --accent-2: #b77938;
        --warn: #a44b3f;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          linear-gradient(90deg, rgba(23,35,30,0.05) 1px, transparent 1px),
          linear-gradient(rgba(23,35,30,0.05) 1px, transparent 1px),
          var(--bg);
        background-size: 28px 28px;
      }
      main {
        display: grid;
        grid-template-columns: 280px minmax(0, 1fr) 360px;
        grid-template-areas: "rail viewport inspector";
        gap: 14px;
        min-height: 100vh;
        padding: 14px;
      }
      section, aside {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 8px;
        min-width: 0;
      }
      .rail, .inspector { padding: 16px; overflow: auto; }
      .rail { grid-area: rail; }
      .viewport { grid-area: viewport; padding: 16px; display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: 14px; }
      .inspector { grid-area: inspector; }
      h1, h2, h3, p { margin-top: 0; }
      h1 { font-size: 22px; line-height: 1.15; margin-bottom: 8px; }
      h2 { font-size: 16px; margin-bottom: 10px; }
      h3 { font-size: 13px; margin-bottom: 8px; }
      p, .muted, button, input { font-size: 13px; }
      .muted { color: var(--muted); line-height: 1.45; }
      .stack { display: grid; gap: 10px; }
      .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .chip {
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 6px 9px;
        background: rgba(255,255,255,0.62);
        font-size: 12px;
      }
      button, input {
        font: inherit;
        border: 1px solid var(--line);
        background: white;
        border-radius: 7px;
        padding: 9px 10px;
        color: var(--ink);
      }
      button { cursor: pointer; text-align: left; }
      button.active { border-color: rgba(46,125,102,0.65); box-shadow: inset 3px 0 0 var(--accent); }
      input { width: 100%; }
      .metric-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(90px, 1fr));
        gap: 10px;
      }
      .metric {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 12px;
        background: rgba(255,255,255,0.7);
      }
      .metric strong { display: block; font-size: 24px; line-height: 1; margin-bottom: 7px; }
      .canvas {
        min-height: 460px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: rgba(255,255,255,0.58);
        overflow: hidden;
        position: relative;
      }
      svg { width: 100%; height: 460px; display: block; }
      .node circle { stroke: rgba(23,35,30,0.35); stroke-width: 1.2; }
      .node text { font-size: 11px; fill: var(--ink); }
      .edge { stroke: rgba(23,35,30,0.22); stroke-width: 1.1; fill: none; }
      .list { display: grid; gap: 8px; }
      .item {
        border: 1px solid var(--line);
        border-radius: 7px;
        padding: 10px;
        background: rgba(255,255,255,0.62);
      }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 12px;
        line-height: 1.45;
        margin: 0;
      }
      .warn { color: var(--warn); }
      @media (max-width: 1100px) {
        main {
          grid-template-columns: 1fr;
          grid-template-areas: "rail" "viewport" "inspector";
        }
        .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }
    </style>
  </head>
  <body>
    <main>
      <aside class="rail stack">
        <div>
          <h1>Tree of Sophia Corpus Graph</h1>
          <p class="muted">Runtime view over the ToS-owned corpus index. Tree of Sophia owns meaning; this surface owns projection and review access.</p>
        </div>
        <div class="stack">
          <h2>Views</h2>
          <div id="viewList" class="stack"></div>
        </div>
        <div class="stack">
          <h2>Search</h2>
          <input id="searchInput" placeholder="node, path, branch, witness">
          <button id="searchButton" type="button">Search corpus</button>
        </div>
        <div class="stack">
          <h2>Projection</h2>
          <button id="syncButton" type="button">Sync corpus projection</button>
          <div id="syncNote" class="muted"></div>
        </div>
      </aside>
      <section class="viewport">
        <div class="row">
          <span class="chip">Index <span id="indexState">loading</span></span>
          <span class="chip">Neo4j <span id="neo4jState">loading</span></span>
          <span class="chip">Default <span id="defaultView">__DEFAULT_VIEW__</span></span>
        </div>
        <div id="metrics" class="metric-grid"></div>
        <div class="canvas">
          <svg id="graphSvg" viewBox="0 0 960 460" role="img" aria-label="ToS corpus graph view"></svg>
        </div>
      </section>
      <aside class="inspector stack">
        <div>
          <h2 id="inspectorTitle">Selection</h2>
          <div id="inspectorMeta" class="muted">Choose a graph view or search result.</div>
        </div>
        <div id="resultList" class="list"></div>
        <div class="item"><pre id="inspectorJson">{}</pre></div>
      </aside>
    </main>
    <script>
      window.__TOS_GRAPH_BOOT__ = __BOOT_PAYLOAD__;

      const boot = window.__TOS_GRAPH_BOOT__;
      const state = { status: null, summary: null, view: null, query: "", results: [] };
      const q = (id) => document.getElementById(id);

      async function fetchJson(url, options = undefined) {
        const response = await fetch(url, options);
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      }

      function escapeHtml(value) {
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }

      function short(value, length = 42) {
        const text = String(value ?? "");
        return text.length > length ? `${text.slice(0, length)}...` : text;
      }

      function renderMetrics() {
        const counts = state.summary?.counts || {};
        const keys = ["branches", "manifests", "nodes", "relation_packs", "relation_edges", "resources"];
        q("metrics").innerHTML = keys.map((key) => `
          <div class="metric"><strong>${counts[key] ?? 0}</strong><span class="muted">${key.replaceAll("_", " ")}</span></div>
        `).join("");
      }

      function renderViews() {
        const views = state.summary?.graph_views || [];
        q("viewList").innerHTML = views.map((view) => `
          <button type="button" data-view="${escapeHtml(view.view_id)}" class="${state.view?.view?.view_id === view.view_id ? "active" : ""}">
            <strong>${escapeHtml(view.view_id)}</strong><br>
            <span class="muted">${escapeHtml(view.layout_hint)}</span>
          </button>
        `).join("");
        for (const button of q("viewList").querySelectorAll("[data-view]")) {
          button.addEventListener("click", () => loadView(button.getAttribute("data-view")));
        }
      }

      function itemLabel(item) {
        return item.id || item.path || item.node_id || item.pack_id || item.edge_id || item.view_id || "item";
      }

      function renderGraph() {
        const svg = q("graphSvg");
        if (!state.view) {
          svg.innerHTML = "";
          return;
        }
        const items = state.view.items || [];
        const width = 960;
        const height = 460;
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(320, 90 + items.length * 7);
        const points = items.slice(0, 80).map((item, index) => {
          const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(items.length, 1));
          return {
            item,
            x: centerX + Math.cos(angle) * radius,
            y: centerY + Math.sin(angle) * Math.min(radius, 170),
          };
        });
        const edges = points.map((point) => `
          <path class="edge" d="M ${centerX} ${centerY} L ${point.x} ${point.y}" />
        `).join("");
        const nodes = points.map((point, index) => {
          const color = ["#2e7d66", "#b77938", "#547aa5", "#8b6fb6", "#b8554a", "#6b8f4f"][index % 6];
          return `
            <g class="node" data-index="${index}">
              <circle cx="${point.x}" cy="${point.y}" r="10" fill="${color}" />
              ${index < 18 ? `<text x="${point.x + 13}" y="${point.y + 4}">${escapeHtml(short(itemLabel(point.item), 30))}</text>` : ""}
            </g>
          `;
        }).join("");
        svg.innerHTML = `
          <circle cx="${centerX}" cy="${centerY}" r="18" fill="rgba(46,125,102,0.18)" stroke="rgba(46,125,102,0.55)"></circle>
          <text x="${centerX + 24}" y="${centerY + 4}">${escapeHtml(state.view.view.view_id)}</text>
          ${edges}
          ${nodes}
        `;
        for (const group of svg.querySelectorAll("[data-index]")) {
          group.addEventListener("click", () => {
            const item = points[Number(group.getAttribute("data-index"))]?.item;
            inspect(itemLabel(item), item);
          });
        }
      }

      function inspect(title, payload) {
        q("inspectorTitle").textContent = title;
        q("inspectorMeta").textContent = "ToS source path and authority layer stay in the payload.";
        q("inspectorJson").textContent = JSON.stringify(payload, null, 2);
      }

      function renderResults() {
        q("resultList").innerHTML = state.results.map((entry, index) => {
          const item = entry.item || entry;
          return `
            <button type="button" class="item" data-result="${index}">
              <strong>${escapeHtml(short(itemLabel(item), 52))}</strong><br>
              <span class="muted">${escapeHtml(entry.collection || item.authority_layer || "result")}</span>
            </button>
          `;
        }).join("");
        for (const button of q("resultList").querySelectorAll("[data-result]")) {
          button.addEventListener("click", () => {
            const entry = state.results[Number(button.getAttribute("data-result"))];
            inspect(itemLabel(entry.item || entry), entry.item || entry);
          });
        }
      }

      function renderAll() {
        q("indexState").textContent = state.status?.index_exists ? "present" : "missing";
        q("neo4jState").textContent = boot.neo4j.ready ? "ready" : (boot.neo4j.configured ? "preview" : "deferred");
        renderMetrics();
        renderViews();
        renderGraph();
        renderResults();
      }

      async function loadView(viewId) {
        state.view = await fetchJson(`/api/corpus/graph-views/${encodeURIComponent(viewId)}?limit=80`);
        state.results = state.view.items || [];
        inspect(viewId, state.view.view);
        renderAll();
      }

      async function searchCorpus() {
        state.query = q("searchInput").value.trim();
        const payload = await fetchJson(`/api/corpus/search?query=${encodeURIComponent(state.query)}&limit=40`);
        state.results = payload.results || [];
        inspect(`Search: ${state.query || "all"}`, payload);
        renderAll();
      }

      async function syncCorpus() {
        q("syncNote").textContent = "syncing...";
        const payload = await fetchJson("/api/project/sync", { method: "POST" });
        q("syncNote").textContent = `${payload.status}: ${payload.node_count} nodes, ${payload.edge_count} edges, ${payload.resource_count} resources`;
        inspect("Projection sync", payload);
      }

      async function init() {
        state.status = await fetchJson("/api/corpus/status");
        state.summary = await fetchJson("/api/corpus/summary");
        q("searchButton").addEventListener("click", searchCorpus);
        q("searchInput").addEventListener("keydown", (event) => { if (event.key === "Enter") searchCorpus(); });
        q("syncButton").addEventListener("click", syncCorpus);
        await loadView(boot.default_view);
        renderAll();
      }

      init().catch((error) => {
        q("inspectorTitle").textContent = "Load failed";
        q("inspectorMeta").innerHTML = `<span class="warn">${escapeHtml(error.message)}</span>`;
      });
    </script>
  </body>
</html>
"""


def render_index(settings: TosGraphSettings, neo4j_status: Neo4jStoreStatus) -> str:
    boot_payload = {
        "service": settings.service_name,
        "corpus_index_path": settings.corpus_index_path.as_posix(),
        "default_view": settings.default_view,
        "write_enabled": settings.write_enabled,
        "projection_mode": settings.projection_mode,
        "neo4j": {
            "configured": neo4j_status.configured,
            "ready": neo4j_status.ready,
            "database": neo4j_status.database,
            "note": neo4j_status.note,
        },
    }
    html = INDEX_TEMPLATE
    html = html.replace("__BOOT_PAYLOAD__", json.dumps(boot_payload, ensure_ascii=False))
    html = html.replace("__DEFAULT_VIEW__", escape(settings.default_view))
    return html
