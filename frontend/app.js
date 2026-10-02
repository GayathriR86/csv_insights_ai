/**
 * CSV Data Analyzer - Frontend
 * Talks to FastAPI backend at /api/*
 */

const API = window.location.origin.includes("8000")
  ? "" // same origin if served by backend
  : "http://localhost:8000";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let overview = null;
let numericCols = [];
let categoricalCols = [];
let allCols = [];

// ---------------------------------------------------------------------------
// Settings (localStorage)
// ---------------------------------------------------------------------------
function loadSettings() {
  document.getElementById("api-key").value = localStorage.getItem("llm_api_key") || "";
  document.getElementById("base-url").value = localStorage.getItem("llm_base_url") || "";
  document.getElementById("model-name").value = localStorage.getItem("llm_model") || "gpt-4o-mini";
}
function saveSettings() {
  localStorage.setItem("llm_api_key", document.getElementById("api-key").value.trim());
  localStorage.setItem("llm_base_url", document.getElementById("base-url").value.trim());
  localStorage.setItem("llm_model", document.getElementById("model-name").value.trim() || "gpt-4o-mini");
  document.getElementById("settings-modal").classList.add("hidden");
  document.getElementById("settings-modal").classList.remove("flex");
}
function getLLMConfig() {
  return {
    api_key: localStorage.getItem("llm_api_key") || "",
    base_url: localStorage.getItem("llm_base_url") || null,
    model: localStorage.getItem("llm_model") || "gpt-4o-mini",
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || JSON.stringify(j);
    } catch (_) {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

function fmt(n) {
  if (n == null) return "—";
  if (typeof n === "number") return n.toLocaleString();
  return String(n);
}

function showToast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = `fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl shadow-lg text-sm text-white ${
    isError ? "bg-red-600" : "bg-emerald-600"
  }`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("border-brand-600", "bg-brand-50");
});
dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("border-brand-600", "bg-brand-50");
});
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("border-brand-600", "bg-brand-50");
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
  const progress = document.getElementById("upload-progress");
  const bar = document.getElementById("progress-bar");
  const msg = document.getElementById("upload-msg");
  progress.classList.remove("hidden");
  bar.style.width = "30%";
  msg.textContent = `Uploading ${file.name}...`;

  const form = new FormData();
  form.append("file", file);

  try {
    bar.style.width = "60%";
    const data = await api("/api/upload", { method: "POST", body: form });
    bar.style.width = "100%";
    msg.textContent = "Analysis ready!";
    overview = data;
    numericCols = data.numeric_columns || [];
    categoricalCols = data.categorical_columns || [];
    allCols = data.columns_list || [];
    document.getElementById("status-badge").textContent = `${file.name} · ${fmt(data.rows)} rows`;
    document.getElementById("status-badge").className =
      "px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/90 text-white";
    document.getElementById("app-content").classList.remove("hidden");
    renderMetrics(data);
    renderOverview(data);
    populateSelects();
    renderSuggestions();
    // auto load rule insights
    loadRuleInsights();
    setTimeout(() => progress.classList.add("hidden"), 800);
    showToast("File loaded successfully");
  } catch (err) {
    msg.textContent = err.message;
    bar.style.width = "100%";
    bar.classList.add("bg-red-500");
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------
function renderMetrics(data) {
  const items = [
    { label: "Rows", value: fmt(data.rows) },
    { label: "Columns", value: data.columns },
    { label: "Numeric", value: (data.numeric_columns || []).length },
    { label: "Categorical", value: (data.categorical_columns || []).length },
    { label: "Missing", value: fmt(data.missing_total) },
    { label: "Memory", value: `${data.memory_mb} MB` },
  ];
  document.getElementById("metrics").innerHTML = items
    .map(
      (i) => `
    <div class="metric-card">
      <div class="value">${i.value}</div>
      <div class="label">${i.label}</div>
    </div>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Overview tables
// ---------------------------------------------------------------------------
function renderOverview(data) {
  // Column info
  const tbody = document.querySelector("#col-info-table tbody");
  tbody.innerHTML = (data.column_info || [])
    .map(
      (c) => `
    <tr>
      <td class="px-3 py-1.5 font-medium">${c.name}</td>
      <td class="px-3 py-1.5 text-slate-500">${c.dtype}</td>
      <td class="px-3 py-1.5 text-right">${c.nulls}</td>
      <td class="px-3 py-1.5 text-right">${c.null_pct}%</td>
      <td class="px-3 py-1.5 text-right">${c.unique}</td>
    </tr>`
    )
    .join("");

  // Preview
  const preview = data.preview || [];
  if (preview.length) {
    const cols = Object.keys(preview[0]);
    const thead = document.querySelector("#preview-table thead tr");
    thead.innerHTML = cols.map((c) => `<th class="px-3 py-2 text-left">${c}</th>`).join("");
    const pbody = document.querySelector("#preview-table tbody");
    pbody.innerHTML = preview
      .map(
        (row) =>
          `<tr>${cols.map((c) => `<td class="px-3 py-1.5">${row[c] ?? ""}</td>`).join("")}</tr>`
      )
      .join("");
  }

  // Describe
  loadDescribe();
}

async function loadDescribe() {
  try {
    const data = await api("/api/describe");
    const box = document.getElementById("describe-container");
    if (!data.numeric) {
      box.innerHTML = '<p class="p-4 text-slate-400 text-sm">No numeric columns</p>';
      return;
    }
    const stats = data.numeric;
    const statNames = Object.keys(stats);
    const cols = Object.keys(stats[statNames[0]] || {});
    let html = '<table class="min-w-full text-sm"><thead class="bg-slate-100"><tr><th class="px-3 py-2 text-left">Stat</th>';
    cols.forEach((c) => (html += `<th class="px-3 py-2 text-right">${c}</th>`));
    html += "</tr></thead><tbody>";
    statNames.forEach((s) => {
      html += `<tr><td class="px-3 py-1.5 font-medium">${s}</td>`;
      cols.forEach((c) => {
        const v = stats[s][c];
        html += `<td class="px-3 py-1.5 text-right">${typeof v === "number" ? v.toFixed(4) : v}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    box.innerHTML = html;
  } catch (e) {
    console.error(e);
  }
}

// ---------------------------------------------------------------------------
// Populate selects
// ---------------------------------------------------------------------------
function populateSelects() {
  const fill = (sel, cols, includeEmpty = false) => {
    sel.innerHTML = includeEmpty ? '<option value="">None</option>' : "";
    cols.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      sel.appendChild(opt);
    });
  };
  fill(document.getElementById("chart-col"), [...numericCols, ...categoricalCols]);
  fill(document.getElementById("chart-x"), numericCols);
  fill(document.getElementById("chart-y"), numericCols);
  fill(document.getElementById("chart-color"), [...categoricalCols, ...numericCols], true);
  fill(document.getElementById("outlier-col"), numericCols);
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });
});

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------
document.getElementById("chart-type").addEventListener("change", () => {
  const t = document.getElementById("chart-type").value;
  document.getElementById("chart-col-wrap").classList.toggle("hidden", t === "scatter");
  document.getElementById("chart-x-wrap").classList.toggle("hidden", t !== "scatter");
  document.getElementById("chart-y-wrap").classList.toggle("hidden", t !== "scatter");
  document.getElementById("chart-color-wrap").classList.toggle("hidden", t !== "scatter");
  if (t === "bar") {
    fillSelect(document.getElementById("chart-col"), [...categoricalCols, ...numericCols]);
  } else if (t === "histogram" || t === "box") {
    fillSelect(document.getElementById("chart-col"), numericCols);
  }
});

function fillSelect(sel, cols) {
  const cur = sel.value;
  sel.innerHTML = "";
  cols.forEach((c) => {
    const o = document.createElement("option");
    o.value = c;
    o.textContent = c;
    sel.appendChild(o);
  });
  if (cols.includes(cur)) sel.value = cur;
}

document.getElementById("btn-draw-chart").addEventListener("click", drawChart);

async function drawChart() {
  const type = document.getElementById("chart-type").value;
  const area = document.getElementById("chart-area");
  try {
    if (type === "histogram") {
      const col = document.getElementById("chart-col").value;
      const data = await api("/api/chart-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chart_type: "histogram", column: col, bins: 40 }),
      });
      const centers = data.bin_edges.slice(0, -1).map((e, i) => (e + data.bin_edges[i + 1]) / 2);
      Plotly.newPlot(
        area,
        [{ x: centers, y: data.counts, type: "bar", marker: { color: "#7c3aed" } }],
        {
          title: `Histogram of ${col}`,
          xaxis: { title: col },
          yaxis: { title: "Count" },
          margin: { t: 40 },
          shapes: [
            { type: "line", x0: data.mean, x1: data.mean, y0: 0, y1: Math.max(...data.counts), line: { color: "red", dash: "dash" } },
          ],
        },
        { responsive: true }
      );
    } else if (type === "bar") {
      const col = document.getElementById("chart-col").value;
      const data = await api("/api/chart-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chart_type: "bar", column: col, top_n: 20 }),
      });
      Plotly.newPlot(
        area,
        [{ x: data.labels, y: data.counts, type: "bar", marker: { color: "#6366f1" } }],
        { title: `Top values in ${col}`, xaxis: { title: col }, yaxis: { title: "Count" }, margin: { t: 40 } },
        { responsive: true }
      );
    } else if (type === "scatter") {
      const x = document.getElementById("chart-x").value;
      const y = document.getElementById("chart-y").value;
      const color = document.getElementById("chart-color").value || null;
      const data = await api("/api/chart-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chart_type: "scatter", x_col: x, y_col: y, color_col: color }),
      });
      const trace = {
        x: data.x,
        y: data.y,
        mode: "markers",
        type: "scatter",
        marker: { size: 7, opacity: 0.7, color: "#7c3aed" },
      };
      if (data.color) {
        trace.marker.color = data.color;
        trace.marker.colorscale = "Viridis";
        trace.marker.showscale = true;
      }
      Plotly.newPlot(
        area,
        [trace],
        { title: `${y} vs ${x}`, xaxis: { title: x }, yaxis: { title: y }, margin: { t: 40 } },
        { responsive: true }
      );
    } else if (type === "box") {
      const col = document.getElementById("chart-col").value;
      const data = await api("/api/chart-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chart_type: "series", column: col }),
      });
      Plotly.newPlot(
        area,
        [{ y: data.values.filter((v) => v != null), type: "box", name: col, marker: { color: "#7c3aed" } }],
        { title: `Box Plot – ${col}`, margin: { t: 40 } },
        { responsive: true }
      );
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Outliers
// ---------------------------------------------------------------------------
document.getElementById("outlier-method").addEventListener("change", () => {
  const m = document.getElementById("outlier-method").value;
  document.getElementById("outlier-col-wrap").classList.toggle("hidden", m === "isolation");
  document.getElementById("z-thresh-wrap").classList.toggle("hidden", m !== "zscore");
});

document.getElementById("btn-outliers").addEventListener("click", runOutliers);

async function runOutliers() {
  const method = document.getElementById("outlier-method").value;
  const body = { method };
  if (method === "iqr" || method === "zscore") {
    body.column = document.getElementById("outlier-col").value;
  }
  if (method === "zscore") body.threshold = parseFloat(document.getElementById("z-thresh").value) || 3;
  if (method === "isolation") body.contamination = 0.05;

  try {
    const data = await api("/api/outliers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    // Metrics
    document.getElementById("outlier-metrics").innerHTML = [
      { label: "Method", value: data.method },
      { label: "Outliers", value: fmt(data.outlier_count) },
      { label: "% of data", value: `${data.outlier_pct}%` },
      data.lower_bound != null
        ? { label: "Bounds", value: `[${data.lower_bound}, ${data.upper_bound}]` }
        : { label: "Columns", value: (data.columns || []).join(", ") || "—" },
    ]
      .map(
        (i) => `
      <div class="metric-card">
        <div class="value text-base">${i.value}</div>
        <div class="label">${i.label}</div>
      </div>`
      )
      .join("");

    // Chart
    if (method === "iqr" || method === "zscore") {
      const col = body.column;
      const series = await api("/api/chart-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chart_type: "series", column: col }),
      });
      Plotly.newPlot(
        document.getElementById("outlier-chart"),
        [{ y: series.values.filter((v) => v != null), type: "box", name: col, boxpoints: "outliers", marker: { color: "#7c3aed" } }],
        { title: `Outliers – ${col}`, margin: { t: 40 } },
        { responsive: true }
      );
    } else if (data.columns && data.columns.length >= 2) {
      // scatter with labels if available – we only have rows; simple message
      Plotly.newPlot(
        document.getElementById("outlier-chart"),
        [],
        { title: `Isolation Forest found ${data.outlier_count} outliers`, annotations: [{ text: "See table below", showarrow: false, x: 0.5, y: 0.5, xref: "paper", yref: "paper" }] },
        { responsive: true }
      );
    }

    // Table
    const rows = data.outlier_rows || [];
    const wrap = document.getElementById("outlier-table-wrap");
    if (rows.length) {
      wrap.classList.remove("hidden");
      const cols = Object.keys(rows[0]);
      document.querySelector("#outlier-table thead tr").innerHTML = cols
        .map((c) => `<th class="px-3 py-2 text-left">${c}</th>`)
        .join("");
      document.querySelector("#outlier-table tbody").innerHTML = rows
        .map((r) => `<tr>${cols.map((c) => `<td class="px-3 py-1.5">${r[c] ?? ""}</td>`).join("")}</tr>`)
        .join("");
    } else {
      wrap.classList.add("hidden");
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Correlation
// ---------------------------------------------------------------------------
document.getElementById("btn-corr").addEventListener("click", runCorrelation);

async function runCorrelation() {
  const method = document.getElementById("corr-method").value;
  try {
    const data = await api("/api/correlation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method }),
    });

    // Heatmap
    Plotly.newPlot(
      document.getElementById("corr-heatmap"),
      [
        {
          z: data.matrix,
          x: data.labels,
          y: data.labels,
          type: "heatmap",
          colorscale: "RdBu",
          zmid: 0,
          text: data.matrix.map((row) => row.map((v) => v.toFixed(2))),
          texttemplate: "%{text}",
          textfont: { size: 10 },
        },
      ],
      {
        title: `${method.charAt(0).toUpperCase() + method.slice(1)} Correlation`,
        margin: { t: 40, l: 100, b: 100 },
      },
      { responsive: true }
    );

    // Pairs table
    const tbody = document.querySelector("#corr-pairs-table tbody");
    tbody.innerHTML = (data.pairs || [])
      .map(
        (p) => `
      <tr>
        <td class="px-3 py-1.5">${p.feature_a}</td>
        <td class="px-3 py-1.5">${p.feature_b}</td>
        <td class="px-3 py-1.5 text-right font-medium ${Math.abs(p.correlation) > 0.7 ? "text-brand-700" : ""}">${p.correlation.toFixed(4)}</td>
      </tr>`
      )
      .join("");
  } catch (err) {
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------
document.getElementById("btn-rule-insights").addEventListener("click", loadRuleInsights);
document.getElementById("btn-llm-insights").addEventListener("click", loadLLMInsights);

async function loadRuleInsights() {
  try {
    const data = await api("/api/insights");
    const list = document.getElementById("insights-list");
    list.innerHTML = (data.insights || [])
      .map(
        (ins) => `
      <div class="insight-card insight-${ins.type}">
        <div class="font-semibold text-sm mb-0.5">${ins.title}</div>
        <div class="text-sm text-slate-700">${ins.text}</div>
      </div>`
      )
      .join("");
  } catch (err) {
    showToast(err.message, true);
  }
}

async function loadLLMInsights() {
  const cfg = getLLMConfig();
  if (!cfg.api_key) {
    showToast("Set your API key in LLM Settings first", true);
    document.getElementById("btn-settings").click();
    return;
  }
  const box = document.getElementById("llm-insights-box");
  const content = document.getElementById("llm-insights-content");
  box.classList.remove("hidden");
  content.innerHTML = '<p class="text-slate-500">Generating narrative with LLM...</p>';
  try {
    const data = await api("/api/llm-insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (data.success) {
      content.innerHTML = marked.parse(data.answer);
    } else {
      content.innerHTML = `<p class="text-red-600">${data.answer}</p>`;
    }
  } catch (err) {
    content.innerHTML = `<p class="text-red-600">${err.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Ask Your Data
// ---------------------------------------------------------------------------
function renderSuggestions() {
  const sugg = [
    "What are the main data quality issues?",
    "Summarize the key findings",
    "Which columns have the strongest correlations?",
    "Are there any outliers I should worry about?",
    "Suggest next analysis steps",
  ];
  if (numericCols.length) {
    sugg.push(`Describe the distribution of ${numericCols[0]}`);
  }
  document.getElementById("suggestions").innerHTML = sugg
    .map((s) => `<span class="chip" data-q="${s.replace(/"/g, "&quot;")}">${s}</span>`)
    .join("");
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.getElementById("ask-input").value = chip.dataset.q;
      askQuestion();
    });
  });
}

document.getElementById("btn-ask").addEventListener("click", askQuestion);
document.getElementById("ask-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion();
});

async function askQuestion() {
  const q = document.getElementById("ask-input").value.trim();
  if (!q) return;
  const cfg = getLLMConfig();
  if (!cfg.api_key) {
    showToast("Set your API key in LLM Settings first", true);
    document.getElementById("btn-settings").click();
    return;
  }
  document.getElementById("ask-loading").classList.remove("hidden");
  document.getElementById("ask-answer").classList.add("hidden");
  try {
    const data = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, ...cfg }),
    });
    document.getElementById("ask-loading").classList.add("hidden");
    document.getElementById("ask-answer").classList.remove("hidden");
    const content = document.getElementById("ask-answer-content");
    if (data.success) {
      content.innerHTML = marked.parse(data.answer);
    } else {
      content.innerHTML = `<p class="text-red-600">${data.answer}</p>`;
    }
  } catch (err) {
    document.getElementById("ask-loading").classList.add("hidden");
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------
document.getElementById("btn-pdf").addEventListener("click", () => downloadReport("pdf"));
document.getElementById("btn-md").addEventListener("click", () => downloadReport("markdown"));

async function downloadReport(format) {
  const includeLLM =
    format === "pdf"
      ? document.getElementById("pdf-include-llm").checked
      : document.getElementById("md-include-llm").checked;
  const cfg = getLLMConfig();
  const status = document.getElementById("report-status");
  status.textContent = includeLLM ? "Generating report with LLM insights (may take a moment)..." : "Generating report...";

  try {
    const res = await fetch(`${API}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format,
        include_llm: includeLLM,
        api_key: cfg.api_key || null,
        base_url: cfg.base_url,
        model: cfg.model,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = format === "pdf" ? "data_analysis_report.pdf" : "data_analysis_report.md";
    a.click();
    URL.revokeObjectURL(url);
    status.textContent = "Download started!";
    showToast("Report downloaded");
  } catch (err) {
    status.textContent = err.message;
    showToast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Settings UI
// ---------------------------------------------------------------------------
document.getElementById("btn-settings").addEventListener("click", () => {
  loadSettings();
  const m = document.getElementById("settings-modal");
  m.classList.remove("hidden");
  m.classList.add("flex");
});
document.getElementById("close-settings").addEventListener("click", () => {
  document.getElementById("settings-modal").classList.add("hidden");
  document.getElementById("settings-modal").classList.remove("flex");
});
document.getElementById("save-settings").addEventListener("click", saveSettings);

// Init
loadSettings();
