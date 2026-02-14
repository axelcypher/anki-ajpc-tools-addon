from __future__ import annotations

import json
from typing import Any, Callable

from aqt.qt import QColor, Qt, QVBoxLayout, QWidget
from aqt.webview import AnkiWebView

from ._note_editor import open_note_editor


_GRAPH_HTML = r"""
<style>
html, body {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: transparent;
}
#ajpc-force-graph-root {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #1f1f1f;
  border-radius: 8px;
  box-sizing: border-box;
}
#ajpc-force-graph-canvas {
  width: 100%;
  height: 100%;
  display: block;
  background: transparent;
}
</style>
<div id="ajpc-force-graph-root">
  <canvas id="ajpc-force-graph-canvas" style="width:100%;height:100%;display:block;"></canvas>
</div>
<script>
(function () {
  const canvas = document.getElementById("ajpc-force-graph-canvas");
  const ctx = canvas.getContext("2d");
  const state = {
    nodes: [],
    links: [],
    byId: new Map(),
    bg: "#1f1f1f",
    selected: null,
    dragNode: null,
    panning: false,
    panStart: { x: 0, y: 0, cx: 0, cy: 0 },
    cam: { x: 0, y: 0, s: 1 },
    initialized: false,
    lastCurrentId: null,
    lastCenteredCurrentId: null,
    pendingFit: false,
    highlight: { nids: new Set(), bucket: "", active: false },
  };

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function resize() {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) {
      return;
    }
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function worldFromScreen(px, py) {
    return {
      x: (px - state.cam.x) / state.cam.s,
      y: (py - state.cam.y) / state.cam.s,
    };
  }

  function nodeRadius(n) {
    return n.role === "current" ? 13 : 9;
  }

  function roundedPath(x, y, w, h, r) {
    const rr = Math.min(r, w * 0.5, h * 0.5);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
    ctx.lineTo(x + rr, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
    ctx.lineTo(x, y + rr);
    ctx.quadraticCurveTo(x, y, x + rr, y);
    ctx.closePath();
  }

  function edgeColor(bucket) {
    if (bucket === "family_prio") return "#3d95e7";
    if (bucket === "family") return "#34d399";
    if (bucket === "mass") return "#f56e0d";
    return "#f59e0b";
  }

  function edgeDashed(bucket) {
    return bucket === "manual" || bucket === "mass";
  }

  function edgeDotted(bucket) {
    return bucket === "family";
  }

  function nodeColor(n) {
    if (n && n.color && String(n.color).trim()) return String(n.color).trim();
    if (n.bucket === "family_prio") return "#3d95e7";
    if (n.bucket === "family") return "#34d399";
    if (n.bucket === "mass") return "#f56e0d";
    return "#f59e0b";
  }

  function nodeHighlighted(n) {
    if (!state.highlight.active) return true;
    if (state.highlight.nids.size) {
      return state.highlight.nids.has(Number(n.nid || 0));
    }
    const b = String(state.highlight.bucket || "");
    if (!b) return true;
    if (b === "family") return n.bucket === "family" || n.bucket === "family_prio";
    return String(n.bucket || "") === b;
  }

  function edgeHighlighted(e) {
    if (!state.highlight.active) return true;
    if (state.highlight.nids.size) {
      const a = Number(e.source.nid || 0);
      const b = Number(e.target.nid || 0);
      return state.highlight.nids.has(a) || state.highlight.nids.has(b);
    }
    const b = String(state.highlight.bucket || "");
    if (!b) return true;
    if (b === "family") return e.bucket === "family" || e.bucket === "family_prio";
    return String(e.bucket || "") === b;
  }

  function fitToNodes() {
    if (!state.nodes.length) return false;
    const vw = canvas.clientWidth;
    const vh = canvas.clientHeight;
    if (vw < 2 || vh < 2) return false;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of state.nodes) {
      const r = nodeRadius(n) + 20;
      minX = Math.min(minX, n.x - r);
      minY = Math.min(minY, n.y - r);
      maxX = Math.max(maxX, n.x + r);
      maxY = Math.max(maxY, n.y + r);
    }
    const bw = Math.max(20, maxX - minX);
    const bh = Math.max(20, maxY - minY);
    const pad = 28;
    const sx = (vw - pad * 2) / bw;
    const sy = (vh - pad * 2) / bh;
    const scale = clamp(Math.min(sx, sy), 0.2, 2.2);
    const cx = (minX + maxX) * 0.5;
    const cy = (minY + maxY) * 0.5;
    state.cam.s = scale;
    state.cam.x = vw * 0.5 - cx * scale;
    state.cam.y = vh * 0.5 - cy * scale;
    return true;
  }

  function build(payload) {
    const keep = new Map();
    for (const n of state.nodes) {
      keep.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy, fx: n.fx, fy: n.fy });
    }

    state.nodes = [];
    state.links = [];
    state.byId = new Map();
    const prevCurrentId = state.lastCurrentId ? String(state.lastCurrentId) : null;
    const nextCurrentId = payload && payload.current_id ? String(payload.current_id) : null;

    const srcNodes = (payload && payload.nodes) || [];
    const srcEdges = (payload && payload.edges) || [];
    const count = Math.max(1, srcNodes.length);
    for (let i = 0; i < srcNodes.length; i++) {
      const s = srcNodes[i] || {};
      const id = String(s.id || "");
      if (!id) continue;
      const old = keep.get(id);
      const isCurrent = !!nextCurrentId && id === nextCurrentId;
      const wasPrevCurrent = !!prevCurrentId && id === prevCurrentId;
      const angle = (i / count) * Math.PI * 2;
      const r = 130 + ((i % 7) * 11);
      const seedX = Math.cos(angle) * r;
      const seedY = Math.sin(angle) * r;
      let x = isCurrent ? 0 : (old ? old.x : seedX);
      let y = isCurrent ? 0 : (old ? old.y : seedY);
      let fx = isCurrent ? 0 : (old ? old.fx : null);
      let fy = isCurrent ? 0 : (old ? old.fy : null);
      if (!isCurrent && wasPrevCurrent) {
        x = seedX;
        y = seedY;
        fx = null;
        fy = null;
      }
      const n = {
        id,
        nid: Number(s.nid || 0),
        label: String(s.label || "Link"),
        role: String(s.role || "linked"),
        bucket: String(s.bucket || "manual"),
        color: String(s.color || "").trim(),
        x,
        y,
        vx: old ? old.vx : 0,
        vy: old ? old.vy : 0,
        fx,
        fy,
      };
      state.nodes.push(n);
      state.byId.set(id, n);
    }

    for (const e of srcEdges) {
      const a = state.byId.get(String(e.source || ""));
      const b = state.byId.get(String(e.target || ""));
      if (!a || !b) continue;
      state.links.push({
        source: a,
        target: b,
        bucket: String(e.bucket || "manual"),
        direction: String(e.direction || "outgoing"),
      });
    }

    if (!state.initialized) {
      const rect = canvas.getBoundingClientRect();
      state.cam.x = rect.width * 0.5;
      state.cam.y = rect.height * 0.5;
      state.cam.s = 1;
      state.initialized = true;
    }

    if (state.selected && state.selected.id) {
      const keptSelected = state.byId.get(String(state.selected.id || ""));
      state.selected = keptSelected || null;
    } else {
      state.selected = null;
    }

    const needCenter = !!nextCurrentId && (
      nextCurrentId !== state.lastCurrentId ||
      nextCurrentId !== state.lastCenteredCurrentId ||
      state.pendingFit
    );
    if (needCenter) {
      const ok = fitToNodes();
      state.pendingFit = !ok;
      if (ok) {
        state.lastCenteredCurrentId = nextCurrentId;
      }
    } else if (!nextCurrentId) {
      state.pendingFit = false;
    }
    state.lastCurrentId = nextCurrentId;
  }

  function physicsStep() {
    const nodes = state.nodes;
    const links = state.links;
    if (!nodes.length) return;

    const repulsion = 6200;
    const springK = 0.012;
    const springLen = 115;
    const centerK = 0.0015;
    const damping = 0.84;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1e-6) {
          // Deterministic micro-jitter to avoid permanent center overlap.
          const ax = ((i * 37) % 11) - 5;
          const ay = ((j * 53) % 13) - 6;
          dx = (ax || 1) * 0.01;
          dy = (ay || -1) * 0.01;
          d2 = dx * dx + dy * dy;
        }
        if (d2 < 1) d2 = 1;
        const f = repulsion / d2;
        const inv = 1 / Math.sqrt(d2);
        dx *= inv;
        dy *= inv;
        a.vx += dx * f;
        a.vy += dy * f;
        b.vx -= dx * f;
        b.vy -= dy * f;
      }
    }

    for (const e of links) {
      const a = e.source;
      const b = e.target;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let d = Math.sqrt(dx * dx + dy * dy);
      if (d < 1e-6) {
        dx = 0.01;
        dy = -0.01;
        d = Math.sqrt(dx * dx + dy * dy);
      }
      if (d < 1) d = 1;
      const dirx = dx / d;
      const diry = dy / d;
      const ext = d - springLen;
      const f = ext * springK;
      a.vx += dirx * f;
      a.vy += diry * f;
      b.vx -= dirx * f;
      b.vy -= diry * f;
    }

    for (const n of nodes) {
      if (n.role === "current") {
        n.fx = 0;
        n.fy = 0;
      }
      n.vx += (-n.x) * centerK;
      n.vy += (-n.y) * centerK;
      n.vx *= damping;
      n.vy *= damping;
      if (n.fx !== null && n.fy !== null) {
        n.x = n.fx;
        n.y = n.fy;
        n.vx = 0;
        n.vy = 0;
      } else {
        n.x += n.vx;
        n.y += n.vy;
      }
    }
  }

  function pickNode(px, py) {
    const w = worldFromScreen(px, py);
    for (let i = state.nodes.length - 1; i >= 0; i--) {
      const n = state.nodes[i];
      const r = nodeRadius(n) + 4;
      const dx = w.x - n.x;
      const dy = w.y - n.y;
      if ((dx * dx + dy * dy) <= (r * r)) return n;
    }
    return null;
  }

  function draw() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w < 2 || h < 2) return;
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    roundedPath(0, 0, w, h, 8);
    ctx.clip();
    ctx.fillStyle = String(state.bg || "#1f1f1f");
    ctx.fillRect(0, 0, w, h);

    if (!state.nodes.length) {
      ctx.fillStyle = "#a5a5a5";
      ctx.font = "13px sans-serif";
      ctx.fillText("No linked nodes", 12, 24);
      ctx.restore();
      return;
    }

    ctx.save();
    ctx.translate(state.cam.x, state.cam.y);
    ctx.scale(state.cam.s, state.cam.s);

    ctx.lineWidth = 1 / state.cam.s;
    for (const e of state.links) {
      const eh = edgeHighlighted(e);
      ctx.globalAlpha = eh ? 0.72 : 0.08;
      ctx.strokeStyle = edgeColor(e.bucket);
      if (edgeDashed(e.bucket)) {
        ctx.lineCap = "butt";
        ctx.setLineDash([10 / state.cam.s, 8 / state.cam.s]);
      } else if (edgeDotted(e.bucket)) {
        ctx.lineCap = "round";
        ctx.setLineDash([1 / state.cam.s, 9 / state.cam.s]);
      } else {
        ctx.lineCap = "butt";
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      ctx.stroke();
    }
    ctx.lineCap = "butt";
    ctx.setLineDash([]);

    const time = performance.now();
    for (let i = 0; i < state.links.length; i++) {
      const e = state.links[i];
      if (!edgeHighlighted(e)) continue;
      const count = e.bucket === "family_prio" ? 3 : 2;
      for (let p = 0; p < count; p++) {
        const t = ((time * 0.00035) + (i * 0.17) + (p / count)) % 1;
        const x = e.source.x + (e.target.x - e.source.x) * t;
        const y = e.source.y + (e.target.y - e.source.y) * t;
        ctx.globalAlpha = 0.70;
        ctx.fillStyle = edgeColor(e.bucket);
        ctx.beginPath();
        ctx.arc(x, y, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    for (const n of state.nodes) {
      const nh = nodeHighlighted(n);
      const r = nodeRadius(n);
      const nColor = nodeColor(n);
      if (n.role === "current") {
        const pulsePhase = (Math.sin(time * 0.006) + 1) * 0.5;
        const pulseR = r + 5 + (8 * pulsePhase);
        ctx.globalAlpha = 0.40;
        ctx.fillStyle = nColor;
        ctx.beginPath();
        ctx.arc(n.x, n.y, pulseR, 0, Math.PI * 2);
        ctx.fill();
      }
      // Opaque underlay keeps edges visually below dimmed nodes in highlight mode.
      ctx.globalAlpha = 1.0;
      ctx.fillStyle = "#1f1f1f";
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + (1.8 / state.cam.s), 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = nh ? 1.0 : 0.2;
      ctx.fillStyle = nColor;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = nh ? 0.95 : 0.2;
      ctx.strokeStyle = nColor;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 3.4, 0, Math.PI * 2);
      ctx.stroke();
      if (state.selected && state.selected.id === n.id) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2 / state.cam.s;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 2, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    function wrapLabel(text, maxWidth, fontPx) {
      const t = String(text || "Link");
      ctx.font = `${fontPx}px sans-serif`;
      const lines = [];
      let cur = "";
      for (const ch of Array.from(t)) {
        const next = cur + ch;
        if (ctx.measureText(next).width <= maxWidth || cur.length === 0) {
          cur = next;
        } else {
          lines.push(cur);
          cur = ch;
          if (lines.length >= 3) break;
        }
      }
      if (cur && lines.length < 3) lines.push(cur);
      if (lines.length >= 3 && (lines[2] || "").length > 0) {
        lines[2] = lines[2].slice(0, Math.max(1, lines[2].length - 1)) + "…";
      }
      return lines.length ? lines : ["Link"];
    }

    function roundRect(x, y, w, h, r) {
      roundedPath(x, y, w, h, r);
    }

    const fontPx = Math.max(7.6, 11 / state.cam.s);
    const lineH = fontPx * 1.15;
    const maxW = Math.max(55, 140 / state.cam.s);
    ctx.font = `${fontPx}px sans-serif`;

    const selectedNode = (state.selected && state.selected.id && state.byId.get(state.selected.id))
      ? state.byId.get(state.selected.id)
      : null;
    if (selectedNode) {
      const n = selectedNode;
      const lines = wrapLabel(n.label, maxW, fontPx);
      let width = 0;
      for (const line of lines) {
        width = Math.max(width, ctx.measureText(line).width);
      }
      const padX = 5 / state.cam.s;
      const padY = 3 / state.cam.s;
      const totalW = width + padX * 2;
      const totalH = lines.length * lineH + padY * 2;
      const x = n.x + nodeRadius(n) + (6 / state.cam.s);
      const y = n.y - totalH * 0.5;

      const nh = nodeHighlighted(n);
      ctx.globalAlpha = nh ? 0.9 : 0.18;
      ctx.fillStyle = "rgba(18,18,18,0.86)";
      roundRect(x, y, totalW, totalH, 4 / state.cam.s);
      ctx.fill();
      ctx.globalAlpha = nh ? 1.0 : 0.4;
      ctx.fillStyle = "#efefef";
      for (let li = 0; li < lines.length; li++) {
        ctx.fillText(lines[li], x + padX, y + padY + (li + 1) * lineH - (lineH * 0.22));
      }
    }
    ctx.globalAlpha = 1.0;

    ctx.restore();

    ctx.restore();
  }

  function frame() {
    resize();
    if (state.pendingFit && state.lastCurrentId) {
      const ok = fitToNodes();
      if (ok) {
        state.pendingFit = false;
        state.lastCenteredCurrentId = state.lastCurrentId;
      }
    }
    physicsStep();
    draw();
    requestAnimationFrame(frame);
  }

  canvas.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    const n = pickNode(ev.offsetX, ev.offsetY);
    if (n) {
      state.selected = n;
      if (n.role !== "current") {
        state.dragNode = n;
        const w = worldFromScreen(ev.offsetX, ev.offsetY);
        n.fx = w.x;
        n.fy = w.y;
      }
      return;
    }
    state.panning = true;
    state.panStart = { x: ev.clientX, y: ev.clientY, cx: state.cam.x, cy: state.cam.y };
  });

  window.addEventListener("mousemove", (ev) => {
    if (state.dragNode) {
      const rect = canvas.getBoundingClientRect();
      const w = worldFromScreen(ev.clientX - rect.left, ev.clientY - rect.top);
      state.dragNode.fx = w.x;
      state.dragNode.fy = w.y;
      return;
    }
    if (!state.panning) return;
    state.cam.x = state.panStart.cx + (ev.clientX - state.panStart.x);
    state.cam.y = state.panStart.cy + (ev.clientY - state.panStart.y);
  });

  window.addEventListener("mouseup", () => {
    if (state.dragNode) {
      state.dragNode = null;
    }
    state.panning = false;
  });

  canvas.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const oldS = state.cam.s;
    const nextS = clamp(oldS * Math.exp(-ev.deltaY * 0.0015), 0.2, 4.0);
    const before = worldFromScreen(ev.offsetX, ev.offsetY);
    state.cam.s = nextS;
    state.cam.x = ev.offsetX - before.x * nextS;
    state.cam.y = ev.offsetY - before.y * nextS;
  }, { passive: false });

  canvas.addEventListener("click", (ev) => {
    state.selected = pickNode(ev.offsetX, ev.offsetY);
    const nid = state.selected && state.selected.nid ? Number(state.selected.nid) : 0;
    pycmd("AJPCForceGraph-selectNid:" + String(nid > 0 ? nid : 0));
  });

  canvas.addEventListener("dblclick", (ev) => {
    const n = pickNode(ev.offsetX, ev.offsetY);
    if (!n || !n.nid) return;
    pycmd("AJPCForceGraph-openEditor:" + String(n.nid));
  });

  canvas.addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    const n = pickNode(ev.offsetX, ev.offsetY);
    if (!n || !n.nid) return;
    state.selected = n;
    pycmd("AJPCForceGraph-contextNid:" + String(n.nid));
  });

  function setHighlight(payload) {
    const p = payload || {};
    const nids = Array.isArray(p.nids) ? p.nids : [];
    const bucket = String(p.bucket || "").trim().toLowerCase();
    state.highlight.nids = new Set(nids.map((x) => Number(x || 0)).filter((x) => x > 0));
    state.highlight.bucket = bucket;
    state.highlight.active = state.highlight.nids.size > 0 || !!bucket;
  }

  function selectNid(rawNid) {
    const nid = Number(rawNid || 0);
    if (!(nid > 0)) {
      state.selected = null;
      return;
    }
    let found = null;
    for (const n of state.nodes) {
      if (Number(n.nid || 0) === nid) {
        found = n;
        break;
      }
    }
    state.selected = found;
  }

  window.AJPCForceGraph = {
    setData(payload) {
      build(payload || {});
    },
    setBackground(color) {
      if (typeof color === "string" && color.trim()) {
        state.bg = color.trim();
      }
    },
    selectNid(nid) {
      selectNid(nid);
    },
    setHighlight(payload) {
      setHighlight(payload || {});
    },
    clearHighlight() {
      state.highlight = { nids: new Set(), bucket: "", active: false };
    },
  };

  if (window.__AJPC_FORCE_DATA) {
    window.AJPCForceGraph.setData(window.__AJPC_FORCE_DATA);
  }

  window.addEventListener("resize", resize);
  resize();
  frame();
})();
</script>
"""


class ForceGraphView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_open_editor: Callable[[int], None] | None = None
        self._on_select: Callable[[int], None] | None = None
        self._on_context_nid: Callable[[int], None] | None = None
        self._ready = False
        self._pending: dict[str, Any] = {"nodes": [], "edges": []}
        self.setMinimumHeight(160)
        self._view = AnkiWebView(parent=self, title="ajpc_force_graph")
        self._view.set_bridge_command(self._on_bridge, self)
        self._view.setStyleSheet("background: transparent;")
        try:
            self._view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        except Exception:
            pass
        self._view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._view)

        self._view.stdHtml(_GRAPH_HTML, context=self)

    def set_open_editor_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_open_editor = callback

    def set_select_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_select = callback

    def set_context_menu_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_context_nid = callback

    def set_data(self, payload: dict[str, Any]) -> None:
        self._pending = payload or {"nodes": [], "edges": []}
        self._push_payload()

    def set_background(self, color: str) -> None:
        c = str(color or "").strip() or "#1f1f1f"
        js_c = json.dumps(c, ensure_ascii=True)
        self._view.eval(
            "if (window.AJPCForceGraph) { window.AJPCForceGraph.setBackground("
            + js_c
            + "); }"
        )

    def highlight_nid(self, nid: int) -> None:
        try:
            n = int(nid)
        except Exception:
            n = 0
        if n <= 0:
            self.clear_highlight()
            return
        self._view.eval(
            "if (window.AJPCForceGraph) { window.AJPCForceGraph.setHighlight({nids:["
            + str(n)
            + "],bucket:''}); }"
        )

    def select_nid(self, nid: int) -> None:
        try:
            n = int(nid)
        except Exception:
            n = 0
        self._view.eval(
            "if (window.AJPCForceGraph) { window.AJPCForceGraph.selectNid("
            + str(n)
            + "); }"
        )

    def highlight_bucket(self, bucket: str) -> None:
        b = str(bucket or "").strip().lower()
        if not b:
            self.clear_highlight()
            return
        js_b = json.dumps(b, ensure_ascii=True)
        self._view.eval(
            "if (window.AJPCForceGraph) { window.AJPCForceGraph.setHighlight({nids:[],bucket:"
            + js_b
            + "}); }"
        )

    def clear_highlight(self) -> None:
        self._view.eval(
            "if (window.AJPCForceGraph) { window.AJPCForceGraph.clearHighlight(); }"
        )

    def _push_payload(self) -> None:
        try:
            data = json.dumps(self._pending or {}, ensure_ascii=False)
            data_js_str = json.dumps(data, ensure_ascii=True)
        except Exception:
            data_js_str = json.dumps("{}", ensure_ascii=True)
        self._view.eval(
            "window.__AJPC_FORCE_DATA = JSON.parse("
            + data_js_str
            + ");"
            "if (window.AJPCForceGraph) { "
            "window.AJPCForceGraph.setData(window.__AJPC_FORCE_DATA); }"
        )

    def _on_bridge(self, cmd: str):
        if not isinstance(cmd, str):
            return None
        if cmd == "domDone":
            self._ready = True
            self._push_payload()
            return None
        if cmd.startswith("AJPCForceGraph-openEditor:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit():
                nid = int(raw)
                if callable(self._on_open_editor):
                    self._on_open_editor(nid)
                else:
                    open_note_editor(nid, title="AJpC Note Editor")
            return None
        if cmd.startswith("AJPCForceGraph-selectNid:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit() and callable(self._on_select):
                self._on_select(int(raw))
            return None
        if cmd.startswith("AJPCForceGraph-contextNid:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit() and callable(self._on_context_nid):
                self._on_context_nid(int(raw))
        return None
