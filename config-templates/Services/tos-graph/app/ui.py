from __future__ import annotations

import json

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
        --bg: #f6f7f9;
        --ink: #18211f;
        --muted: #61706b;
        --line: rgba(24, 33, 31, 0.16);
        --panel: rgba(255, 255, 255, 0.9);
        --tool: #eef2f5;
        --accent: #247865;
        --blue: #3e6fa3;
        --gold: #b1742f;
        --red: #a3483f;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--ink);
        background: var(--bg);
      }
      main {
        display: grid;
        grid-template-columns: 292px minmax(0, 1fr) 376px;
        grid-template-areas: "rail viewport inspector";
        gap: 12px;
        min-height: 100vh;
        padding: 12px;
      }
      section, aside {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 8px;
        min-width: 0;
      }
      .rail, .inspector {
        padding: 14px;
        overflow: auto;
      }
      .rail { grid-area: rail; }
      .viewport {
        grid-area: viewport;
        padding: 14px;
        display: grid;
        grid-template-rows: auto auto minmax(0, 1fr);
        gap: 12px;
      }
      .inspector { grid-area: inspector; }
      h1, h2, h3, p { margin-top: 0; }
      h1 { font-size: 21px; line-height: 1.15; margin-bottom: 8px; }
      h2 { font-size: 15px; margin-bottom: 9px; }
      h3 { font-size: 13px; margin-bottom: 7px; }
      p, .muted, button, input, label { font-size: 13px; }
      .muted { color: var(--muted); line-height: 1.45; }
      .stack { display: grid; gap: 10px; }
      .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .split { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
      .chip {
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 6px 9px;
        background: var(--tool);
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
      button.active { border-color: rgba(36, 120, 101, 0.72); box-shadow: inset 3px 0 0 var(--accent); }
      input { width: 100%; }
      .metric-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(82px, 1fr));
        gap: 8px;
      }
      .metric {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
        background: white;
        min-width: 0;
      }
      .metric strong { display: block; font-size: 22px; line-height: 1; margin-bottom: 6px; }
      .canvas {
        min-height: 520px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: white;
        overflow: hidden;
        position: relative;
      }
      svg { width: 100%; height: 520px; display: block; }
      .node circle { stroke: rgba(24,33,31,0.35); stroke-width: 1.2; }
      .node text { font-size: 11px; fill: var(--ink); }
      .edge-line { stroke: rgba(24,33,31,0.2); stroke-width: 1.2; fill: none; cursor: pointer; }
      .edge-line:hover { stroke: var(--gold); stroke-width: 2.2; }
      .list { display: grid; gap: 8px; }
      .item {
        border: 1px solid var(--line);
        border-radius: 7px;
        padding: 10px;
        background: white;
      }
      .layer-list { display: grid; gap: 6px; }
      .layer-toggle {
        display: flex;
        align-items: center;
        gap: 8px;
        border: 1px solid var(--line);
        border-radius: 7px;
        padding: 8px;
        background: white;
      }
      .mini-label {
        display: block;
        margin-bottom: 4px;
        color: var(--muted);
        font-size: 11px;
        text-transform: uppercase;
      }
      .layer-toggle input { width: auto; }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 12px;
        line-height: 1.45;
        margin: 0;
      }
      .warn { color: var(--red); }
      @media (max-width: 1120px) {
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
          <h1>Tree of Sophia Graph</h1>
          <p class="muted">Tree of Sophia owns meaning. abyss-stack serves projection, cache, UI, and MCP access.</p>
        </div>
        <div class="split">
          <button id="modePhilosophy" type="button">Philosophy</button>
          <button id="modeCorpus" type="button">Corpus</button>
        </div>
        <div class="stack">
          <h2>Views</h2>
          <div id="viewList" class="stack"></div>
        </div>
        <div class="stack">
          <h2>Layers</h2>
          <div id="layerList" class="layer-list"></div>
        </div>
        <div class="stack">
          <h2>Graph Mode</h2>
          <div class="split">
            <button id="clusterMode" type="button">Clusters</button>
            <button id="nodeMode" type="button">Nodes</button>
          </div>
        </div>
        <div class="stack">
          <h2>Review</h2>
          <button id="reviewButton" type="button">Review packet</button>
          <button id="snapshotButton" type="button">Snapshot</button>
          <button id="auditButton" type="button">Planting audit</button>
          <button id="unresolvedButton" type="button">Unresolved</button>
        </div>
        <div class="stack">
          <h2>Path</h2>
          <label><span class="mini-label">from</span><input id="pathFrom" placeholder="atlas-row:A01"></label>
          <label><span class="mini-label">to</span><input id="pathTo" placeholder="dossier:A01"></label>
          <button id="pathButton" type="button">Find path</button>
        </div>
        <div class="stack">
          <h2>Search</h2>
          <input id="searchInput" placeholder="node, source_ref, predicate">
          <button id="searchButton" type="button">Search</button>
        </div>
        <div class="stack">
          <h2>Projection</h2>
          <button id="syncButton" type="button">Sync projection</button>
          <div id="syncNote" class="muted"></div>
        </div>
      </aside>
      <section class="viewport">
        <div class="row">
          <span class="chip">Mode <span id="modeState">philosophy</span></span>
          <span class="chip">Projection <span id="projectionState">loading</span></span>
          <span class="chip">Neo4j <span id="neo4jState">loading</span></span>
          <span class="chip">View <span id="viewState">loading</span></span>
        </div>
        <div id="metrics" class="metric-grid"></div>
        <div class="canvas">
          <svg id="graphSvg" viewBox="0 0 1000 520" role="img" aria-label="ToS graph projection view"></svg>
        </div>
      </section>
      <aside class="inspector stack">
        <div>
          <h2 id="inspectorTitle">Selection</h2>
          <div id="inspectorMeta" class="muted">No selection.</div>
        </div>
        <div id="sourceRefs" class="list"></div>
        <div id="clusterList" class="list"></div>
        <div id="reviewList" class="list"></div>
        <div id="resultList" class="list"></div>
        <div class="item"><pre id="inspectorJson">{}</pre></div>
      </aside>
    </main>
    <script>
      window.__TOS_GRAPH_BOOT__ = __BOOT_PAYLOAD__;

      const boot = window.__TOS_GRAPH_BOOT__;
      const q = (id) => document.getElementById(id);
      const state = {
        mode: "philosophy",
        status: {},
        corpusSummary: null,
        philosophyViews: null,
        currentView: null,
        activeLayers: new Set(),
        graphMode: "clusters",
        expandedCluster: null,
        results: [],
      };

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

      function short(value, length = 44) {
        const text = String(value ?? "");
        return text.length > length ? `${text.slice(0, length)}...` : text;
      }

      function itemId(item) {
        return item.node_id || item.edge_id || item.id || item.path || item.pack_id || item.view_id || item.layer_id || "item";
      }

      function itemTitle(item) {
        return item.label || item.title || itemId(item);
      }

      function layerAllowed(item) {
        const layers = item.graph_layers || [];
        if (!layers.length || !state.activeLayers.size) return true;
        return layers.some((layer) => state.activeLayers.has(layer));
      }

      function setMode(mode) {
        state.mode = mode;
        q("modePhilosophy").classList.toggle("active", mode === "philosophy");
        q("modeCorpus").classList.toggle("active", mode === "corpus");
        q("modeState").textContent = mode;
      }

      function setGraphMode(mode) {
        state.graphMode = mode;
        q("clusterMode").classList.toggle("active", mode === "clusters");
        q("nodeMode").classList.toggle("active", mode === "nodes");
        renderGraph();
      }

      function renderMetrics() {
        const counts = state.mode === "philosophy"
          ? (state.status.philosophy?.counts || {})
          : (state.corpusSummary?.counts || {});
        const keys = state.mode === "philosophy"
          ? ["views", "graph_layers", "nodes", "edges", "clusters", "review_packets"]
          : ["branches", "manifests", "nodes", "relation_packs", "relation_edges", "resources"];
        q("metrics").innerHTML = keys.map((key) => `
          <div class="metric"><strong>${counts[key] ?? 0}</strong><span class="muted">${key.replaceAll("_", " ")}</span></div>
        `).join("");
      }

      function renderViews() {
        const views = state.mode === "philosophy"
          ? (state.philosophyViews?.views || [])
          : (state.corpusSummary?.graph_views || []);
        q("viewList").innerHTML = views.map((view) => `
          <button type="button" data-view="${escapeHtml(view.view_id)}" class="${state.currentViewId === view.view_id ? "active" : ""}">
            <strong>${escapeHtml(view.title || view.view_id)}</strong><br>
            <span class="muted">${escapeHtml(view.layout_hint || view.purpose || "")}</span>
          </button>
        `).join("");
        for (const button of q("viewList").querySelectorAll("[data-view]")) {
          button.addEventListener("click", () => loadView(button.getAttribute("data-view")));
        }
      }

      function renderLayers() {
        if (state.mode !== "philosophy") {
          q("layerList").innerHTML = '<span class="muted">Corpus views do not expose projection layers.</span>';
          return;
        }
        const layers = state.currentView?.view?.graph_layers || [];
        if (!layers.length) {
          q("layerList").innerHTML = '<span class="muted">No layers.</span>';
          return;
        }
        q("layerList").innerHTML = layers.map((layer) => `
          <label class="layer-toggle">
            <input type="checkbox" data-layer="${escapeHtml(layer)}" ${state.activeLayers.has(layer) ? "checked" : ""}>
            <span>${escapeHtml(layer)}</span>
          </label>
        `).join("");
        for (const input of q("layerList").querySelectorAll("[data-layer]")) {
          input.addEventListener("change", () => {
            const layer = input.getAttribute("data-layer");
            if (input.checked) state.activeLayers.add(layer);
            else state.activeLayers.delete(layer);
            renderGraph();
          });
        }
      }

      function inspect(title, payload, sourceRefs = []) {
        q("inspectorTitle").textContent = title;
        q("inspectorMeta").textContent = state.mode === "philosophy"
          ? "Philosophy projection packet. Source authority stays in Tree of Sophia."
          : "Corpus projection packet. Source authority stays in Tree of Sophia.";
        q("inspectorJson").textContent = JSON.stringify(payload, null, 2);
        const refs = [...new Set(sourceRefs.filter(Boolean))];
        q("sourceRefs").innerHTML = refs.map((ref) => `
          <div class="item"><strong>source_ref</strong><br><span class="muted">${escapeHtml(ref)}</span></div>
        `).join("");
      }

      function renderClusters() {
        if (state.mode !== "philosophy" || !state.currentView) {
          q("clusterList").innerHTML = "";
          return;
        }
        const clusters = (state.currentView.clusters || []).filter(layerAllowed).slice(0, 16);
        q("clusterList").innerHTML = clusters.length ? clusters.map((cluster, index) => `
          <button type="button" class="item" data-cluster="${index}">
            <strong>${escapeHtml(short(cluster.label, 58))}</strong><br>
            <span class="muted">${escapeHtml(cluster.cluster_kind)} · ${cluster.member_node_ids?.length || 0} nodes · ${cluster.source_refs?.length || 0} refs</span>
          </button>
        `).join("") : '<div class="item"><span class="muted">No clusters for this view.</span></div>';
        for (const button of q("clusterList").querySelectorAll("[data-cluster]")) {
          button.addEventListener("click", () => {
            const cluster = clusters[Number(button.getAttribute("data-cluster"))];
            state.expandedCluster = cluster;
            setGraphMode("nodes");
            inspect(cluster.label, cluster, cluster.source_refs || []);
          });
        }
      }

      function renderReview() {
        if (state.mode !== "philosophy" || !state.currentView?.review_packet?.packet) {
          q("reviewList").innerHTML = "";
          return;
        }
        const packet = state.currentView.review_packet.packet;
        q("reviewList").innerHTML = `
          <div class="item">
            <strong>Review packet</strong><br>
            <span class="muted">${escapeHtml(short(packet.review_intent, 120))}</span>
          </div>
          <div class="item">
            <strong>${packet.counts?.clusters ?? 0}</strong> clusters ·
            <strong>${packet.counts?.unresolved_diagnostics ?? 0}</strong> unresolved ·
            <strong>${packet.counts?.weak_source_refs ?? 0}</strong> weak refs
          </div>
        `;
      }

      function renderResults() {
        q("resultList").innerHTML = state.results.slice(0, 40).map((entry, index) => {
          const item = entry.item || entry;
          return `
            <button type="button" class="item" data-result="${index}">
              <strong>${escapeHtml(short(itemTitle(item), 54))}</strong><br>
              <span class="muted">${escapeHtml(entry.collection || item.node_type || item.predicate_id || item.source_ref || "result")}</span>
            </button>
          `;
        }).join("");
        for (const button of q("resultList").querySelectorAll("[data-result]")) {
          button.addEventListener("click", () => {
            const entry = state.results[Number(button.getAttribute("data-result"))];
            const item = entry.item || entry;
            inspect(itemTitle(item), item, [item.source_ref]);
          });
        }
      }

      function renderGraph() {
        const svg = q("graphSvg");
        if (!state.currentView) {
          svg.innerHTML = "";
          return;
        }
        if (state.mode === "corpus") {
          renderCorpusGraph(svg);
          return;
        }
        if (state.graphMode === "clusters" && (state.currentView.clusters || []).length) {
          renderClusterGraph(svg);
          return;
        }
        const nodes = (state.currentView.nodes || []).filter(layerAllowed).slice(0, 180);
        const expandedIds = new Set(state.expandedCluster?.member_node_ids || []);
        const visibleNodes = expandedIds.size ? nodes.filter((node) => expandedIds.has(node.node_id)) : nodes;
        const nodeIds = new Set(visibleNodes.map((node) => node.node_id));
        const edges = (state.currentView.edges || [])
          .filter(layerAllowed)
          .filter((edge) => nodeIds.has(edge.from_id) && nodeIds.has(edge.to_id))
          .slice(0, 260);
        renderNodeGraph(svg, visibleNodes, edges);
      }

      function renderNodeGraph(svg, nodes, edges) {
        const width = 1000;
        const height = 520;
        const cx = width / 2;
        const cy = height / 2;
        const rx = Math.min(390, 120 + nodes.length * 4);
        const ry = Math.min(205, 80 + nodes.length * 2);
        const positions = new Map();
        nodes.forEach((node, index) => {
          const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(nodes.length, 1));
          positions.set(node.node_id, { x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry });
        });
        const edgeMarkup = edges.map((edge, index) => {
          const from = positions.get(edge.from_id);
          const to = positions.get(edge.to_id);
          if (!from || !to) return "";
          return `<path class="edge-line" data-edge="${index}" d="M ${from.x} ${from.y} L ${to.x} ${to.y}" />`;
        }).join("");
        const nodeMarkup = nodes.map((node, index) => {
          const point = positions.get(node.node_id);
          const palette = ["#247865", "#3e6fa3", "#b1742f", "#8a5fa2", "#a3483f", "#5f7f3d"];
          const color = palette[index % palette.length];
          return `
            <g class="node" data-node="${index}">
              <circle cx="${point.x}" cy="${point.y}" r="10" fill="${color}" />
              ${index < 42 ? `<text x="${point.x + 13}" y="${point.y + 4}">${escapeHtml(short(itemTitle(node), 34))}</text>` : ""}
            </g>
          `;
        }).join("");
        svg.innerHTML = `${edgeMarkup}${nodeMarkup}`;
        for (const group of svg.querySelectorAll("[data-node]")) {
          group.addEventListener("click", () => {
            const node = nodes[Number(group.getAttribute("data-node"))];
            inspect(itemTitle(node), node, [node.source_ref]);
          });
        }
        for (const path of svg.querySelectorAll("[data-edge]")) {
          path.addEventListener("click", () => {
            const edge = edges[Number(path.getAttribute("data-edge"))];
            inspect(edge.edge_id, edge, [edge.source_ref]);
          });
        }
      }

      function renderClusterGraph(svg) {
        const clusters = (state.currentView.clusters || []).filter(layerAllowed).slice(0, 90);
        const width = 1000;
        const height = 520;
        const cx = width / 2;
        const cy = height / 2;
        const rx = 390;
        const ry = 210;
        const points = clusters.map((cluster, index) => {
          const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(clusters.length, 1));
          return { cluster, x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry };
        });
        svg.innerHTML = points.map((point) => {
          const size = Math.max(11, Math.min(34, 8 + (point.cluster.member_node_ids?.length || 0) * 0.18));
          const color = point.cluster.cluster_kind === "source-witness" ? "#3e6fa3"
            : point.cluster.cluster_kind === "canon-candidate-status" ? "#b1742f"
            : point.cluster.cluster_kind === "evidence-status" ? "#a3483f"
            : "#247865";
          return `
            <g class="node" data-cluster-node="${points.indexOf(point)}">
              <circle cx="${point.x}" cy="${point.y}" r="${size}" fill="${color}" />
              <text x="${point.x + size + 5}" y="${point.y + 4}">${escapeHtml(short(point.cluster.label, 38))}</text>
            </g>
          `;
        }).join("");
        for (const group of svg.querySelectorAll("[data-cluster-node]")) {
          group.addEventListener("click", () => {
            const cluster = points[Number(group.getAttribute("data-cluster-node"))].cluster;
            state.expandedCluster = cluster;
            inspect(cluster.label, cluster, cluster.source_refs || []);
            renderClusters();
          });
        }
      }

      function renderCorpusGraph(svg) {
        const items = (state.currentView.items || []).slice(0, 80);
        const width = 1000;
        const height = 520;
        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(360, 100 + items.length * 6);
        const points = items.map((item, index) => {
          const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(items.length, 1));
          return { item, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * 180 };
        });
        svg.innerHTML = points.map((point) => `<path class="edge-line" d="M ${cx} ${cy} L ${point.x} ${point.y}" />`).join("") +
          points.map((point, index) => `
            <g class="node" data-node="${index}">
              <circle cx="${point.x}" cy="${point.y}" r="10" fill="${index % 2 ? "#3e6fa3" : "#247865"}" />
              ${index < 30 ? `<text x="${point.x + 13}" y="${point.y + 4}">${escapeHtml(short(itemTitle(point.item), 32))}</text>` : ""}
            </g>
          `).join("");
        for (const group of svg.querySelectorAll("[data-node]")) {
          group.addEventListener("click", () => {
            const item = points[Number(group.getAttribute("data-node"))].item;
            inspect(itemTitle(item), item, [item.source_ref || item.source_path || item.path]);
          });
        }
      }

      function updateStatusChips() {
        q("projectionState").textContent = state.mode === "philosophy"
          ? (state.status.philosophy?.projection_exists ? "present" : "missing")
          : (state.status.corpus?.index_exists ? "present" : "missing");
        q("neo4jState").textContent = boot.neo4j.ready ? "ready" : (boot.neo4j.configured ? "preview" : "deferred");
        q("viewState").textContent = state.currentViewId || "none";
      }

      function renderAll() {
        updateStatusChips();
        renderMetrics();
        renderViews();
        renderLayers();
        renderClusters();
        renderReview();
        renderGraph();
        renderResults();
      }

      async function loadView(viewId) {
        state.currentViewId = viewId;
        if (state.mode === "philosophy") {
          state.currentView = await fetchJson(`/api/philosophy/views/${encodeURIComponent(viewId)}`);
          state.activeLayers = new Set(state.currentView.view.graph_layers || []);
          state.graphMode = "clusters";
          state.expandedCluster = null;
          state.results = [
            ...(state.currentView.clusters || []),
            ...(state.currentView.nodes || []),
            ...(state.currentView.edges || [])
          ];
          inspect(state.currentView.view.title || viewId, state.currentView.view, state.currentView.source_refs || []);
        } else {
          state.currentView = await fetchJson(`/api/corpus/graph-views/${encodeURIComponent(viewId)}?limit=80`);
          state.results = state.currentView.items || [];
          inspect(viewId, state.currentView.view, [state.currentView.view.entry_surface]);
        }
        renderAll();
        setGraphMode(state.graphMode);
      }

      async function showReviewPacket() {
        if (state.mode !== "philosophy" || !state.currentViewId) return;
        const payload = await fetchJson(`/api/philosophy/review-packet?view_id=${encodeURIComponent(state.currentViewId)}`);
        inspect(`Review packet: ${state.currentViewId}`, payload.packet, payload.packet.source_refs || []);
      }

      async function showSnapshot() {
        if (state.mode !== "philosophy") return;
        const payload = await fetchJson("/api/philosophy/snapshot");
        const snapshot = payload.snapshot_review?.current_snapshot || {};
        inspect("Snapshot", payload, []);
        q("inspectorMeta").textContent = `projection ${short(snapshot.projection_fingerprint || "missing", 18)} · ${payload.snapshot_review?.diff_route?.mode || "no diff route"}`;
      }

      async function showAudit() {
        if (state.mode !== "philosophy") return;
        const payload = await fetchJson("/api/philosophy/audit");
        const audit = payload.audit || {};
        inspect("Planting audit", payload, []);
        q("inspectorMeta").textContent = audit.review_readiness?.status || (payload.audit_exists ? "audit loaded" : "audit missing");
      }

      async function showUnresolved() {
        if (state.mode !== "philosophy") return;
        const suffix = state.currentViewId ? `?view_id=${encodeURIComponent(state.currentViewId)}` : "";
        const payload = await fetchJson(`/api/philosophy/unresolved${suffix}`);
        state.results = payload.unresolved || [];
        inspect(`Unresolved: ${state.currentViewId || "all"}`, payload, []);
        renderAll();
      }

      async function findPath() {
        if (state.mode !== "philosophy") return;
        const from = q("pathFrom").value.trim();
        const to = q("pathTo").value.trim();
        if (!from || !to) return;
        const layers = [...state.activeLayers].join(",");
        const payload = await fetchJson(`/api/philosophy/paths?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&layers=${encodeURIComponent(layers)}`);
        state.results = [...(payload.nodes || []), ...(payload.edges || [])];
        inspect(`Path: ${from} → ${to}`, payload, payload.source_refs || []);
        renderAll();
      }

      async function searchCurrentMode() {
        const query = q("searchInput").value.trim();
        if (state.mode === "philosophy") {
          const payload = await fetchJson(`/api/philosophy/search?query=${encodeURIComponent(query)}&limit=40`);
          state.results = payload.results || [];
          inspect(`Search: ${query || "all"}`, payload, []);
        } else {
          const payload = await fetchJson(`/api/corpus/search?query=${encodeURIComponent(query)}&limit=40`);
          state.results = payload.results || [];
          inspect(`Search: ${query || "all"}`, payload, []);
        }
        renderAll();
      }

      async function syncProjection() {
        q("syncNote").textContent = "syncing...";
        const url = state.mode === "philosophy" ? "/api/philosophy/project/sync" : "/api/project/sync";
        const payload = await fetchJson(url, { method: "POST" });
        q("syncNote").textContent = `${payload.status}: ${payload.node_count} nodes, ${payload.edge_count} edges`;
        inspect("Projection sync", payload, []);
      }

      async function loadMode(mode) {
        setMode(mode);
        state.currentView = null;
        state.results = [];
        if (mode === "philosophy") {
          state.status.philosophy = await fetchJson("/api/philosophy/status");
          if (!state.status.philosophy.projection_exists) {
            inspect("Missing projection", state.status.philosophy, []);
            renderAll();
            return;
          }
          state.philosophyViews = await fetchJson("/api/philosophy/views");
          await loadView(boot.default_philosophy_view);
        } else {
          state.status.corpus = await fetchJson("/api/corpus/status");
          state.corpusSummary = await fetchJson("/api/corpus/summary");
          await loadView(boot.default_view);
        }
      }

      async function init() {
        q("modePhilosophy").addEventListener("click", () => loadMode("philosophy"));
        q("modeCorpus").addEventListener("click", () => loadMode("corpus"));
        q("clusterMode").addEventListener("click", () => { state.expandedCluster = null; setGraphMode("clusters"); });
        q("nodeMode").addEventListener("click", () => setGraphMode("nodes"));
        q("reviewButton").addEventListener("click", showReviewPacket);
        q("snapshotButton").addEventListener("click", showSnapshot);
        q("auditButton").addEventListener("click", showAudit);
        q("unresolvedButton").addEventListener("click", showUnresolved);
        q("pathButton").addEventListener("click", findPath);
        q("searchButton").addEventListener("click", searchCurrentMode);
        q("searchInput").addEventListener("keydown", (event) => { if (event.key === "Enter") searchCurrentMode(); });
        q("syncButton").addEventListener("click", syncProjection);
        await loadMode("philosophy");
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
        "philosophy_graph_projection_path": settings.philosophy_graph_projection_path.as_posix(),
        "default_view": settings.default_view,
        "default_philosophy_view": settings.default_philosophy_view,
        "write_enabled": settings.write_enabled,
        "projection_mode": settings.projection_mode,
        "neo4j": {
            "configured": neo4j_status.configured,
            "ready": neo4j_status.ready,
            "database": neo4j_status.database,
            "note": neo4j_status.note,
        },
    }
    return INDEX_TEMPLATE.replace("__BOOT_PAYLOAD__", json.dumps(boot_payload, ensure_ascii=False))
