from __future__ import annotations

import json
from typing import Any, Callable

from aqt.qt import QColor, Qt, QVBoxLayout, QWidget
from aqt.webview import AnkiWebView

from ._note_editor import open_note_editor


_HTML = r"""
<style>
html, body {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: transparent;
}
#ajpc-prio-root {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: transparent;
}
#ajpc-prio-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
<div id="ajpc-prio-root">
  <canvas id="ajpc-prio-canvas"></canvas>
</div>
<script>
(function () {
  const canvas = document.getElementById("ajpc-prio-canvas");
  const ctx = canvas.getContext("2d");
  const state = {
    nodes: [],
    edges: [],
    byId: new Map(),
    boxes: new Map(),
    bg: "transparent",
    currentNid: 0,
    currentId: "",
    selectedId: "",
    view: { x: 0, y: 0 },
    pan: { active: false, sx: 0, sy: 0, ox: 0, oy: 0, moved: false },
    neededHeight: 0,
    lastNeededSent: -1,
    ready: false,
  };

  function postNeededHeight(value) {
    const v = Math.max(0, Math.round(Number(value || 0)));
    if (v === state.lastNeededSent) return;
    state.lastNeededSent = v;
    pycmd("AJPCPrioChain-neededHeight:" + String(v));
  }

  function resize() {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function wrapText(text, maxW, maxLines) {
    const chars = Array.from(String(text || "Node"));
    const lines = [];
    let cur = "";
    for (const ch of chars) {
      const next = cur + ch;
      if (ctx.measureText(next).width <= maxW || cur.length === 0) {
        cur = next;
      } else {
        lines.push(cur);
        cur = ch;
        if (lines.length >= maxLines) break;
      }
    }
    if (cur && lines.length < maxLines) lines.push(cur);
    if (lines.length >= maxLines && chars.length > 0) {
      lines[maxLines - 1] = lines[maxLines - 1].slice(0, Math.max(1, lines[maxLines - 1].length - 3)) + "...";
    }
    return lines.length ? lines : ["Node"];
  }

  function build(payload) {
    state.nodes = [];
    state.edges = [];
    state.byId = new Map();
    state.currentNid = Number((payload && payload.current_nid) || 0);
    state.currentId = "";

    const pNodes = (payload && payload.nodes) || [];
    const pEdges = (payload && payload.edges) || [];
    for (const n of pNodes) {
      const id = String(n.id || "");
      if (!id) continue;
      const node = {
        id,
        nid: Number(n.nid || 0),
        label: String(n.label || "Node"),
        color: String(n.color || "#3d95e7"),
        x: 0,
        y: 0,
      };
      state.nodes.push(node);
      state.byId.set(id, node);
    }
    if (state.currentNid > 0) {
      const maybe = "n" + String(state.currentNid);
      if (state.byId.has(maybe)) state.currentId = maybe;
    }
    if (!state.currentId && payload && payload.current_id) {
      const maybe = String(payload.current_id || "");
      if (maybe && state.byId.has(maybe)) state.currentId = maybe;
    }
    if (!state.currentId && state.nodes.length) {
      state.currentId = String(state.nodes[0].id || "");
    }
    if (!state.selectedId || !state.byId.has(state.selectedId)) {
      state.selectedId = "";
    }
    state.view.x = 0;
    state.view.y = 0;
    state.pan.active = false;
    state.pan.moved = false;
    canvas.style.cursor = "default";

    for (const e of pEdges) {
      const s = state.byId.get(String(e.source || ""));
      const t = state.byId.get(String(e.target || ""));
      if (!s || !t) continue;
      state.edges.push({ source: s, target: t });
    }
    layout();
  }

  function layout() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w < 2 || h < 2 || !state.nodes.length) {
      state.boxes = new Map();
      state.neededHeight = state.nodes.length ? 96 : 0;
      postNeededHeight(state.neededHeight);
      return;
    }

    const preds = new Map();
    const outs = new Map();
    for (const n of state.nodes) {
      preds.set(n.id, []);
      outs.set(n.id, []);
    }
    for (const e of state.edges) {
      outs.get(e.source.id).push(e.target.id);
      preds.get(e.target.id).push(e.source.id);
    }

    let rootId = String(state.currentId || "");
    if (!rootId || !state.byId.has(rootId)) {
      rootId = String(state.nodes[0].id || "");
    }

    const depth = new Map();
    depth.set(rootId, 0);

    const ancQueue = [rootId];
    while (ancQueue.length) {
      const id = ancQueue.shift();
      const d = depth.get(id) || 0;
      for (const p of (preds.get(id) || [])) {
        const nd = d - 1;
        if (!depth.has(p) || nd < (depth.get(p) || 0)) {
          depth.set(p, nd);
          ancQueue.push(p);
        }
      }
    }

    const depQueue = [rootId];
    while (depQueue.length) {
      const id = depQueue.shift();
      const d = depth.get(id) || 0;
      for (const c of (outs.get(id) || [])) {
        const nd = d + 1;
        if (!depth.has(c) || nd > (depth.get(c) || 0)) {
          depth.set(c, nd);
          depQueue.push(c);
        }
      }
    }

    const levels = new Map();
    let minDepth = 0;
    let maxDepth = 0;
    for (const n of state.nodes) {
      const d = depth.has(n.id) ? Number(depth.get(n.id) || 0) : 0;
      n.depth = d;
      minDepth = Math.min(minDepth, d);
      maxDepth = Math.max(maxDepth, d);
      if (!levels.has(d)) levels.set(d, []);
      levels.get(d).push(n);
    }

    const depthKeys = Array.from(levels.keys()).sort((a, b) => a - b);
    const orderByLevel = new Map();
    function resetLevelOrder(depthKey) {
      const list = levels.get(depthKey) || [];
      list.sort((a, b) => String(a.label).localeCompare(String(b.label)));
      const om = new Map();
      for (let i = 0; i < list.length; i++) om.set(list[i].id, i);
      orderByLevel.set(depthKey, om);
    }
    for (const d of depthKeys) resetLevelOrder(d);

    function neighborBary(nodeId, neighborDepth) {
      const ids = [];
      for (const p of (preds.get(nodeId) || [])) {
        if ((depth.get(p) || 0) === neighborDepth) ids.push(p);
      }
      for (const c of (outs.get(nodeId) || [])) {
        if ((depth.get(c) || 0) === neighborDepth) ids.push(c);
      }
      const om = orderByLevel.get(neighborDepth) || new Map();
      const vals = ids.map((id) => om.has(id) ? om.get(id) : null).filter((v) => v !== null);
      if (!vals.length) return null;
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    }

    for (let pass = 0; pass < 6; pass++) {
      for (let i = 1; i < depthKeys.length; i++) {
        const d = depthKeys[i];
        const prev = depthKeys[i - 1];
        const list = levels.get(d) || [];
        const curOrder = orderByLevel.get(d) || new Map();
        list.sort((a, b) => {
          const ba = neighborBary(a.id, prev);
          const bb = neighborBary(b.id, prev);
          const fa = ba === null ? (curOrder.get(a.id) || 0) : ba;
          const fb = bb === null ? (curOrder.get(b.id) || 0) : bb;
          if (fa !== fb) return fa - fb;
          return String(a.label).localeCompare(String(b.label));
        });
        const om = new Map();
        for (let i = 0; i < list.length; i++) om.set(list[i].id, i);
        orderByLevel.set(d, om);
      }
      for (let i = depthKeys.length - 2; i >= 0; i--) {
        const d = depthKeys[i];
        const nxt = depthKeys[i + 1];
        const list = levels.get(d) || [];
        const curOrder = orderByLevel.get(d) || new Map();
        list.sort((a, b) => {
          const ba = neighborBary(a.id, nxt);
          const bb = neighborBary(b.id, nxt);
          const fa = ba === null ? (curOrder.get(a.id) || 0) : ba;
          const fb = bb === null ? (curOrder.get(b.id) || 0) : bb;
          if (fa !== fb) return fa - fb;
          return String(a.label).localeCompare(String(b.label));
        });
        const om = new Map();
        for (let i = 0; i < list.length; i++) om.set(list[i].id, i);
        orderByLevel.set(d, om);
      }
    }

    const marginX = 36;
    const marginY = 44;
    const usableH = Math.max(10, h - marginY * 2);
    const padX = 7;
    const padY = 5;
    const lineH = 12;
    const singleLineNodeH = Math.ceil(lineH + (padY * 2));
    const maxLines = 2;
    const offsetFactor = 0.20;
    state.boxes = new Map();
    ctx.font = "11px sans-serif";
    const rowLayouts = [];

    function _measureRawWidth(label) {
      const txt = String(label || "Node");
      return Math.max(48, Math.ceil(ctx.measureText(txt).width + (padX * 2)));
    }

    for (let row = 0; row < depthKeys.length; row++) {
      const d = depthKeys[row];
      const list = levels.get(d) || [];
      const n = list.length;
      const usableW = Math.max(10, w - marginX * 2);
      const minGap = n > 1 ? singleLineNodeH : 0;
      const laneGapBase = singleLineNodeH;

      const measured = list.map((node) => ({ node: node, rawW: _measureRawWidth(node.label) }));

      function _packGreedy(items) {
        const lanes = [];
        let lane = [];
        let laneContentW = 0;
        for (const item of items) {
          const nextContentW = lane.length > 0 ? (laneContentW + minGap + item.rawW) : item.rawW;
          const nextWithOffset = Math.ceil(nextContentW * (1 + offsetFactor));
          if (lane.length > 0 && nextWithOffset > usableW) {
            lanes.push(lane);
            lane = [item];
            laneContentW = item.rawW;
          } else {
            lane.push(item);
            laneContentW = nextContentW;
          }
        }
        if (lane.length > 0) lanes.push(lane);
        return lanes;
      }

      const packed = _packGreedy(measured);
      const cols = Math.max(1, packed.reduce((mx, ln) => Math.max(mx, ln.length), 0));
      const colW = usableW / Math.max(1, cols);
      const maxLabelW = Math.max(24, Math.floor((colW * 0.84) - (padX * 2)));

      function _buildLaneBoxes(items) {
        const out = [];
        for (const item of items) {
          const lines = wrapText(item.node.label, maxLabelW, maxLines);
          let textW = 0;
          for (const line of lines) {
            textW = Math.max(textW, ctx.measureText(line).width);
          }
          const capW = Math.max(48, Math.floor(colW * 0.95));
          const boxW = Math.max(48, Math.min(capW, Math.ceil(textW + (padX * 2))));
          const boxH = Math.max(22, Math.ceil(lines.length * lineH + (padY * 2)));
          out.push({ node: item.node, lines: lines, w: boxW, h: boxH });
        }
        return out;
      }

      const lanes = packed.map((ln) => _buildLaneBoxes(ln));
      const laneGap = lanes.length > 1 ? Math.max(6, Math.floor(laneGapBase * 0.7)) : laneGapBase;
      const laneHeights = lanes.map((ln) => ln.reduce((mh, b) => Math.max(mh, b.h), 22));
      const totalLaneH = laneHeights.reduce((acc, v) => acc + v, 0) + (laneGap * Math.max(0, lanes.length - 1));

      rowLayouts.push({
        depth: d,
        lanes: lanes,
        laneHeights: laneHeights,
        totalLaneH: totalLaneH,
        usableW: usableW,
        minGap: minGap,
        laneGap: laneGap,
        cols: cols,
        colW: colW,
        offsetStep: colW * offsetFactor,
      });
    }

    const rowCount = rowLayouts.length;
    if (rowCount <= 0) return;
    const minRowGap = singleLineNodeH;
    const totalRowsH = rowLayouts.reduce((acc, r) => acc + Number(r.totalLaneH || 0), 0);
    const levelGapBonus = rowCount > 1 ? Math.max(2, Math.floor(minRowGap * 0.2)) : 0;
    const baseLevelGap = minRowGap + levelGapBonus;
    const requiredMin = totalRowsH + (baseLevelGap * Math.max(0, rowCount - 1)) + (marginY * 2);
    state.neededHeight = Math.max(96, Math.ceil(requiredMin));
    postNeededHeight(state.neededHeight);

    let rowGap = baseLevelGap;
    if (rowCount > 1) {
      const compactMin = totalRowsH + (baseLevelGap * (rowCount - 1));
      if (compactMin <= usableH) {
        rowGap = baseLevelGap + ((usableH - compactMin) / (rowCount - 1));
      }
    }

    const totalPackedH = totalRowsH + (rowGap * Math.max(0, rowCount - 1));
    let yCursor = marginY;
    if (totalPackedH < usableH) {
      yCursor = marginY + ((usableH - totalPackedH) * 0.5);
    }

    for (const rowLayout of rowLayouts) {
      let yTop = yCursor;
      const lanes = rowLayout.lanes || [];
      const laneHeights = rowLayout.laneHeights || [];
      const laneGap = Number(rowLayout.laneGap || minRowGap);
      const rowUsableW = Number(rowLayout.usableW || Math.max(10, w - marginX * 2));
      const rowMinGap = Number(rowLayout.minGap || minRowGap);
      const cols = Math.max(1, Number(rowLayout.cols || 1));
      const colW = Number(rowLayout.colW || (rowUsableW / cols));

      for (let li = 0; li < lanes.length; li++) {
        const lane = lanes[li] || [];
        const m = lane.length;
        if (m <= 0) {
          yTop += Number(laneHeights[li] || 22) + laneGap;
          continue;
        }

        const laneH = Number(laneHeights[li] || 22);
        const laneY = yTop + (laneH * 0.5);
        const startCol = (cols - m) * 0.5;

        const baseCenters = [];
        let laneLeft = Number.POSITIVE_INFINITY;
        let laneRight = Number.NEGATIVE_INFINITY;
        for (let i = 0; i < m; i++) {
          const slot = startCol + i;
          const cxBase = marginX + ((slot + 0.5) * colW);
          baseCenters.push(cxBase);
          const bw = Number(lane[i].w || 48);
          laneLeft = Math.min(laneLeft, cxBase - (bw * 0.5));
          laneRight = Math.max(laneRight, cxBase + (bw * 0.5));
        }

        let laneShift = 0;
        if (lanes.length > 1) {
          const sign = (li % 2 === 0) ? 1 : -1; // +,-,+,-
          const mul = Math.floor(li / 2) + 1;
          laneShift = sign * mul * Number(rowLayout.offsetStep || (colW * offsetFactor));
          const minShift = marginX - laneLeft;
          const maxShift = (marginX + rowUsableW) - laneRight;
          if (laneShift < minShift) laneShift = minShift;
          if (laneShift > maxShift) laneShift = maxShift;
        }

        let prevRight = Number.NEGATIVE_INFINITY;
        for (let i = 0; i < m; i++) {
          const b = lane[i];
          const bw = Number(b.w || 48);
          const bh = Number(b.h || 22);
          const cx = baseCenters[i] + laneShift;

          let bx = Math.round(cx - (bw * 0.5));
          if (bx < (prevRight + rowMinGap)) {
            bx = Math.round(prevRight + rowMinGap);
          }
          const minX = Math.round(marginX);
          const maxX = Math.round(marginX + rowUsableW - bw);
          if (bx < minX) bx = minX;
          if (bx > maxX) bx = maxX;

          const by = Math.round(laneY - (bh * 0.5));
          b.node.x = bx + (bw * 0.5);
          b.node.y = laneY;
          state.boxes.set(b.node.id, { x: bx, y: by, w: bw, h: bh, lines: b.lines });
          prevRight = bx + bw;
        }

        yTop += laneH + laneGap;
      }
      yCursor += Number(rowLayout.totalLaneH || 0) + rowGap;
    }
  }
  function pickNode(px, py) {
    const wx = Number(px || 0) - Number(state.view.x || 0);
    const wy = Number(py || 0) - Number(state.view.y || 0);
    for (let i = state.nodes.length - 1; i >= 0; i--) {
      const n = state.nodes[i];
      const b = state.boxes.get(n.id);
      if (!b) continue;
      if (wx >= b.x && wx <= (b.x + b.w) && wy >= b.y && wy <= (b.y + b.h)) {
        return n;
      }
    }
    return null;
  }

  function draw() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w < 2 || h < 2) return;
    ctx.clearRect(0, 0, w, h);
    const bg = String(state.bg || "").trim().toLowerCase();
    if (bg && bg !== "transparent") {
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
    }

    if (!state.nodes.length) {
      ctx.fillStyle = "#9a9a9a";
      ctx.font = "12px sans-serif";
      ctx.fillText("No priority chains", 12, 20);
      return;
    }

    if (!state.boxes || state.boxes.size !== state.nodes.length) {
      layout();
    }
    const padX = 7;
    const padY = 5;
    const lineH = 12;
    const vx = Number(state.view.x || 0);
    const vy = Number(state.view.y || 0);
    const now = performance.now();

    ctx.save();
    ctx.translate(vx, vy);

    function edgePoints(srcBox, dstBox) {
      if (!srcBox || !dstBox) return null;
      if ((srcBox.y + srcBox.h * 0.5) <= (dstBox.y + dstBox.h * 0.5)) {
        return {
          x1: srcBox.x + srcBox.w * 0.5,
          y1: srcBox.y + srcBox.h,
          x2: dstBox.x + dstBox.w * 0.5,
          y2: dstBox.y,
        };
      }
      return {
        x1: srcBox.x + srcBox.w * 0.5,
        y1: srcBox.y,
        x2: dstBox.x + dstBox.w * 0.5,
        y2: dstBox.y + dstBox.h,
      };
    }

    ctx.lineWidth = 1.3;

    function pointInRect(px, py, r) {
      return px >= r.x && px <= (r.x + r.w) && py >= r.y && py <= (r.y + r.h);
    }

    function segmentsIntersect(a, b, c, d) {
      function orient(p, q, r) {
        return (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
      }
      function onSeg(p, q, r) {
        return (
          Math.min(p.x, r.x) <= q.x && q.x <= Math.max(p.x, r.x) &&
          Math.min(p.y, r.y) <= q.y && q.y <= Math.max(p.y, r.y)
        );
      }
      const o1 = orient(a, b, c);
      const o2 = orient(a, b, d);
      const o3 = orient(c, d, a);
      const o4 = orient(c, d, b);
      if ((o1 === 0 && onSeg(a, c, b)) || (o2 === 0 && onSeg(a, d, b)) || (o3 === 0 && onSeg(c, a, d)) || (o4 === 0 && onSeg(c, b, d))) {
        return true;
      }
      return ((o1 > 0) !== (o2 > 0)) && ((o3 > 0) !== (o4 > 0));
    }

    function segmentIntersectsRect(x1, y1, x2, y2, box, pad) {
      const p = Math.max(0, Number(pad || 0));
      const r = {
        x: Number(box.x || 0) - p,
        y: Number(box.y || 0) - p,
        w: Number(box.w || 0) + (p * 2),
        h: Number(box.h || 0) + (p * 2),
      };
      if (pointInRect(x1, y1, r) || pointInRect(x2, y2, r)) return true;
      const a = { x: x1, y: y1 };
      const b = { x: x2, y: y2 };
      const e1 = [{ x: r.x, y: r.y }, { x: r.x + r.w, y: r.y }];
      const e2 = [{ x: r.x + r.w, y: r.y }, { x: r.x + r.w, y: r.y + r.h }];
      const e3 = [{ x: r.x + r.w, y: r.y + r.h }, { x: r.x, y: r.y + r.h }];
      const e4 = [{ x: r.x, y: r.y + r.h }, { x: r.x, y: r.y }];
      return (
        segmentsIntersect(a, b, e1[0], e1[1]) ||
        segmentsIntersect(a, b, e2[0], e2[1]) ||
        segmentsIntersect(a, b, e3[0], e3[1]) ||
        segmentsIntersect(a, b, e4[0], e4[1])
      );
    }

    function pathIntersectsAnyBox(points, sourceId, targetId) {
      if (!points || points.length < 2) return false;
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1];
        const b = points[i];
        for (const n of state.nodes) {
          const nid = String(n.id || "");
          if (!nid || nid === sourceId || nid === targetId) continue;
          const box = state.boxes.get(nid);
          if (!box) continue;
          if (segmentIntersectsRect(a.x, a.y, b.x, b.y, box, 2)) return true;
        }
      }
      return false;
    }

    function drawRoundedOrthPath(points, radius) {
      if (!points || points.length < 2) return;
      const rr = Math.max(0, Number(radius || 0));
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length - 1; i++) {
        const p0 = points[i - 1];
        const p1 = points[i];
        const p2 = points[i + 1];
        const v1x = p1.x - p0.x;
        const v1y = p1.y - p0.y;
        const v2x = p2.x - p1.x;
        const v2y = p2.y - p1.y;
        const l1 = Math.hypot(v1x, v1y);
        const l2 = Math.hypot(v2x, v2y);
        if (l1 < 1 || l2 < 1 || rr <= 0) {
          ctx.lineTo(p1.x, p1.y);
          continue;
        }
        const r = Math.min(rr, l1 * 0.45, l2 * 0.45);
        const ux1 = v1x / l1;
        const uy1 = v1y / l1;
        const ux2 = v2x / l2;
        const uy2 = v2y / l2;
        const ax = p1.x - (ux1 * r);
        const ay = p1.y - (uy1 * r);
        const bx = p1.x + (ux2 * r);
        const by = p1.y + (uy2 * r);
        ctx.lineTo(ax, ay);
        ctx.quadraticCurveTo(p1.x, p1.y, bx, by);
      }
      const last = points[points.length - 1];
      ctx.lineTo(last.x, last.y);
      ctx.stroke();
    }

    const outMap = new Map();
    const inMap = new Map();
    for (const e of state.edges) {
      if (!outMap.has(e.source.id)) outMap.set(e.source.id, []);
      if (!inMap.has(e.target.id)) inMap.set(e.target.id, []);
      outMap.get(e.source.id).push(e);
      inMap.get(e.target.id).push(e);
    }

    for (const [sid, arr] of outMap.entries()) {
      arr.sort((a, b) => {
        const ax = (state.boxes.get(a.target.id) || { x: 0 }).x;
        const bx = (state.boxes.get(b.target.id) || { x: 0 }).x;
        return ax - bx;
      });
    }

    let minBoxX = Number.POSITIVE_INFINITY;
    let maxBoxX = Number.NEGATIVE_INFINITY;
    for (const n of state.nodes) {
      const b = state.boxes.get(n.id);
      if (!b) continue;
      minBoxX = Math.min(minBoxX, Number(b.x || 0));
      maxBoxX = Math.max(maxBoxX, Number(b.x || 0) + Number(b.w || 0));
    }
    if (!Number.isFinite(minBoxX) || !Number.isFinite(maxBoxX)) {
      minBoxX = 0;
      maxBoxX = w;
    }

    let detourRight = 0;
    let detourLeft = 0;

    const sourceMeta = new Map();
    for (const [sid, arr] of outMap.entries()) {
      const sBox = state.boxes.get(sid);
      if (!sBox) continue;
      let sumTy = 0;
      let count = 0;
      for (const e of arr) {
        const tBox = state.boxes.get(e.target.id);
        if (!tBox) continue;
        const tCy = Number(tBox.y || 0) + (Number(tBox.h || 0) * 0.5);
        sumTy += tCy;
        count += 1;
      }
      const sCy = Number(sBox.y || 0) + (Number(sBox.h || 0) * 0.5);
      const dir = count > 0 && (sumTy / count) < sCy ? -1 : 1;
      const sx = Number(sBox.x || 0) + (Number(sBox.w || 0) * 0.5);
      const sy = dir > 0 ? (Number(sBox.y || 0) + Number(sBox.h || 0)) : Number(sBox.y || 0);
      const stub = 12;
      const forkY = sy + (dir * stub);
      sourceMeta.set(sid, { sx: sx, sy: sy, dir: dir, stub: stub, forkY: forkY, outCount: Math.max(0, arr.length) });
    }
    const forkPoints = [];
    for (const meta of sourceMeta.values()) {
      if (Number(meta.outCount || 0) > 1) {
        forkPoints.push({ x: Number(meta.sx || 0), y: Number(meta.forkY || 0) });
      }
    }

    const routes = [];
    for (const e of state.edges) {
      const sourceId = String(e.source.id || "");
      const targetId = String(e.target.id || "");
      const sBox = state.boxes.get(sourceId);
      const tBox = state.boxes.get(e.target.id);
      const pts = edgePoints(sBox, tBox);
      if (!pts) continue;

      const meta = sourceMeta.get(sourceId);
      const sx = meta ? Number(meta.sx) : Number(pts.x1);
      const sy = meta ? Number(meta.sy) : Number(pts.y1);
      const dir = meta ? Number(meta.dir) : ((pts.y2 >= pts.y1) ? 1 : -1);
      const stub = meta ? Number(meta.stub) : 12;
      const forkY = meta ? Number(meta.forkY) : (sy + (dir * stub));

      const tx = Number(pts.x2);
      const ty = Number(pts.y2);
      const targetPreY = ty - (dir * stub);

      const p0 = { x: sx, y: sy };
      const p1 = { x: sx, y: forkY };
      const p2 = { x: tx, y: forkY };
      const p3 = { x: tx, y: targetPreY };
      const p4 = { x: tx, y: ty };
      let path = [p0, p1, p2, p3, p4];

      if (pathIntersectsAnyBox(path, sourceId, targetId)) {
        const centerX = (sx + tx) * 0.5;
        const graphCenterX = (minBoxX + maxBoxX) * 0.5;
        let side = centerX >= graphCenterX ? 1 : -1;

        let detourX;
        if (side > 0) {
          detourX = maxBoxX + 16 + (detourRight * 10);
          detourRight += 1;
        } else {
          detourX = minBoxX - 16 - (detourLeft * 10);
          detourLeft += 1;
        }

        const pA = { x: detourX, y: p1.y };
        const pB = { x: detourX, y: p3.y };
        const detourPath = [p0, p1, pA, pB, p3, p4];
        if (!pathIntersectsAnyBox(detourPath, sourceId, targetId)) {
          path = detourPath;
        } else {
          side = -side;
          if (side > 0) {
            detourX = maxBoxX + 16 + (detourRight * 10);
            detourRight += 1;
          } else {
            detourX = minBoxX - 16 - (detourLeft * 10);
            detourLeft += 1;
          }
          path = [p0, p1, { x: detourX, y: p1.y }, { x: detourX, y: p3.y }, p3, p4];
        }
      }

      routes.push({
        sourceId: sourceId,
        targetId: targetId,
        dir: dir,
        path: path,
      });
    }

    ctx.strokeStyle = "#3d95e7";
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    const trunkDrawn = new Set();
    for (const route of routes) {
      const sid = String(route.sourceId || "");
      if (!sid || trunkDrawn.has(sid)) continue;
      const path = route.path || [];
      if (path.length < 2) continue;
      const meta = sourceMeta.get(sid);
      if (meta && Number(meta.outCount || 0) > 1) {
        const trunk = [path[0], path[1]];
        drawRoundedOrthPath(trunk, 7);
        trunkDrawn.add(sid);
      }
    }

    for (const route of routes) {
      const full = route.path || [];
      if (full.length < 2) continue;
      const meta = sourceMeta.get(String(route.sourceId || ""));
      const sharedSource = !!(meta && Number(meta.outCount || 0) > 1);
      const branch = (sharedSource && full.length > 2) ? full.slice(1) : full;
      if (sharedSource) {
        const branchDir = Number(route.dir || 1);
        const entryLen = 8;
        const start = branch[0];
        const synthetic = { x: Number(start.x || 0), y: Number(start.y || 0) - (branchDir * entryLen) };
        const branchWithEntry = [synthetic].concat(branch);
        drawRoundedOrthPath(branchWithEntry, 7);
      } else {
        drawRoundedOrthPath(branch, 7);
      }

      let tail = branch[branch.length - 2];
      const head = branch[branch.length - 1];
      let ti = branch.length - 2;
      while (ti > 0 && Math.hypot(head.x - tail.x, head.y - tail.y) < 1) {
        ti -= 1;
        tail = branch[ti];
      }
      const dx = head.x - tail.x;
      const dy = head.y - tail.y;
      const len = Math.hypot(dx, dy);
      if (len < 1) continue;
      const ux = dx / len;
      const uy = dy / len;
      const headLen = 7;
      const headW = 4;
      const bx = head.x - (ux * headLen);
      const by = head.y - (uy * headLen);
      const lx = bx - (uy * headW);
      const ly = by + (ux * headW);
      const rx = bx + (uy * headW);
      const ry = by - (ux * headW);
      ctx.fillStyle = "#3d95e7";
      ctx.beginPath();
      ctx.moveTo(head.x, head.y);
      ctx.lineTo(lx, ly);
      ctx.lineTo(rx, ry);
      ctx.closePath();
      ctx.fill();
    }

    // Fill fork joints so split points do not look spiky at T-intersections.
    const joinR = Math.max(1.4, ctx.lineWidth * 0.8);
    ctx.fillStyle = "#3d95e7";
    for (const fp of forkPoints) {
      ctx.beginPath();
      ctx.arc(Number(fp.x || 0), Number(fp.y || 0), joinR, 0, Math.PI * 2);
      ctx.fill();
    }
    function roundRect(x, y, w, h, r) {
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

    for (const n of state.nodes) {
      const b = state.boxes.get(n.id);
      if (!b) continue;
      const c = String(n.color || "#3d95e7");
      ctx.globalAlpha = 0.24;
      ctx.fillStyle = c;
      roundRect(b.x, b.y, b.w, b.h, 7);
      ctx.fill();
      ctx.globalAlpha = 1.0;
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.4;
      roundRect(b.x, b.y, b.w, b.h, 7);
      ctx.stroke();
      if (state.currentId && n.id === state.currentId) {
        const phase = (Math.sin(now * 0.006) + 1) * 0.5;
        const grow = 2 + (phase * 6);
        ctx.globalAlpha = 0.40;
        ctx.strokeStyle = c;
        ctx.lineWidth = 1.8;
        roundRect(
          b.x - grow,
          b.y - grow,
          b.w + (grow * 2),
          b.h + (grow * 2),
          8 + (grow * 0.35),
        );
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      }
      if (state.selectedId && n.id === state.selectedId) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.8;
        roundRect(b.x - 2.2, b.y - 2.2, b.w + 4.4, b.h + 4.4, 8);
        ctx.stroke();
      }

      ctx.fillStyle = "#f2f2f2";
      const lines = b.lines || [];
      for (let li = 0; li < lines.length; li++) {
        ctx.fillText(lines[li], b.x + padX, b.y + padY + 10 + (li * lineH));
      }
    }
    ctx.restore();
  }

  canvas.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    const hit = pickNode(ev.offsetX, ev.offsetY);
    if (hit) return;
    state.pan.active = true;
    state.pan.sx = Number(ev.clientX || 0);
    state.pan.sy = Number(ev.clientY || 0);
    state.pan.ox = Number(state.view.x || 0);
    state.pan.oy = Number(state.view.y || 0);
    state.pan.moved = false;
    canvas.style.cursor = "grabbing";
  });

  window.addEventListener("mousemove", (ev) => {
    if (!state.pan.active) return;
    const dx = Number(ev.clientX || 0) - state.pan.sx;
    const dy = Number(ev.clientY || 0) - state.pan.sy;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
      state.pan.moved = true;
    }
    state.view.x = state.pan.ox + dx;
    state.view.y = state.pan.oy + dy;
    draw();
  });

  window.addEventListener("mouseup", () => {
    if (!state.pan.active) return;
    state.pan.active = false;
    canvas.style.cursor = "default";
  });

  canvas.addEventListener("dblclick", (ev) => {
    const n = pickNode(ev.offsetX, ev.offsetY);
    if (!n || !n.nid) return;
    pycmd("AJPCPrioChain-openEditor:" + String(n.nid));
  });

  canvas.addEventListener("click", (ev) => {
    if (state.pan.moved) {
      state.pan.moved = false;
      return;
    }
    const n = pickNode(ev.offsetX, ev.offsetY);
    if (n && n.id) {
      state.selectedId = String(n.id);
      pycmd("AJPCPrioChain-selectNid:" + String(Number(n.nid || 0)));
      draw();
      return;
    }
    state.selectedId = "";
    pycmd("AJPCPrioChain-selectNid:0");
    draw();
  });

  window.addEventListener("resize", () => {
    resize();
    layout();
    draw();
  });

  function frame() {
    draw();
    requestAnimationFrame(frame);
  }

  window.AJPCPrioChain = {
    setData(payload) {
      build(payload || {});
      draw();
    },
    setBackground(color) {
      if (typeof color === "string" && color.trim()) {
        state.bg = color.trim();
      }
      draw();
    },
    selectNid(nid) {
      const n = Number(nid || 0);
      if (!(n > 0)) {
        state.selectedId = "";
        draw();
        return;
      }
      const key = "n" + String(n);
      state.selectedId = state.byId.has(key) ? key : "";
      draw();
    },
  };

  if (window.__AJPC_PRIO_DATA) {
    window.AJPCPrioChain.setData(window.__AJPC_PRIO_DATA);
  }

  resize();
  frame();
})();
</script>
"""


class PrioChainView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_open_editor: Callable[[int], None] | None = None
        self._on_select: Callable[[int], None] | None = None
        self._on_needed_height: Callable[[int], None] | None = None
        self._pending: dict[str, Any] = {"nodes": [], "edges": []}
        self.setMinimumHeight(130)
        self._view = AnkiWebView(parent=self, title="ajpc_prio_chain")
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

        self._view.stdHtml(_HTML, context=self)

    def set_open_editor_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_open_editor = callback

    def set_select_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_select = callback

    def set_needed_height_handler(self, callback: Callable[[int], None] | None) -> None:
        self._on_needed_height = callback

    def set_data(self, payload: dict[str, Any]) -> None:
        self._pending = payload or {"nodes": [], "edges": []}
        self._push()

    def set_background(self, color: str) -> None:
        c = str(color or "").strip() or "#1f1f1f"
        js_c = json.dumps(c, ensure_ascii=True)
        self._view.eval(
            "if (window.AJPCPrioChain) { window.AJPCPrioChain.setBackground("
            + js_c
            + "); }"
        )

    def select_nid(self, nid: int) -> None:
        try:
            n = int(nid)
        except Exception:
            n = 0
        self._view.eval(
            "if (window.AJPCPrioChain) { window.AJPCPrioChain.selectNid("
            + str(n)
            + "); }"
        )

    def _push(self) -> None:
        try:
            data = json.dumps(self._pending or {}, ensure_ascii=False)
            data_js = json.dumps(data, ensure_ascii=True)
        except Exception:
            data_js = json.dumps("{}", ensure_ascii=True)
        self._view.eval(
            "window.__AJPC_PRIO_DATA = JSON.parse(" + data_js + ");"
            "if (window.AJPCPrioChain) { window.AJPCPrioChain.setData(window.__AJPC_PRIO_DATA); }"
        )

    def _on_bridge(self, cmd: str):
        if not isinstance(cmd, str):
            return None
        if cmd == "domDone":
            self._push()
            return None
        if cmd.startswith("AJPCPrioChain-openEditor:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit():
                nid = int(raw)
                if callable(self._on_open_editor):
                    self._on_open_editor(nid)
                else:
                    open_note_editor(nid, title="AJpC Note Editor")
            return None
        if cmd.startswith("AJPCPrioChain-selectNid:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit() and callable(self._on_select):
                self._on_select(int(raw))
            return None
        if cmd.startswith("AJPCPrioChain-neededHeight:"):
            raw = cmd.split(":", 1)[1].strip()
            if raw.isdigit() and callable(self._on_needed_height):
                self._on_needed_height(int(raw))
        return None
