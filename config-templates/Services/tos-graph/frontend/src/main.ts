import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import "./styles.css";

type Mode = "philosophy" | "corpus";
type GraphMode = "clusters" | "nodes";
type DensityMode = "overview" | "focused" | "dense";

type BootPayload = {
  service: string;
  default_view: string;
  default_philosophy_view: string;
  write_enabled: boolean;
  projection_mode: string;
  neo4j: {
    configured: boolean;
    ready: boolean;
    note: string;
  };
};

type AnyItem = Record<string, unknown>;

type ViewCard = {
  view_id: string;
  title?: string;
  purpose?: string;
  layout_hint?: string;
  graph_layers?: string[];
  entry_surface?: string;
};

type Cluster = AnyItem & {
  cluster_id: string;
  cluster_kind?: string;
  label?: string;
  member_node_ids?: string[];
  source_refs?: string[];
  graph_layers?: string[];
};

type GraphNode = AnyItem & {
  node_id: string;
  label?: string;
  node_type?: string;
  source_ref?: string;
  graph_layers?: string[];
};

type GraphEdge = AnyItem & {
  edge_id: string;
  from_id: string;
  to_id: string;
  predicate_id?: string;
  source_ref?: string;
  graph_layers?: string[];
};

type PhilosophyViewPayload = {
  view: ViewCard;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  clusters?: Cluster[];
  source_refs?: string[];
  review_packet?: {
    packet?: AnyItem;
  };
};

type CorpusViewPayload = {
  view: ViewCard;
  items?: AnyItem[];
};

type AppState = {
  mode: Mode;
  graphMode: GraphMode;
  currentViewId: string;
  activeLayers: Set<string>;
  activePredicates: Set<string>;
  densityMode: DensityMode;
  minRelationCount: number;
  status: Record<string, AnyItem>;
  philosophyViews: ViewCard[];
  corpusViews: ViewCard[];
  currentView: PhilosophyViewPayload | CorpusViewPayload | null;
  selected: AnyItem | null;
  selectedGraphId: string | null;
  results: AnyItem[];
  relationItems: AnyItem[];
  expandedCluster: Cluster | null;
  searchQuery: string;
};

declare global {
  interface Window {
    __TOS_GRAPH_BOOT__: BootPayload;
  }
}

const boot = window.__TOS_GRAPH_BOOT__;

const palette = {
  default: "#247865",
  blue: "#426fa3",
  gold: "#b1742f",
  red: "#a3483f",
  violet: "#765fa2",
  grey: "#66736e",
  line: "rgba(23,32,29,0.22)",
};

const state: AppState = {
  mode: "philosophy",
  graphMode: "clusters",
  currentViewId: "",
  activeLayers: new Set(),
  activePredicates: new Set(),
  densityMode: "overview",
  minRelationCount: 1,
  status: {},
  philosophyViews: [],
  corpusViews: [],
  currentView: null,
  selected: null,
  selectedGraphId: null,
  results: [],
  relationItems: [],
  expandedCluster: null,
  searchQuery: "",
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("missing #app");
const appRoot = app;

let graph = new Graph({ multi: true, type: "directed" });
let renderer: Sigma | null = null;
let graphContainer: HTMLDivElement | null = null;
let nodeTooltip: HTMLDivElement | null = null;
let lastGraphItems = new Map<string, AnyItem>();
let hoveredNodeId: string | null = null;
const lastPointer = { x: 0, y: 0 };

function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

function short(value: unknown, length = 58): string {
  const raw = text(value);
  return raw.length > length ? `${raw.slice(0, length - 1)}...` : raw;
}

function escapeHtml(value: unknown): string {
  return text(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function itemId(item: AnyItem): string {
  return text(item.node_id || item.edge_id || item.cluster_id || item.packet_id || item.pack_id || item.id || item.path || item.view_id || "item");
}

function itemTitle(item: AnyItem): string {
  return text(item.label || item.title || item.name || item.view_id || itemId(item));
}

function itemSubtitle(item: AnyItem): string {
  return text(
    item.node_type ||
      item.cluster_kind ||
      item.predicate_id ||
      item.source_ref ||
      item.source_path ||
      item.path ||
      item.layout_hint ||
      item.purpose ||
      "",
  );
}

function humanKind(value: unknown): string {
  return text(value).replaceAll("_", " ").replaceAll("-", " ").trim();
}

function displayTitle(item: AnyItem): string {
  const raw = itemTitle(item).trim();
  const canon = raw.match(/^Canon Or Candidate Status:\s*(.+)$/i);
  if (canon) return `Status ${canon[1].trim()}`;
  const concept = raw.match(/^Concept Or Problem:\s*(.+)$/i);
  if (concept) return concept[1].trim();
  const corpus = raw.match(/^Corpus Or Prepared Source Document:\s*(.+)$/i);
  const title = corpus ? corpus[1].trim() : raw;
  return (
    title
      .replace(/^ToS Deep Research[_ ]*/i, "")
      .replace(/\.docx$/i, "")
      .replace(/\s+/g, " ")
      .trim() || raw
  );
}

function displaySubtitle(item: AnyItem): string {
  if (item.relation_count) {
    return `${humanKind(item.primary_predicate || item.predicate_id || "relation")} · ${text(item.relation_count)} relations`;
  }
  const kind = humanKind(item.cluster_kind || item.node_type || item.predicate_id);
  const subtitle = itemSubtitle(item);
  const pieces = [kind, subtitle === kind || subtitle.replaceAll("-", " ") === kind ? "" : humanKind(subtitle)].filter(Boolean);
  return [...new Set(pieces)].join(" · ");
}

function compactGraphLabel(item: AnyItem): string {
  const kind = text(item.cluster_kind || item.node_type || item.predicate_id);
  if (kind === "corpus") return short(displayTitle(item), 28);
  if (kind === "canon-candidate-status") return displayTitle(item);
  if (kind === "concept-problem") return short(displayTitle(item), 18);
  if (kind) return short(humanKind(kind), 18);
  return short(displayTitle(item), 18);
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

function isPhilosophyView(payload: PhilosophyViewPayload | CorpusViewPayload | null): payload is PhilosophyViewPayload {
  return Boolean(payload && ("nodes" in payload || "clusters" in payload || "edges" in payload));
}

function itemLayers(item: AnyItem): string[] {
  const layers = item.graph_layers;
  return Array.isArray(layers) ? layers.map(text) : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : [];
}

function layerAllowed(item: AnyItem): boolean {
  const layers = itemLayers(item);
  if (state.activeLayers.size === 0 || layers.length === 0) return true;
  return layers.some((layer) => state.activeLayers.has(layer));
}

function predicateId(item: AnyItem): string {
  return text(item.predicate_id || item.primary_predicate || "relation");
}

function currentPredicates(): string[] {
  if (!isPhilosophyView(state.currentView)) return [];
  const predicates = new Set<string>();
  (state.currentView.edges || []).forEach((edge) => {
    if (layerAllowed(edge)) predicates.add(predicateId(edge));
  });
  return [...predicates].sort();
}

function predicateAllowed(item: AnyItem): boolean {
  if (!isPhilosophyView(state.currentView) || (state.currentView.edges || []).length === 0) return true;
  return state.activePredicates.has(predicateId(item));
}

function relationAllowed(item: AnyItem): boolean {
  return layerAllowed(item) && predicateAllowed(item);
}

function relationLimit(): number {
  if (state.densityMode === "dense") return 520;
  if (state.densityMode === "focused") return 280;
  return 150;
}

function edgeLimit(): number {
  if (state.densityMode === "dense") return 3200;
  if (state.densityMode === "focused") return 1800;
  return 900;
}

function relationCountAllowed(item: AnyItem): boolean {
  const count = Number(item.relation_count || 1);
  return !Number.isFinite(count) || count >= state.minRelationCount;
}

function countBy<T>(items: T[], key: (item: T) => string): Map<string, number> {
  const counts = new Map<string, number>();
  items.forEach((item) => {
    const value = key(item);
    if (!value) return;
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  return counts;
}

function colorFor(item: AnyItem, index: number): string {
  const kind = text(item.cluster_kind || item.node_type || item.predicate_id);
  if (kind.includes("source") || kind.includes("corpus")) return palette.blue;
  if (kind.includes("canon") || kind.includes("candidate")) return palette.gold;
  if (kind.includes("evidence") || kind.includes("unresolved")) return palette.red;
  if (kind.includes("concept") || kind.includes("lineage")) return palette.violet;
  return [palette.default, palette.blue, palette.gold, palette.violet, palette.grey][index % 5];
}

function edgeColorFor(item: AnyItem): string {
  const predicate = text(item.predicate_id || item.primary_predicate || "");
  const layers = itemLayers(item).join(" ");
  const signal = `${predicate} ${layers}`;
  if (signal.includes("source") || signal.includes("prepared") || signal.includes("contains")) return "rgba(66,111,163,0.55)";
  if (signal.includes("canon") || signal.includes("candidate")) return "rgba(177,116,47,0.56)";
  if (signal.includes("evidence") || signal.includes("unresolved")) return "rgba(163,72,63,0.52)";
  if (signal.includes("concept") || signal.includes("lineage")) return "rgba(118,95,162,0.54)";
  return palette.line;
}

function relationWeight(item: AnyItem): number {
  const count = Number(item.relation_count || item.member_count || item.count || 1);
  if (!Number.isFinite(count) || count <= 1) return 1.05;
  return Math.min(5.2, 1.05 + Math.log2(count + 1) * 0.52);
}

function renderShell(): void {
  appRoot.innerHTML = `
    <div class="app-shell">
      <aside class="panel left-rail">
        <div class="rail-head">
          <h1 class="brand-title">Tree of Sophia Graph</h1>
          <p class="brand-note">Runtime workbench for ToS-owned projection exports.</p>
        </div>
        <div class="segmented">
          <button id="mode-philosophy" class="mode-button" type="button">Philosophy</button>
          <button id="mode-corpus" class="mode-button" type="button">Corpus</button>
        </div>
        <div class="rail-scroll">
          <div class="input-row">
            <input id="search" type="search" placeholder="Search nodes, clusters, refs" />
            <div class="inline-actions">
              <button id="search-button" type="button">Search</button>
              <button id="sync-button" type="button">Sync</button>
            </div>
          </div>
          <div class="section-title">Views</div>
          <div id="view-list" class="stack"></div>
          <div class="section-title">Layers</div>
          <div id="layer-list" class="stack"></div>
          <div class="section-title">Relations</div>
          <div id="relation-controls" class="relation-controls"></div>
        </div>
      </aside>
      <main class="panel main-stage">
        <div class="toolbar">
          <div class="chip-row">
            <span class="chip">Mode <strong id="mode-chip"></strong></span>
            <span class="chip">View <strong id="view-chip"></strong></span>
            <span class="chip">Neo4j <strong id="neo4j-chip"></strong></span>
            <span class="chip">Projection <strong id="projection-chip"></strong></span>
          </div>
          <div id="metrics" class="metric-row"></div>
          <div class="inline-actions">
            <button id="clusters-button" type="button">Clusters</button>
            <button id="nodes-button" type="button">Nodes</button>
            <button id="fit-button" type="button">Fit</button>
            <button id="review-button" type="button">Review packet</button>
            <button id="unresolved-button" type="button">Unresolved</button>
          </div>
        </div>
        <div class="graph-wrap">
          <div id="graph"></div>
          <div id="graph-empty" class="graph-empty" hidden>No graph payload for this view.</div>
          <div id="graph-caption" class="graph-caption"></div>
          <div id="node-tooltip" class="node-tooltip" hidden></div>
        </div>
      </main>
      <aside class="panel right-rail">
        <div class="inspector-head">
          <h2 id="inspector-title" class="inspector-title">Selection</h2>
          <div id="inspector-meta" class="muted">Nothing selected.</div>
        </div>
        <div class="segmented">
          <button id="snapshot-button" type="button">Snapshot</button>
          <button id="audit-button" type="button">Audit</button>
        </div>
        <div class="inspector-scroll">
          <div id="detail-list" class="detail-grid"></div>
        </div>
      </aside>
    </div>
  `;

  graphContainer = document.querySelector<HTMLDivElement>("#graph");
  nodeTooltip = document.querySelector<HTMLDivElement>("#node-tooltip");
  bindShellEvents();
}

function bindShellEvents(): void {
  byId("mode-philosophy").addEventListener("click", () => void loadMode("philosophy"));
  byId("mode-corpus").addEventListener("click", () => void loadMode("corpus"));
  byId("clusters-button").addEventListener("click", () => {
    state.expandedCluster = null;
    state.graphMode = "clusters";
    renderAll();
  });
  byId("nodes-button").addEventListener("click", () => {
    state.graphMode = "nodes";
    renderAll();
  });
  byId("fit-button").addEventListener("click", () => renderer?.getCamera().animatedReset({ duration: 260 }));
  byId("review-button").addEventListener("click", () => void showReviewPacket());
  byId("unresolved-button").addEventListener("click", () => void showUnresolved());
  byId("snapshot-button").addEventListener("click", () => void showSnapshot());
  byId("audit-button").addEventListener("click", () => void showAudit());
  byId("sync-button").addEventListener("click", () => void syncProjection());
  byId("search-button").addEventListener("click", () => void search());
  const searchInput = byId("search") as HTMLInputElement;
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") void search();
  });
  graphContainer?.addEventListener("pointermove", (event) => {
    lastPointer.x = event.clientX;
    lastPointer.y = event.clientY;
    if (hoveredNodeId) positionNodeTooltip();
  });
  graphContainer?.addEventListener("pointerleave", hideNodeTooltip);
  graphContainer?.addEventListener("wheel", hideNodeTooltip, { passive: true });
}

function byId(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id}`);
  return element;
}

function setActive(id: string, active: boolean): void {
  byId(id).classList.toggle("active", active);
}

function renderChips(): void {
  byId("mode-chip").textContent = state.mode;
  byId("view-chip").textContent = state.currentViewId || "none";
  byId("neo4j-chip").textContent = boot.neo4j.ready ? "ready" : boot.neo4j.configured ? "preview" : "deferred";
  const status = state.mode === "philosophy" ? state.status.philosophy : state.status.corpus;
  byId("projection-chip").textContent = text(status?.projection_exists ?? status?.index_exists ?? "loading");
  setActive("mode-philosophy", state.mode === "philosophy");
  setActive("mode-corpus", state.mode === "corpus");
  setActive("clusters-button", state.graphMode === "clusters");
  setActive("nodes-button", state.graphMode === "nodes");
}

function renderMetrics(): void {
  const status = state.mode === "philosophy" ? state.status.philosophy : state.status.corpus;
  const counts = (status?.counts || {}) as Record<string, unknown>;
  const keys =
    state.mode === "philosophy"
      ? ["views", "graph_layers", "nodes", "edges", "clusters", "review_packets"]
      : ["branches", "manifests", "nodes", "relation_packs", "relation_edges", "resources"];
  byId("metrics").innerHTML = keys
    .map(
      (key) => `
        <div class="metric">
          <strong>${text(counts[key] ?? 0)}</strong>
          <span>${key.replaceAll("_", " ")}</span>
        </div>
      `,
    )
    .join("");
}

function renderViews(): void {
  const views = state.mode === "philosophy" ? state.philosophyViews : state.corpusViews;
  byId("view-list").innerHTML = views
    .map(
      (view) => `
        <button class="view-card ${view.view_id === state.currentViewId ? "active" : ""}" data-view="${view.view_id}" type="button">
          <span class="view-title">${short(view.title || view.view_id, 72)}</span>
          <span class="view-subtitle">${short(view.layout_hint || view.purpose || view.entry_surface || "", 92)}</span>
        </button>
      `,
    )
    .join("");
  byId("view-list").querySelectorAll<HTMLButtonElement>("[data-view]").forEach((button) => {
    button.addEventListener("click", () => void loadView(button.dataset.view || ""));
  });
}

function renderLayers(): void {
  if (state.mode !== "philosophy" || !isPhilosophyView(state.currentView)) {
    byId("layer-list").innerHTML = `<div class="muted">No layer contract for corpus view.</div>`;
    return;
  }
  const layers = state.currentView.view.graph_layers || [];
  if (layers.length === 0) {
    byId("layer-list").innerHTML = `<div class="muted">No layers for this view.</div>`;
    return;
  }
  byId("layer-list").innerHTML = layers
    .map(
      (layer) => `
        <label class="layer-toggle ${state.activeLayers.has(layer) ? "active" : ""}">
          <input data-layer="${layer}" type="checkbox" ${state.activeLayers.has(layer) ? "checked" : ""} />
          <span>${layer}</span>
        </label>
      `,
    )
    .join("");
  byId("layer-list").querySelectorAll<HTMLInputElement>("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = input.dataset.layer || "";
      if (input.checked) state.activeLayers.add(layer);
      else state.activeLayers.delete(layer);
      renderAll();
    });
  });
}

function renderRelationControls(): void {
  const root = byId("relation-controls");
  if (state.mode !== "philosophy" || !isPhilosophyView(state.currentView)) {
    root.innerHTML = `<div class="muted">No relation contract for corpus view.</div>`;
    return;
  }
  const layerEdges = (state.currentView.edges || []).filter(layerAllowed);
  const activeEdges = layerEdges.filter(predicateAllowed);
  const predicateCounts = countBy(layerEdges, predicateId);
  const predicates = [...predicateCounts.entries()].sort((left, right) => right[1] - left[1]);
  root.innerHTML = `
    <div class="relation-summary">
      <strong>${activeEdges.length}</strong>
      <span>of ${layerEdges.length} relations</span>
    </div>
    <div class="density-row">
      ${(["overview", "focused", "dense"] as DensityMode[])
        .map(
          (mode) => `
            <button class="density-button ${state.densityMode === mode ? "active" : ""}" data-density="${mode}" type="button">
              ${mode}
            </button>
          `,
        )
        .join("")}
    </div>
    <div class="threshold-row">
      <button id="relation-min-dec" type="button">-</button>
      <span>min ${state.minRelationCount}</span>
      <button id="relation-min-inc" type="button">+</button>
      <button id="predicate-reset" type="button">All</button>
    </div>
    <div class="predicate-list">
      ${predicates
        .map(
          ([predicate, count]) => `
            <label class="predicate-toggle ${state.activePredicates.has(predicate) ? "active" : ""}">
              <input data-predicate="${escapeHtml(predicate)}" type="checkbox" ${
                state.activePredicates.has(predicate) ? "checked" : ""
              } />
              <span>${escapeHtml(humanKind(predicate))}</span>
              <small>${count}</small>
            </label>
          `,
        )
        .join("")}
    </div>
  `;

  root.querySelectorAll<HTMLButtonElement>("[data-density]").forEach((button) => {
    button.addEventListener("click", () => {
      state.densityMode = (button.dataset.density || "overview") as DensityMode;
      renderAll();
    });
  });
  root.querySelectorAll<HTMLInputElement>("[data-predicate]").forEach((input) => {
    input.addEventListener("change", () => {
      const predicate = input.dataset.predicate || "";
      if (input.checked) state.activePredicates.add(predicate);
      else state.activePredicates.delete(predicate);
      renderAll();
    });
  });
  root.querySelector<HTMLButtonElement>("#relation-min-dec")?.addEventListener("click", () => {
    state.minRelationCount = Math.max(1, state.minRelationCount - 1);
    renderAll();
  });
  root.querySelector<HTMLButtonElement>("#relation-min-inc")?.addEventListener("click", () => {
    state.minRelationCount = Math.min(50, state.minRelationCount + 1);
    renderAll();
  });
  root.querySelector<HTMLButtonElement>("#predicate-reset")?.addEventListener("click", () => {
    state.activePredicates = new Set(currentPredicates());
    renderAll();
  });
}

function renderInspector(): void {
  const title = state.selected ? displayTitle(state.selected) : state.currentView?.view?.title || state.currentViewId || "Selection";
  byId("inspector-title").textContent = title;
  byId("inspector-meta").textContent = state.selected
    ? displaySubtitle(state.selected)
    : "Select a graph node, cluster, result, review packet, snapshot, or audit entry.";

  const cards: string[] = [];
  if (state.selected) {
    cards.push(...relationDetailCards(state.selected));
    const refs = collectRefs(state.selected);
    if (refs.length) {
      cards.push(detailCard("Source refs", refs.slice(0, 8).join("\n")));
    }
    cards.push(detailCard("Payload", JSON.stringify(state.selected, null, 2), true));
  }
  if (state.results.length) {
    cards.push(`<div class="section-title">Results</div>`);
    cards.push(
      ...state.results.slice(0, 48).map(
        (item, index) => `
          <button class="result-card" data-result="${index}" type="button">
            <span class="result-title">${escapeHtml(short(displayTitle(item), 82))}</span>
            <span class="result-subtitle">${escapeHtml(short(displaySubtitle(item), 98))}</span>
          </button>
        `,
      ),
    );
  }
  if (state.relationItems.length) {
    cards.push(`<div class="section-title">Relations</div>`);
    cards.push(
      ...state.relationItems.slice(0, 48).map(
        (item, index) => `
          <button class="result-card relation-card" data-relation="${index}" type="button">
            <span class="result-title">${escapeHtml(short(displayTitle(item), 86))}</span>
            <span class="result-subtitle">${escapeHtml(short(displaySubtitle(item), 102))}</span>
          </button>
        `,
      ),
    );
  }
  byId("detail-list").innerHTML = cards.join("") || detailCard("No detail", "Use search or click the graph.");
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-result]").forEach((button) => {
    button.addEventListener("click", () => selectItem(state.results[Number(button.dataset.result)]));
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-relation]").forEach((button) => {
    button.addEventListener("click", () => selectItem(state.relationItems[Number(button.dataset.relation)]));
  });
}

function detailCard(title: string, body: string, pre = false): string {
  const safeTitle = escapeHtml(title);
  const safeBody = escapeHtml(body);
  return `
    <div class="detail-card">
      <span class="detail-title">${safeTitle}</span>
      ${pre ? `<pre>${safeBody}</pre>` : `<span class="detail-body">${safeBody}</span>`}
    </div>
  `;
}

function relationDetailCards(item: AnyItem): string[] {
  if (!item.relation_count) return [];
  const predicates = item.predicates && typeof item.predicates === "object" ? (item.predicates as Record<string, unknown>) : {};
  const predicateText = Object.entries(predicates)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .slice(0, 8)
    .map(([predicate, count]) => `${humanKind(predicate)}: ${count}`)
    .join("\n");
  const layers = itemLayers(item).join("\n");
  const memberEdges = stringList(item.member_edge_ids).slice(0, 12).join("\n");
  const cards = [
    detailCard("From", text(item.from_label || item.from_id)),
    detailCard("To", text(item.to_label || item.to_id)),
    detailCard("Predicate", humanKind(item.primary_predicate || item.predicate_id)),
    detailCard("Relation count", text(item.relation_count)),
  ];
  if (predicateText) cards.push(detailCard("Predicate mix", predicateText));
  if (layers) cards.push(detailCard("Graph layers", layers));
  if (memberEdges) cards.push(detailCard("Member edges", memberEdges));
  return cards;
}

function collectRefs(item: AnyItem): string[] {
  const refs = new Set<string>();
  for (const key of ["source_ref", "source_path", "path"]) {
    if (item[key]) refs.add(text(item[key]));
  }
  const sourceRefs = item.source_refs;
  if (Array.isArray(sourceRefs)) sourceRefs.forEach((ref) => refs.add(text(ref)));
  return [...refs].filter(Boolean);
}

function showNodeTooltip(nodeId: string): void {
  const item = lastGraphItems.get(nodeId);
  if (!nodeTooltip || !item) return;
  hoveredNodeId = nodeId;
  const refs = collectRefs(item).slice(0, 3);
  const layers = itemLayers(item).slice(0, 4);
  const memberIds = item.member_node_ids;
  const members = Array.isArray(memberIds) ? `${memberIds.length} members` : "";
  const meta = [displaySubtitle(item), members].filter(Boolean).join(" · ");
  nodeTooltip.innerHTML = `
    <div class="node-tooltip-title">${escapeHtml(displayTitle(item))}</div>
    ${meta ? `<div class="node-tooltip-meta">${escapeHtml(meta)}</div>` : ""}
    ${
      layers.length
        ? `<div class="node-tooltip-tags">${layers.map((layer) => `<span>${escapeHtml(layer)}</span>`).join("")}</div>`
        : ""
    }
    ${
      refs.length
        ? `<div class="node-tooltip-refs">${refs.map((ref) => `<span>${escapeHtml(short(ref, 128))}</span>`).join("")}</div>`
        : ""
    }
  `;
  nodeTooltip.hidden = false;
  positionNodeTooltip();
}

function hideNodeTooltip(): void {
  hoveredNodeId = null;
  if (nodeTooltip) nodeTooltip.hidden = true;
}

function positionNodeTooltip(): void {
  if (!nodeTooltip || nodeTooltip.hidden) return;
  const rect = nodeTooltip.parentElement?.getBoundingClientRect();
  if (!rect) return;
  const margin = 10;
  const width = nodeTooltip.offsetWidth || 320;
  const height = nodeTooltip.offsetHeight || 140;
  const preferredLeft = lastPointer.x - rect.left + 16;
  const preferredTop = lastPointer.y - rect.top + 16;
  const left = Math.max(margin, Math.min(preferredLeft, rect.width - width - margin));
  const top = Math.max(margin, Math.min(preferredTop, rect.height - height - margin));
  nodeTooltip.style.left = `${left}px`;
  nodeTooltip.style.top = `${top}px`;
}

function graphFocus(): { nodes: Set<string>; edges: Set<string> } | null {
  const selected = state.selectedGraphId;
  if (!selected) return null;
  const nodes = new Set<string>();
  const edges = new Set<string>();
  if (graph.hasEdge(selected)) {
    const [source, target] = graph.extremities(selected);
    nodes.add(source);
    nodes.add(target);
    edges.add(selected);
    return { nodes, edges };
  }
  if (!graph.hasNode(selected)) return null;
  nodes.add(selected);
  graph.forEachEdge((edge, _attributes, source, target) => {
    if (source === selected || target === selected) {
      nodes.add(source);
      nodes.add(target);
      edges.add(edge);
    }
  });
  return { nodes, edges };
}

function renderGraph(): void {
  if (!graphContainer) return;
  hideNodeTooltip();
  renderer?.kill();
  graph.clear();
  lastGraphItems = new Map();
  state.relationItems = [];

  if (!state.currentView) {
    setGraphEmpty(true, "No view loaded.");
    return;
  }

  if (state.mode === "corpus") buildCorpusGraph();
  else if (state.graphMode === "clusters") buildClusterGraph();
  else buildNodeGraph();

  if (graph.order === 0) {
    setGraphEmpty(true, "No graph payload for current filters.");
    return;
  }

  setGraphEmpty(false);
  const focus = graphFocus();
  renderer = new Sigma(graph, graphContainer, {
    allowInvalidContainer: true,
    defaultNodeColor: palette.default,
    defaultEdgeColor: palette.line,
    enableEdgeEvents: true,
    labelDensity: 0.008,
    labelGridCellSize: 220,
    labelRenderedSizeThreshold: 24,
    minEdgeThickness: 0.7,
    minCameraRatio: 0.08,
    maxCameraRatio: 8,
    renderEdgeLabels: false,
    nodeReducer: (node, data) => {
      if (!focus) return data;
      if (focus.nodes.has(node)) {
        return { ...data, forceLabel: true, highlighted: true, zIndex: Number(data.zIndex || 0) + 100 };
      }
      return { ...data, label: "", color: "rgba(102, 115, 110, 0.18)", zIndex: 0 };
    },
    edgeReducer: (edge, data) => {
      if (!focus) return data;
      if (focus.edges.has(edge)) {
        return { ...data, size: Number(data.size || 1) * 1.9, color: "rgba(36, 120, 101, 0.76)", zIndex: 100 };
      }
      return { ...data, size: 0.22, color: "rgba(102, 115, 110, 0.07)", zIndex: 0 };
    },
    defaultDrawNodeHover: (context, data) => {
      context.beginPath();
      context.arc(data.x, data.y, data.size + 4, 0, Math.PI * 2);
      context.fillStyle = "rgba(255, 255, 255, 0.9)";
      context.fill();
      context.lineWidth = 2;
      context.strokeStyle = "rgba(23, 32, 29, 0.26)";
      context.stroke();
    },
    zIndex: true,
  });
  renderer.on("enterNode", ({ node }) => showNodeTooltip(node));
  renderer.on("leaveNode", hideNodeTooltip);
  renderer.on("enterEdge", ({ edge }) => showNodeTooltip(edge));
  renderer.on("leaveEdge", hideNodeTooltip);
  renderer.on("clickNode", ({ node }) => {
    const payload = lastGraphItems.get(node);
    if (payload) selectItem(payload);
  });
  renderer.on("clickEdge", ({ edge }) => {
    const payload = lastGraphItems.get(edge);
    if (payload) selectItem(payload);
  });
  renderer.getCamera().animatedReset({ duration: 220 });
}

function setGraphEmpty(empty: boolean, message = ""): void {
  const emptyNode = byId("graph-empty");
  emptyNode.hidden = !empty;
  emptyNode.textContent = message || "No graph payload.";
  const caption = byId("graph-caption");
  const view = state.currentView?.view;
  const graphSummary = graph.order > 0 ? ` · ${graph.order} nodes · ${graph.size} links` : "";
  caption.textContent = `${view?.title || state.currentViewId || "View"} · ${view?.layout_hint || view?.purpose || boot.projection_mode}${graphSummary}`;
}

function buildClusterGraph(): void {
  if (!isPhilosophyView(state.currentView)) return;
  const clusters = (state.currentView.clusters || []).filter(layerAllowed).slice(0, 360);
  const nodes = (state.currentView.nodes || []).filter(layerAllowed);
  const edges = (state.currentView.edges || []).filter(relationAllowed);
  const nodeToCluster = new Map<string, string[]>();
  clusters.forEach((cluster) => {
    stringList(cluster.member_node_ids).forEach((nodeId) => {
      const ids = nodeToCluster.get(nodeId) || [];
      ids.push(cluster.cluster_id);
      nodeToCluster.set(nodeId, ids);
    });
  });

  clusters.forEach((cluster, index) => {
    addGraphNode(cluster.cluster_id, cluster, index, Math.max(8, Math.min(30, 8 + (cluster.member_node_ids?.length || 0) * 0.16)));
  });
  const relationBuild = addClusterRelationEdges(edges, nodeToCluster, clusters);
  const relationPairs = relationBuild.relationPairs;
  const linked = new Set<string>();
  if (state.densityMode !== "overview") {
    nodes.slice(0, state.densityMode === "dense" ? 1200 : 700).forEach((node) => {
      const ids = nodeToCluster.get(node.node_id) || [];
      for (let i = 0; i < ids.length; i += 1) {
        for (let j = i + 1; j < ids.length; j += 1) {
          const key = [ids[i], ids[j]].sort().join("::");
          if (linked.has(key)) continue;
          linked.add(key);
          if (relationPairs.has(key)) continue;
          graph.addDirectedEdgeWithKey(`cluster-edge:${key}`, ids[i], ids[j], {
            size: 0.5,
            color: "rgba(23,32,29,0.1)",
          });
        }
      }
    });
  }
  layoutGraph();
  state.results = clusters;
  state.relationItems = relationBuild.relationItems;
}

function addClusterRelationEdges(
  edges: GraphEdge[],
  nodeToCluster: Map<string, string[]>,
  clusters: Cluster[],
): { relationPairs: Set<string>; relationItems: AnyItem[] } {
  const clusterById = new Map(clusters.map((cluster) => [cluster.cluster_id, cluster]));
  const aggregates = new Map<
    string,
    {
      from_id: string;
      to_id: string;
      relation_count: number;
      predicates: Map<string, number>;
      graph_layers: Set<string>;
      source_refs: Set<string>;
      member_edge_ids: string[];
    }
  >();
  const relationPairs = new Set<string>();
  const relationItems: AnyItem[] = [];

  edges.forEach((edge) => {
    const fromClusterIds = nodeToCluster.get(edge.from_id) || [];
    const toClusterIds = nodeToCluster.get(edge.to_id) || [];
    fromClusterIds.forEach((fromId) => {
      toClusterIds.forEach((toId) => {
        if (fromId === toId) return;
        const key = `${fromId}->${toId}`;
        const existing =
          aggregates.get(key) ||
          {
            from_id: fromId,
            to_id: toId,
            relation_count: 0,
            predicates: new Map<string, number>(),
            graph_layers: new Set<string>(),
            source_refs: new Set<string>(),
            member_edge_ids: [],
          };
        existing.relation_count += 1;
        const predicate = edge.predicate_id || "relation";
        existing.predicates.set(predicate, (existing.predicates.get(predicate) || 0) + 1);
        itemLayers(edge).forEach((layer) => existing.graph_layers.add(layer));
        collectRefs(edge).forEach((ref) => existing.source_refs.add(ref));
        if (edge.edge_id) existing.member_edge_ids.push(edge.edge_id);
        aggregates.set(key, existing);
        relationPairs.add([fromId, toId].sort().join("::"));
      });
    });
  });

  [...aggregates.values()]
    .filter(relationCountAllowed)
    .sort((left, right) => right.relation_count - left.relation_count)
    .slice(0, relationLimit())
    .forEach((aggregate, index) => {
      const predicates = Object.fromEntries(aggregate.predicates.entries());
      const primaryPredicate =
        [...aggregate.predicates.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || "relation";
      const fromCluster = clusterById.get(aggregate.from_id);
      const toCluster = clusterById.get(aggregate.to_id);
      const payload: AnyItem = {
        edge_id: `cluster-relation:${index}`,
        from_id: aggregate.from_id,
        to_id: aggregate.to_id,
        predicate_id: primaryPredicate,
        primary_predicate: primaryPredicate,
        relation_count: aggregate.relation_count,
        predicates,
        graph_layers: [...aggregate.graph_layers],
        source_refs: [...aggregate.source_refs],
        member_edge_ids: aggregate.member_edge_ids.slice(0, 80),
        from_label: displayTitle(fromCluster || { label: aggregate.from_id }),
        to_label: displayTitle(toCluster || { label: aggregate.to_id }),
        label: `${displayTitle(fromCluster || { label: aggregate.from_id })} -> ${displayTitle(toCluster || { label: aggregate.to_id })}`,
      };
      addGraphEdge(payload.edge_id as string, aggregate.from_id, aggregate.to_id, payload);
      relationItems.push(payload);
    });

  return { relationPairs, relationItems };
}

function buildNodeGraph(): void {
  if (!isPhilosophyView(state.currentView)) return;
  const expandedIds = new Set(state.expandedCluster?.member_node_ids || []);
  const nodes = (state.currentView.nodes || [])
    .filter(layerAllowed)
    .filter((node) => expandedIds.size === 0 || expandedIds.has(node.node_id))
    .slice(0, 1200);
  const visible = new Set(nodes.map((node) => node.node_id));
  nodes.forEach((node, index) => addGraphNode(node.node_id, node, index, 7));
  const visibleEdges = (state.currentView.edges || [])
    .filter(relationAllowed)
    .filter((edge) => visible.has(edge.from_id) && visible.has(edge.to_id))
    .slice(0, edgeLimit());
  visibleEdges.forEach((edge, index) => addGraphEdge(edge.edge_id || `edge:${index}`, edge.from_id, edge.to_id, edge));
  layoutGraph();
  state.results = nodes;
  state.relationItems = visibleEdges.slice(0, 180);
}

function buildCorpusGraph(): void {
  const payload = state.currentView as CorpusViewPayload;
  const items = (payload.items || []).slice(0, 700);
  const rootId = `view:${state.currentViewId}`;
  addGraphNode(rootId, payload.view, 0, 16);
  items.forEach((item, index) => {
    const id = itemId(item);
    addGraphNode(id, item, index + 1, 7);
    addGraphEdge(`corpus-edge:${rootId}:${id}`, rootId, id, { edge_id: `corpus-edge:${id}`, predicate_id: "contains", ...item });
  });
  layoutGraph();
  state.results = items;
  state.relationItems = [];
}

function addGraphNode(id: string, item: AnyItem, index: number, size: number): void {
  if (graph.hasNode(id)) return;
  lastGraphItems.set(id, item);
  graph.addNode(id, {
    label: compactGraphLabel(item),
    size,
    color: colorFor(item, index),
    x: Math.cos(index) * (1 + index / 40),
    y: Math.sin(index) * (1 + index / 40),
    zIndex: size,
  });
}

function addGraphEdge(id: string, from: string, to: string, item: AnyItem): void {
  if (!graph.hasNode(from) || !graph.hasNode(to) || graph.hasEdge(id)) return;
  lastGraphItems.set(id, item);
  graph.addDirectedEdgeWithKey(id, from, to, {
    size: relationWeight(item),
    color: edgeColorFor(item),
  });
}

function hashNumber(value: string): number {
  return value.split("").reduce((acc, char) => (acc * 31 + char.charCodeAt(0)) % 100000, 17);
}

function laneForItem(item: AnyItem, fallback: number): number {
  const signal = text(item.cluster_kind || item.node_type || item.primary_predicate || item.predicate_id || item.label || item.title);
  if (signal.includes("canon") || signal.includes("candidate")) return 0;
  if (signal.includes("source") || signal.includes("corpus")) return 1;
  if (signal.includes("concept") || signal.includes("lineage")) return 2;
  if (signal.includes("evidence") || signal.includes("unresolved")) return 3;
  return fallback % 5;
}

function layoutGraph(): void {
  const count = Math.max(graph.order, 1);
  const hint = text(state.currentView?.view?.layout_hint);
  const nodes = graph.nodes();
  const span = 1 + count / 90;
  nodes.forEach((node, index) => {
    const item = lastGraphItems.get(node) || {};
    const hash = hashNumber(node);
    const lane = laneForItem(item, hash);
    const jitter = ((hash % 29) - 14) / 120;
    let x = 0;
    let y = 0;
    if (hint.includes("timeline") || hint.includes("lane")) {
      x = ((index / Math.max(count - 1, 1)) * 2 - 1) * (1.4 + count / 80);
      y = (lane - 2) * 0.72 + jitter;
    } else if (hint.includes("directed") || hint.includes("flow") || hint.includes("corridor")) {
      x = (lane - 2) * 1.2 + jitter;
      y = ((index / Math.max(count - 1, 1)) * 2 - 1) * (1.2 + count / 95);
    } else if (hint.includes("dag") || hint.includes("evidence") || hint.includes("uncertainty")) {
      x = (lane - 2) * 1.1 + jitter;
      y = ((hash % 97) / 48.5 - 1) * (1.4 + count / 110);
    } else {
      const angle = (Math.PI * 2 * (hash % Math.max(count, 2))) / Math.max(count, 2);
      x = Math.cos(angle) * span + jitter;
      y = Math.sin(angle) * span + jitter;
    }
    graph.setNodeAttribute(node, "x", x);
    graph.setNodeAttribute(node, "y", y);
  });
  if (graph.order > 1) {
    forceAtlas2.assign(graph, {
      iterations: graph.order > 500 ? 38 : 74,
      settings: {
        ...forceAtlas2.inferSettings(graph),
        gravity: hint.includes("timeline") ? 0.1 : 0.055,
        scalingRatio: graph.order > 500 ? 7 : 11,
      },
    });
  }
}

function selectItem(item: AnyItem): void {
  state.selected = item;
  state.selectedGraphId = text(item.node_id || item.cluster_id || item.edge_id || "") || null;
  const cluster = item as Cluster;
  if (cluster.cluster_id && cluster.member_node_ids?.length) {
    state.expandedCluster = cluster;
  }
  renderGraph();
  renderInspector();
}

function renderAll(): void {
  renderChips();
  renderMetrics();
  renderViews();
  renderLayers();
  renderRelationControls();
  renderGraph();
  renderInspector();
}

async function loadMode(mode: Mode): Promise<void> {
  state.mode = mode;
  state.currentView = null;
  state.selected = null;
  state.selectedGraphId = null;
  state.results = [];
  state.relationItems = [];
  state.expandedCluster = null;
  if (mode === "philosophy") {
    state.status.philosophy = await fetchJson<AnyItem>("/api/philosophy/status");
    const views = await fetchJson<{ views: ViewCard[] }>("/api/philosophy/views");
    state.philosophyViews = views.views || [];
    await loadView(boot.default_philosophy_view || state.philosophyViews[0]?.view_id || "");
  } else {
    state.status.corpus = await fetchJson<AnyItem>("/api/corpus/status");
    const summary = await fetchJson<{ graph_views?: ViewCard[]; counts?: AnyItem }>("/api/corpus/summary");
    state.status.corpus = { ...state.status.corpus, counts: summary.counts || state.status.corpus.counts };
    state.corpusViews = summary.graph_views || [];
    await loadView(boot.default_view || state.corpusViews[0]?.view_id || "");
  }
}

async function loadView(viewId: string): Promise<void> {
  if (!viewId) return;
  state.currentViewId = viewId;
  state.selected = null;
  state.selectedGraphId = null;
  state.results = [];
  state.relationItems = [];
  state.expandedCluster = null;
  if (state.mode === "philosophy") {
    const payload = await fetchJson<PhilosophyViewPayload>(`/api/philosophy/views/${encodeURIComponent(viewId)}`);
    state.currentView = payload;
    state.activeLayers = new Set(payload.view.graph_layers || []);
    state.activePredicates = new Set((payload.edges || []).map(predicateId));
    state.densityMode = "overview";
    state.minRelationCount = 1;
    state.graphMode = "clusters";
    state.results = payload.clusters || [];
  } else {
    const payload = await fetchJson<CorpusViewPayload>(`/api/corpus/graph-views/${encodeURIComponent(viewId)}?limit=700`);
    state.currentView = payload;
    state.activeLayers = new Set();
    state.activePredicates = new Set();
    state.graphMode = "nodes";
    state.results = payload.items || [];
  }
  renderAll();
}

async function search(): Promise<void> {
  const query = (byId("search") as HTMLInputElement).value.trim();
  state.searchQuery = query;
  const payload =
    state.mode === "philosophy"
      ? await fetchJson<{ results?: AnyItem[] }>(`/api/philosophy/search?query=${encodeURIComponent(query)}&limit=80`)
      : await fetchJson<{ results?: AnyItem[] }>(`/api/corpus/search?query=${encodeURIComponent(query)}&limit=80`);
  state.results = payload.results || [];
  state.selected = { title: query ? `Search: ${query}` : "Search", results: state.results.length };
  state.selectedGraphId = null;
  renderInspector();
}

async function showReviewPacket(): Promise<void> {
  if (state.mode !== "philosophy") return;
  const payload = await fetchJson<{ packet: AnyItem }>(`/api/philosophy/review-packet?view_id=${encodeURIComponent(state.currentViewId)}`);
  state.selected = { title: `Review packet: ${state.currentViewId}`, ...payload.packet };
  state.selectedGraphId = null;
  renderInspector();
}

async function showUnresolved(): Promise<void> {
  if (state.mode !== "philosophy") return;
  const payload = await fetchJson<{ unresolved?: AnyItem[] }>(`/api/philosophy/unresolved?view_id=${encodeURIComponent(state.currentViewId)}`);
  state.results = payload.unresolved || [];
  state.selected = { title: `Unresolved: ${state.currentViewId}`, unresolved: state.results.length };
  state.selectedGraphId = null;
  renderInspector();
}

async function showSnapshot(): Promise<void> {
  if (state.mode !== "philosophy") return;
  state.selected = await fetchJson<AnyItem>("/api/philosophy/snapshot");
  state.selectedGraphId = null;
  renderInspector();
}

async function showAudit(): Promise<void> {
  if (state.mode !== "philosophy") return;
  state.selected = await fetchJson<AnyItem>("/api/philosophy/audit");
  state.selectedGraphId = null;
  renderInspector();
}

async function syncProjection(): Promise<void> {
  const url = state.mode === "philosophy" ? "/api/philosophy/project/sync" : "/api/project/sync";
  state.selected = await fetchJson<AnyItem>(url, { method: "POST" });
  state.selectedGraphId = null;
  renderInspector();
}

renderShell();
void loadMode("philosophy").catch((error: unknown) => {
  byId("inspector-title").textContent = "Load failed";
  byId("inspector-meta").innerHTML = `<span class="danger">${text(error)}</span>`;
});
