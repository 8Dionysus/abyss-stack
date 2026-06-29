import type { Graph as CosmosGraph, GraphConfig } from "@cosmos.gl/graph";
import Graphology from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import "./styles.css";

type Mode = "philosophy" | "corpus";
type GraphMode = "clusters" | "nodes";
type DensityMode = "overview" | "focused" | "dense";
type RendererMode = "cosmos" | "sigma";
type LayoutFamily = "timeline" | "flow" | "evidence" | "semantic" | "infrastructure" | "organic";
type Language = "en" | "ru";

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

type RelationDirection = "outgoing" | "incoming" | "internal" | "adjacent";

type RelationRow = GraphEdge & {
  direction?: RelationDirection;
  from_label?: string;
  to_label?: string;
  primary_predicate?: string;
  relation_count?: number;
  member_edge_ids?: string[];
  source_refs?: string[];
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

type NeighborhoodPayload = {
  query_backend?: string;
  fallback_reason?: string | null;
  node?: GraphNode;
  neighbors?: GraphNode[];
  edges?: GraphEdge[];
  depth?: number;
  layers?: string[];
  predicates?: string[];
  source_refs?: string[];
};

type PathPayload = {
  query_backend?: string;
  fallback_reason?: string | null;
  from_id?: string;
  to_id?: string;
  found?: boolean;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  max_depth?: number;
  layers?: string[];
  predicates?: string[];
  source_refs?: string[];
};

type ScaleExportTable = "nodes" | "edges" | "clusters" | "cluster-node-memberships" | "cluster-edge-memberships";

type AppState = {
  language: Language;
  mode: Mode;
  graphMode: GraphMode;
  rendererMode: RendererMode;
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
  neighborhood: NeighborhoodPayload | null;
  pathStartNodeId: string | null;
  pathPacket: PathPayload | null;
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

const scaleExportTables: { table: ScaleExportTable; titleKey: string }[] = [
  { table: "nodes", titleKey: "export.nodes" },
  { table: "edges", titleKey: "export.edges" },
  { table: "clusters", titleKey: "export.clusters" },
  { table: "cluster-node-memberships", titleKey: "export.clusterNodes" },
  { table: "cluster-edge-memberships", titleKey: "export.clusterEdges" },
];

const uiText: Record<Language, Record<string, string>> = {
  en: {
    "brand.title": "Tree of Sophia Graph",
    "brand.note": "Runtime workbench for ToS-owned projection exports.",
    "language.label": "Language",
    "mode.philosophy": "Philosophy",
    "mode.corpus": "Corpus",
    "search.placeholder": "Search nodes, clusters, refs",
    "button.search": "Search",
    "button.sync": "Sync",
    "section.views": "Views",
    "section.layers": "Layers",
    "section.relations": "Relations",
    "section.scaleExport": "Scale Export",
    "chip.mode": "Mode",
    "chip.view": "View",
    "chip.renderer": "Renderer",
    "chip.neo4j": "Neo4j",
    "chip.projection": "Projection",
    "button.clusters": "Clusters",
    "button.nodes": "Nodes",
    "button.fit": "Fit",
    "button.fullView": "Full view",
    "button.reviewPacket": "Review packet",
    "button.unresolved": "Unresolved",
    "button.snapshot": "Snapshot",
    "button.audit": "Audit",
    "button.copy": "Copy",
    "button.copyUrl": "Copy URL",
    "button.contracts": "Contracts",
    "button.manifest": "Manifest",
    "empty.graph": "No graph payload for this view.",
    "empty.noView": "No view loaded.",
    "empty.filters": "No graph payload for current filters.",
    "inspector.selection": "Selection",
    "inspector.nothing": "Nothing selected.",
    "inspector.help": "Select a graph node, cluster, result, review packet, snapshot, or audit entry.",
    "muted.noLayerCorpus": "No layer contract for corpus view.",
    "muted.noLayers": "No layers for this view.",
    "muted.noRelationCorpus": "No relation contract for corpus view.",
    "muted.scaleCorpus": "Scale export follows the ToS philosophy projection.",
    "relation.of": "of",
    "relation.relations": "relations",
    "relation.min": "min",
    "relation.all": "All",
    "relation.refs": "refs",
    "relation.memberEdges": "member edges",
    "export.allLayers": "all layers",
    "export.nodes": "Nodes",
    "export.edges": "Edges",
    "export.clusters": "Clusters",
    "export.clusterNodes": "Cluster nodes",
    "export.clusterEdges": "Cluster edges",
    "detail.results": "Results",
    "detail.relations": "Relations",
    "detail.noDetail": "No detail",
    "detail.noDetailBody": "Use search or click the graph.",
    "detail.sourceRefs": "Source refs",
    "detail.payload": "Payload",
    "detail.relationRoute": "Relation route",
    "detail.from": "From",
    "detail.to": "To",
    "detail.predicate": "Predicate",
    "detail.relationCount": "Relation count",
    "detail.predicateMix": "Predicate mix",
    "detail.graphLayers": "Graph layers",
    "detail.memberEdges": "Member edges",
    "detail.relationReading": "Relation reading",
    "detail.predicatesNearby": "Predicates nearby",
    "detail.selectedRelations": "Selected relations",
    "detail.neighborhood": "Neighborhood",
    "detail.members": "members",
    "detail.neighbors": "Neighbors",
    "detail.neighborCount": "neighbors",
    "detail.neighborhoodRelations": "Neighborhood relations",
    "detail.pathStart": "Path start",
    "detail.path": "Path",
    "detail.pathNodes": "Path nodes",
    "detail.pathRelations": "Path relations",
    "detail.noRoute": "No route found",
    "detail.maxDepth": "max depth",
    "detail.allActiveLayers": "all active layers",
    "detail.allActivePredicates": "all active predicates",
    "detail.backend": "backend",
    "detail.fallback": "fallback",
    "route.neighborhood": "Neighborhood",
    "route.pathStartSet": "Path start set",
    "route.useAsPathStart": "Use as path start",
    "route.pathFrom": "Path from",
    "state.loading": "loading",
    "state.none": "none",
    "caption.view": "View",
    "caption.nodes": "nodes",
    "caption.links": "links",
    "selection.scaleExportUrl": "Scale export URL",
    "selection.search": "Search",
    "selection.reviewPacket": "Review packet",
    "selection.unresolved": "Unresolved",
    "load.failed": "Load failed",
  },
  ru: {
    "brand.title": "Граф Древа Софии",
    "brand.note": "Рабочая runtime-панель для проекций, которыми владеет ToS.",
    "language.label": "Язык",
    "mode.philosophy": "Философия",
    "mode.corpus": "Корпус",
    "search.placeholder": "Поиск узлов, кластеров, ссылок",
    "button.search": "Поиск",
    "button.sync": "Синхронизировать",
    "section.views": "Виды",
    "section.layers": "Слои",
    "section.relations": "Связи",
    "section.scaleExport": "Масштабный экспорт",
    "chip.mode": "Режим",
    "chip.view": "Вид",
    "chip.renderer": "Рендерер",
    "chip.neo4j": "Neo4j",
    "chip.projection": "Проекция",
    "button.clusters": "Кластеры",
    "button.nodes": "Узлы",
    "button.fit": "Вписать",
    "button.fullView": "Полный вид",
    "button.reviewPacket": "Пакет ревью",
    "button.unresolved": "Нерешенное",
    "button.snapshot": "Снимок",
    "button.audit": "Аудит",
    "button.copy": "Копировать",
    "button.copyUrl": "Копировать URL",
    "button.contracts": "Контракты",
    "button.manifest": "Манифест",
    "empty.graph": "Для этого вида нет графового пакета.",
    "empty.noView": "Вид не загружен.",
    "empty.filters": "Для текущих фильтров нет графового пакета.",
    "inspector.selection": "Выбор",
    "inspector.nothing": "Ничего не выбрано.",
    "inspector.help": "Выберите узел, кластер, результат, пакет ревью, снимок или запись аудита.",
    "muted.noLayerCorpus": "У корпусного вида нет контракта слоев.",
    "muted.noLayers": "У этого вида нет слоев.",
    "muted.noRelationCorpus": "У корпусного вида нет контракта связей.",
    "muted.scaleCorpus": "Масштабный экспорт следует философской проекции ToS.",
    "relation.of": "из",
    "relation.relations": "связей",
    "relation.min": "мин.",
    "relation.all": "Все",
    "relation.refs": "ссылок",
    "relation.memberEdges": "вложенных связей",
    "export.allLayers": "все слои",
    "export.nodes": "Узлы",
    "export.edges": "Связи",
    "export.clusters": "Кластеры",
    "export.clusterNodes": "Узлы кластеров",
    "export.clusterEdges": "Связи кластеров",
    "detail.results": "Результаты",
    "detail.relations": "Связи",
    "detail.noDetail": "Нет деталей",
    "detail.noDetailBody": "Используйте поиск или кликните по графу.",
    "detail.sourceRefs": "Ссылки на источник",
    "detail.payload": "Пакет",
    "detail.relationRoute": "Маршрут связи",
    "detail.from": "От",
    "detail.to": "К",
    "detail.predicate": "Предикат",
    "detail.relationCount": "Число связей",
    "detail.predicateMix": "Состав предикатов",
    "detail.graphLayers": "Слои графа",
    "detail.memberEdges": "Вложенные связи",
    "detail.relationReading": "Чтение связей",
    "detail.predicatesNearby": "Ближайшие предикаты",
    "detail.selectedRelations": "Выбранные связи",
    "detail.neighborhood": "Окрестность",
    "detail.members": "участников",
    "detail.neighbors": "Соседи",
    "detail.neighborCount": "соседей",
    "detail.neighborhoodRelations": "Связи окрестности",
    "detail.pathStart": "Начало пути",
    "detail.path": "Путь",
    "detail.pathNodes": "Узлы пути",
    "detail.pathRelations": "Связи пути",
    "detail.noRoute": "Маршрут не найден",
    "detail.maxDepth": "макс. глубина",
    "detail.allActiveLayers": "все активные слои",
    "detail.allActivePredicates": "все активные предикаты",
    "detail.backend": "движок",
    "detail.fallback": "запасной путь",
    "route.neighborhood": "Окрестность",
    "route.pathStartSet": "Начало пути задано",
    "route.useAsPathStart": "Сделать началом пути",
    "route.pathFrom": "Путь от",
    "state.loading": "загрузка",
    "state.none": "нет",
    "caption.view": "Вид",
    "caption.nodes": "узлов",
    "caption.links": "связей",
    "selection.scaleExportUrl": "URL масштабного экспорта",
    "selection.search": "Поиск",
    "selection.reviewPacket": "Пакет ревью",
    "selection.unresolved": "Нерешенное",
    "load.failed": "Загрузка не удалась",
  },
};

const tokenText: Record<Language, Record<string, string>> = {
  en: {},
  ru: {
    adjacent: "Смежные",
    "authority-layers": "слои авторитетности",
    belongs_to_genre: "принадлежит жанру",
    branches: "ветви",
    candidate: "кандидат",
    "candidate-endpoint": "кандидатная точка",
    "candidate-node": "кандидатный узел",
    "candidate-relation": "кандидатные связи",
    "canon-candidate-status": "статус канона/кандидата",
    "canon-promotion": "продвижение в канон",
    canonized_by: "канонизирован через",
    "canonical-relation": "канонические связи",
    clusters: "кластеры",
    commented_by: "комментируется через",
    concept: "понятие",
    "concept-problem": "понятие или проблема",
    "conceptual-relation": "понятийные связи",
    contains: "содержит",
    contains_row: "содержит строку",
    contains_view: "содержит вид",
    contested_by: "оспаривается через",
    dense: "плотно",
    deferred: "отложено",
    develops_concept: "развивает понятие",
    "diff-snapshot": "снимок различий",
    edges: "связи",
    "evidence-relation": "свидетельские связи",
    "evidence-status": "статус свидетельств",
    flow: "поток",
    fragments_preserved_by: "фрагменты сохранены через",
    focused: "фокус",
    "graph-view": "графовый вид",
    graph_layers: "слои графа",
    "graph-layers": "слои графа",
    has_node_type_pressure: "давление типа узла",
    has_prepared_dossier: "имеет подготовленное досье",
    has_relation_pressure: "давление типа связи",
    "historical-relation": "исторические связи",
    incoming: "Входящие",
    influences: "влияет",
    institutionalized_in: "институционализировано в",
    internal: "Внутренние",
    manifests: "манифесты",
    "master-table": "мастер-таблица",
    "master-table-row": "строка мастер-таблицы",
    "node-neighborhood": "окрестность узла",
    nodes: "узлы",
    organic: "органика",
    outgoing: "Исходящие",
    overview: "обзор",
    polemicizes_with: "полемизирует с",
    prepared_dossier: "подготовленное досье",
    "prepared-dossier": "подготовленное досье",
    "promotion-flow": "поток продвижения",
    preserved_in: "сохранено в",
    preserves_in: "сохраняет в",
    "provenance-dag": "DAG происхождения",
    preview: "предпросмотр",
    ready: "готово",
    receives_from: "получает от",
    region: "регион",
    relation: "связь",
    relation_edges: "ребра связей",
    "relation-edges": "ребра связей",
    relation_packs: "пакеты связей",
    "relation-packs": "пакеты связей",
    resources: "ресурсы",
    review_packets: "пакеты ревью",
    "review-packets": "пакеты ревью",
    "route-graph": "граф маршрутов",
    "school-institution": "школа/институт",
    semantic: "семантика",
    "source-relation": "источниковые связи",
    "source-witness": "источник-свидетель",
    survives_as: "выживает как",
    timeline: "хронология",
    transforms_concept: "преобразует понятие",
    translated_into: "переведено в",
    "transmission-relation": "связи передачи",
    transmits_to: "передает к",
    uncertain_relation: "неуверенная связь",
    uses_language: "использует язык",
    uses_script: "использует письмо",
    views: "виды",
    "view-section": "раздел вида",
    work: "работа",
  },
};

const viewTitleText: Record<Language, Record<string, string>> = {
  en: {},
  ru: {
    chronology: "Хронологический граф",
    transmission: "Граф передачи",
    "source-evidence": "Граф источниковых свидетельств",
    "concept-lineage": "Граф родословия понятий",
    "institution-media": "Граф институтов и медиа",
    "script-decipherment": "Граф письменностей и дешифровки",
    "imperial-multilingualism": "Граф имперского многоязычия",
    "ritual-law": "Граф ритуала и закона",
    "epigraphic-network": "Эпиграфическая сеть",
    "lost-corpus": "Граф утраченных корпусов",
    "canon-promotion": "Граф продвижения в канон",
    "corpus-topology": "Топология корпуса",
    "authority-layers": "Слои авторитетности",
    "route-graph": "Граф маршрутов",
    "node-neighborhood": "Окрестность узла",
    "provenance-dag": "DAG происхождения",
    "promotion-flow": "Поток продвижения",
    "diff-snapshot": "Снимок различий",
  },
};

const viewSubtitleText: Record<Language, Record<string, string>> = {
  en: {},
  ru: {
    chronology: "хронологические линии",
    transmission: "направленные коридоры",
    "source-evidence": "DAG свидетельств",
    "concept-lineage": "семантическая родословная",
    "institution-media": "карта инфраструктуры",
    "script-decipherment": "маршрут неопределенности",
    "imperial-multilingualism": "карта параллельных версий",
    "ritual-law": "инфраструктура закона и ритуала",
    "epigraphic-network": "распределенное публичное письмо",
    "lost-corpus": "маршрут отсутствия и свидетельств",
    "canon-promotion": "поток продвижения",
    "corpus-topology": "ветвящееся дерево дома ToS",
    "authority-layers": "переключение видимости по слоям корпуса",
    "route-graph": "маршруты пакетов связей",
    "node-neighborhood": "ограниченное расширение вокруг узла",
    "provenance-dag": "давление источников к кандидату, канону и экспорту",
    "promotion-flow": "проверка кандидатного материала к канону",
    "diff-snapshot": "сравнение снимков корпусного индекса",
  },
};

function initialLanguage(): Language {
  const stored = window.localStorage.getItem("tos-graph-language");
  if (stored === "ru" || stored === "en") return stored;
  return navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
}

const state: AppState = {
  language: initialLanguage(),
  mode: "philosophy",
  graphMode: "clusters",
  rendererMode: "cosmos",
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
  neighborhood: null,
  pathStartNodeId: null,
  pathPacket: null,
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("missing #app");
const appRoot = app;
document.documentElement.lang = state.language;

let graph = new Graphology({ multi: true, type: "directed" });
let renderer: Sigma | null = null;
let cosmosRenderer: CosmosGraph | null = null;
let cosmosModulePromise: Promise<typeof import("@cosmos.gl/graph")> | null = null;
let graphContainer: HTMLDivElement | null = null;
let nodeTooltip: HTMLDivElement | null = null;
let lastGraphItems = new Map<string, AnyItem>();
let cosmosPointItems: AnyItem[] = [];
let cosmosLinkItems: AnyItem[] = [];
let hoveredNodeId: string | null = null;
let ignoreGraphClicksUntil = 0;
let ignoreInspectorSelectionsUntil = 0;
let graphRenderVersion = 0;
const lastPointer = { x: 0, y: 0 };

function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

function t(key: string): string {
  return uiText[state.language][key] || uiText.en[key] || key;
}

function tokenLabel(value: unknown): string {
  const original = text(value).trim();
  if (!original) return "";
  const lower = original.toLowerCase();
  const normalized = lower.replaceAll("_", "-");
  return tokenText[state.language][normalized] || tokenText[state.language][lower] || tokenText.en[normalized] || tokenText.en[lower] || original.replaceAll("_", " ").replaceAll("-", " ");
}

function viewDisplayTitle(view?: ViewCard | null): string {
  if (!view) return state.currentViewId || t("caption.view");
  return viewTitleText[state.language][view.view_id] || view.title || view.view_id;
}

function viewDisplaySubtitle(view?: ViewCard | null): string {
  if (!view) return "";
  return viewSubtitleText[state.language][view.view_id] || view.layout_hint || view.purpose || view.entry_surface || "";
}

function short(value: unknown, length = 58): string {
  const raw = text(value);
  return raw.length > length ? `${raw.slice(0, length - 1)}...` : raw;
}

function unwrapItem(item: AnyItem): AnyItem {
  const nested = item.item;
  return nested && typeof nested === "object" && !Array.isArray(nested) ? (nested as AnyItem) : item;
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
  const source = unwrapItem(item);
  return text(
    source.node_id ||
      source.edge_id ||
      source.cluster_id ||
      source.packet_id ||
      source.pack_id ||
      source.id ||
      source.path ||
      source.view_id ||
      item.collection ||
      "item",
  );
}

function itemTitle(item: AnyItem): string {
  const source = unwrapItem(item);
  if (source.from_id && source.to_id) {
    return relationRouteText(source);
  }
  return text(source.label || source.title || source.name || source.view_id || itemId(source));
}

function itemSubtitle(item: AnyItem): string {
  const source = unwrapItem(item);
  return text(
    source.node_type ||
      source.cluster_kind ||
      source.predicate_id ||
      source.source_ref ||
      source.source_path ||
      source.path ||
      source.layout_hint ||
      source.purpose ||
      item.collection ||
      "",
  );
}

function humanKind(value: unknown): string {
  return tokenLabel(value);
}

function displayTitle(item: AnyItem): string {
  const source = unwrapItem(item);
  if (source.from_id && source.to_id) return relationRouteText(source);
  if (source.view_id) return viewDisplayTitle(source as ViewCard);
  const raw = itemTitle(item).trim();
  const canon = raw.match(/^Canon Or Candidate Status:\s*(.+)$/i);
  if (canon) return `${state.language === "ru" ? "Статус" : "Status"} ${canon[1].trim()}`;
  const concept = raw.match(/^Concept Or Problem:\s*(.+)$/i);
  if (concept) return concept[1].trim();
  const corpus = raw.match(/^Corpus Or Prepared Source Document:\s*(.+)$/i);
  const title = corpus ? corpus[1].trim() : raw;
  return (
    title
      .replace(/^ToS Deep Research[_\s:—-]*/i, "")
      .replace(/\.docx$/i, "")
      .replace(/\s+/g, " ")
      .trim() || raw
  );
}

function displaySubtitle(item: AnyItem): string {
  if (item.relation_count) {
    return `${humanKind(item.primary_predicate || item.predicate_id || "relation")} · ${text(item.relation_count)} ${t("relation.relations")}`;
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

function relationRouteText(item: AnyItem): string {
  return `${text(item.from_label || endpointLabel(item.from_id))} -> ${humanKind(item.primary_predicate || item.predicate_id || "relation")} -> ${text(item.to_label || endpointLabel(item.to_id))}`;
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

function itemProperties(item: AnyItem): AnyItem {
  const source = unwrapItem(item);
  return source.properties && typeof source.properties === "object" && !Array.isArray(source.properties)
    ? (source.properties as AnyItem)
    : {};
}

function propertyText(item: AnyItem, key: string): string {
  return text(itemProperties(item)[key]);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : [];
}

function itemContains(value: unknown, needle: string): boolean {
  if (!needle) return true;
  if (typeof value === "string") return value.toLowerCase().includes(needle);
  if (Array.isArray(value)) return value.some((item) => itemContains(item, needle));
  if (value && typeof value === "object") return Object.values(value).some((item) => itemContains(item, needle));
  return false;
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

function currentItemsById(): Map<string, AnyItem> {
  const items = new Map<string, AnyItem>();
  if (!isPhilosophyView(state.currentView)) return items;
  (state.currentView.nodes || []).forEach((node) => items.set(node.node_id, node));
  (state.currentView.clusters || []).forEach((cluster) => items.set(cluster.cluster_id, cluster));
  return items;
}

function endpointLabel(id: unknown): string {
  const key = text(id);
  const item = currentItemsById().get(key);
  return item ? displayTitle(item) : key;
}

function relationSearchAllowed(item: AnyItem): boolean {
  const needle = state.searchQuery.toLowerCase().trim();
  if (!needle) return true;
  const routeText = [
    displayTitle(item),
    displaySubtitle(item),
    text(item.from_id),
    endpointLabel(item.from_id),
    text(item.to_id),
    endpointLabel(item.to_id),
    humanKind(predicateId(item)),
    itemLayers(item).join(" "),
    collectRefs(item).join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return routeText.includes(needle) || itemContains(item, needle);
}

function relationAllowed(item: AnyItem): boolean {
  return layerAllowed(item) && predicateAllowed(item) && relationSearchAllowed(item);
}

function relationLimit(): number {
  if (state.rendererMode === "cosmos") {
    if (state.densityMode === "dense") return 12000;
    if (state.densityMode === "focused") return 6000;
    return 2200;
  }
  if (state.densityMode === "dense") return 520;
  if (state.densityMode === "focused") return 280;
  return 150;
}

function edgeLimit(): number {
  if (state.rendererMode === "cosmos") {
    if (state.densityMode === "dense") return 60000;
    if (state.densityMode === "focused") return 30000;
    return 12000;
  }
  if (state.densityMode === "dense") return 3200;
  if (state.densityMode === "focused") return 1800;
  return 900;
}

function nodeLimit(): number {
  if (state.rendererMode === "cosmos") {
    if (state.densityMode === "dense") return 50000;
    if (state.densityMode === "focused") return 22000;
    return 9000;
  }
  return 1200;
}

function clusterLimit(): number {
  if (state.rendererMode === "cosmos") return 8000;
  return 360;
}

function corpusItemLimit(): number {
  if (state.rendererMode === "cosmos") return 12000;
  return 700;
}

function relationCountAllowed(item: AnyItem): boolean {
  const count = Number(item.relation_count || 1);
  return !Number.isFinite(count) || count >= state.minRelationCount;
}

function inspectorSelectionAllowed(): boolean {
  return Date.now() >= ignoreInspectorSelectionsUntil;
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
  if (signal.includes("source") || signal.includes("prepared") || signal.includes("contains")) return "rgba(66,111,163,0.72)";
  if (signal.includes("canon") || signal.includes("candidate")) return "rgba(177,116,47,0.74)";
  if (signal.includes("evidence") || signal.includes("unresolved")) return "rgba(163,72,63,0.7)";
  if (signal.includes("concept") || signal.includes("lineage")) return "rgba(118,95,162,0.72)";
  return "rgba(36,120,101,0.5)";
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
          <div class="rail-head-row">
            <div>
              <h1 class="brand-title">${t("brand.title")}</h1>
              <p class="brand-note">${t("brand.note")}</p>
            </div>
            <div class="language-toggle" aria-label="${t("language.label")}">
              <button id="language-en" type="button">EN</button>
              <button id="language-ru" type="button">RU</button>
            </div>
          </div>
        </div>
        <div class="segmented">
          <button id="mode-philosophy" class="mode-button" type="button">${t("mode.philosophy")}</button>
          <button id="mode-corpus" class="mode-button" type="button">${t("mode.corpus")}</button>
        </div>
        <div class="rail-scroll">
          <div class="input-row">
            <input id="search" type="search" placeholder="${t("search.placeholder")}" />
            <div class="inline-actions">
              <button id="search-button" type="button">${t("button.search")}</button>
              <button id="sync-button" type="button">${t("button.sync")}</button>
            </div>
          </div>
          <div class="section-title">${t("section.views")}</div>
          <div id="view-list" class="stack"></div>
          <div class="section-title">${t("section.layers")}</div>
          <div id="layer-list" class="stack"></div>
          <div class="section-title">${t("section.relations")}</div>
          <div id="relation-controls" class="relation-controls"></div>
          <div class="section-title">${t("section.scaleExport")}</div>
          <div id="scale-export-controls" class="scale-export-controls"></div>
        </div>
      </aside>
      <main class="panel main-stage">
        <div class="toolbar">
          <div class="chip-row">
            <span class="chip">${t("chip.mode")} <strong id="mode-chip"></strong></span>
            <span class="chip">${t("chip.view")} <strong id="view-chip"></strong></span>
            <span class="chip">${t("chip.renderer")} <strong id="renderer-chip"></strong></span>
            <span class="chip">${t("chip.neo4j")} <strong id="neo4j-chip"></strong></span>
            <span class="chip">${t("chip.projection")} <strong id="projection-chip"></strong></span>
          </div>
          <div id="metrics" class="metric-row"></div>
          <div class="inline-actions">
            <button id="renderer-cosmos" class="renderer-button" type="button">Cosmos</button>
            <button id="renderer-sigma" class="renderer-button" type="button">Sigma</button>
            <button id="clusters-button" type="button">${t("button.clusters")}</button>
            <button id="nodes-button" type="button">${t("button.nodes")}</button>
            <button id="fit-button" type="button">${t("button.fit")}</button>
            <button id="focus-clear-button" type="button">${t("button.fullView")}</button>
            <button id="review-button" type="button">${t("button.reviewPacket")}</button>
            <button id="unresolved-button" type="button">${t("button.unresolved")}</button>
          </div>
        </div>
        <div class="graph-wrap">
          <div id="graph"></div>
          <div id="graph-empty" class="graph-empty" hidden>${t("empty.graph")}</div>
          <div id="graph-caption" class="graph-caption"></div>
          <div id="node-tooltip" class="node-tooltip" hidden></div>
        </div>
      </main>
      <aside class="panel right-rail">
        <div class="inspector-head">
          <h2 id="inspector-title" class="inspector-title">${t("inspector.selection")}</h2>
          <div id="inspector-meta" class="muted">${t("inspector.nothing")}</div>
        </div>
        <div class="segmented">
          <button id="snapshot-button" type="button">${t("button.snapshot")}</button>
          <button id="audit-button" type="button">${t("button.audit")}</button>
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
  byId("language-en").addEventListener("click", () => setLanguage("en"));
  byId("language-ru").addEventListener("click", () => setLanguage("ru"));
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
  byId("renderer-cosmos").addEventListener("click", () => {
    state.rendererMode = "cosmos";
    renderAll();
  });
  byId("renderer-sigma").addEventListener("click", () => {
    state.rendererMode = "sigma";
    renderAll();
  });
  byId("fit-button").addEventListener("click", () => fitActiveGraph());
  byId("focus-clear-button").addEventListener("click", clearFocus);
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

function setLanguage(language: Language): void {
  if (state.language === language) return;
  state.language = language;
  window.localStorage.setItem("tos-graph-language", language);
  document.documentElement.lang = language;
  renderShell();
  renderAll();
}

function renderChips(): void {
  setActive("language-en", state.language === "en");
  setActive("language-ru", state.language === "ru");
  byId("mode-chip").textContent = t(`mode.${state.mode}`);
  byId("view-chip").textContent = state.currentViewId || t("state.none");
  byId("renderer-chip").textContent = state.rendererMode;
  byId("neo4j-chip").textContent = boot.neo4j.ready ? humanKind("ready") : boot.neo4j.configured ? humanKind("preview") : humanKind("deferred");
  const status = state.mode === "philosophy" ? state.status.philosophy : state.status.corpus;
  byId("projection-chip").textContent = text(status?.projection_exists ?? status?.index_exists ?? t("state.loading"));
  setActive("mode-philosophy", state.mode === "philosophy");
  setActive("mode-corpus", state.mode === "corpus");
  setActive("renderer-cosmos", state.rendererMode === "cosmos");
  setActive("renderer-sigma", state.rendererMode === "sigma");
  setActive("clusters-button", state.graphMode === "clusters");
  setActive("nodes-button", state.graphMode === "nodes");
  const focusButton = byId("focus-clear-button") as HTMLButtonElement;
  focusButton.disabled = !state.neighborhood && !state.pathPacket && !state.expandedCluster;
  focusButton.classList.toggle("active", Boolean(state.neighborhood || state.pathPacket || state.expandedCluster));
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
          <span>${humanKind(key)}</span>
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
          <span class="view-title">${short(viewDisplayTitle(view), 72)}</span>
          <span class="view-subtitle">${short(viewDisplaySubtitle(view), 92)}</span>
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
    byId("layer-list").innerHTML = `<div class="muted">${t("muted.noLayerCorpus")}</div>`;
    return;
  }
  const layers = state.currentView.view.graph_layers || [];
  if (layers.length === 0) {
    byId("layer-list").innerHTML = `<div class="muted">${t("muted.noLayers")}</div>`;
    return;
  }
  byId("layer-list").innerHTML = layers
    .map(
      (layer) => `
        <label class="layer-toggle ${state.activeLayers.has(layer) ? "active" : ""}">
          <input data-layer="${layer}" type="checkbox" ${state.activeLayers.has(layer) ? "checked" : ""} />
          <span>${escapeHtml(humanKind(layer))}</span>
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
    root.innerHTML = `<div class="muted">${t("muted.noRelationCorpus")}</div>`;
    return;
  }
  const layerEdges = (state.currentView.edges || []).filter(layerAllowed);
  const activeEdges = layerEdges.filter(predicateAllowed);
  const predicateCounts = countBy(layerEdges, predicateId);
  const predicates = [...predicateCounts.entries()].sort((left, right) => right[1] - left[1]);
  root.innerHTML = `
    <div class="relation-summary">
      <strong>${activeEdges.length}</strong>
      <span>${t("relation.of")} ${layerEdges.length} ${t("relation.relations")}</span>
    </div>
    <div class="density-row">
      ${(["overview", "focused", "dense"] as DensityMode[])
        .map(
          (mode) => `
            <button class="density-button ${state.densityMode === mode ? "active" : ""}" data-density="${mode}" type="button">
              ${humanKind(mode)}
            </button>
          `,
        )
        .join("")}
    </div>
    <div class="threshold-row">
      <button id="relation-min-dec" type="button">-</button>
      <span>${t("relation.min")} ${state.minRelationCount}</span>
      <button id="relation-min-inc" type="button">+</button>
      <button id="predicate-reset" type="button">${t("relation.all")}</button>
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

function scaleExportQuery(): string {
  const params = new URLSearchParams();
  if (state.currentViewId) params.set("view_id", state.currentViewId);
  const layers = [...state.activeLayers].filter(Boolean);
  if (layers.length) params.set("layers", layers.join(","));
  const query = params.toString();
  return query ? `?${query}` : "";
}

function scaleExportPath(table?: ScaleExportTable, format?: "csv" | "jsonl"): string {
  const suffix = table && format ? `/${table}.${format}` : "/manifest";
  return `/api/philosophy/scale-export${suffix}${scaleExportQuery()}`;
}

function scaleExportAbsoluteUrl(table?: ScaleExportTable, format?: "csv" | "jsonl"): string {
  return new URL(scaleExportPath(table, format), window.location.origin).toString();
}

function renderScaleExportControls(): void {
  const root = byId("scale-export-controls");
  if (state.mode !== "philosophy" || !isPhilosophyView(state.currentView)) {
    root.innerHTML = `<div class="muted">${t("muted.scaleCorpus")}</div>`;
    return;
  }
  const layers = [...state.activeLayers].filter(Boolean);
  root.innerHTML = `
    <div class="export-summary">
      <strong>${escapeHtml(state.currentViewId || "view")}</strong>
      <span>${escapeHtml(layers.length ? layers.map(humanKind).join(", ") : t("export.allLayers"))}</span>
    </div>
    <div class="export-actions">
      <a class="export-link" data-export-link="contracts" href="/api/philosophy/contracts" target="_blank" rel="noreferrer">${t("button.contracts")}</a>
      <a class="export-link" data-export-link="manifest" href="${escapeHtml(scaleExportPath())}" target="_blank" rel="noreferrer">${t("button.manifest")}</a>
      <button data-copy-export="manifest" type="button">${t("button.copyUrl")}</button>
    </div>
    <div class="export-table-list">
      ${scaleExportTables
        .map(
          ({ table, titleKey }) => `
            <div class="export-row">
              <span>${escapeHtml(t(titleKey))}</span>
              <a class="export-link" data-export-link="${table}-csv" href="${escapeHtml(scaleExportPath(table, "csv"))}" target="_blank" rel="noreferrer">CSV</a>
              <a class="export-link" data-export-link="${table}-jsonl" href="${escapeHtml(scaleExportPath(table, "jsonl"))}" target="_blank" rel="noreferrer">JSONL</a>
              <button data-copy-export="${table}" type="button">${t("button.copy")}</button>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
  root.querySelectorAll<HTMLButtonElement>("[data-copy-export]").forEach((button) => {
    button.addEventListener("click", () => {
      const table = button.dataset.copyExport || "";
      if (table === "manifest") void copyScaleExportUrl();
      else void copyScaleExportUrl(table as ScaleExportTable, "jsonl");
    });
  });
}

function renderInspector(): void {
  const title = state.selected ? displayTitle(state.selected) : viewDisplayTitle(state.currentView?.view) || state.currentViewId || t("inspector.selection");
  byId("inspector-title").textContent = title;
  byId("inspector-meta").textContent = state.selected
    ? displaySubtitle(state.selected)
    : t("inspector.help");

  const cards: string[] = [];
  const selectedRelationRows = state.selected ? relationRowsForSelection(state.selected) : [];
  const selectedNodeId = state.selected ? selectedNodeIdFor(state.selected) : "";
  if (state.selected) {
    if (selectedNodeId) {
      cards.push(nodeRouteActions(selectedNodeId));
    }
    cards.push(...relationDetailCards(state.selected));
    if (selectedRelationRows.length) {
      cards.push(...relationReadingCards(selectedRelationRows));
      cards.push(relationRowsSection(t("detail.selectedRelations"), selectedRelationRows));
    }
    if (selectedNodeId) {
      cards.push(...neighborhoodCards(selectedNodeId));
      cards.push(...pathCards(selectedNodeId));
    }
    const refs = collectRefs(state.selected);
    if (refs.length) {
      cards.push(detailCard(t("detail.sourceRefs"), refs.slice(0, 8).join("\n")));
    }
    cards.push(detailCard(t("detail.payload"), JSON.stringify(state.selected, null, 2), true));
  }
  if (state.results.length) {
    cards.push(`<div class="section-title">${t("detail.results")}</div>`);
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
    cards.push(`<div class="section-title">${t("detail.relations")}</div>`);
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
  byId("detail-list").innerHTML = cards.join("") || detailCard(t("detail.noDetail"), t("detail.noDetailBody"));
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-result]").forEach((button) => {
    button.addEventListener("click", () => {
      if (inspectorSelectionAllowed()) selectItem(state.results[Number(button.dataset.result)]);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-relation]").forEach((button) => {
    button.addEventListener("click", () => {
      if (inspectorSelectionAllowed()) selectItem(state.relationItems[Number(button.dataset.relation)]);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-selected-relation]").forEach((button) => {
    button.addEventListener("click", () => {
      if (inspectorSelectionAllowed()) selectItem(selectedRelationRows[Number(button.dataset.selectedRelation)]);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-neighbor]").forEach((button) => {
    const item = state.neighborhood?.neighbors?.[Number(button.dataset.neighbor)];
    button.addEventListener("click", () => {
      if (item && inspectorSelectionAllowed()) selectItem(item);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-path-node]").forEach((button) => {
    const item = state.pathPacket?.nodes?.[Number(button.dataset.pathNode)];
    button.addEventListener("click", () => {
      if (item && inspectorSelectionAllowed()) selectItem(item);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-path-edge]").forEach((button) => {
    const item = state.pathPacket?.edges?.[Number(button.dataset.pathEdge)];
    button.addEventListener("click", () => {
      if (item && inspectorSelectionAllowed()) selectItem(item);
    });
  });
  byId("detail-list").querySelectorAll<HTMLButtonElement>("[data-neighborhood-edge]").forEach((button) => {
    const item = state.neighborhood?.edges?.[Number(button.dataset.neighborhoodEdge)];
    button.addEventListener("click", () => {
      if (item && inspectorSelectionAllowed()) selectItem(item);
    });
  });
  document.getElementById("neighborhood-button")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    void showNeighborhood(selectedNodeId);
  });
  document.getElementById("path-start-button")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    setPathStart(selectedNodeId);
  });
  document.getElementById("path-to-button")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    void showPathTo(selectedNodeId);
  });
}

function scrollInspectorTop(): void {
  document.querySelector<HTMLDivElement>(".inspector-scroll")?.scrollTo({ top: 0 });
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
  const source = unwrapItem(item);
  if (!source.from_id || !source.to_id) return [];
  const predicates = item.predicates && typeof item.predicates === "object" ? (item.predicates as Record<string, unknown>) : {};
  const predicateText = Object.entries(predicates)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .slice(0, 8)
    .map(([predicate, count]) => `${humanKind(predicate)}: ${count}`)
    .join("\n");
  const layers = itemLayers(item).join("\n");
  const memberEdges = stringList(item.member_edge_ids).slice(0, 12).join("\n");
  const cards = [
    detailCard(t("detail.relationRoute"), `${text(source.from_label || endpointLabel(source.from_id))}\n-> ${humanKind(source.primary_predicate || source.predicate_id)}\n-> ${text(source.to_label || endpointLabel(source.to_id))}`),
    detailCard(t("detail.from"), text(source.from_label || endpointLabel(source.from_id))),
    detailCard(t("detail.to"), text(source.to_label || endpointLabel(source.to_id))),
    detailCard(t("detail.predicate"), humanKind(source.primary_predicate || source.predicate_id)),
  ];
  if (source.relation_count) cards.push(detailCard(t("detail.relationCount"), text(source.relation_count)));
  if (predicateText) cards.push(detailCard(t("detail.predicateMix"), predicateText));
  if (layers) cards.push(detailCard(t("detail.graphLayers"), layers.split("\n").map(humanKind).join("\n")));
  if (memberEdges) cards.push(detailCard(t("detail.memberEdges"), memberEdges));
  return cards;
}

function selectedNodeIdFor(item: AnyItem): string {
  const source = unwrapItem(item);
  return text(source.node_id);
}

function collectRefs(item: AnyItem): string[] {
  const source = unwrapItem(item);
  const refs = new Set<string>();
  for (const key of ["source_ref", "source_path", "path"]) {
    if (source[key]) refs.add(text(source[key]));
  }
  const sourceRefs = source.source_refs;
  if (Array.isArray(sourceRefs)) sourceRefs.forEach((ref) => refs.add(text(ref)));
  return [...refs].filter(Boolean);
}

function relationReadingCards(rows: RelationRow[]): string[] {
  const counts = countBy(rows, (row) => row.direction || "adjacent");
  const predicates = countBy(rows, (row) => predicateId(row));
  const predicateText = [...predicates.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8)
    .map(([predicate, count]) => `${humanKind(predicate)}: ${count}`)
    .join("\n");
  const summary = [
    `${humanKind("outgoing")}: ${counts.get("outgoing") || 0}`,
    `${humanKind("incoming")}: ${counts.get("incoming") || 0}`,
    `${humanKind("internal")}: ${counts.get("internal") || 0}`,
    `${humanKind("adjacent")}: ${counts.get("adjacent") || 0}`,
  ].join("\n");
  return [detailCard(t("detail.relationReading"), summary), predicateText ? detailCard(t("detail.predicatesNearby"), predicateText) : ""].filter(Boolean);
}

function relationRowsSection(title: string, rows: RelationRow[], source: "selected" | "neighborhood" | "path" = "selected"): string {
  const grouped = relationRowsByDirection(rows);
  const actionAttr =
    source === "neighborhood" ? "data-neighborhood-edge" : source === "path" ? "data-path-edge" : "data-selected-relation";
  return `
    <div class="section-title">${escapeHtml(title)}</div>
    <div class="relation-table">
      ${grouped
        .map(
          (group) => `
            <div class="relation-group-label">${escapeHtml(group.title)}</div>
            ${group.rows
              .map(({ row, index }) => {
          const refs = collectRefs(row);
          const layers = itemLayers(row);
          const meta = [
            humanKind(predicateId(row)),
            layers.length ? layers.slice(0, 3).join(", ") : "",
            refs.length ? `${refs.length} ${t("relation.refs")}` : "",
            row.member_edge_ids?.length ? `${row.member_edge_ids.length} ${t("relation.memberEdges")}` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `
            <button class="relation-row" ${actionAttr}="${index}" type="button">
              <span class="relation-direction ${row.direction || "adjacent"}">${escapeHtml(humanKind(row.direction || "adjacent"))}</span>
              <span class="relation-route">${escapeHtml(short(relationRouteText(row), 116))}</span>
              <span class="relation-meta">${escapeHtml(short(meta, 128))}</span>
            </button>
          `;
        })
        .join("")}
          `,
        )
        .join("")}
    </div>
  `;
}

function relationRowsByDirection(rows: RelationRow[]): { title: string; rows: { row: RelationRow; index: number }[] }[] {
  const labels: Record<RelationDirection, string> = {
    outgoing: humanKind("outgoing"),
    incoming: humanKind("incoming"),
    internal: humanKind("internal"),
    adjacent: humanKind("adjacent"),
  };
  const order: RelationDirection[] = ["outgoing", "incoming", "internal", "adjacent"];
  const indexed = rows.slice(0, 100).map((row, index) => ({ row, index }));
  return order
    .map((direction) => ({
      title: labels[direction],
      rows: indexed.filter((item) => (item.row.direction || "adjacent") === direction),
    }))
    .filter((group) => group.rows.length > 0);
}

function relationRowsForSelection(item: AnyItem): RelationRow[] {
  const source = unwrapItem(item);
  if (!isPhilosophyView(state.currentView)) return [];
  const edges = (state.currentView.edges || []).filter(relationAllowed);
  const byEdgeId = new Map(edges.map((edge) => [edge.edge_id, edge]));
  if (source.from_id && source.to_id) {
    const memberRows = stringList(source.member_edge_ids)
      .map((edgeId) => byEdgeId.get(edgeId))
      .filter((edge): edge is GraphEdge => Boolean(edge))
      .map((edge) => relationRowFromEdge(edge, "adjacent"));
    if (memberRows.length) return memberRows;
    return [relationRowFromEdge(source as GraphEdge, "adjacent")];
  }

  const selectedIds = new Set<string>();
  if (source.node_id) selectedIds.add(text(source.node_id));
  if (source.cluster_id) selectedIds.add(text(source.cluster_id));
  stringList(source.member_node_ids).forEach((nodeId) => selectedIds.add(nodeId));
  if (selectedIds.size === 0) return [];

  return edges
    .filter((edge) => selectedIds.has(edge.from_id) || selectedIds.has(edge.to_id))
    .map((edge) => {
      const fromSelected = selectedIds.has(edge.from_id);
      const toSelected = selectedIds.has(edge.to_id);
      const direction: RelationDirection = fromSelected && toSelected ? "internal" : fromSelected ? "outgoing" : toSelected ? "incoming" : "adjacent";
      return relationRowFromEdge(edge, direction);
    })
    .sort((left, right) => {
      const order: Record<RelationDirection, number> = { outgoing: 0, incoming: 1, internal: 2, adjacent: 3 };
      return order[left.direction || "adjacent"] - order[right.direction || "adjacent"] || predicateId(left).localeCompare(predicateId(right));
    })
    .slice(0, 160);
}

function relationRowFromEdge(edge: GraphEdge, direction: RelationDirection): RelationRow {
  return {
    ...edge,
    direction,
    from_label: text(edge.from_label || endpointLabel(edge.from_id)),
    to_label: text(edge.to_label || endpointLabel(edge.to_id)),
    source_refs: collectRefs(edge),
  };
}

function showNodeTooltip(nodeId: string): void {
  const item = lastGraphItems.get(nodeId);
  if (!nodeTooltip || !item) return;
  hoveredNodeId = nodeId;
  const refs = collectRefs(item).slice(0, 3);
  const layers = itemLayers(item).slice(0, 4);
  const memberIds = item.member_node_ids;
  const members = Array.isArray(memberIds) ? `${memberIds.length} ${t("detail.members")}` : "";
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
  if (state.pathPacket?.found) {
    const pathNodes = new Set(stringList(state.pathPacket.nodes?.map((node) => node.node_id)));
    const pathEdges = new Set(stringList(state.pathPacket.edges?.map((edge) => edge.edge_id)));
    if (pathNodes.size || pathEdges.size) return { nodes: pathNodes, edges: pathEdges };
  }
  if (state.neighborhood?.node) {
    const nodes = new Set<string>([
      state.neighborhood.node.node_id,
      ...stringList(state.neighborhood.neighbors?.map((node) => node.node_id)),
    ]);
    const edges = new Set<string>(stringList(state.neighborhood.edges?.map((edge) => edge.edge_id)));
    if (nodes.size || edges.size) return { nodes, edges };
  }
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
  destroyGraphRenderers();
  graph.clear();
  lastGraphItems = new Map();
  state.relationItems = [];

  if (!state.currentView) {
    setGraphEmpty(true, t("empty.noView"));
    return;
  }

  if (state.mode === "corpus") buildCorpusGraph();
  else if (state.graphMode === "clusters") buildClusterGraph();
  else buildNodeGraph();

  if (graph.order === 0) {
    setGraphEmpty(true, t("empty.filters"));
    return;
  }

  setGraphEmpty(false);
  const renderVersion = graphRenderVersion;
  if (state.rendererMode === "cosmos") void renderCosmosGraph(renderVersion);
  else renderSigmaGraph();
}

function destroyGraphRenderers(): void {
  graphRenderVersion += 1;
  renderer?.kill();
  renderer = null;
  cosmosRenderer?.destroy();
  cosmosRenderer = null;
  cosmosPointItems = [];
  cosmosLinkItems = [];
  if (graphContainer) graphContainer.innerHTML = "";
}

function fitActiveGraph(): void {
  if (state.rendererMode === "cosmos") {
    cosmosRenderer?.fitView(260, 0.18, false);
    return;
  }
  renderer?.getCamera().animatedReset({ duration: 260 });
}

function loadCosmosModule(): Promise<typeof import("@cosmos.gl/graph")> {
  cosmosModulePromise ||= import("@cosmos.gl/graph");
  return cosmosModulePromise;
}

function renderSigmaGraph(): void {
  if (!graphContainer) return;
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
      return { ...data, label: "", color: "rgba(102, 115, 110, 0.3)", zIndex: 0 };
    },
    edgeReducer: (edge, data) => {
      if (!focus) return data;
      if (focus.edges.has(edge)) {
        return { ...data, size: Number(data.size || 1) * 2.5, color: "rgba(23, 32, 29, 0.82)", zIndex: 100 };
      }
      return { ...data, size: 0.3, color: "rgba(102, 115, 110, 0.16)", zIndex: 0 };
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
    if (Date.now() < ignoreGraphClicksUntil) return;
    const payload = lastGraphItems.get(node);
    if (payload) selectItem(payload);
  });
  renderer.on("clickEdge", ({ edge }) => {
    if (Date.now() < ignoreGraphClicksUntil) return;
    const payload = lastGraphItems.get(edge);
    if (payload) selectItem(payload);
  });
  renderer.getCamera().animatedReset({ duration: 220 });
}

type CosmosPayload = {
  nodeIds: string[];
  edgeIds: string[];
  pointPositions: Float32Array;
  pointColors: Float32Array;
  pointSizes: Float32Array;
  links: Float32Array;
  linkColors: Float32Array;
  linkWidths: Float32Array;
  linkArrows: boolean[];
  focusedPointIndex?: number;
  focusedLinkIndex?: number;
  highlightedPointIndices?: number[];
  highlightedLinkIndices?: number[];
  outlinedPointIndices?: number[];
};

async function renderCosmosGraph(renderVersion: number): Promise<void> {
  if (!graphContainer) return;
  const payload = cosmosPayloadFromGraph();
  const { Graph: CosmosGraphClass } = await loadCosmosModule();
  if (renderVersion !== graphRenderVersion || state.rendererMode !== "cosmos" || !graphContainer) return;
  const family = layoutFamily();
  const simulationEnabled = cosmosSimulationEnabled(family);
  const config: GraphConfig = {
    backgroundColor: [1, 1, 1, 0],
    spaceSize: 4096,
    randomSeed: 41,
    rescalePositions: true,
    fitViewOnInit: true,
    fitViewDelay: 140,
    fitViewDuration: 260,
    fitViewPadding: family === "timeline" || family === "flow" ? 0.06 : 0.1,
    pointDefaultColor: palette.blue,
    pointDefaultSize: 5,
    pointSizeScale: state.graphMode === "clusters" ? 0.86 : 1.22,
    pointGreyoutOpacity: 0.32,
    renderHoveredPointRing: true,
    hoveredPointRingColor: [1, 1, 1, 0.96],
    focusedPointRingColor: [0.09, 0.13, 0.12, 0.9],
    outlinedPointRingColor: [0.09, 0.13, 0.12, 0.72],
    focusedPointIndex: payload.focusedPointIndex,
    highlightedPointIndices: payload.highlightedPointIndices,
    outlinedPointIndices: payload.outlinedPointIndices,
    renderLinks: payload.links.length > 0,
    linkDefaultColor: [0.09, 0.13, 0.12, 0.22],
    linkOpacity: linkOpacityForLayout(family),
    linkGreyoutOpacity: 0.08,
    linkDefaultWidth: 0.7,
    linkWidthScale: linkWidthScaleForLayout(family),
    linkVisibilityDistanceRange: [8000, 12000],
    linkVisibilityMinTransparency: state.densityMode === "dense" ? 0.32 : 0.86,
    scaleLinksOnZoom: true,
    linkBlending: state.densityMode !== "dense",
    curvedLinks: family === "semantic" || family === "infrastructure",
    linkDefaultArrows: family === "flow" || family === "evidence",
    focusedLinkIndex: payload.focusedLinkIndex,
    highlightedLinkIndices: payload.highlightedLinkIndices,
    hoveredLinkWidthIncrease: 2,
    focusedLinkWidthIncrease: 3,
    enableDrag: true,
    enableSimulation: simulationEnabled,
    simulationGravity: family === "organic" ? 0.12 : 0.04,
    simulationCenter: simulationEnabled ? 0.05 : 0,
    simulationRepulsion: simulationEnabled ? (state.densityMode === "dense" ? 0.36 : 0.62) : 0,
    simulationLinkSpring: simulationEnabled ? 0.58 : 0,
    simulationLinkDistance: state.graphMode === "clusters" ? 26 : 18,
    simulationFriction: 0.84,
    transitionDuration: 420,
    hoveredPointCursor: "pointer",
    hoveredLinkCursor: "pointer",
    onPointClick: (index, _pointPosition, _event) => {
      if (Date.now() < ignoreGraphClicksUntil) return;
      const item = cosmosPointItems[index];
      if (item) selectItem(item);
    },
    onLinkClick: (index, _event) => {
      if (Date.now() < ignoreGraphClicksUntil) return;
      const item = cosmosLinkItems[index];
      if (item) selectItem(item);
    },
    onMouseMove: (_index, _pointPosition, event) => {
      lastPointer.x = event.clientX;
      lastPointer.y = event.clientY;
      if (hoveredNodeId) positionNodeTooltip();
    },
    onPointMouseOver: (index, _pointPosition, event) => {
      if (event && "clientX" in event) {
        lastPointer.x = event.clientX;
        lastPointer.y = event.clientY;
      }
      const nodeId = payload.nodeIds[index];
      if (nodeId) showNodeTooltip(nodeId);
    },
    onPointMouseOut: (_event) => hideNodeTooltip(),
    onLinkMouseOver: (index) => {
      const edgeId = payload.edgeIds[index];
      if (edgeId) showNodeTooltip(edgeId);
    },
    onLinkMouseOut: (_event) => hideNodeTooltip(),
  };
  cosmosRenderer = new CosmosGraphClass(graphContainer, config);
  cosmosPointItems = payload.nodeIds.map((nodeId) => lastGraphItems.get(nodeId) || { node_id: nodeId, label: nodeId });
  cosmosLinkItems = payload.edgeIds.map((edgeId) => lastGraphItems.get(edgeId) || { edge_id: edgeId, label: edgeId });
  cosmosRenderer.setPointPositions(payload.pointPositions);
  cosmosRenderer.setPointColors(payload.pointColors);
  cosmosRenderer.setPointSizes(payload.pointSizes);
  cosmosRenderer.setLinks(payload.links);
  cosmosRenderer.setLinkColors(payload.linkColors);
  cosmosRenderer.setLinkWidths(payload.linkWidths);
  cosmosRenderer.setLinkArrows(payload.linkArrows);
  cosmosRenderer.render(simulationEnabled ? undefined : 0);
}

function cosmosSimulationEnabled(family: LayoutFamily): boolean {
  if (state.graphMode === "nodes" && state.densityMode !== "overview") return true;
  return family === "semantic" || family === "organic";
}

function linkOpacityForLayout(family: LayoutFamily): number {
  if (state.densityMode === "dense") return 0.28;
  if (family === "timeline" || family === "flow") return 0.42;
  if (family === "evidence") return 0.5;
  return 0.62;
}

function linkWidthScaleForLayout(family: LayoutFamily): number {
  if (state.densityMode === "dense") return 0.72;
  if (family === "timeline" || family === "flow") return 0.82;
  if (family === "evidence") return 0.94;
  return 1.22;
}

function cosmosPayloadFromGraph(): CosmosPayload {
  const family = layoutFamily();
  const nodeIds = graph.nodes();
  const nodeIndex = new Map(nodeIds.map((nodeId, index) => [nodeId, index]));
  const pointPositions = new Float32Array(nodeIds.length * 2);
  const pointColors = new Float32Array(nodeIds.length * 4);
  const pointSizes = new Float32Array(nodeIds.length);
  nodeIds.forEach((nodeId, index) => {
    const x = numberAttr(graph.getNodeAttribute(nodeId, "x"));
    const y = numberAttr(graph.getNodeAttribute(nodeId, "y"));
    pointPositions[index * 2] = x;
    pointPositions[index * 2 + 1] = y;
    writeRgba(pointColors, index, colorToRgba(text(graph.getNodeAttribute(nodeId, "color") || palette.default)));
    const sizeMultiplier = state.graphMode === "clusters" ? 0.94 : 1.42;
    const maxSize = state.graphMode === "clusters" ? 28 : 38;
    pointSizes[index] = Math.max(4.5, Math.min(maxSize, numberAttr(graph.getNodeAttribute(nodeId, "size"), 7) * sizeMultiplier));
  });

  const edgeIds: string[] = [];
  const links: number[] = [];
  const linkColors: number[] = [];
  const linkWidths: number[] = [];
  const linkArrows: boolean[] = [];
  graph.edges().forEach((edgeId) => {
    const [source, target] = graph.extremities(edgeId);
    const sourceIndex = nodeIndex.get(source);
    const targetIndex = nodeIndex.get(target);
    if (sourceIndex === undefined || targetIndex === undefined) return;
    edgeIds.push(edgeId);
    links.push(sourceIndex, targetIndex);
    linkColors.push(...colorToRgba(text(graph.getEdgeAttribute(edgeId, "color") || palette.line)));
    const minWidth = state.densityMode === "dense" ? 0.9 : family === "timeline" || family === "flow" ? 1.15 : 1.6;
    linkWidths.push(Math.max(minWidth, Math.min(9, numberAttr(graph.getEdgeAttribute(edgeId, "size"), 1))));
    linkArrows.push(state.mode === "philosophy" && state.densityMode !== "dense");
  });

  const focus = graphFocus();
  const focusPointIndices = focus
    ? nodeIds.map((nodeId, index) => (focus.nodes.has(nodeId) ? index : -1)).filter((index) => index >= 0)
    : undefined;
  const focusLinkIndices = focus
    ? edgeIds.map((edgeId, index) => (focus.edges.has(edgeId) ? index : -1)).filter((index) => index >= 0)
    : undefined;
  const hardHighlight = Boolean(state.pathPacket?.found);
  const focusedPointIndex =
    state.selectedGraphId && nodeIndex.has(state.selectedGraphId) ? nodeIndex.get(state.selectedGraphId) : undefined;
  const focusedLinkIndex = state.selectedGraphId ? edgeIds.indexOf(state.selectedGraphId) : -1;
  return {
    nodeIds,
    edgeIds,
    pointPositions,
    pointColors,
    pointSizes,
    links: new Float32Array(links),
    linkColors: new Float32Array(linkColors),
    linkWidths: new Float32Array(linkWidths),
    linkArrows,
    focusedPointIndex,
    focusedLinkIndex: focusedLinkIndex >= 0 ? focusedLinkIndex : undefined,
    highlightedPointIndices: hardHighlight ? focusPointIndices : undefined,
    highlightedLinkIndices: hardHighlight ? focusLinkIndices : undefined,
    outlinedPointIndices: focusPointIndices,
  };
}

function numberAttr(value: unknown, fallback = 0): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function colorToRgba(value: string): [number, number, number, number] {
  const color = value.trim();
  if (color.startsWith("#")) {
    const hex = color.slice(1);
    if (hex.length === 6) {
      const red = parseInt(hex.slice(0, 2), 16) / 255;
      const green = parseInt(hex.slice(2, 4), 16) / 255;
      const blue = parseInt(hex.slice(4, 6), 16) / 255;
      return [red, green, blue, 1];
    }
  }
  const rgba = color.match(/rgba?\\(([^)]+)\\)/i);
  if (rgba) {
    const parts = rgba[1].split(",").map((part) => Number(part.trim()));
    const [red = 36, green = 120, blue = 101, alpha = 1] = parts;
    return [red / 255, green / 255, blue / 255, alpha > 1 ? alpha / 255 : alpha];
  }
  return [0.14, 0.47, 0.4, 1];
}

function writeRgba(target: Float32Array, index: number, rgba: [number, number, number, number]): void {
  target[index * 4] = rgba[0];
  target[index * 4 + 1] = rgba[1];
  target[index * 4 + 2] = rgba[2];
  target[index * 4 + 3] = rgba[3];
}

function setGraphEmpty(empty: boolean, message = ""): void {
  const emptyNode = byId("graph-empty");
  emptyNode.hidden = !empty;
  emptyNode.textContent = message || t("empty.graph");
  const caption = byId("graph-caption");
  const view = state.currentView?.view;
  const graphSummary = graph.order > 0 ? ` · ${graph.order} ${t("caption.nodes")} · ${graph.size} ${t("caption.links")}` : "";
  const layoutSummary =
    state.mode === "philosophy"
      ? `${viewDisplaySubtitle(view) || boot.projection_mode} · ${humanKind(layoutFamily())}`
      : viewDisplaySubtitle(view) || boot.projection_mode;
  caption.textContent = `${viewDisplayTitle(view) || state.currentViewId || t("caption.view")} · ${layoutSummary}${graphSummary}`;
}

function buildClusterGraph(): void {
  if (!isPhilosophyView(state.currentView)) return;
  const clusters = (state.currentView.clusters || []).filter(layerAllowed).slice(0, clusterLimit());
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
  const focusPacket = focusedNodePacket();
  const expandedIds = new Set(state.expandedCluster?.member_node_ids || []);
  const sourceNodes = focusPacket?.nodes || state.currentView.nodes || [];
  const sourceEdges = focusPacket?.edges || state.currentView.edges || [];
  const nodes = sourceNodes
    .filter(layerAllowed)
    .filter((node) => focusPacket || expandedIds.size === 0 || expandedIds.has(node.node_id))
    .slice(0, nodeLimit());
  const visible = new Set(nodes.map((node) => node.node_id));
  nodes.forEach((node, index) => addGraphNode(node.node_id, node, index, 7));
  const visibleEdges = sourceEdges
    .filter(relationAllowed)
    .filter((edge) => visible.has(edge.from_id) && visible.has(edge.to_id))
    .slice(0, edgeLimit());
  visibleEdges.forEach((edge, index) => addGraphEdge(edge.edge_id || `edge:${index}`, edge.from_id, edge.to_id, edge));
  layoutGraph();
  state.results = nodes;
  state.relationItems = visibleEdges.slice(0, 180);
}

function focusedNodePacket(): { nodes: GraphNode[]; edges: GraphEdge[] } | null {
  if (state.pathPacket?.found && state.pathPacket.nodes?.length) {
    return {
      nodes: state.pathPacket.nodes || [],
      edges: state.pathPacket.edges || [],
    };
  }
  if (state.neighborhood?.node) {
    return {
      nodes: [state.neighborhood.node, ...(state.neighborhood.neighbors || [])],
      edges: state.neighborhood.edges || [],
    };
  }
  return null;
}

function buildCorpusGraph(): void {
  const payload = state.currentView as CorpusViewPayload;
  const items = (payload.items || []).slice(0, corpusItemLimit());
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
    label: humanKind(predicateId(item)),
  });
}

function hashNumber(value: string): number {
  return value.split("").reduce((acc, char) => (acc * 31 + char.charCodeAt(0)) % 100000, 17);
}

function layoutFamily(): LayoutFamily {
  const viewId = state.currentViewId;
  const hint = text(state.currentView?.view?.layout_hint).toLowerCase();
  if (viewId === "chronology" || hint.includes("timeline") || hint.includes("lane")) return "timeline";
  if (viewId === "transmission" || viewId === "canon-promotion" || hint.includes("directed") || hint.includes("flow") || hint.includes("corridor") || hint.includes("promotion")) return "flow";
  if (
    viewId === "source-evidence" ||
    viewId === "script-decipherment" ||
    viewId === "lost-corpus" ||
    hint.includes("dag") ||
    hint.includes("evidence") ||
    hint.includes("uncertainty") ||
    hint.includes("absence")
  ) {
    return "evidence";
  }
  if (viewId === "concept-lineage" || hint.includes("semantic") || hint.includes("lineage")) return "semantic";
  if (
    viewId === "institution-media" ||
    viewId === "imperial-multilingualism" ||
    viewId === "ritual-law" ||
    viewId === "epigraphic-network" ||
    hint.includes("infrastructure") ||
    hint.includes("parallel") ||
    hint.includes("ritual") ||
    hint.includes("law") ||
    hint.includes("distributed")
  ) {
    return "infrastructure";
  }
  return "organic";
}

function dossierOrdinal(item: AnyItem, fallback: number): number {
  const source = unwrapItem(item);
  const raw = [
    propertyText(source, "dossier_id"),
    propertyText(source, "atlas_row_id"),
    propertyText(source, "candidate_id"),
    propertyText(source, "original_node_id"),
    text(source.node_id || source.cluster_id || source.edge_id || source.label),
  ].join(" ");
  const tableThree = raw.match(/T3[-_ ]?(\d+)/i);
  if (tableThree) return 3000 + Number(tableThree[1]);
  const tableTwo = raw.match(/T2[-_ ]?(\d+)/i);
  if (tableTwo) return 2000 + Number(tableTwo[1]);
  const dossier = raw.match(/\bA(\d{1,3})\b/i);
  if (dossier) return Number(dossier[1]);
  return fallback;
}

function normalized(value: number, min: number, max: number): number {
  if (!Number.isFinite(value) || max <= min) return 0;
  return ((value - min) / (max - min)) * 2 - 1;
}

function laneForItem(item: AnyItem, fallback: number): number {
  const signal = text(item.cluster_kind || item.node_type || item.primary_predicate || item.predicate_id || item.label || item.title);
  if (signal.includes("canon") || signal.includes("candidate")) return 0;
  if (signal.includes("source") || signal.includes("corpus")) return 1;
  if (signal.includes("concept") || signal.includes("lineage")) return 2;
  if (signal.includes("evidence") || signal.includes("unresolved")) return 3;
  return fallback % 5;
}

function flowLaneForItem(item: AnyItem, fallback: number): number {
  const signal = `${text(item.cluster_kind || item.node_type || item.primary_predicate || item.predicate_id || item.label || item.title)} ${itemLayers(item).join(" ")}`.toLowerCase();
  if (signal.includes("source") || signal.includes("witness") || signal.includes("evidence")) return 0;
  if (signal.includes("corpus") || signal.includes("dossier") || signal.includes("prepared")) return 1;
  if (signal.includes("candidate") || signal.includes("concept")) return 2;
  if (signal.includes("transmission") || signal.includes("preserved") || signal.includes("survives") || signal.includes("medium")) return 3;
  if (signal.includes("canon") || signal.includes("status") || signal.includes("promotion")) return 4;
  return fallback % 5;
}

function evidenceLaneForItem(item: AnyItem, fallback: number): number {
  const signal = `${text(item.cluster_kind || item.node_type || item.primary_predicate || item.predicate_id || item.label || item.title)} ${propertyText(item, "original_node_type")} ${itemLayers(item).join(" ")}`.toLowerCase();
  if (signal.includes("source") || signal.includes("document") || signal.includes("witness")) return 0;
  if (signal.includes("preservation") || signal.includes("survives") || signal.includes("preserved")) return 1;
  if (signal.includes("evidence") || signal.includes("dossier") || signal.includes("corpus")) return 2;
  if (signal.includes("contested") || signal.includes("controversy") || signal.includes("uncertainty")) return 3;
  if (signal.includes("lost") || signal.includes("absence") || signal.includes("fragment")) return 4;
  return fallback % 5;
}

function semanticLaneForItem(item: AnyItem, fallback: number): number {
  const signal = `${text(item.cluster_kind || item.node_type || item.primary_predicate || item.predicate_id || item.label || item.title)} ${propertyText(item, "original_node_type")} ${itemLayers(item).join(" ")}`.toLowerCase();
  if (signal.includes("concept") || signal.includes("problem")) return 0;
  if (signal.includes("method") || signal.includes("genre")) return 1;
  if (signal.includes("candidate")) return 2;
  if (signal.includes("canon") || signal.includes("canonical")) return 3;
  if (signal.includes("source") || signal.includes("evidence")) return 4;
  return fallback % 5;
}

function branchRegionLane(item: AnyItem, fallback: number): number {
  const branch = propertyText(item, "branch_path").toLowerCase();
  if (branch.includes("west-asia")) return 0;
  if (branch.includes("north-africa")) return 1;
  if (branch.includes("east-asia")) return 2;
  if (branch.includes("south-asia")) return 3;
  if (branch.includes("southeast-asia")) return 4;
  if (branch.includes("mediterranean")) return 5;
  return fallback % 6;
}

function layoutForceIterations(family: LayoutFamily): number {
  if (state.rendererMode === "cosmos" && family !== "organic" && family !== "semantic") return 0;
  if (family === "timeline" || family === "flow" || family === "evidence") return graph.order > 500 ? 10 : 18;
  if (family === "semantic") return graph.order > 500 ? 24 : 42;
  return graph.order > 500 ? 34 : 68;
}

function layoutGraph(): void {
  const count = Math.max(graph.order, 1);
  const family = layoutFamily();
  const nodes = graph.nodes();
  const ordinals = nodes.map((node, index) => dossierOrdinal(lastGraphItems.get(node) || {}, index));
  const minOrdinal = Math.min(...ordinals);
  const maxOrdinal = Math.max(...ordinals);
  const span = 1 + count / 90;
  nodes.forEach((node, index) => {
    const item = lastGraphItems.get(node) || {};
    const hash = hashNumber(node);
    const lane = laneForItem(item, hash);
    const orderX = normalized(ordinals[index], minOrdinal, maxOrdinal);
    const jitter = ((hash % 29) - 14) / 120;
    let x = 0;
    let y = 0;
    if (family === "timeline") {
      x = orderX * (2.7 + count / 75);
      y = (lane - 2) * 0.58 + jitter;
    } else if (family === "flow") {
      const flowLane = flowLaneForItem(item, hash);
      x = (flowLane - 2) * 1.08 + jitter;
      y = orderX * (2.2 + count / 92) + ((hash % 17) - 8) / 180;
    } else if (family === "evidence") {
      const evidenceLane = evidenceLaneForItem(item, hash);
      x = (evidenceLane - 2) * 1.0 + jitter;
      y = orderX * (2.3 + count / 105) + ((hash % 23) - 11) / 180;
    } else if (family === "semantic") {
      const semanticLane = semanticLaneForItem(item, hash);
      const radius = 0.45 + semanticLane * 0.42 + count / 520;
      const angle = Math.PI * 2 * ((hash % 997) / 997);
      x = Math.cos(angle) * radius + orderX * 0.12;
      y = Math.sin(angle) * radius + (semanticLane - 2) * 0.08;
    } else if (family === "infrastructure") {
      const regionLane = branchRegionLane(item, hash);
      const mediaLane = evidenceLaneForItem(item, hash);
      x = (regionLane - 2.5) * 0.82 + jitter;
      y = (mediaLane - 2) * 0.66 + orderX * 0.72 + ((hash % 19) - 9) / 160;
    } else {
      const angle = (Math.PI * 2 * (hash % Math.max(count, 2))) / Math.max(count, 2);
      x = Math.cos(angle) * span + jitter;
      y = Math.sin(angle) * span + jitter;
    }
    graph.setNodeAttribute(node, "x", x);
    graph.setNodeAttribute(node, "y", y);
  });
  const iterations = layoutForceIterations(family);
  if (graph.order > 1 && iterations > 0) {
    forceAtlas2.assign(graph, {
      iterations,
      settings: {
        ...forceAtlas2.inferSettings(graph),
        gravity: family === "timeline" ? 0.16 : family === "flow" || family === "evidence" ? 0.12 : 0.055,
        scalingRatio: graph.order > 500 ? 7 : family === "semantic" ? 8 : 11,
      },
    });
  }
}

function selectItem(item: AnyItem): void {
  state.selected = item;
  state.selectedGraphId = text(item.node_id || item.cluster_id || item.edge_id || "") || null;
  const nodeId = selectedNodeIdFor(item);
  if (!nodeId || state.neighborhood?.node?.node_id !== nodeId) state.neighborhood = null;
  const pathNodeIds = new Set(stringList(state.pathPacket?.nodes?.map((node) => node.node_id)));
  if (!nodeId || (state.pathPacket && !pathNodeIds.has(nodeId))) state.pathPacket = null;
  const cluster = item as Cluster;
  if (cluster.cluster_id && cluster.member_node_ids?.length) {
    state.expandedCluster = cluster;
  }
  renderChips();
  renderGraph();
  renderInspector();
  scrollInspectorTop();
}

function nodeRouteActions(nodeId: string): string {
  const pathStartLabel = state.pathStartNodeId ? endpointLabel(state.pathStartNodeId) || state.pathStartNodeId : "";
  const canPathTo = Boolean(state.pathStartNodeId && state.pathStartNodeId !== nodeId);
  return `
    <div class="route-actions">
      <button id="neighborhood-button" type="button">${t("route.neighborhood")}</button>
      <button id="path-start-button" type="button">${state.pathStartNodeId === nodeId ? t("route.pathStartSet") : t("route.useAsPathStart")}</button>
      ${canPathTo ? `<button id="path-to-button" type="button">${t("route.pathFrom")} ${escapeHtml(short(pathStartLabel, 24))}</button>` : ""}
    </div>
  `;
}

function neighborhoodCards(nodeId: string): string[] {
  if (!state.neighborhood || state.neighborhood.node?.node_id !== nodeId) return [];
  const neighbors = state.neighborhood.neighbors || [];
  const edges = state.neighborhood.edges || [];
  const cards = [
    detailCard(
      t("detail.neighborhood"),
      [
        `${neighbors.length} ${t("detail.neighborCount")}`,
        `${edges.length} ${t("relation.relations")}`,
        state.neighborhood.layers?.length ? state.neighborhood.layers.map(humanKind).join(", ") : t("detail.allActiveLayers"),
        state.neighborhood.predicates?.length ? state.neighborhood.predicates.map(humanKind).join(", ") : t("detail.allActivePredicates"),
        state.neighborhood.query_backend ? `${t("detail.backend")}: ${state.neighborhood.query_backend}` : "",
        state.neighborhood.fallback_reason ? `${t("detail.fallback")}: ${state.neighborhood.fallback_reason}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    ),
  ];
  if (neighbors.length) {
    cards.push(`<div class="section-title">${t("detail.neighbors")}</div>`);
    cards.push(
      ...neighbors.slice(0, 24).map(
        (item, index) => `
          <button class="result-card" data-neighbor="${index}" type="button">
            <span class="result-title">${escapeHtml(short(displayTitle(item), 82))}</span>
            <span class="result-subtitle">${escapeHtml(short(displaySubtitle(item), 98))}</span>
          </button>
        `,
      ),
    );
  }
  if (edges.length) {
    cards.push(relationRowsSection(t("detail.neighborhoodRelations"), edges.map((edge) => relationRowFromEdge(edge, "adjacent")), "neighborhood"));
  }
  return cards;
}

function pathCards(nodeId: string): string[] {
  const cards: string[] = [];
  if (state.pathStartNodeId) {
    cards.push(detailCard(t("detail.pathStart"), endpointLabel(state.pathStartNodeId) || state.pathStartNodeId));
  }
  if (!state.pathPacket || (state.pathPacket.from_id !== nodeId && state.pathPacket.to_id !== nodeId)) return cards;
  const nodes = state.pathPacket.nodes || [];
  const edges = state.pathPacket.edges || [];
  cards.push(
    detailCard(
      t("detail.path"),
      state.pathPacket.found
        ? [
            `${nodes.length} ${t("caption.nodes")}`,
            `${edges.length} ${t("relation.relations")}`,
            `${t("detail.maxDepth")} ${state.pathPacket.max_depth || 6}`,
            state.pathPacket.predicates?.length ? state.pathPacket.predicates.map(humanKind).join(", ") : t("detail.allActivePredicates"),
            state.pathPacket.query_backend ? `${t("detail.backend")}: ${state.pathPacket.query_backend}` : "",
            state.pathPacket.fallback_reason ? `${t("detail.fallback")}: ${state.pathPacket.fallback_reason}` : "",
          ]
            .filter(Boolean)
            .join("\n")
        : [
            t("detail.noRoute"),
            `${t("detail.maxDepth")} ${state.pathPacket.max_depth || 6}`,
            state.pathPacket.query_backend ? `${t("detail.backend")}: ${state.pathPacket.query_backend}` : "",
            state.pathPacket.fallback_reason ? `${t("detail.fallback")}: ${state.pathPacket.fallback_reason}` : "",
          ]
            .filter(Boolean)
            .join("\n"),
    ),
  );
  if (nodes.length) {
    cards.push(`<div class="section-title">${t("detail.pathNodes")}</div>`);
    cards.push(
      ...nodes.map(
        (item, index) => `
          <button class="result-card" data-path-node="${index}" type="button">
            <span class="result-title">${escapeHtml(short(displayTitle(item), 82))}</span>
            <span class="result-subtitle">${escapeHtml(short(displaySubtitle(item), 98))}</span>
          </button>
        `,
      ),
    );
  }
  if (edges.length) {
    cards.push(relationRowsSection(t("detail.pathRelations"), edges.map((edge) => relationRowFromEdge(edge, "adjacent")), "path"));
  }
  return cards;
}

function activeLayerParam(): string {
  const layers = [...state.activeLayers].filter(Boolean).join(",");
  return layers ? `&layers=${encodeURIComponent(layers)}` : "";
}

function activePredicateParam(): string {
  const predicates = [...state.activePredicates].filter(Boolean).join(",");
  return predicates ? `&predicates=${encodeURIComponent(predicates)}` : "";
}

async function showNeighborhood(nodeId: string): Promise<void> {
  if (!nodeId) return;
  const selected = state.selected;
  ignoreGraphClicksUntil = Date.now() + 1500;
  ignoreInspectorSelectionsUntil = Date.now() + 1500;
  state.graphMode = "nodes";
  state.expandedCluster = null;
  state.selectedGraphId = nodeId;
  state.neighborhood = await fetchJson<NeighborhoodPayload>(
    `/api/philosophy/query/neighborhood/${encodeURIComponent(nodeId)}?depth=1&limit=160${activeLayerParam()}${activePredicateParam()}`,
  );
  state.selected = selected;
  state.selectedGraphId = nodeId;
  renderChips();
  renderGraph();
  ignoreGraphClicksUntil = Date.now() + 1500;
  ignoreInspectorSelectionsUntil = Date.now() + 1500;
  renderInspector();
  scrollInspectorTop();
}

function setPathStart(nodeId: string): void {
  if (!nodeId) return;
  state.pathStartNodeId = nodeId;
  state.pathPacket = null;
  renderInspector();
}

async function showPathTo(nodeId: string): Promise<void> {
  if (!nodeId || !state.pathStartNodeId || state.pathStartNodeId === nodeId) return;
  const selected = state.selected;
  ignoreGraphClicksUntil = Date.now() + 1500;
  ignoreInspectorSelectionsUntil = Date.now() + 1500;
  state.graphMode = "nodes";
  state.expandedCluster = null;
  state.pathPacket = await fetchJson<PathPayload>(
    `/api/philosophy/query/paths?from=${encodeURIComponent(state.pathStartNodeId)}&to=${encodeURIComponent(nodeId)}&max_depth=6${activeLayerParam()}${activePredicateParam()}`,
  );
  state.selected = selected;
  state.selectedGraphId = nodeId;
  renderChips();
  renderGraph();
  ignoreGraphClicksUntil = Date.now() + 1500;
  ignoreInspectorSelectionsUntil = Date.now() + 1500;
  renderInspector();
  scrollInspectorTop();
}

function clearFocus(): void {
  state.neighborhood = null;
  state.pathPacket = null;
  state.expandedCluster = null;
  state.graphMode = state.mode === "philosophy" ? "clusters" : "nodes";
  renderAll();
}

function renderAll(): void {
  renderChips();
  renderMetrics();
  renderViews();
  renderLayers();
  renderRelationControls();
  renderScaleExportControls();
  renderGraph();
  renderInspector();
}

async function copyScaleExportUrl(table?: ScaleExportTable, format?: "csv" | "jsonl"): Promise<void> {
  const url = scaleExportAbsoluteUrl(table, format);
  try {
    await navigator.clipboard.writeText(url);
    state.selected = { title: t("selection.scaleExportUrl"), url };
  } catch (error) {
    state.selected = { title: t("selection.scaleExportUrl"), url, copy_error: text(error) };
  }
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function loadMode(mode: Mode): Promise<void> {
  state.mode = mode;
  state.currentView = null;
  state.selected = null;
  state.selectedGraphId = null;
  state.results = [];
  state.relationItems = [];
  state.expandedCluster = null;
  state.neighborhood = null;
  state.pathStartNodeId = null;
  state.pathPacket = null;
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
  state.neighborhood = null;
  state.pathStartNodeId = null;
  state.pathPacket = null;
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
  state.selected = { title: query ? `${t("selection.search")}: ${query}` : t("selection.search"), results: state.results.length };
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function showReviewPacket(): Promise<void> {
  if (state.mode !== "philosophy") return;
  const payload = await fetchJson<{ packet: AnyItem }>(`/api/philosophy/review-packet?view_id=${encodeURIComponent(state.currentViewId)}`);
  state.selected = { title: `${t("selection.reviewPacket")}: ${state.currentViewId}`, ...payload.packet };
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function showUnresolved(): Promise<void> {
  if (state.mode !== "philosophy") return;
  const payload = await fetchJson<{ unresolved?: AnyItem[] }>(`/api/philosophy/unresolved?view_id=${encodeURIComponent(state.currentViewId)}`);
  state.results = payload.unresolved || [];
  state.selected = { title: `${t("selection.unresolved")}: ${state.currentViewId}`, unresolved: state.results.length };
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function showSnapshot(): Promise<void> {
  if (state.mode !== "philosophy") return;
  state.selected = await fetchJson<AnyItem>("/api/philosophy/snapshot");
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function showAudit(): Promise<void> {
  if (state.mode !== "philosophy") return;
  state.selected = await fetchJson<AnyItem>("/api/philosophy/audit");
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

async function syncProjection(): Promise<void> {
  const url = state.mode === "philosophy" ? "/api/philosophy/project/sync" : "/api/project/sync";
  state.selected = await fetchJson<AnyItem>(url, { method: "POST" });
  state.selectedGraphId = null;
  renderInspector();
  scrollInspectorTop();
}

renderShell();
void loadMode("philosophy").catch((error: unknown) => {
  byId("inspector-title").textContent = t("load.failed");
  byId("inspector-meta").innerHTML = `<span class="danger">${text(error)}</span>`;
});
