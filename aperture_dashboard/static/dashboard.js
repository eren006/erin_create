(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  let currentRange = "90d";
  let loading = false;

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function fmtCompact(n, prefix) {
    prefix = prefix || "";
    const abs = Math.abs(n);
    if (abs >= 1e6) return prefix + (n / 1e6).toFixed(1) + "M";
    if (abs >= 1e3) return prefix + (n / 1e3).toFixed(1) + "K";
    return prefix + Math.round(n).toLocaleString();
  }

  function fmtMoney(n) {
    return "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(iso) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function niceMax(v) {
    if (v <= 0) return 10;
    const mag = Math.pow(10, Math.floor(Math.log10(v)));
    const norm = v / mag;
    let step;
    if (norm <= 1) step = 1;
    else if (norm <= 2) step = 2;
    else if (norm <= 5) step = 5;
    else step = 10;
    return step * mag;
  }

  // ---------------------------------------------------------------------
  // Tooltip (one shared element per chart-wrap)
  // ---------------------------------------------------------------------

  function ensureTooltip(wrap) {
    let tt = wrap.querySelector(".viz-tooltip");
    if (!tt) {
      tt = document.createElement("div");
      tt.className = "viz-tooltip";
      wrap.appendChild(tt);
    }
    return tt;
  }

  function showTooltip(wrap, x, y, html) {
    const tt = ensureTooltip(wrap);
    tt.replaceChildren();
    tt.appendChild(html);
    tt.style.left = x + "px";
    tt.style.top = y + "px";
    tt.style.opacity = "1";
  }

  function hideTooltip(wrap) {
    const tt = wrap.querySelector(".viz-tooltip");
    if (tt) tt.style.opacity = "0";
  }

  function ttRow(colorVar, label, value) {
    const row = document.createElement("div");
    row.className = "tt-row";
    if (colorVar) {
      const key = document.createElement("span");
      key.className = "tt-key";
      key.style.background = colorVar;
      row.appendChild(key);
    }
    const labelEl = document.createTextNode(label + ": ");
    row.appendChild(labelEl);
    const val = document.createElement("span");
    val.className = "tt-value";
    val.textContent = value;
    row.appendChild(val);
    return row;
  }

  function ttGroup(rows, title) {
    const box = document.createElement("div");
    if (title) {
      const t = document.createElement("div");
      t.style.color = "var(--text-muted)";
      t.style.marginBottom = "4px";
      t.textContent = title;
      box.appendChild(t);
    }
    rows.forEach((r) => box.appendChild(r));
    return box;
  }

  // ---------------------------------------------------------------------
  // KPI tiles
  // ---------------------------------------------------------------------

  function deltaClass(delta) {
    if (delta === null || delta === undefined) return "flat";
    if (delta > 0) return "up";
    if (delta < 0) return "down";
    return "flat";
  }

  function deltaText(delta) {
    if (delta === null || delta === undefined) return "vs prior period —";
    const sign = delta > 0 ? "+" : "";
    return sign + delta.toFixed(1) + "% vs prior period";
  }

  function renderSparkline(svg, values) {
    svg.replaceChildren();
    if (!values || values.length < 2) return;
    const W = 100, H = 28, pad = 2;
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const range = max - min || 1;
    const stepX = (W - pad * 2) / (values.length - 1);
    const pts = values.map((v, i) => {
      const x = pad + i * stepX;
      const y = H - pad - ((v - min) / range) * (H - pad * 2);
      return [x, y];
    });
    const d = "M " + pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L ");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("preserveAspectRatio", "none");
    const path = svgEl("path", { d: d, class: "trend-line", "stroke-width": "1.5" });
    svg.appendChild(path);
    const last = pts[pts.length - 1];
    svg.appendChild(svgEl("circle", { cx: last[0], cy: last[1], r: 2, class: "trend-dot" }));
  }

  const KPI_DEFS = [
    { key: "revenue", label: "Revenue", format: (v) => fmtCompact(v, "$"), spark: true },
    { key: "orders", label: "Orders", format: (v) => v.toLocaleString(), spark: false },
    { key: "aov", label: "Avg. order value", format: (v) => "$" + v.toFixed(2), spark: false },
    { key: "new_share", label: "New customer share", format: (v) => v.toFixed(1) + "%", spark: false },
  ];

  function renderKPIs(data) {
    const row = document.getElementById("kpiRow");
    row.replaceChildren();
    KPI_DEFS.forEach((def) => {
      const k = data.kpis[def.key];
      const tile = document.createElement("div");
      tile.className = "stat-tile";

      const label = document.createElement("div");
      label.className = "stat-label";
      label.textContent = def.label;
      tile.appendChild(label);

      const valueRow = document.createElement("div");
      valueRow.className = "stat-value-row";

      const value = document.createElement("div");
      value.className = "stat-value";
      value.textContent = def.format(k.value);
      valueRow.appendChild(value);

      const delta = document.createElement("div");
      delta.className = "stat-delta " + deltaClass(k.delta_pct);
      delta.textContent = deltaText(k.delta_pct);
      valueRow.appendChild(delta);

      tile.appendChild(valueRow);

      if (def.spark) {
        const svg = svgEl("svg", { class: "stat-spark" });
        tile.appendChild(svg);
        renderSparkline(svg, k.sparkline);
      }

      row.appendChild(tile);
    });
  }

  // ---------------------------------------------------------------------
  // Trend chart (line + area + crosshair)
  // ---------------------------------------------------------------------

  function renderTrendChart(points) {
    const wrap = document.getElementById("trendChart");
    wrap.querySelectorAll("svg").forEach((n) => n.remove());

    const W = 640, H = 220;
    const padL = 44, padR = 12, padT = 16, padB = 24;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const values = points.map((p) => p.revenue);
    const max = niceMax(Math.max(...values, 1) * 1.15);
    const n = points.length;

    const xAt = (i) => padL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
    const yAt = (v) => padT + plotH - (v / max) * plotH;

    const svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H });

    // gridlines (0/50%/100%)
    [0, 0.5, 1].forEach((f) => {
      const y = padT + plotH - f * plotH;
      svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y, y2: y, class: f === 0 ? "baseline" : "grid-line" }));
      const label = svgEl("text", { x: padL - 8, y: y + 3, class: "axis-label", "text-anchor": "end" });
      label.textContent = fmtCompact(max * f, "$");
      svg.appendChild(label);
    });

    // x-axis labels: first, middle, last
    [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => {
      if (i < 0 || i >= n) return;
      const label = svgEl("text", { x: xAt(i), y: H - 6, class: "axis-label", "text-anchor": "middle" });
      label.textContent = fmtDate(points[i].date);
      svg.appendChild(label);
    });

    const linePts = points.map((p, i) => [xAt(i), yAt(p.revenue)]);
    const lineD = "M " + linePts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L ");
    const areaD = lineD + " L " + xAt(n - 1).toFixed(1) + "," + (padT + plotH) + " L " + xAt(0).toFixed(1) + "," + (padT + plotH) + " Z";

    svg.appendChild(svgEl("path", { d: areaD, class: "trend-area" }));
    svg.appendChild(svgEl("path", { d: lineD, class: "trend-line" }));

    const last = linePts[linePts.length - 1];
    svg.appendChild(svgEl("circle", { cx: last[0], cy: last[1], r: 4, class: "trend-dot" }));
    const endLabel = svgEl("text", { x: last[0] - 6, y: last[1] - 10, class: "bar-value-label", "text-anchor": "end" });
    endLabel.textContent = fmtCompact(points[n - 1].revenue, "$");
    svg.appendChild(endLabel);

    const crosshair = svgEl("line", { x1: padL, x2: padL, y1: padT, y2: padT + plotH, class: "crosshair-line" });
    svg.appendChild(crosshair);
    const hoverDot = svgEl("circle", { r: 4, class: "trend-dot", style: "opacity:0" });
    svg.appendChild(hoverDot);

    const hit = svgEl("rect", { x: padL, y: padT, width: plotW, height: plotH, class: "hit-rect" });
    svg.appendChild(hit);

    function onMove(evt) {
      const rect = svg.getBoundingClientRect();
      const relX = ((evt.clientX - rect.left) / rect.width) * W;
      let idx = Math.round(((relX - padL) / plotW) * (n - 1));
      idx = Math.max(0, Math.min(n - 1, idx));
      const px = xAt(idx), py = yAt(points[idx].revenue);
      crosshair.setAttribute("x1", px);
      crosshair.setAttribute("x2", px);
      crosshair.setAttribute("opacity", "1");
      hoverDot.setAttribute("cx", px);
      hoverDot.setAttribute("cy", py);
      hoverDot.style.opacity = "1";

      const wrapRect = wrap.getBoundingClientRect();
      const tx = ((px / W) * wrapRect.width);
      const ty = ((py / H) * (wrapRect.width * (H / W)));
      showTooltip(
        wrap, tx, ty,
        ttGroup([
          ttRow("var(--series-blue)", "Revenue", fmtMoney(points[idx].revenue)),
          ttRow(null, "Orders", points[idx].orders.toLocaleString()),
        ], fmtDate(points[idx].date))
      );
    }

    function onLeave() {
      crosshair.setAttribute("opacity", "0");
      hoverDot.style.opacity = "0";
      hideTooltip(wrap);
    }

    hit.addEventListener("pointermove", onMove);
    hit.addEventListener("pointerleave", onLeave);

    wrap.appendChild(svg);
  }

  // ---------------------------------------------------------------------
  // Horizontal bar chart (single hue, magnitude comparison)
  // ---------------------------------------------------------------------

  function roundedBarPath(x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w, h / 2));
    if (w <= 0) return "M " + x + "," + y + " L " + x + "," + (y + h) + " Z";
    return [
      "M", x, y,
      "L", (x + w - r).toFixed(1), y,
      "A", r, r, 0, 0, 1, (x + w).toFixed(1), (y + r).toFixed(1),
      "L", (x + w).toFixed(1), (y + h - r).toFixed(1),
      "A", r, r, 0, 0, 1, (x + w - r).toFixed(1), (y + h).toFixed(1),
      "L", x, (y + h),
      "Z",
    ].join(" ");
  }

  function renderBarChart(containerId, data, opts) {
    const wrap = document.getElementById(containerId);
    wrap.querySelectorAll("svg").forEach((n) => n.remove());

    const W = 460;
    const rowH = 34, barH = 18;
    const labelW = 118;
    const padR = 56;
    const H = data.length * rowH + 8;
    const plotW = W - labelW - padR;
    const max = Math.max(...data.map((d) => d.value), 1);

    const svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H });

    data.forEach((d, i) => {
      const y = i * rowH + 4;
      const w = (d.value / max) * plotW;

      const catLabel = svgEl("text", {
        x: labelW - 10, y: y + barH / 2 + 4, class: "bar-cat-label", "text-anchor": "end",
      });
      catLabel.textContent = d.label;
      svg.appendChild(catLabel);

      const track = svgEl("rect", { x: labelW, y: y, width: plotW, height: barH, fill: "var(--gridline)", rx: 3 });
      svg.appendChild(track);

      const bar = svgEl("path", { d: roundedBarPath(labelW, y, w, barH, 4), fill: opts.color });
      svg.appendChild(bar);

      const valueLabel = svgEl("text", {
        x: labelW + w + 8, y: y + barH / 2 + 4, class: "bar-value-label",
      });
      valueLabel.textContent = opts.format(d.value);
      svg.appendChild(valueLabel);

      const hit = svgEl("rect", { x: labelW, y: y - 2, width: plotW + padR, height: barH + 4, class: "hit-rect" });
      svg.appendChild(hit);

      hit.addEventListener("pointerenter", () => {
        bar.setAttribute("opacity", "0.8");
        const wrapRect = wrap.getBoundingClientRect();
        const tx = ((labelW + w / 2) / W) * wrapRect.width;
        const ty = (y / H) * (wrapRect.width * (H / W));
        showTooltip(wrap, tx, ty, ttGroup([ttRow(opts.color, d.label, opts.format(d.value))]));
      });
      hit.addEventListener("pointerleave", () => {
        bar.setAttribute("opacity", "1");
        hideTooltip(wrap);
      });
    });

    svg.appendChild(svgEl("line", { x1: labelW, x2: labelW, y1: 0, y2: H, class: "baseline" }));

    wrap.appendChild(svg);
  }

  // ---------------------------------------------------------------------
  // Customer mix (2-segment stacked bar)
  // ---------------------------------------------------------------------

  function renderMixChart(mix) {
    const wrap = document.getElementById("mixChart");
    wrap.querySelectorAll("svg, .mix-legend").forEach((n) => n.remove());

    const W = 460, H = 40, barH = 28, y = 4;
    const gap = 2;
    const newW = (mix.new_pct / 100) * W;
    const retW = W - newW - gap;

    const svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H });

    const newBar = svgEl("path", { d: roundedBarPath(0, y, Math.max(newW - 0, 0), barH, 4), fill: "var(--series-aqua)" });
    svg.appendChild(newBar);

    const retX = newW + gap;
    const retBar = svgEl("rect", { x: retX, y: y, width: Math.max(retW, 0), height: barH, fill: "var(--series-yellow)", rx: 4 });
    svg.appendChild(retBar);

    function segLabel(x, w, text, dark) {
      if (w < 40) return;
      const t = svgEl("text", {
        x: x + w / 2, y: y + barH / 2 + 4, "text-anchor": "middle",
        fill: dark ? "#0b0b0b" : "#ffffff", "font-size": "12", "font-weight": "600",
      });
      t.textContent = text;
      svg.appendChild(t);
    }
    segLabel(0, newW, mix.new_pct.toFixed(1) + "%", false);
    segLabel(retX, retW, mix.returning_pct.toFixed(1) + "%", true);

    const hitNew = svgEl("rect", { x: 0, y: y, width: newW, height: barH, class: "hit-rect" });
    const hitRet = svgEl("rect", { x: retX, y: y, width: Math.max(retW, 0), height: barH, class: "hit-rect" });
    svg.appendChild(hitNew);
    svg.appendChild(hitRet);

    hitNew.addEventListener("pointerenter", () => {
      const wrapRect = wrap.getBoundingClientRect();
      showTooltip(wrap, (newW / 2 / W) * wrapRect.width, (y / H) * (wrapRect.width * (H / W)),
        ttGroup([ttRow("var(--series-aqua)", "New customers", mix.new_pct.toFixed(1) + "%")]));
    });
    hitNew.addEventListener("pointerleave", () => hideTooltip(wrap));
    hitRet.addEventListener("pointerenter", () => {
      const wrapRect = wrap.getBoundingClientRect();
      showTooltip(wrap, ((retX + retW / 2) / W) * wrapRect.width, (y / H) * (wrapRect.width * (H / W)),
        ttGroup([ttRow("var(--series-yellow)", "Returning customers", mix.returning_pct.toFixed(1) + "%")]));
    });
    hitRet.addEventListener("pointerleave", () => hideTooltip(wrap));

    wrap.appendChild(svg);

    const legend = document.createElement("div");
    legend.className = "mix-legend";
    [
      ["var(--series-aqua)", "New", mix.new_pct],
      ["var(--series-yellow)", "Returning", mix.returning_pct],
    ].forEach(([color, label, pct]) => {
      const item = document.createElement("div");
      item.className = "mix-legend-item";
      const sw = document.createElement("span");
      sw.className = "legend-swatch";
      sw.style.background = color;
      item.appendChild(sw);
      item.appendChild(document.createTextNode(label + " — " + pct.toFixed(1) + "%"));
      legend.appendChild(item);
    });
    wrap.appendChild(legend);
  }

  // ---------------------------------------------------------------------
  // Top products table
  // ---------------------------------------------------------------------

  function renderTable(rows) {
    const container = document.getElementById("productsTable");
    container.replaceChildren();

    const table = document.createElement("table");
    table.className = "data-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["Product", "Category", "Units", "Revenue"].forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      if (h === "Units" || h === "Revenue") th.style.textAlign = "right";
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      const nameTd = document.createElement("td");
      nameTd.className = "product-cell";
      nameTd.textContent = r.name;
      tr.appendChild(nameTd);

      const catTd = document.createElement("td");
      catTd.className = "cat-cell";
      catTd.textContent = r.category;
      tr.appendChild(catTd);

      const unitsTd = document.createElement("td");
      unitsTd.className = "num";
      unitsTd.textContent = r.units.toLocaleString();
      tr.appendChild(unitsTd);

      const revTd = document.createElement("td");
      revTd.className = "num";
      revTd.textContent = fmtMoney(r.revenue);
      tr.appendChild(revTd);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  // ---------------------------------------------------------------------
  // Fetch + orchestration
  // ---------------------------------------------------------------------

  const RANGE_LABELS = { "7d": "Last 7 days", "30d": "Last 30 days", "90d": "Last 90 days", "12m": "Last 12 months" };

  function setLoading(isLoading) {
    loading = isLoading;
    const kpiRow = document.getElementById("kpiRow");
    const grid = document.querySelector(".charts-grid");
    kpiRow.style.opacity = isLoading ? "0.45" : "1";
    grid.style.opacity = isLoading ? "0.45" : "1";
  }

  async function loadData(range) {
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch("/api/summary?range=" + encodeURIComponent(range));
      const data = await res.json();
      document.getElementById("periodLabel").textContent =
        RANGE_LABELS[range] + " · " + fmtDate(data.period.start) + " – " + fmtDate(data.period.end);
      renderKPIs(data);
      renderTrendChart(data.revenue_trend);
      renderBarChart("categoryChart", data.category_breakdown, {
        color: "var(--series-blue)",
        format: (v) => fmtCompact(v, "$"),
      });
      renderBarChart("regionChart", data.region_breakdown, {
        color: "var(--series-orange)",
        format: (v) => v.toLocaleString(),
      });
      renderMixChart(data.customer_mix);
      renderTable(data.top_products);
    } finally {
      setLoading(false);
    }
  }

  function init() {
    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach((b) => {
          b.classList.remove("active");
          b.removeAttribute("aria-selected");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        currentRange = btn.dataset.range;
        loadData(currentRange);
      });
    });
    loadData(currentRange);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
