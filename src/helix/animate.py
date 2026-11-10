"""把 DEBUG 输出转换为独立的 HTML 动画播放器。

播放器只依赖 run.json / model.json / events.ndjson / states.ndjson，
生成单个 HTML 文件，不需要额外 JavaScript 依赖。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .errors import HelixRuntimeError


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HelixRuntimeError(f"缺少 DEBUG 文件: {path}") from exc


def _read_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _json_for_html(data) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # 防止数据中的字符串提前关闭 <script>。
    return text.replace("</", "<\\/")


def build_player(debug_dir: str | Path, output: str | Path,
                 title: str | None = None) -> Path:
    """读取 DEBUG 目录并生成独立 HTML 播放器。"""
    debug_dir = Path(debug_dir)
    output = Path(output)
    run = _read_json(debug_dir / "run.json")
    model = _read_json(debug_dir / "model.json")
    events = _read_ndjson(debug_dir / "events.ndjson")
    states = _read_ndjson(debug_dir / "states.ndjson")
    if not states:
        raise HelixRuntimeError(
            "DEBUG 目录缺少 states.ndjson；请用当前版本重新运行 --debug")

    data = {
        "run": run,
        "model": model,
        "events": events,
        "states": states,
    }
    display_title = title or run.get("project") or "Helix Animation"
    document = (
        _TEMPLATE
        .replace("__TITLE__", html.escape(display_title))
        .replace("__DATA__", _json_for_html(data))
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Helix Animation</title>
<style>
  :root {
    --bg: #0d1117;
    --panel: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --green: #7ee787;
    --yellow: #f2cc60;
    --red: #ff7b72;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
  }
  header {
    padding: 12px 18px; background: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; gap: 16px;
    align-items: center;
  }
  h1 { margin: 0; font-size: 16px; font-weight: 600; }
  #meta { color: var(--muted); font-size: 12px; }
  main {
    display: grid; grid-template-columns: minmax(0, 1fr) 300px;
    gap: 12px; padding: 12px; min-height: calc(100vh - 57px);
  }
  #stage {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; overflow: auto; min-height: 420px;
  }
  #graph { display: block; min-width: 900px; }
  aside {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px; align-self: start;
  }
  aside h2 { font-size: 12px; color: var(--muted); margin: 14px 0 6px; }
  aside h2:first-child { margin-top: 0; }
  table { border-collapse: collapse; width: 100%; }
  td, th { text-align: left; padding: 3px 4px; border-bottom: 1px solid #21262d; }
  th { color: var(--muted); font-weight: 400; }
  .controls {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 18px; background: var(--panel);
    border-top: 1px solid var(--border); position: sticky; bottom: 0;
  }
  button, select {
    background: #21262d; color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 5px 10px; cursor: pointer;
  }
  button:hover { border-color: var(--accent); }
  #slider { flex: 1; accent-color: var(--accent); }
  #time { min-width: 170px; color: var(--accent); }
  .entity { cursor: help; }
  .empty { color: var(--muted); padding: 16px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <div id="meta"></div>
  </div>
  <div id="time">t = 0</div>
</header>
<main>
  <section id="stage"><svg id="graph"></svg></section>
  <aside>
    <h2>EVENT</h2>
    <div id="event">—</div>
    <h2>QUEUES</h2>
    <table id="queues"></table>
    <h2>ACTIVITIES</h2>
    <table id="activities"></table>
    <h2>RESOURCES</h2>
    <table id="resources"></table>
    <h2>ENTITIES</h2>
    <div id="entities"></div>
  </aside>
</main>
<div class="controls">
  <button id="prev">◀</button>
  <button id="play">▶</button>
  <button id="next">▶</button>
  <input id="slider" type="range" min="0" max="0" value="0">
  <select id="speed">
    <option value="2000">0.25×</option>
    <option value="1000" selected>0.5×</option>
    <option value="500">1×</option>
    <option value="250">2×</option>
  </select>
</div>
<script>
const DATA = __DATA__;

const state = {
  index: 0,
  timer: null,
  positions: new Map(),
  graphWidth: 1200,
  graphHeight: 500,
};

const fmt = (value, digits = 2) => {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
};

const nodes = DATA.model.nodes || [];
const byLabel = new Map(nodes.map(node => [node.label, node]));
const incoming = new Map(nodes.map(node => [node.label, 0]));
const outgoing = new Map(nodes.map(node => [node.label, []]));
for (const node of nodes) {
  for (const target of (node.outgoing || [])) {
    if (!byLabel.has(target)) continue;
    outgoing.get(node.label).push(target);
    incoming.set(target, (incoming.get(target) || 0) + 1);
  }
}

function buildLayout() {
  const depth = new Map();
  const roots = nodes.filter(node => (incoming.get(node.label) || 0) === 0);
  const queue = roots.length ? roots.map(node => node.label) : nodes.map(n => n.label);
  for (const label of queue) depth.set(label, 0);
  for (let pass = 0; pass < nodes.length + 2; pass++) {
    let changed = false;
    for (const node of nodes) {
      const current = depth.get(node.label) || 0;
      for (const target of outgoing.get(node.label) || []) {
        const next = Math.max(depth.get(target) || 0, current + 1);
        if (next !== (depth.get(target) || 0)) {
          depth.set(target, next);
          changed = true;
        }
      }
    }
    if (!changed) break;
  }
  const columns = new Map();
  for (const node of nodes) {
    const d = depth.get(node.label) || 0;
    if (!columns.has(d)) columns.set(d, []);
    columns.get(d).push(node);
  }
  const maxDepth = Math.max(0, ...columns.keys());
  const positions = new Map();
  const gapX = 190;
  const gapY = 108;
  const maxRows = Math.max(1, ...Array.from(columns.values()).map(v => v.length));
  const height = Math.max(420, maxRows * gapY + 100);
  for (const [d, column] of columns.entries()) {
    column.forEach((node, index) => {
      positions.set(node.label, {
        x: 70 + d * gapX,
        y: 70 + index * gapY + (maxRows - column.length) * gapY / 2,
      });
    });
  }
  state.positions = positions;
  state.graphWidth = 70 + maxDepth * gapX + 170;
  state.graphHeight = height;
}

function svgElement(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function drawGraph() {
  const svg = document.getElementById("graph");
  svg.setAttribute("viewBox", `0 0 ${state.graphWidth} ${state.graphHeight}`);
  svg.setAttribute("width", state.graphWidth);
  svg.setAttribute("height", state.graphHeight);
  svg.innerHTML = "";
  const defs = svgElement("defs");
  defs.innerHTML = '<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8b949e"/></marker>';
  svg.appendChild(defs);
  for (const node of nodes) {
    const from = state.positions.get(node.label);
    if (!from) continue;
    for (const target of outgoing.get(node.label) || []) {
      const to = state.positions.get(target);
      if (!to) continue;
      const line = svgElement("line", {
        x1: from.x + 130, y1: from.y + 25,
        x2: to.x - 8, y2: to.y + 25,
        stroke: "#8b949e", "stroke-width": 1.2,
        "marker-end": "url(#arrow)",
        opacity: 0.65,
      });
      svg.appendChild(line);
    }
  }
  for (const node of nodes) {
    const pos = state.positions.get(node.label);
    if (!pos) continue;
    const group = svgElement("g", { "data-node": node.label });
    const color = colorForKind(node.kind);
    group.appendChild(svgElement("rect", {
      x: pos.x, y: pos.y, width: 130, height: 50, rx: 7,
      fill: "#1f2630", stroke: color, "stroke-width": 1.4,
    }));
    const label = svgElement("text", {
      x: pos.x + 10, y: pos.y + 19, fill: "#e6edf3",
      "font-size": 12, "font-family": "inherit",
    });
    label.textContent = node.label.length > 16 ? node.label.slice(0, 15) + "…" : node.label;
    group.appendChild(label);
    const kind = svgElement("text", {
      x: pos.x + 10, y: pos.y + 36, fill: color,
      "font-size": 10, "font-family": "inherit",
    });
    kind.textContent = node.kind;
    group.appendChild(kind);
    group.appendChild(svgElement("rect", {
      x: pos.x + 100, y: pos.y - 8, width: 30, height: 16, rx: 8,
      fill: "#30363d", opacity: 0.7,
    }));
    const badge = svgElement("text", {
      x: pos.x + 115, y: pos.y + 3, "text-anchor": "middle",
      fill: "#e6edf3", "font-size": 10, "font-family": "inherit",
    });
    badge.textContent = "0";
    group.appendChild(badge);
    group.classList.add("node-group");
    svg.appendChild(group);
  }
  render();
}

function colorForKind(kind) {
  return {
    CREATE: "#58a6ff", QUEUE: "#f2cc60", ACTIVITY: "#7ee787",
    TERMINATE: "#ff7b72", IF: "#d2a8ff", AWAIT: "#ffa657",
    FREE: "#ffa657", ALTER: "#79c0ff", DETECT: "#ffa657",
    PREEMPT: "#ff7b72", MERGE: "#8b949e",
  }[kind] || "#8b949e";
}

function currentState() {
  return DATA.states[state.index] || {entities: [], queues: [], activities: [], resources: []};
}

function render() {
  const current = currentState();
  document.getElementById("time").textContent = `t = ${fmt(current.t, 4)}`;
  document.getElementById("event").textContent = current.event || "—";
  const slider = document.getElementById("slider");
  slider.max = Math.max(0, DATA.states.length - 1);
  slider.value = state.index;

  const svg = document.getElementById("graph");
  for (const old of Array.from(svg.querySelectorAll(".entity"))) old.remove();

  const counts = new Map();
  for (const entity of current.entities) {
    if (!entity.node || !state.positions.has(entity.node)) continue;
    counts.set(entity.node, (counts.get(entity.node) || 0) + 1);
  }
  for (const group of Array.from(svg.querySelectorAll(".node-group"))) {
    const label = group.getAttribute("data-node");
    const badge = group.querySelector("text:last-of-type");
    if (badge) badge.textContent = String(counts.get(label) || 0);
  }

  const byNode = new Map();
  for (const entity of current.entities) {
    if (!entity.node) continue;
    if (!byNode.has(entity.node)) byNode.set(entity.node, []);
    byNode.get(entity.node).push(entity);
  }
  for (const [nodeLabel, group] of byNode.entries()) {
    const pos = state.positions.get(nodeLabel);
    if (!pos) continue;
    group.slice(0, 24).forEach((entity, index) => {
      const col = index % 6;
      const row = Math.floor(index / 6);
      const circle = svgElement("circle", {
        cx: pos.x + 12 + col * 15,
        cy: pos.y + 58 + row * 14,
        r: 5,
        fill: statusColor(entity.status),
        stroke: "#0d1117", "stroke-width": 1,
        class: "entity",
      });
      circle.appendChild(svgElement("title")).textContent =
        `#${entity.id} ${entity.status}` +
        (Object.keys(entity.attrs || {}).length
          ? "\\n" + JSON.stringify(entity.attrs) : "");
      svg.appendChild(circle);
      const text = svgElement("text", {
        x: pos.x + 20 + col * 15,
        y: pos.y + 61 + row * 14,
        fill: "#0d1117", "font-size": 7,
        "font-weight": "700", "text-anchor": "middle",
        class: "entity",
      });
      text.textContent = String(entity.id);
      svg.appendChild(text);
    });
  }
  renderTable("queues", current.queues || [], ["label", "length", "capacity"]);
  renderTable("activities", current.activities || [],
    ["label", "active", "waiting", "completed"]);
  renderTable("resources", current.resources || [],
    ["name", "held", "capacity", "waiting"]);
  document.getElementById("entities").textContent =
    `${(current.entities || []).length} active / ${DATA.states.length} snapshots`;
}

function statusColor(status) {
  return {BUSY: "#7ee787", QUEUED: "#f2cc60", WAITING: "#ffa657",
    BLOCKED: "#ff7b72"}[status] || "#58a6ff";
}

function renderTable(id, rows, fields) {
  const table = document.getElementById(id);
  table.innerHTML = "";
  if (!rows.length) return;
  const head = document.createElement("tr");
  for (const field of fields) {
    const th = document.createElement("th");
    th.textContent = field;
    head.appendChild(th);
  }
  table.appendChild(head);
  for (const row of rows.slice(0, 40)) {
    const tr = document.createElement("tr");
    for (const field of fields) {
      const td = document.createElement("td");
      td.textContent = String(row[field] ?? "—");
      tr.appendChild(td);
    }
    table.appendChild(tr);
  }
}

function step(delta) {
  state.index = Math.max(0, Math.min(DATA.states.length - 1, state.index + delta));
  render();
}

function togglePlay() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
    document.getElementById("play").textContent = "▶";
    return;
  }
  document.getElementById("play").textContent = "❚❚";
  const speed = Number(document.getElementById("speed").value);
  state.timer = setInterval(() => {
    if (state.index >= DATA.states.length - 1) {
      clearInterval(state.timer);
      state.timer = null;
      document.getElementById("play").textContent = "▶";
      return;
    }
    step(1);
  }, speed);
}

buildLayout();
const run = DATA.run || {};
document.getElementById("meta").textContent =
  `seed ${run.seed ?? "?"} · ${fmt(run.start, 2)} → ${fmt(run.end, 2)}` +
  ` · ${DATA.events.length} events`;
document.getElementById("slider").addEventListener("input", event => {
  state.index = Number(event.target.value);
  render();
});
document.getElementById("prev").addEventListener("click", () => step(-1));
document.getElementById("next").addEventListener("click", () => step(1));
document.getElementById("play").addEventListener("click", togglePlay);
document.getElementById("speed").addEventListener("change", () => {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
    togglePlay();
  }
});
drawGraph();
</script>
</body>
</html>
"""
