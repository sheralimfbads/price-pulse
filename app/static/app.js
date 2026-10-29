/**
 * PricePulse — Interactive Frontend Application Engine
 * High-performance, zero-dependency modern vanilla JavaScript
 */

// --- DOM Elements ---
const themeToggle = document.getElementById("theme-toggle");
const overviewStatus = document.getElementById("overview-status");
const overviewMetrics = document.getElementById("overview-metrics");
const moversStatus = document.getElementById("movers-status");
const moversTables = document.getElementById("movers-tables");
const moversComparisonBadge = document.getElementById("movers-comparison-badge");
const productSelect = document.getElementById("product-select");
const productForm = document.getElementById("product-form");
const productStatus = document.getElementById("product-status");
const pricesBody = document.getElementById("prices-body");
const chartCard = document.getElementById("chart-card");
const chartWrapper = document.getElementById("chart-wrapper");
const chart = document.getElementById("price-chart");
const chartTitle = document.getElementById("chart-title");
const chartSubtitle = document.getElementById("chart-subtitle");
const chartTooltip = document.getElementById("chart-tooltip");
const tableRowCount = document.getElementById("table-row-count");
const quickChips = document.getElementById("quick-chips");
const resetFilterBtn = document.getElementById("reset-filter-btn");

// Global state
let currentProductCode = "";
let currentPriceItems = [];

// --- Theme Management ---
function initTheme() {
  const savedTheme = localStorage.getItem("pricepulse-theme");
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = savedTheme || (prefersDark ? "dark" : "light");
  
  document.documentElement.setAttribute("data-theme", initialTheme);

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("pricepulse-theme", next);
      if (currentPriceItems.length > 0) {
        drawInteractiveChart(currentPriceItems);
      }
    });
  }
}

// --- Formatting Helpers ---
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (Number.isNaN(num)) return null;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  }).format(num) + " UZS";
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (Number.isNaN(num)) return null;
  const prefix = num > 0 ? "+" : "";
  return prefix + num.toFixed(2) + "%";
}

function formatMonth(isoDate) {
  if (!isoDate) return "—";
  const parts = isoDate.slice(0, 10).split("-");
  if (parts.length < 2) return isoDate;
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const mIndex = parseInt(parts[1], 10) - 1;
  return `${monthNames[mIndex] || parts[1]} ${parts[0]}`;
}

function formatFullDate(isoString) {
  if (!isoString) return "Not recorded";
  try {
    const d = new Date(isoString);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    }) + " UTC";
  } catch {
    return isoString;
  }
}

function monthInputToDate(value) {
  if (!value) return "";
  return value + "-01";
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || "Request failed";
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return payload;
}

// --- Load Market Overview ---
async function loadOverview() {
  try {
    const data = await fetchJson("/api/v1/overview");
    const timelineRange = data.earliest_month && data.latest_month
      ? `${escapeHtml(formatMonth(data.earliest_month))} – ${escapeHtml(formatMonth(data.latest_month))}`
      : "No observations";
    const snapshotName = data.latest_source_snapshot
      ? escapeHtml(data.latest_source_snapshot)
      : "No loaded snapshot";
    overviewStatus.hidden = true;
    overviewMetrics.hidden = false;

    overviewMetrics.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-label">Timeline Range</span>
          <div class="kpi-icon-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
          </div>
        </div>
        <div class="kpi-value">${data.latest_month ? escapeHtml(formatMonth(data.latest_month)) : "No data"}</div>
        <div class="kpi-footer">
          <span class="kpi-badge badge-emerald">${Number(data.month_count).toLocaleString()} Months</span>
          <span>${timelineRange}</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-label">Commodity Basket</span>
          <div class="kpi-icon-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <path d="M16 10a4 4 0 0 1-8 0"></path>
            </svg>
          </div>
        </div>
        <div class="kpi-value">${data.product_count} Products</div>
        <div class="kpi-footer">
          <span class="kpi-badge">Multilingual</span>
          <span>100% Unique Grain</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-label">Observations Modeled</span>
          <div class="kpi-icon-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
            </svg>
          </div>
        </div>
        <div class="kpi-value">${data.total_observations.toLocaleString()}</div>
        <div class="kpi-footer">
          <span class="kpi-badge badge-emerald">${data.available_observations.toLocaleString()} Active</span>
          <span class="kpi-badge badge-amber">${data.unavailable_observations} Unavailable</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-header">
          <span class="kpi-label">Loaded Snapshot Lineage</span>
          <div class="kpi-icon-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
            </svg>
          </div>
        </div>
        <div class="kpi-value" style="font-size: 1.15rem; font-weight: 600;">
          <span class="snapshot-pill" title="${snapshotName}">
            ${snapshotName}
          </span>
        </div>
        <div class="kpi-footer">
          <span>Fetched: ${formatFullDate(data.latest_source_fetched_at_utc)}</span>
        </div>
      </div>
    `;
  } catch (error) {
    overviewStatus.textContent = `Telemetry error: ${error.message}`;
    overviewStatus.classList.add("status-error");
  }
}

// --- Load Market Movers (Top YoY Gainers & Decliners) ---
function moverRow(item) {
  const isUp = Number(item.yoy_change_percent) >= 0;
  const pillClass = isUp ? "up" : "down";
  const arrow = isUp ? "▲" : "▼";
  const rankClass = item.rank === 1 ? "rank-1" : "";

  return `
    <tr data-code="${escapeHtml(item.product_code)}" title="Click to inspect ${escapeHtml(item.product_name_en || item.product_code)} chart">
      <td class="th-rank"><span class="rank-badge ${rankClass}">#${item.rank}</span></td>
      <td>
        <div class="commodity-cell">
          <span class="commodity-name">${escapeHtml(item.product_name_en || item.product_code)}</span>
              <span class="commodity-code-pill">CODE: ${escapeHtml(item.product_code)}</span>
        </div>
      </td>
      <td class="price-cell">${formatPrice(item.current_price_uzs_per_kg) || "—"}</td>
      <td class="price-cell" style="color: var(--text-muted);">${formatPrice(item.price_12_months_ago_uzs_per_kg) || "—"}</td>
      <td style="text-align: right;">
        <span class="change-pill ${pillClass}">
          ${arrow} ${formatPercent(item.yoy_change_percent) || "—"}
        </span>
      </td>
    </tr>
  `;
}

async function loadMovers() {
  try {
    const data = await fetchJson("/api/v1/analytics/latest-movers?limit=5");
    moversStatus.hidden = true;
    if (!data.latest_month) {
      moversComparisonBadge.textContent = "No data";
      return;
    }

    moversComparisonBadge.textContent = `${formatMonth(data.latest_month)} vs ${formatMonth(data.comparison_month)}`;
    
    document.getElementById("increases-body").innerHTML =
      data.increases.map(moverRow).join("") || `<tr><td colspan="5" class="empty-cell">No comparable increases recorded.</td></tr>`;
      
    document.getElementById("decreases-body").innerHTML =
      data.decreases.map(moverRow).join("") || `<tr><td colspan="5" class="empty-cell">No comparable decreases recorded.</td></tr>`;
      
    moversTables.hidden = false;

    // Row click listeners: jump straight to product exploration!
    document.querySelectorAll(".data-table tbody tr[data-code]").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.getAttribute("data-code");
        if (code) {
          selectProduct(code, true);
        }
      });
    });
  } catch (error) {
    moversStatus.textContent = `Could not load rankings: ${error.message}`;
  }
}

// --- Product Exploration ---
async function loadProducts() {
  try {
    const data = await fetchJson("/api/v1/products?limit=200");
    if (!data.items.length) {
      productSelect.innerHTML = `<option value="">No products found</option>`;
      productStatus.textContent = "Empty catalog";
      return;
    }

    productSelect.innerHTML = data.items.map((p) => {
      const label = p.product_name_en ? `${p.product_name_en} (${p.product_code})` : p.product_code;
      return `<option value="${escapeHtml(p.product_code)}">${escapeHtml(label)}</option>`;
    }).join("");

    // Auto-select first product (Rice 001)
    selectProduct(data.items[0].product_code);
  } catch (error) {
    productSelect.innerHTML = `<option value="">Unavailable</option>`;
    productStatus.textContent = `Catalog error: ${error.message}`;
  }
}

function selectProduct(code, scrollToChart = false) {
  currentProductCode = code;
  productSelect.value = code;

  // Highlight matching quick chip
  document.querySelectorAll(".chip-btn").forEach((chip) => {
    chip.classList.toggle("active", chip.getAttribute("data-code") === code);
  });

  loadPrices(code);

  if (scrollToChart) {
    document.getElementById("explorer").scrollIntoView({ behavior: "smooth" });
  }
}

function statusBadge(status) {
  if (status === "observed") {
    return `<span class="status-tag status-tag-observed">● Observed</span>`;
  }
  if (status === "zero_marked_unavailable") {
    return `<span class="status-tag status-tag-unavailable">▲ Source 0 (Unavailable)</span>`;
  }
  return `<span class="status-tag">${escapeHtml(status || "—")}</span>`;
}

// --- Interactive High-End SVG Chart ---
function drawInteractiveChart(items) {
  const width = 960;
  const height = 340;
  const pad = { top: 28, right: 36, bottom: 48, left: 88 };

  const parsed = items.map((item, idx) => ({
    idx,
    month: item.month_start,
    price: item.current_price_uzs_per_kg === null ? null : Number(item.current_price_uzs_per_kg),
    changePercent: item.change_percent,
    changeUzs: item.change_uzs_per_kg,
    status: item.current_price_status,
  }));

  const numeric = parsed.filter((p) => p.price !== null && !Number.isNaN(p.price));
  if (numeric.length === 0) {
    chartCard.hidden = true;
    return;
  }
  chartCard.hidden = false;

  const minPrice = Math.min(...numeric.map((p) => p.price));
  const maxPrice = Math.max(...numeric.map((p) => p.price));
  const priceMargin = (maxPrice - minPrice) * 0.08 || minPrice * 0.05 || 100;
  const yMin = Math.max(0, minPrice - priceMargin);
  const yMax = maxPrice + priceMargin;
  const ySpan = yMax - yMin || 1;

  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const getX = (i) => pad.left + (parsed.length === 1 ? innerW / 2 : (i / (parsed.length - 1)) * innerW);
  const getY = (val) => pad.top + innerH - ((val - yMin) / ySpan) * innerH;

  // Build SVG Content
  let svgHtml = `
    <defs>
      <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--chart-line)" stop-opacity="0.32" />
        <stop offset="100%" stop-color="var(--chart-line)" stop-opacity="0.0" />
      </linearGradient>
    </defs>
  `;

  // Gridlines & Y-Axis labels (5 ticks)
  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const val = yMin + (t / ticks) * ySpan;
    const yPos = getY(val);
    svgHtml += `
      <line x1="${pad.left}" y1="${yPos}" x2="${width - pad.right}" y2="${yPos}" stroke="var(--chart-grid)" stroke-width="1" />
      <text x="${pad.left - 12}" y="${yPos + 4}" fill="var(--text-muted)" font-size="11" text-anchor="end" font-family="'JetBrains Mono', monospace">
        ${formatPrice(val)}
      </text>
    `;
  }

  // X-Axis Year/Month Labels
  const step = Math.max(1, Math.floor(parsed.length / 8));
  parsed.forEach((p, i) => {
    if (i % step === 0 || i === parsed.length - 1) {
      const xPos = getX(i);
      svgHtml += `
        <line x1="${xPos}" y1="${height - pad.bottom}" x2="${xPos}" y2="${height - pad.bottom + 6}" stroke="var(--border-subtle)" stroke-width="1" />
        <text x="${xPos}" y="${height - pad.bottom + 22}" fill="var(--text-muted)" font-size="11" text-anchor="middle" font-family="'JetBrains Mono', monospace">
          ${escapeHtml(formatMonth(p.month))}
        </text>
      `;
    }
  });

  // Continuous line segments & Area fills
  let segments = [];
  let currentSegment = [];

  parsed.forEach((p) => {
    if (p.price === null || Number.isNaN(p.price)) {
      if (currentSegment.length > 0) {
        segments.push(currentSegment);
        currentSegment = [];
      }
    } else {
      currentSegment.push(p);
    }
  });
  if (currentSegment.length > 0) segments.push(currentSegment);

  // Render each observed segment
  segments.forEach((seg) => {
    if (seg.length === 1) {
      svgHtml += `<circle cx="${getX(seg[0].idx)}" cy="${getY(seg[0].price)}" r="5" fill="var(--chart-line)" />`;
      return;
    }

    // Path points
    const points = seg.map((p) => `${getX(p.idx)},${getY(p.price)}`).join(" ");
    
    // Area polygon
    const firstX = getX(seg[0].idx);
    const lastX = getX(seg[seg.length - 1].idx);
    const baseY = height - pad.bottom;
    const areaPoints = `${firstX},${baseY} ${points} ${lastX},${baseY}`;
    svgHtml += `<polygon points="${areaPoints}" fill="url(#priceGradient)" />`;

    // Line path
    svgHtml += `<polyline points="${points}" fill="none" stroke="var(--chart-line)" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />`;
  });

  // Circle points for observed points
  parsed.forEach((p) => {
    if (p.price !== null) {
      svgHtml += `
        <circle cx="${getX(p.idx)}" cy="${getY(p.price)}" r="3" fill="var(--bg-surface)" stroke="var(--chart-line)" stroke-width="2" class="chart-point" data-idx="${p.idx}" />
      `;
    } else {
      // Missing / Unavailable Indicator
      const xPos = getX(p.idx);
      svgHtml += `
        <line x1="${xPos}" y1="${pad.top}" x2="${xPos}" y2="${height - pad.bottom}" stroke="var(--warning-color)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.6" />
        <circle cx="${xPos}" cy="${height - pad.bottom}" r="4" fill="var(--warning-color)" />
      `;
    }
  });

  // Interactive Crosshair Layer
  svgHtml += `
    <g id="crosshair-group" opacity="0">
      <line id="crosshair-line" x1="0" y1="${pad.top}" x2="0" y2="${height - pad.bottom}" stroke="var(--accent-cyan)" stroke-width="1.5" stroke-dasharray="4,3" />
      <circle id="crosshair-dot" cx="0" cy="0" r="6" fill="var(--accent-cyan)" stroke="#fff" stroke-width="2" />
    </g>
  `;

  chart.innerHTML = svgHtml;

  // --- Attach Mouse / Touch Tracking for Dynamic Tooltip ---
  const crosshairGroup = document.getElementById("crosshair-group");
  const crosshairLine = document.getElementById("crosshair-line");
  const crosshairDot = document.getElementById("crosshair-dot");

  function handlePointer(event) {
    const rect = chart.getBoundingClientRect();
    const clientX = event.clientX || (event.touches && event.touches[0].clientX);
    if (!clientX) return;

    const relX = ((clientX - rect.left) / rect.width) * width;
    if (relX < pad.left || relX > width - pad.right) {
      hideTooltip();
      return;
    }

    // Find nearest point by X
    let closest = parsed[0];
    let minDiff = Infinity;
    parsed.forEach((p) => {
      const diff = Math.abs(getX(p.idx) - relX);
      if (diff < minDiff) {
        minDiff = diff;
        closest = p;
      }
    });

    if (!closest) return;

    const ptX = getX(closest.idx);
    const ptY = closest.price !== null ? getY(closest.price) : height - pad.bottom;

    crosshairGroup.setAttribute("opacity", "1");
    crosshairLine.setAttribute("x1", ptX);
    crosshairLine.setAttribute("x2", ptX);
    crosshairDot.setAttribute("cx", ptX);
    crosshairDot.setAttribute("cy", ptY);

    // Tooltip position (relative to container)
    const containerX = (ptX / width) * rect.width;
    const containerY = (ptY / height) * rect.height;

    chartTooltip.style.left = `${containerX}px`;
    chartTooltip.style.top = `${containerY}px`;
    chartTooltip.hidden = false;

    const changeTxt = closest.changePercent !== null ? formatPercent(closest.changePercent) : "—";
    const changeClass = Number(closest.changePercent) >= 0 ? "gain-color" : "loss-color";
    const priceTxt = closest.price !== null ? formatPrice(closest.price) : "Unavailable (Source Zero)";

    chartTooltip.innerHTML = `
      <div style="font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">${escapeHtml(formatMonth(closest.month))}</div>
      <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; font-weight: 700; color: var(--accent-cyan);">${priceTxt}</div>
      <div style="display: flex; gap: 0.6rem; align-items: center; margin-top: 0.25rem; font-size: 0.76rem;">
        <span style="color: ${Number(closest.changePercent) >= 0 ? 'var(--gain-color)' : 'var(--loss-color)'}; font-weight: 700;">MoM: ${changeTxt}</span>
        <span style="color: var(--text-muted);">${statusBadge(closest.status)}</span>
      </div>
    `;
  }

  function hideTooltip() {
    if (crosshairGroup) crosshairGroup.setAttribute("opacity", "0");
    if (chartTooltip) chartTooltip.hidden = true;
  }

  chart.onmousemove = handlePointer;
  chart.ontouchmove = handlePointer;
  chart.onmouseleave = hideTooltip;
  chart.ontouchend = hideTooltip;
}

// --- Load Price History for Selected Product ---
async function loadPrices(productCode, fromMonth = "", toMonth = "") {
  productStatus.textContent = "Loading time-series…";
  productStatus.className = "status-pill status-loading";

  const params = new URLSearchParams({ limit: "200" });
  if (fromMonth) params.set("from_month", fromMonth);
  if (toMonth) params.set("to_month", toMonth);

  try {
    const data = await fetchJson(`/api/v1/products/${encodeURIComponent(productCode)}/prices?${params}`);
    currentPriceItems = data.items || [];

    const pName = data.product.product_name_en || productCode;
    chartTitle.textContent = `${pName} (${data.product.product_code})`;
    chartSubtitle.textContent = `Historical official price dynamics · ${data.total} observations loaded`;
    tableRowCount.textContent = `${data.items.length} of ${data.total} observations`;
    productStatus.textContent = `Active: ${pName}`;
    productStatus.className = "status-pill";

    if (!data.items.length) {
      pricesBody.innerHTML = `<tr><td colspan="5" class="empty-cell">No observations recorded in this date range.</td></tr>`;
      chartCard.hidden = true;
      return;
    }

    // Populate data table
    pricesBody.innerHTML = data.items.map((item) => {
      const isMissing = item.current_price_uzs_per_kg === null;
      const isUp = Number(item.change_percent) >= 0;
      const changeClass = item.change_percent === null ? "neutral" : (isUp ? "up" : "down");
      const arrow = item.change_percent === null ? "" : (isUp ? "▲ " : "▼ ");

      return `
        <tr>
          <td style="font-family: 'JetBrains Mono', monospace; font-weight: 600;">${escapeHtml(formatMonth(item.month_start))}</td>
          <td class="price-cell" style="font-weight: 700; color: ${isMissing ? 'var(--warning-color)' : 'var(--text-primary)'};">
            ${isMissing ? 'Unavailable' : formatPrice(item.current_price_uzs_per_kg)}
          </td>
          <td>${statusBadge(item.current_price_status)}</td>
          <td class="price-cell" style="color: var(--text-muted);">
            ${item.change_uzs_per_kg === null ? '—' : formatPrice(item.change_uzs_per_kg)}
          </td>
          <td style="text-align: right;">
            <span class="change-pill ${changeClass}">
              ${arrow}${formatPercent(item.change_percent) || '—'}
            </span>
          </td>
        </tr>
      `;
    }).join("");

    // Draw interactive SVG Chart
    drawInteractiveChart(data.items);
  } catch (error) {
    pricesBody.innerHTML = `<tr><td colspan="5" class="empty-cell">Error loading history: ${escapeHtml(error.message)}</td></tr>`;
    chartCard.hidden = true;
    productStatus.textContent = "Load error";
    productStatus.className = "status-pill status-error";
  }
}

// --- Event Listeners ---
productForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const code = productSelect.value;
  if (!code) return;
  loadPrices(
    code,
    monthInputToDate(document.getElementById("from-month").value),
    monthInputToDate(document.getElementById("to-month").value)
  );
});

productSelect.addEventListener("change", (e) => {
  if (e.target.value) {
    selectProduct(e.target.value);
  }
});

quickChips.addEventListener("click", (e) => {
  const btn = e.target.closest(".chip-btn");
  if (!btn) return;
  const code = btn.getAttribute("data-code");
  if (code) {
    selectProduct(code);
  }
});

resetFilterBtn.addEventListener("click", () => {
  document.getElementById("from-month").value = "";
  document.getElementById("to-month").value = "";
  if (currentProductCode) {
    loadPrices(currentProductCode);
  }
});

// --- Boot Application ---
initTheme();
loadOverview();
loadMovers();
loadProducts();
