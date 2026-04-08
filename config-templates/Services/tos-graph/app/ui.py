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
        --bg-ink: #14261f;
        --bg-forest: #1d3c34;
        --bg-wash: #e8dfd0;
        --bg-paper: rgba(252, 248, 241, 0.86);
        --line-soft: rgba(27, 49, 42, 0.12);
        --line-strong: rgba(27, 49, 42, 0.24);
        --accent-gold: #b8843f;
        --accent-coral: #d66d4b;
        --accent-sky: #7ea6b8;
        --accent-sage: #7e9f7d;
        --text-main: #1a241f;
        --text-soft: #56655d;
        --shadow-soft: 0 10px 32px rgba(20, 38, 31, 0.08);
        --radius-xl: 28px;
        --radius-lg: 22px;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        min-height: 100vh;
        font-family: "IBM Plex Mono", "SFMono-Regular", "Menlo", "Consolas", monospace;
        color: var(--text-main);
        background:
          radial-gradient(circle at top left, rgba(214, 109, 75, 0.22), transparent 34%),
          radial-gradient(circle at right 18%, rgba(126, 166, 184, 0.24), transparent 26%),
          linear-gradient(160deg, var(--bg-ink) 0%, var(--bg-forest) 42%, #efe3d3 42%, #efe3d3 100%);
      }

      body::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image:
          linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
        background-size: 24px 24px;
        opacity: 0.08;
      }

      .shell {
        position: relative;
        z-index: 1;
        min-height: 100vh;
        padding: 20px;
        display: grid;
        grid-template-columns: 300px minmax(0, 1fr) 360px;
        grid-template-areas:
          "hero hero hero"
          "rail viewport inspector";
        gap: 18px;
      }

      .panel {
        position: relative;
        overflow: hidden;
        border: 1px solid var(--line-soft);
        background: var(--bg-paper);
        border-radius: var(--radius-xl);
        box-shadow: var(--shadow-soft);
        backdrop-filter: blur(18px);
        animation: rise-in 420ms ease both;
      }

      .panel::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: inherit;
        pointer-events: none;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.22), transparent 22%);
      }

      .hero {
        grid-area: hero;
        padding: 26px 28px 24px;
        background:
          radial-gradient(circle at right top, rgba(184, 132, 63, 0.22), transparent 28%),
          linear-gradient(140deg, rgba(250, 246, 239, 0.96), rgba(240, 233, 222, 0.88));
      }

      .hero-top,
      .hero-bottom,
      .viewport-top,
      .section-head {
        display: flex;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
      }

      .kicker,
      .eyebrow {
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 11px;
        color: var(--text-soft);
      }

      .brand {
        margin: 10px 0 8px;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
        font-size: clamp(32px, 4vw, 54px);
        line-height: 0.98;
        max-width: 14ch;
      }

      .hero-copy {
        max-width: 74ch;
        color: var(--text-soft);
        line-height: 1.6;
        font-size: 14px;
      }

      .chip-row,
      .legend,
      .pill-row {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border-radius: 999px;
        padding: 9px 14px;
        background: rgba(24, 43, 37, 0.06);
        border: 1px solid rgba(24, 43, 37, 0.08);
        font-size: 12px;
      }

      .rail,
      .inspector { padding: 20px; }

      .rail {
        grid-area: rail;
        display: grid;
        gap: 16px;
        align-content: start;
      }

      .viewport {
        grid-area: viewport;
        padding: 18px;
        display: grid;
        gap: 16px;
        align-content: start;
      }

      .inspector {
        grid-area: inspector;
        display: grid;
        gap: 16px;
        align-content: start;
      }

      .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }

      .metric-card,
      .detail-card,
      .list-card {
        border-radius: var(--radius-lg);
        padding: 16px;
        border: 1px solid var(--line-soft);
        background: rgba(255, 255, 255, 0.58);
      }

      .metric-value {
        margin-top: 12px;
        font-size: 32px;
        line-height: 1;
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      }

      .metric-note,
      .section-subtitle,
      .muted,
      .empty-state {
        color: var(--text-soft);
        font-size: 12px;
        line-height: 1.55;
      }

      .route-list,
      .family-list,
      .node-list,
      .edge-list,
      .fact-grid {
        display: grid;
        gap: 10px;
      }

      button,
      .route-item,
      .family-item,
      .node-item,
      .edge-item {
        font: inherit;
        color: inherit;
      }

      .ghost-button,
      .route-item,
      .family-item,
      .node-item,
      .edge-item {
        width: 100%;
        text-align: left;
        border: 1px solid var(--line-soft);
        background: rgba(255, 255, 255, 0.56);
        border-radius: 16px;
        padding: 14px 15px;
        transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
        cursor: pointer;
      }

      .ghost-button:hover,
      .route-item:hover,
      .family-item:hover,
      .node-item:hover,
      .edge-item:hover {
        transform: translateY(-1px);
        border-color: var(--line-strong);
        background: rgba(255, 255, 255, 0.78);
      }

      .route-item.active,
      .family-item.active,
      .node-item.active,
      .edge-item.active {
        border-color: rgba(184, 132, 63, 0.42);
        background: linear-gradient(180deg, rgba(248, 238, 220, 0.98), rgba(243, 231, 209, 0.82));
      }

      .route-item small,
      .family-item small,
      .node-item small,
      .edge-item small {
        display: block;
        margin-top: 6px;
        color: var(--text-soft);
      }

      .graph-stage {
        position: relative;
        overflow: hidden;
        border-radius: var(--radius-xl);
        padding: 16px;
        border: 1px solid var(--line-soft);
        background:
          radial-gradient(circle at top right, rgba(126, 166, 184, 0.18), transparent 26%),
          radial-gradient(circle at left 80%, rgba(214, 109, 75, 0.12), transparent 28%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(245, 238, 228, 0.9));
        min-height: 500px;
      }

      .graph-stage svg {
        width: 100%;
        height: 420px;
        display: block;
      }

      .graph-stage footer {
        display: flex;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 10px;
        font-size: 12px;
        color: var(--text-soft);
      }

      .graph-edge {
        fill: none;
        stroke: rgba(24, 43, 37, 0.14);
        stroke-width: 1.2;
      }

      .graph-edge.active {
        stroke: rgba(214, 109, 75, 0.5);
        stroke-width: 2.1;
      }

      .graph-node { cursor: pointer; }
      .graph-node circle {
        stroke: rgba(20, 38, 31, 0.34);
        stroke-width: 1.2;
      }
      .graph-node text {
        font-size: 11px;
        fill: var(--text-main);
      }

      .legend-item {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--text-soft);
        font-size: 12px;
      }

      .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 999px;
      }

      .detail-card h3,
      .list-card h3,
      .panel h2 {
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
        font-size: 21px;
      }

      .pill {
        padding: 7px 10px;
        border-radius: 999px;
        background: rgba(24, 43, 37, 0.08);
        font-size: 11px;
      }

      .fact {
        padding: 12px;
        border-radius: 14px;
        background: rgba(247, 242, 233, 0.9);
        border: 1px solid rgba(20, 38, 31, 0.08);
      }

      .fact strong {
        display: block;
        margin-bottom: 6px;
        font-size: 12px;
      }

      .fact pre,
      details pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 12px;
        line-height: 1.5;
      }

      .status-banner {
        padding: 12px 14px;
        border-radius: 16px;
        font-size: 12px;
        line-height: 1.55;
      }

      .status-banner.info {
        background: rgba(126, 166, 184, 0.16);
        border: 1px solid rgba(126, 166, 184, 0.3);
      }

      .status-banner.warn {
        background: rgba(214, 109, 75, 0.14);
        border: 1px solid rgba(214, 109, 75, 0.28);
      }

      .status-banner.ok {
        background: rgba(126, 159, 125, 0.16);
        border: 1px solid rgba(126, 159, 125, 0.28);
      }

      .empty-state { padding: 26px 18px; text-align: center; }

      .loading { opacity: 0.6; }

      @keyframes rise-in {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
      }

      @media (max-width: 1220px) {
        .shell {
          grid-template-columns: minmax(0, 1fr) 320px;
          grid-template-areas:
            "hero hero"
            "viewport inspector"
            "rail inspector";
        }
        .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }

      @media (max-width: 900px) {
        .shell {
          grid-template-columns: 1fr;
          grid-template-areas:
            "hero"
            "rail"
            "viewport"
            "inspector";
          padding: 14px;
        }
        .hero, .rail, .viewport, .inspector { padding: 18px; }
        .graph-stage { min-height: 420px; }
        .graph-stage svg { height: 320px; }
        .metric-grid { grid-template-columns: 1fr 1fr; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero panel">
        <div class="hero-top">
          <div>
            <div class="kicker">Preview-first ToS graph curation</div>
            <h1 class="brand">Route-first reading surface for Tree of Sophia</h1>
          </div>
          <div class="chip-row" id="heroChips"></div>
        </div>
        <p class="hero-copy">
          Canon stays in Tree of Sophia, Neo4j stays a projection, and this helper stays localhost-only.
          The current slice is read-first: navigate routes, inspect nodes and edges, and preview the shape
          of a sync without crossing into writeback.
        </p>
        <div class="hero-bottom">
          <div class="chip-row">
            <span class="chip"><strong>Default route</strong> <span id="routeChip">__DEFAULT_ROUTE__</span></span>
            <span class="chip"><strong>Projection mode</strong> __PROJECTION_MODE__</span>
            <span class="chip"><strong>Write enabled</strong> __WRITE_MODE__</span>
          </div>
          <div class="muted" id="heroNote">Loading route truth...</div>
        </div>
      </section>

      <aside class="rail panel">
        <div class="section-head">
          <div>
            <div class="eyebrow">Routes</div>
            <h2>Navigator</h2>
          </div>
          <div class="muted" id="routeCount">0 routes</div>
        </div>
        <div class="route-list" id="routeList"></div>

        <div class="list-card">
          <div class="section-head">
            <div>
              <div class="eyebrow">Node types</div>
              <h3>Family stack</h3>
            </div>
            <div class="muted" id="familyNote">Awaiting graph</div>
          </div>
          <div class="family-list" id="familyList"></div>
        </div>

        <div class="list-card">
          <div class="section-head">
            <div>
              <div class="eyebrow">Projection</div>
              <h3>Sync preview</h3>
            </div>
            <button class="ghost-button" id="syncButton" type="button">Preview sync counts</button>
          </div>
          <div id="syncStatus" class="status-banner info">
            Preview-only lane: no Neo4j mutation is attempted in this slice.
          </div>
        </div>
      </aside>

      <section class="viewport panel">
        <div class="viewport-top">
          <div>
            <div class="eyebrow">Active route</div>
            <h2 id="activeRouteTitle">Loading route...</h2>
          </div>
          <div class="chip-row">
            <span class="chip"><strong>Source node</strong> <span id="sourceNodeId">pending</span></span>
            <span class="chip"><strong>Missing nodes</strong> <span id="missingNodes">0</span></span>
          </div>
        </div>

        <div class="metric-grid" id="metricGrid"></div>

        <div class="graph-stage">
          <div class="section-head">
            <div>
              <div class="eyebrow">Graph canvas</div>
              <h3>Route constellation</h3>
            </div>
            <div class="muted" id="graphNote">Rendering current route graph</div>
          </div>
          <svg id="graphSvg" viewBox="0 0 860 420" role="img" aria-label="Route graph"></svg>
          <footer>
            <div id="graphLegend" class="legend"></div>
            <div id="graphFooter" class="muted">Click a node or edge to focus the inspector.</div>
          </footer>
        </div>

        <div class="list-card">
          <div class="section-head">
            <div>
              <div class="eyebrow">Node roster</div>
              <h3>Route inventory</h3>
            </div>
            <div class="muted" id="nodeRosterNote">Awaiting nodes</div>
          </div>
          <div class="node-list" id="nodeList"></div>
        </div>

        <div class="list-card">
          <div class="section-head">
            <div>
              <div class="eyebrow">Relation pack</div>
              <h3>Edge ledger</h3>
            </div>
            <div class="muted" id="edgeRosterNote">Awaiting edges</div>
          </div>
          <div class="edge-list" id="edgeList"></div>
        </div>
      </section>

      <aside class="inspector panel">
        <div class="section-head">
          <div>
            <div class="eyebrow">Inspector</div>
            <h2 id="inspectorTitle">Selection</h2>
          </div>
          <div class="chip"><strong>Mode</strong> <span id="inspectorMode">Node</span></div>
        </div>
        <div id="inspectorBody" class="detail-card">
          <div class="empty-state">Choose a node or edge to inspect its canonical payload.</div>
        </div>
      </aside>
    </main>

    <script>
      window.__TOS_GRAPH_BOOT__ = __BOOT_PAYLOAD__;

      const boot = window.__TOS_GRAPH_BOOT__;
      const state = {
        routes: [],
        route: null,
        graph: null,
        tree: null,
        health: null,
        selectedNodeId: null,
        selectedEdgeId: null,
        syncResult: null,
      };

      const FAMILY_COLORS = ["#b8843f", "#7ea6b8", "#7e9f7d", "#d66d4b", "#8c7bb8", "#4f7f86", "#bb6e74", "#5e8e68"];
      const q = (id) => document.getElementById(id);

      function routeFromHash() {
        const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
        return params.get("route");
      }

      function setRouteHash(route) {
        const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
        params.set("route", route);
        window.history.replaceState(null, "", `#${params.toString()}`);
      }

      async function fetchJson(url, options = undefined) {
        const response = await fetch(url, options);
        if (!response.ok) {
          const detail = await response.text();
          throw new Error(detail || `${response.status} ${response.statusText}`);
        }
        return response.json();
      }

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }

      function nodeLabel(node) {
        return node?.canonical_label || node?.source_anchor || node?.node_id || "Unnamed node";
      }

      function shortCode(value, length = 10) {
        if (!value) return "n/a";
        return value.length <= length ? value : `${value.slice(0, length)}...`;
      }

      function formatList(items) {
        if (!Array.isArray(items) || items.length === 0) {
          return `<div class="muted">none</div>`;
        }
        return `<div class="pill-row">${items.map((item) => `<span class="pill">${escapeHtml(String(item))}</span>`).join("")}</div>`;
      }

      function formatJson(value) {
        return escapeHtml(JSON.stringify(value, null, 2));
      }

      function nodeMap() {
        const map = new Map();
        if (!state.graph) return map;
        if (state.graph.source_node) map.set(state.graph.source_node.node_id, state.graph.source_node);
        for (const node of state.graph.nodes || []) map.set(node.node_id, node);
        return map;
      }

      function familyEntries() {
        if (!state.tree?.family_counts) return [];
        return Object.entries(state.tree.family_counts).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
      }

      function familyColorMap() {
        const map = new Map();
        familyEntries().forEach(([family], index) => {
          map.set(family, FAMILY_COLORS[index % FAMILY_COLORS.length]);
        });
        return map;
      }

      function routeLabel(route) {
        const entry = state.routes.find((candidate) => candidate.route === route);
        return entry?.label || route;
      }

      function selectNode(nodeId) {
        state.selectedNodeId = nodeId;
        state.selectedEdgeId = null;
        renderAll();
      }

      function selectEdge(edgeId) {
        state.selectedEdgeId = edgeId;
        state.selectedNodeId = null;
        renderAll();
      }

      function buildGraphLayout(nodes, sourceNodeId) {
        const width = 860;
        const height = 420;
        const cx = width / 2;
        const cy = height / 2;
        const families = familyEntries().map(([family]) => family);
        const colors = familyColorMap();
        const grouped = new Map();

        for (const node of nodes) {
          const family = node.node_type || "unknown";
          if (!grouped.has(family)) grouped.set(family, []);
          grouped.get(family).push(node);
        }

        const positions = new Map();
        if (sourceNodeId) {
          positions.set(sourceNodeId, { x: cx, y: cy, color: colors.get(nodeMap().get(sourceNodeId)?.node_type || "unknown") || "#b8843f" });
        }

        families.forEach((family, familyIndex) => {
          const group = (grouped.get(family) || []).filter((node) => node.node_id !== sourceNodeId);
          if (group.length === 0) return;
          const anchorAngle = (-Math.PI / 2) + ((Math.PI * 2 * familyIndex) / Math.max(families.length, 1));
          const anchorX = cx + Math.cos(anchorAngle) * 150;
          const anchorY = cy + Math.sin(anchorAngle) * 120;
          const radius = Math.max(38, 28 + group.length * 4);
          group.forEach((node, index) => {
            const angle = anchorAngle + ((Math.PI * 2 * index) / group.length);
            positions.set(node.node_id, {
              x: anchorX + Math.cos(angle) * radius,
              y: anchorY + Math.sin(angle) * radius,
              color: colors.get(family) || "#7ea6b8",
            });
          });
        });
        return positions;
      }

      function renderHero() {
        q("routeChip").textContent = state.route || boot.route_default;
        q("heroChips").innerHTML = `
          <span class="chip"><strong>Neo4j</strong> ${boot.neo4j.configured ? "configured preview" : "deferred preview"}</span>
          <span class="chip"><strong>ToS mount</strong> ${state.health?.tos_root_exists ? "present" : "missing"}</span>
          <span class="chip"><strong>Routes visible</strong> ${state.routes.length}</span>
        `;
        q("heroNote").textContent = boot.neo4j.note;
      }

      function renderMetrics() {
        if (!state.graph) {
          q("metricGrid").innerHTML = "";
          return;
        }
        const diagnostics = state.graph.diagnostics || {};
        const cards = [
          ["Nodes in route", state.graph.nodes.length, "Canonical nodes in the current route graph payload."],
          ["Edges in pack", state.graph.edges.length, "Rows visible from the relation-pack ledger."],
          ["Node families", familyEntries().length, "Distinct node_type families visible in this route slice."],
          ["Relation hash", shortCode(diagnostics.edge_file_sha256 || "", 12), diagnostics.edge_file || "No relation file available."],
        ];
        q("metricGrid").innerHTML = cards.map(([label, value, note]) => `
          <article class="metric-card">
            <div class="eyebrow">${escapeHtml(label)}</div>
            <div class="metric-value">${escapeHtml(String(value))}</div>
            <div class="metric-note">${escapeHtml(String(note))}</div>
          </article>
        `).join("");
      }

      function renderRoutes() {
        q("routeCount").textContent = `${state.routes.length} route${state.routes.length === 1 ? "" : "s"}`;
        q("routeList").innerHTML = state.routes.map((route) => `
          <button type="button" class="route-item ${route.route === state.route ? "active" : ""}" data-route="${escapeHtml(route.route)}">
            <strong>${escapeHtml(route.label)}</strong>
            <small>${escapeHtml(route.route)}</small>
            <small>${route.edge_count} edges · ${route.has_source_node ? "source node present" : "source node missing"}</small>
          </button>
        `).join("") || `<div class="empty-state">No routes are currently available.</div>`;

        for (const button of q("routeList").querySelectorAll("[data-route]")) {
          button.addEventListener("click", () => {
            const route = button.getAttribute("data-route");
            if (route) void loadRoute(route);
          });
        }
      }

      function renderFamilies() {
        const entries = familyEntries();
        q("familyNote").textContent = entries.length === 0 ? "Awaiting graph" : `${entries.length} node families in the selected route`;
        const nodesByFamily = new Map();
        for (const node of state.graph?.nodes || []) {
          const family = node.node_type || "unknown";
          if (!nodesByFamily.has(family)) nodesByFamily.set(family, []);
          nodesByFamily.get(family).push(node);
        }

        q("familyList").innerHTML = entries.map(([family, count]) => `
          <button type="button" class="family-item" data-family="${escapeHtml(family)}">
            <strong>${escapeHtml(family)}</strong>
            <small>${count} node${count === 1 ? "" : "s"} in the current route slice.</small>
          </button>
        `).join("") || `<div class="empty-state">No family counts yet.</div>`;

        for (const button of q("familyList").querySelectorAll("[data-family]")) {
          button.addEventListener("click", () => {
            const family = button.getAttribute("data-family");
            const firstNode = family ? nodesByFamily.get(family)?.[0] : null;
            if (firstNode) selectNode(firstNode.node_id);
          });
        }
      }

      function renderGraph() {
        if (!state.graph) {
          q("graphSvg").innerHTML = "";
          return;
        }

        const nodes = state.graph.nodes || [];
        const edges = state.graph.edges || [];
        const sourceNodeId = state.graph.source_node?.node_id || null;
        const positions = buildGraphLayout(nodes, sourceNodeId);
        const colors = familyColorMap();
        const labelsToShow = new Set([sourceNodeId, state.selectedNodeId].filter(Boolean));

        q("graphNote").textContent = `${nodes.length} nodes · ${edges.length} edges · source anchored in the center`;
        q("graphFooter").textContent = state.selectedEdgeId
          ? `Focused edge ${state.selectedEdgeId} from the relation pack.`
          : state.selectedNodeId
            ? `Focused node ${state.selectedNodeId}.`
            : "Click a node or edge to focus the inspector.";

        const edgeSvg = edges.map((edge) => {
          const fromPos = positions.get(edge.from_id);
          const toPos = positions.get(edge.to_id);
          if (!fromPos || !toPos) return "";
          const midX = (fromPos.x + toPos.x) / 2;
          const midY = (fromPos.y + toPos.y) / 2 - 26;
          return `
            <path class="graph-edge ${state.selectedEdgeId === edge.edge_id ? "active" : ""}" d="M ${fromPos.x} ${fromPos.y} Q ${midX} ${midY} ${toPos.x} ${toPos.y}" />
          `;
        }).join("");

        const nodeSvg = nodes.map((node) => {
          const point = positions.get(node.node_id);
          if (!point) return "";
          const showLabel = labelsToShow.has(node.node_id);
          const radius = node.node_id === state.selectedNodeId ? 16 : (node.node_id === sourceNodeId ? 17 : 11);
          return `
            <g class="graph-node" data-node-id="${escapeHtml(node.node_id)}">
              <title>${escapeHtml(nodeLabel(node))}</title>
              <circle cx="${point.x}" cy="${point.y}" r="${radius}" fill="${colors.get(node.node_type || "unknown") || point.color}" />
              ${showLabel ? `<text x="${point.x + 14}" y="${point.y - 12}">${escapeHtml(nodeLabel(node).slice(0, 34))}</text>` : ""}
            </g>
          `;
        }).join("");

        const sourceHalo = sourceNodeId && positions.get(sourceNodeId)
          ? `<circle cx="${positions.get(sourceNodeId).x}" cy="${positions.get(sourceNodeId).y}" r="28" fill="rgba(184, 132, 63, 0.08)" stroke="rgba(184, 132, 63, 0.28)" stroke-dasharray="4 6" />`
          : "";

        q("graphSvg").innerHTML = `
          <rect x="0" y="0" width="860" height="420" rx="24" fill="rgba(255,255,255,0.24)"></rect>
          ${sourceHalo}
          ${edgeSvg}
          ${nodeSvg}
        `;

        for (const nodeGroup of q("graphSvg").querySelectorAll("[data-node-id]")) {
          nodeGroup.addEventListener("click", () => {
            const nodeId = nodeGroup.getAttribute("data-node-id");
            if (nodeId) selectNode(nodeId);
          });
        }

        q("graphLegend").innerHTML = familyEntries().map(([family]) => `
          <span class="legend-item"><span class="legend-dot" style="background:${colors.get(family)}"></span>${escapeHtml(family)}</span>
        `).join("");
      }

      function renderNodeList() {
        if (!state.graph) {
          q("nodeList").innerHTML = "";
          return;
        }
        const entries = [...state.graph.nodes].sort((left, right) => nodeLabel(left).localeCompare(nodeLabel(right)));
        q("nodeRosterNote").textContent = `${entries.length} selectable nodes in the current route`;
        q("nodeList").innerHTML = entries.slice(0, 36).map((node) => `
          <button type="button" class="node-item ${node.node_id === state.selectedNodeId ? "active" : ""}" data-node-id="${escapeHtml(node.node_id)}">
            <strong>${escapeHtml(nodeLabel(node))}</strong>
            <small>${escapeHtml(node.node_type || "unknown")} · ${escapeHtml(node.node_id)}</small>
          </button>
        `).join("");
        for (const button of q("nodeList").querySelectorAll("[data-node-id]")) {
          button.addEventListener("click", () => {
            const nodeId = button.getAttribute("data-node-id");
            if (nodeId) selectNode(nodeId);
          });
        }
      }

      function renderEdgeList() {
        if (!state.graph) {
          q("edgeList").innerHTML = "";
          return;
        }
        const nodes = nodeMap();
        q("edgeRosterNote").textContent = `${state.graph.edges.length} edges from the active relation pack`;
        q("edgeList").innerHTML = state.graph.edges.slice(0, 40).map((edge) => `
          <button type="button" class="edge-item ${edge.edge_id === state.selectedEdgeId ? "active" : ""}" data-edge-id="${escapeHtml(edge.edge_id)}">
            <strong>${escapeHtml(edge.edge_id)} · ${escapeHtml(edge.predicate_id || "predicate-free")}</strong>
            <small>${escapeHtml(nodeLabel(nodes.get(edge.from_id)))} -> ${escapeHtml(nodeLabel(nodes.get(edge.to_id)))}</small>
          </button>
        `).join("");
        for (const button of q("edgeList").querySelectorAll("[data-edge-id]")) {
          button.addEventListener("click", () => {
            const edgeId = button.getAttribute("data-edge-id");
            if (edgeId) selectEdge(edgeId);
          });
        }
      }

      function renderInspector() {
        if (!state.graph) {
          q("inspectorBody").innerHTML = `<div class="empty-state">Choose a node or edge to inspect its canonical payload.</div>`;
          return;
        }

        const nodes = nodeMap();
        const selectedNode = state.selectedNodeId ? nodes.get(state.selectedNodeId) : null;
        const selectedEdge = state.selectedEdgeId ? state.graph.edges.find((edge) => edge.edge_id === state.selectedEdgeId) : null;

        if (selectedNode) {
          q("inspectorTitle").textContent = nodeLabel(selectedNode);
          q("inspectorMode").textContent = "Node";
          q("inspectorBody").innerHTML = `
            <div class="section-subtitle">${escapeHtml(selectedNode.node_id)}</div>
            <p class="muted">${escapeHtml(selectedNode.distilled_thesis || selectedNode.source_anchor || "No distilled thesis recorded for this node.")}</p>
            <div class="pill-row">
              <span class="pill">${escapeHtml(selectedNode.node_type || "unknown")}</span>
              <span class="pill">route ${escapeHtml(selectedNode.route_path || state.route || "n/a")}</span>
            </div>
            <div class="fact-grid">
              <div class="fact"><strong>Key terms</strong>${formatList(selectedNode.key_terms)}</div>
              <div class="fact"><strong>Interpretation layers</strong>${formatList(selectedNode.interpretation_layers)}</div>
              <div class="fact"><strong>Language witnesses</strong>${formatList(selectedNode.language_witnesses)}</div>
              <div class="fact"><strong>Translation tensions</strong>${formatList(selectedNode.translation_tensions)}</div>
            </div>
            <details><summary>Raw payload</summary><pre>${formatJson(selectedNode.raw_payload || {})}</pre></details>
          `;
          return;
        }

        if (selectedEdge) {
          q("inspectorTitle").textContent = `Edge ${selectedEdge.edge_id}`;
          q("inspectorMode").textContent = "Edge";
          q("inspectorBody").innerHTML = `
            <div class="section-subtitle">${escapeHtml(selectedEdge.from_id)} -> ${escapeHtml(selectedEdge.to_id)}</div>
            <div class="pill-row">
              <span class="pill">${escapeHtml(selectedEdge.predicate_id || "predicate-free")}</span>
              <span class="pill">${escapeHtml(selectedEdge.layer || "layer-free")}</span>
              <span class="pill">${escapeHtml(selectedEdge.edge_kind || "edge")}</span>
            </div>
            <div class="fact-grid">
              <div class="fact"><strong>Anchor mode</strong><pre>${escapeHtml(selectedEdge.anchor_mode || "n/a")}</pre></div>
              <div class="fact"><strong>Connectivity role</strong><pre>${escapeHtml(selectedEdge.connectivity_role || "n/a")}</pre></div>
              <div class="fact"><strong>Witness scope</strong><pre>${escapeHtml(selectedEdge.witness_scope || "n/a")}</pre></div>
              <div class="fact"><strong>Confidence / note</strong><pre>${escapeHtml(selectedEdge.confidence || "n/a")}\n${escapeHtml(selectedEdge.note || "")}</pre></div>
            </div>
            <details><summary>Raw edge row</summary><pre>${formatJson(selectedEdge)}</pre></details>
          `;
          return;
        }

        q("inspectorBody").innerHTML = `<div class="empty-state">Choose a node or edge to inspect its canonical payload.</div>`;
      }

      function renderSyncStatus() {
        const banner = q("syncStatus");
        if (!state.syncResult) {
          banner.className = "status-banner info";
          banner.textContent = boot.neo4j.note;
          return;
        }
        banner.className = "status-banner ok";
        banner.innerHTML = `Preview sync for <span class="code">${escapeHtml(state.syncResult.route)}</span>: ${state.syncResult.node_count} nodes, ${state.syncResult.edge_count} edges, target <span class="code">${escapeHtml(state.syncResult.projection_target)}</span>. ${escapeHtml(state.syncResult.note)}`;
      }

      function renderRouteSummary() {
        q("activeRouteTitle").textContent = routeLabel(state.route || boot.route_default);
        q("sourceNodeId").textContent = state.graph?.source_node?.node_id || "missing";
        q("missingNodes").textContent = String(state.graph?.diagnostics?.missing_nodes?.length || 0);
      }

      function renderAll() {
        renderHero();
        renderRouteSummary();
        renderMetrics();
        renderRoutes();
        renderFamilies();
        renderGraph();
        renderNodeList();
        renderEdgeList();
        renderInspector();
        renderSyncStatus();
      }

      async function loadRoutes() {
        const payload = await fetchJson("/api/routes");
        state.routes = payload.routes || [];
        state.route = routeFromHash() || state.routes[0]?.route || boot.route_default;
      }

      async function loadRoute(route) {
        document.body.classList.add("loading");
        try {
          setRouteHash(route);
          state.route = route;
          const [health, graph, tree] = await Promise.all([
            fetchJson("/health"),
            fetchJson(`/api/graph?route=${encodeURIComponent(route)}`),
            fetchJson(`/api/tree?route=${encodeURIComponent(route)}`),
          ]);
          state.health = health;
          state.graph = graph;
          state.tree = tree;
          state.syncResult = null;
          state.selectedEdgeId = null;
          state.selectedNodeId = graph.source_node?.node_id || graph.nodes?.[0]?.node_id || null;
          renderAll();
        } catch (error) {
          q("inspectorTitle").textContent = "Load failed";
          q("inspectorMode").textContent = "Error";
          q("inspectorBody").innerHTML = `<div class="status-banner warn">${escapeHtml(error.message || String(error))}</div>`;
        } finally {
          document.body.classList.remove("loading");
        }
      }

      async function previewSync() {
        if (!state.route) return;
        q("syncButton").disabled = true;
        q("syncButton").textContent = "Previewing...";
        try {
          state.syncResult = await fetchJson(`/api/project/sync?route=${encodeURIComponent(state.route)}`, { method: "POST" });
          renderSyncStatus();
        } catch (error) {
          q("syncStatus").className = "status-banner warn";
          q("syncStatus").textContent = error.message || String(error);
        } finally {
          q("syncButton").disabled = false;
          q("syncButton").textContent = "Preview sync counts";
        }
      }

      async function bootstrap() {
        q("syncButton").addEventListener("click", previewSync);
        window.addEventListener("hashchange", () => {
          const route = routeFromHash();
          if (route && route !== state.route) void loadRoute(route);
        });
        await loadRoutes();
        await loadRoute(state.route || boot.route_default);
      }

      void bootstrap();
    </script>
  </body>
</html>
"""


def render_index(settings: TosGraphSettings, neo4j_status: Neo4jStoreStatus) -> str:
    boot_payload = json.dumps(
        {
            "route_default": settings.route_default,
            "projection_mode": settings.projection_mode,
            "write_enabled": settings.write_enabled,
            "neo4j": {
                "configured": neo4j_status.configured,
                "uri": neo4j_status.uri,
                "user": neo4j_status.user,
                "note": neo4j_status.note,
            },
        },
        ensure_ascii=True,
    )

    html = INDEX_TEMPLATE.replace("__BOOT_PAYLOAD__", boot_payload)
    html = html.replace("__DEFAULT_ROUTE__", escape(settings.route_default))
    html = html.replace("__PROJECTION_MODE__", escape(settings.projection_mode))
    html = html.replace("__WRITE_MODE__", "true" if settings.write_enabled else "false")
    return html
