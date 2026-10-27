const overviewStatus = document.getElementById("overview-status");
const overviewMetrics = document.getElementById("overview-metrics");
const moversStatus = document.getElementById("movers-status");
const moversTables = document.getElementById("movers-tables");
const productSelect = document.getElementById("product-select");
const productForm = document.getElementById("product-form");
const productStatus = document.getElementById("product-status");
const pricesBody = document.getElementById("prices-body");
const chartCard = document.getElementById("chart-card");
const chart = document.getElementById("price-chart");

function formatPrice(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(number) + " UZS/kg";
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  const prefix = number > 0 ? "+" : "";
  return prefix + number.toFixed(2) + "%";
}

function formatMonth(isoDate) {
  if (!isoDate) {
    return "—";
  }
  return isoDate.slice(0, 7);
}

function monthInputToDate(value) {
  if (!value) {
    return "";
  }
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

function setError(element, message) {
  element.classList.add("error");
  element.textContent = message;
}

function clearStatus(element) {
  element.classList.remove("error");
  element.textContent = "";
}

async function loadOverview() {
  try {
    const data = await fetchJson("/api/v1/overview");
    overviewStatus.hidden = true;
    overviewMetrics.hidden = false;
    overviewMetrics.innerHTML = [
      ["Latest month", formatMonth(data.latest_month)],
      ["Products", data.product_count],
      ["Available observations", data.available_observations],
      ["Unavailable observations", data.unavailable_observations],
      ["Latest source snapshot", data.latest_source_snapshot || "Not recorded"],
      [
        "Source fetched (UTC)",
        data.latest_source_fetched_at_utc
          ? new Date(data.latest_source_fetched_at_utc).toISOString().replace(".000Z", "Z")
          : "Not recorded",
      ],
    ].map(([label, value]) => (
      `<div><dt>${label}</dt><dd>${value}</dd></div>`
    )).join("");
  } catch (error) {
    setError(overviewStatus, error.message);
  }
}

function moverRow(item) {
  const changeClass = Number(item.yoy_change_percent) >= 0 ? "up" : "down";
  return `
    <tr>
      <td>${item.rank}</td>
      <td>${item.product_name_en || item.product_code}<br><code>${item.product_code}</code></td>
      <td>${formatPrice(item.current_price_uzs_per_kg) || "—"}</td>
      <td>${formatPrice(item.price_12_months_ago_uzs_per_kg) || "—"}</td>
      <td class="${changeClass}">${formatPercent(item.yoy_change_percent) || "—"}</td>
    </tr>
  `;
}

async function loadMovers() {
  try {
    const data = await fetchJson("/api/v1/analytics/latest-movers");
    if (!data.latest_month) {
      moversStatus.textContent = "No modeled months are available yet.";
      return;
    }
    moversStatus.textContent = `Comparison: ${formatMonth(data.latest_month)} vs ${formatMonth(data.comparison_month)}.`;
    document.getElementById("increases-body").innerHTML =
      data.increases.map(moverRow).join("") || `<tr><td colspan="5">No comparable increases.</td></tr>`;
    document.getElementById("decreases-body").innerHTML =
      data.decreases.map(moverRow).join("") || `<tr><td colspan="5">No comparable decreases.</td></tr>`;
    moversTables.hidden = false;
  } catch (error) {
    setError(moversStatus, error.message);
  }
}

async function loadProducts() {
  try {
    const data = await fetchJson("/api/v1/products?limit=200");
    if (!data.items.length) {
      productSelect.innerHTML = `<option value="">No products found</option>`;
      productStatus.textContent = "The product list is empty.";
      return;
    }
    productSelect.innerHTML = data.items.map((product) => (
      `<option value="${product.product_code}">${product.product_name_en || product.product_code} (${product.product_code})</option>`
    )).join("");
    await loadPrices(data.items[0].product_code);
  } catch (error) {
    productSelect.innerHTML = `<option value="">Unavailable</option>`;
    setError(productStatus, error.message);
  }
}

function statusLabel(status) {
  if (status === "observed") return "Observed";
  if (status === "zero_marked_unavailable") return "Source zero, unavailable";
  if (status === "missing_in_source") return "Missing in source";
  return status || "—";
}

function drawChart(items) {
  const width = 720;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 36, left: 64 };
  const values = items
    .map((item, index) => ({
      index,
      month: item.month_start,
      price: item.current_price_uzs_per_kg === null ? null : Number(item.current_price_uzs_per_kg),
    }));
  const numeric = values.filter((item) => item.price !== null && !Number.isNaN(item.price));
  chart.innerHTML = "";
  if (numeric.length === 0) {
    chartCard.hidden = true;
    return;
  }
  chartCard.hidden = false;
  const min = Math.min(...numeric.map((item) => item.price));
  const max = Math.max(...numeric.map((item) => item.price));
  const span = max - min || 1;
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (values.length === 1 ? innerWidth / 2 : (index / (values.length - 1)) * innerWidth);
  const y = (price) => pad.top + innerHeight - ((price - min) / span) * innerHeight;

  const axis = document.createElementNS("http://www.w3.org/2000/svg", "g");
  axis.innerHTML = `
    <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#5c6573" />
    <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#5c6573" />
    <text x="8" y="${pad.top + 4}" fill="#5c6573" font-size="12">${formatPrice(max)}</text>
    <text x="8" y="${height - pad.bottom}" fill="#5c6573" font-size="12">${formatPrice(min)}</text>
  `;
  chart.appendChild(axis);

  let segment = [];
  const flush = () => {
    if (segment.length < 2) {
      if (segment.length === 1) {
        const point = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        point.setAttribute("cx", x(segment[0].index));
        point.setAttribute("cy", y(segment[0].price));
        point.setAttribute("r", "3.5");
        point.setAttribute("fill", "#1f5c4d");
        chart.appendChild(point);
      }
      segment = [];
      return;
    }
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute(
      "d",
      segment.map((item, offset) => `${offset === 0 ? "M" : "L"} ${x(item.index)} ${y(item.price)}`).join(" ")
    );
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#1f5c4d");
    path.setAttribute("stroke-width", "2.5");
    chart.appendChild(path);
    segment = [];
  };

  values.forEach((item) => {
    if (item.price === null || Number.isNaN(item.price)) {
      flush();
      return;
    }
    segment.push(item);
  });
  flush();
}

async function loadPrices(productCode, fromMonth = "", toMonth = "") {
  clearStatus(productStatus);
  productStatus.textContent = "Loading price history…";
  const params = new URLSearchParams({ limit: "200" });
  if (fromMonth) params.set("from_month", fromMonth);
  if (toMonth) params.set("to_month", toMonth);
  try {
    const data = await fetchJson(`/api/v1/products/${encodeURIComponent(productCode)}/prices?${params}`);
    if (!data.items.length) {
      pricesBody.innerHTML = `<tr><td colspan="5">No observations in this date range.</td></tr>`;
      chartCard.hidden = true;
      productStatus.textContent = `${data.product.product_name_en || productCode} has no rows for the selected range.`;
      return;
    }
    pricesBody.innerHTML = data.items.map((item) => {
      const missing = item.current_price_uzs_per_kg === null;
      const change = formatPercent(item.change_percent);
      const changeClass = item.change_percent === null ? "missing" : (Number(item.change_percent) < 0 ? "down" : "up");
      return `
        <tr>
          <td>${formatMonth(item.month_start)}</td>
          <td class="${missing ? "missing" : ""}">${missing ? "Unavailable" : formatPrice(item.current_price_uzs_per_kg)}</td>
          <td>${statusLabel(item.current_price_status)}</td>
          <td>${item.change_uzs_per_kg === null ? "—" : formatPrice(item.change_uzs_per_kg)}</td>
          <td class="${changeClass}">${change || "—"}</td>
        </tr>
      `;
    }).join("");
    drawChart(data.items);
    productStatus.textContent = `${data.product.product_name_en || productCode} · ${data.total} months`;
  } catch (error) {
    pricesBody.innerHTML = `<tr><td colspan="5">Price history could not be loaded.</td></tr>`;
    chartCard.hidden = true;
    setError(productStatus, error.message);
  }
}

productForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const productCode = productSelect.value;
  if (!productCode) {
    return;
  }
  loadPrices(
    productCode,
    monthInputToDate(document.getElementById("from-month").value),
    monthInputToDate(document.getElementById("to-month").value)
  );
});

loadOverview();
loadMovers();
loadProducts();
