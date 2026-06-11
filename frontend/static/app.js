let dashboardData = window.__TCCC_BOOTSTRAP__ || {};
let state = { ...(dashboardData.selections || {}) };
let loading = false;

const STORAGE_KEYS = Object.freeze({
  state: "tccc.app.state.v1",
  dashboard: "tccc.app.dashboard-cache.v1",
  ask: "tccc.app.ask-cache.v2",
});

const storage = getStorageDriver();
const els = {};
const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function getPageKey() {
  return String(document.body?.dataset?.page || window.__TCCC_PAGE__ || "");
}

function isAskPage() {
  return getPageKey() === "ask";
}

function isBrandDetailPage() {
  return getPageKey() === "brand-detail";
}

document.addEventListener("DOMContentLoaded", init);

document.addEventListener("DOMContentLoaded", init);

function init() {
  cacheElements();
  syncStateFromUrl();
  const hasPersistedState = hydrateState();

  // Clear any stale browser cache for filters
  if (!hasPersistedState) {
    // First visit: ensure clean state
    const cache = getDashboardCache();
    const keys = Object.keys(cache);
    if (keys.length > 10) {
      // Limit cache size to prevent stale entries
      const sorted = keys.sort();
      for (let i = 0; i < sorted.length - 5; i++) {
        delete cache[sorted[i]];
      }
      writeStoredJson(STORAGE_KEYS.dashboard, cache);
    }
  }

  bindEvents();
  seedInitialDashboardCache(hasPersistedState);
  renderAll();
  restoreAskState();
  void loadDashboard();
}

function syncStateFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);

  const urlBrand = urlParams.get("brand");
  const urlPeriod = urlParams.get("period");
  const urlYear = urlParams.get("year");
  const urlChannel = urlParams.get("channel");
  const urlCustomer = urlParams.get("customer");
  const urlRegion = urlParams.get("region");

  if (urlBrand) state.brand = urlBrand;
  if (urlPeriod) state.period = urlPeriod;
  if (urlYear) state.year = urlYear;
  if (urlChannel) state.channel = urlChannel;
  if (urlCustomer) state.customer = urlCustomer;
  if (urlRegion) state.region = urlRegion;
}

function cacheElements() {
  [
    "brandSelect",
    "yearSelect",
    "periodSelect",
    "breadcrumb",
    "channelSwitcher",
    "channelHeroTitle",
    "channelHeroSummary",
    "channelHeroMetrics",
    "nlForm",
    "nlInput",
    "nlAnswer",
    "pageTitle",
    "aiStatus",
    "kpiGrid",
    "periodBadge",
    "brandCards",
    "trendTitle",
    "monthCards",
    "monthTrend",
    "monthLegend",
    "channelCards",
    "customerTitle",
    "customerCards",
    "regionTitle",
    "regionCards",
    "rootTitle",
    "rootCauseChip",
    "rootCauseSummary",
    "rootCauseMetrics",
    "rootCauseReasons",
    "rootCauseDrivers",
    "rootCauseActions",
    "monthChannelBreakdown",
    "monthEmptyState",
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function getStorageDriver() {
  const candidates = [];
  if (typeof window !== "undefined") {
    try {
      candidates.push(window.localStorage);
    } catch (error) {
      void error;
    }
    try {
      candidates.push(window.sessionStorage);
    } catch (error) {
      void error;
    }
  }
  for (const candidate of candidates) {
    try {
      const probe = "__tccc_probe__";
      candidate.setItem(probe, "1");
      candidate.removeItem(probe);
      return candidate;
    } catch (error) {
      void error;
    }
  }
  return null;
}

function readStoredJson(key, fallback) {
  if (!storage) return fallback;
  try {
    const raw = storage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch (error) {
    void error;
    return fallback;
  }
}

function writeStoredJson(key, value) {
  if (!storage) return;
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch (error) {
    void error;
  }
}

function getDefaultYear() {
  return "ALL";
}

function normalizeState(nextState = {}) {
  const period = nextState.period === undefined || nextState.period === null ? "" : String(nextState.period);
  const year = nextState.year === undefined || nextState.year === null || nextState.year === "" ? "ALL" : String(nextState.year);
  const brand = nextState.brand === undefined || nextState.brand === null || nextState.brand === "" ? "ALL" : String(nextState.brand);
  const channel = nextState.channel === undefined || nextState.channel === null || nextState.channel === "" ? "TEG" : String(nextState.channel);
  const customer = nextState.customer === undefined || nextState.customer === null ? "" : String(nextState.customer);
  const region = nextState.region === undefined || nextState.region === null ? "" : String(nextState.region);
  const country = nextState.country === undefined || nextState.country === null ? dashboardData.country || "" : String(nextState.country);

  return {
    ...nextState,
    brand,
    year,
    period,
    channel,
    customer,
    region,
    country,
    period_label: period ? String(nextState.period_label || "") : "All Months",
  };
}

function buildDefaultState() {
  return normalizeState({
    ...(dashboardData.selections || {}),
    year: getDefaultYear(),
    period: "",
    period_label: "All Months",
  });
}

function hydrateState() {
  const persistedState = readStoredJson(STORAGE_KEYS.state, null);
  const hasPersistedState = persistedState && typeof persistedState === "object";
  state = normalizeState({
    ...buildDefaultState(),
    ...(hasPersistedState ? persistedState : {}),
  });

  const routeLockedPage = isBrandDetailPage() || getPageKey() === "channels";
  if (routeLockedPage) {
    const routeSelections = dashboardData.selections || {};
    state = normalizeState({
      ...state,
      brand: routeSelections.brand ?? state.brand,
      year: routeSelections.year ?? state.year,
      period: routeSelections.period ?? state.period,
      channel: routeSelections.channel ?? state.channel,
      customer: routeSelections.customer ?? state.customer,
      region: routeSelections.region ?? state.region,
      country: routeSelections.country ?? state.country,
    });
  }

  const cachedDashboard = getCachedDashboard(state);
  if (cachedDashboard) {
    dashboardData = cachedDashboard;
  }

  applyServerSelections(dashboardData.selections || {});
  persistState();
  return hasPersistedState;
}

function seedInitialDashboardCache(hasPersistedState) {
  if (hasPersistedState) return;
  setCachedDashboard(dashboardData, state);
}

function getDashboardCacheKey(snapshot = state) {
  return JSON.stringify({
    brand: String(snapshot.brand || ""),
    year: String(snapshot.year || ""),
    period: String(snapshot.period || ""),
    channel: String(snapshot.channel || ""),
    customer: String(snapshot.customer || ""),
    region: String(snapshot.region || ""),
  });
}

function getDashboardCache() {
  return readStoredJson(STORAGE_KEYS.dashboard, {});
}

function setCachedDashboard(payload, snapshot = state) {
  const cache = getDashboardCache();
  cache[getDashboardCacheKey(snapshot)] = payload;
  writeStoredJson(STORAGE_KEYS.dashboard, cache);
}

function getCachedDashboard(snapshot = state) {
  const cache = getDashboardCache();
  return cache[getDashboardCacheKey(snapshot)] || null;
}

function persistState() {
  writeStoredJson(STORAGE_KEYS.state, state);
}

function getAskCache() {
  return readStoredJson(STORAGE_KEYS.ask, { entries: {}, lastKey: "", draft: "" });
}

function setAskCache(cache) {
  writeStoredJson(STORAGE_KEYS.ask, cache);
}

function getAskCacheKey(prompt) {
  return JSON.stringify({
    prompt: String(prompt || "").trim(),
  });
}

function findAskCacheEntry(cache, key, prompt) {
  if (cache.entries?.[key]) {
    return cache.entries[key];
  }

  const normalizedPrompt = String(prompt || "").trim();
  return (
    Object.values(cache.entries || {}).find((entry) => String(entry?.prompt || "").trim() === normalizedPrompt) || null
  );
}

function restoreAskState() {
  if (!els.nlInput || !els.nlAnswer) return;
  const cache = getAskCache();
  if (cache.draft) {
    els.nlInput.value = cache.draft;
  }
  const entry = cache.lastKey ? findAskCacheEntry(cache, cache.lastKey, els.nlInput.value) : null;
  if (entry) {
    if (entry?.prompt && !els.nlInput.value.trim()) {
      els.nlInput.value = entry.prompt;
    }
    if (entry?.message) {
      showAssistantMessage(entry.message);
    }
  }
}

function persistAskDraft(value) {
  const cache = getAskCache();
  cache.draft = String(value || "");
  setAskCache(cache);
}

function persistAskResponse(prompt, message) {
  const cache = getAskCache();
  const key = getAskCacheKey(prompt);
  cache.entries = cache.entries || {};
  cache.entries[key] = {
    prompt: String(prompt || ""),
    message: String(message || ""),
    savedAt: Date.now(),
  };
  cache.lastKey = key;
  cache.draft = String(prompt || "");
  setAskCache(cache);
}

function getPeriodDisplayLabel() {
  return state.period ? state.period_label || "" : "All Months";
}

function applyServerSelections(selections = {}) {
  state = normalizeState({
    ...state,
    brand_label: selections.brand_label || state.brand_label || "",
    brand_subject: selections.brand_subject || state.brand_subject || "",
    channel_label: selections.channel_label || state.channel_label || "",
    channel_title: selections.channel_title || state.channel_title || "",
    channel_description: selections.channel_description || state.channel_description || "",
    month: selections.month || state.month || "",
    country: selections.country || state.country || dashboardData.country || "",
    period_label: state.period ? selections.period_label || state.period_label || "" : "All Months",
  });
}

function bindEvents() {
  // Helper handlers to keep behavior consistent
  const handleBrandChange = () => {
    clearFilterCache();
    state.brand = els.brandSelect.value;
    state.customer = "";
    state.region = "";
    persistState();
    updateUrlParams();
    loadDashboard();
  };

  const handleYearChange = () => {
    clearFilterCache();
    state.year = els.yearSelect.value;
    state.period = "";
    state.customer = "";
    state.region = "";
    persistState();
    updateUrlParams();
    loadDashboard();
  };

  const handlePeriodChange = () => {
    clearFilterCache();
    state.period = els.periodSelect.value;
    state.customer = "";
    state.region = "";
    persistState();
    updateUrlParams();
    loadDashboard();
  };

  // Brand select
  els.brandSelect?.addEventListener("change", handleBrandChange);
  els.brandSelect?.addEventListener("input", handleBrandChange);
  els.brandSelect?.addEventListener("keyup", handleBrandChange);
  els.brandSelect?.addEventListener("wheel", () => {
    // Wheel may change the focused select value in some browsers — re-run the handler shortly after
    setTimeout(handleBrandChange, 0);
  });

  // Year select
  els.yearSelect?.addEventListener("change", handleYearChange);
  els.yearSelect?.addEventListener("input", handleYearChange);
  els.yearSelect?.addEventListener("keyup", handleYearChange);
  els.yearSelect?.addEventListener("wheel", () => setTimeout(handleYearChange, 0));

  // Period select
  els.periodSelect?.addEventListener("change", handlePeriodChange);
  els.periodSelect?.addEventListener("input", handlePeriodChange);
  els.periodSelect?.addEventListener("keyup", handlePeriodChange);
  els.periodSelect?.addEventListener("wheel", () => setTimeout(handlePeriodChange, 0));

  // Card clicks (month/customer/region)
  els.monthCards?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-period]");
    if (!card) return;
    clearFilterCache();
    state.period = card.dataset.period;
    state.customer = "";
    state.region = "";
    persistState();
    updateUrlParams();
    loadDashboard();
  });

  els.customerCards?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-customer]");
    if (!card) return;
    clearFilterCache();
    state.customer = card.dataset.customer;
    state.region = "";
    persistState();
    updateUrlParams();
    loadDashboard();
  });

  els.regionCards?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-region]");
    if (!card) return;
    clearFilterCache();
    state.region = card.dataset.region;
    persistState();
    updateUrlParams();
    loadDashboard();
  });

  // NL form
  els.nlForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = els.nlInput?.value.trim() || buildDefaultPrompt();
    if (els.nlInput && !els.nlInput.value.trim()) {
      els.nlInput.value = prompt;
    }
    await submitPrompt(prompt);
  });

  els.nlInput?.addEventListener("input", () => {
    persistAskDraft(els.nlInput.value);
  });

  // Back/forward navigation
  window.addEventListener("popstate", () => {
    syncStateFromUrl();
    clearFilterCache();
    loadDashboard();
  });
}

function clearFilterCache() {
  const cache = getDashboardCache();
  const key = getDashboardCacheKey(state);
  if (cache && cache[key]) {
    delete cache[key];
    writeStoredJson(STORAGE_KEYS.dashboard, cache);
    console.log("[CACHE] Cleared browser cache for", key);
  }
}

function updateUrlParams() {
  const params = new URLSearchParams();
  if (state.brand) appendParam(params, "brand", state.brand);
  if (state.period) appendParam(params, "period", state.period);
  if (state.year) appendParam(params, "year", state.year);
  if (state.channel) appendParam(params, "channel", state.channel);
  if (state.customer) appendParam(params, "customer", state.customer);
  if (state.region) appendParam(params, "region", state.region);

  const newUrl = `${window.location.pathname}${params.toString() ? "?" + params.toString() : ""}`;
  window.history.pushState({}, "", newUrl);
}

async function loadDashboard() {
  if (loading) return;

  loading = true;
  document.body.classList.add("loading");

  const params = new URLSearchParams();
  appendParam(params, "brand", state.brand);
  appendParam(params, "period", state.period);
  appendParam(params, "year", state.year);
  appendParam(params, "channel", state.channel);
  appendParam(params, "customer", state.customer);
  appendParam(params, "region", state.region);

  try {
    // Always request server-side payload so all browsers use DB if available
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    dashboardData = await response.json();
    applyServerSelections(dashboardData.selections || {});
    persistState();
    // Update local cache after fetching so subsequent same-browser loads can reuse it
    setCachedDashboard(dashboardData, state);
    renderAll();
  } catch (error) {
    // If server fails, fall back to client cache (best-effort)
    const cachedDashboard = getCachedDashboard(state);
    if (cachedDashboard) {
      dashboardData = cachedDashboard;
      applyServerSelections(dashboardData.selections || {});
      persistState();
      renderAll();
      showAssistantMessage(`Server unavailable, using local cache.`);
    } else {
      showAssistantMessage(`Dashboard data could not be refreshed.\n${error.message}`);
    }
  } finally {
    loading = false;
    document.body.classList.remove("loading");
  }
}

function appendParam(params, key, value) {
  if (value !== undefined && value !== null && String(value).length) {
    params.append(key, value);
  }
}

function renderAll() {
  renderFilters();
  renderHeader();
  renderChannelSwitcher();
  renderChannelHero();
  renderKpis();
  renderBrandCards();
  renderMonthCards();
  renderTrend();
  renderPath();
  renderChannels();
  renderCustomers();
  renderRegions();
  renderRootCause();
  renderMonthBreakdown(); // Add this line
}

function renderFilters() {
  const filters = dashboardData.filters || {};
  const periods = filters.periods || [];
  const selectedYear = String(state.year || "");
  const lockedPage = isAskPage() || isBrandDetailPage();
  // Prepend "All" options and deduplicate if server already provides them
  const brandOptions = [
    { value: "ALL", label: "All Brands" },
    ...(filters.brands || [])
      .filter(b => b.name !== "All Brands" && b.value !== "" && b.value !== "ALL")
      .map((brand) => ({ value: brand.value ?? brand.name, label: brand.name }))
  ];

  const yearOptions = [
    { value: "ALL", label: "All Years" },
    ...(filters.years || [])
      .filter(y => y !== "All Years" && y !== "ALL")
      .map((year) => ({ value: year, label: year }))
  ];
  setOptions(els.brandSelect, brandOptions, state.brand);
  setOptions(els.yearSelect, yearOptions, state.year);
  const monthOptions = periods
    .filter((period) => !selectedYear || selectedYear === "ALL" || String(period.year) === selectedYear)
    .map((period) => ({ value: period.key, label: period.label }));
  setOptions(els.periodSelect, [{ value: "", label: "All Months" }, ...monthOptions], state.period);

  // Disable selects on locked pages and preserve selected values
  [els.brandSelect, els.yearSelect, els.periodSelect].forEach((select) => {
    if (!select) return;
    select.disabled = lockedPage;
    // Force value sync after DOM update
    if (select === els.brandSelect) select.value = String(state.brand || "");
    if (select === els.yearSelect) select.value = String(state.year || "");
    if (select === els.periodSelect) select.value = String(state.period || "");
  });
}

function setOptions(select, options, selectedValue) {
  if (!select) return;
  const selected = String(selectedValue || "");
  const next = options
    .map((option) => {
      const value = String(option.value);
      const isSelected = value === selected ? "selected" : "";
      return `<option value="${escapeAttr(value)}" ${isSelected}>${escapeHtml(option.label)}</option>`;
    })
    .join("");
  if (select.innerHTML !== next) {
    select.innerHTML = next;
  }
  select.value = selected;
}

function renderHeader() {
  const pageKey = String(document.body.dataset.page || "");
  const brandLabel = getBrandLabel();
  const channelLabel = getChannelLabel(state.channel);
  const periodLabel = getPeriodDisplayLabel();
  if (els.pageTitle) {
    if (pageKey === "ask") {
      els.pageTitle.textContent = "Ask AI";
    } else if (pageKey === "brand-detail") {
      els.pageTitle.textContent = `${brandLabel} detail`;
    } else if (pageKey === "dashboard" || pageKey === "all") {
      els.pageTitle.textContent = "Dashboard";
    } else if (pageKey === "analysis") {
      els.pageTitle.textContent = "Analysis Hub";
    } else if (pageKey === "customer") {
      els.pageTitle.textContent = "Customer Analysis";
    } else if (pageKey === "regional") {
      els.pageTitle.textContent = "Regional Analysis";
    } else if (pageKey === "channels") {
      els.pageTitle.textContent = `${channelLabel || "TEG"} share drilldown`;
    } else if (pageKey === "root") {
      els.pageTitle.textContent = `${brandLabel} root cause`;
    } else if (pageKey === "month") {
      els.pageTitle.textContent = `${brandLabel} trend in ${periodLabel}`;
    } else {
      els.pageTitle.textContent = `${brandLabel} performance in ${periodLabel}`;
    }
  }
  if (els.periodBadge) {
    els.periodBadge.textContent = periodLabel;
  }
}

function renderKpis() {
  const portfolio = dashboardData.portfolio || {};
  const isAllBrand = isAllBrandSelection();
  const brandLabel = getBrandLabel();
  const periodLabel = getPeriodDisplayLabel();
  const cards = isAllBrand
    ? [
      ["Market value share", formatPct(portfolio.brand_value_share_pct), brandLabel],
      ["Market volume share", formatPct(portfolio.brand_volume_share_pct), periodLabel],
      ["Growth", formatGrowth(portfolio.brand_growth_pct), "vs previous period"],
      ["Market size", formatMoney(portfolio.market_size_value), "category sales value"],
      ["Market rank", "-", "all brands view"],
    ]
    : [
      ["Brand value share", formatPct(portfolio.brand_value_share_pct), periodLabel],
      ["Brand volume share", formatPct(portfolio.brand_volume_share_pct), brandLabel],
      ["Growth", formatGrowth(portfolio.brand_growth_pct), "vs previous period"],
      ["Market size", formatMoney(portfolio.market_size_value), "category sales value"],
      ["Brand rank", portfolio.selected_brand_rank ? `#${portfolio.selected_brand_rank}` : "-", "within selected month"],
    ];

  if (!els.kpiGrid) return;
  els.kpiGrid.innerHTML = cards
    .map(
      ([label, value, note]) => `
        <article class="kpi-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(note)}</small>
        </article>
      `
    )
    .join("");
}

function renderBrandCards() {
  if (!els.brandCards) return;
  const cards = dashboardData.portfolio?.brand_cards || [];
  const maxShare = Math.max(...cards.map((card) => Number(card.value_share_pct) || 0), 1);
  const isAllBrand = isAllBrandSelection();
  const pageKey = getPageKey();
  els.brandCards.innerHTML = cards
    .map((card) => {
      const active = !isAllBrand && String(card.brand).toUpperCase() === String(state.brand).toUpperCase();
      const width = Math.max(((Number(card.value_share_pct) || 0) / maxShare) * 100, 5);
      if (pageKey === "brand") {
        const href = buildBrandDetailHref(card.brand);
        return `
          <a class="brand-card ${active ? "active" : ""}" href="${escapeAttr(href)}">
            <span class="rank">#${card.rank}</span>
            <strong>${escapeHtml(card.brand)}</strong>
            <span class="bar"><i style="width:${width}%"></i></span>
            <span class="card-meta">${formatPct(card.value_share_pct)} value / ${formatPct(card.volume_share_pct)} volume</span>
          </a>
        `;
      }
      return `
        <button type="button" class="brand-card ${active ? "active" : ""}" data-brand="${escapeAttr(card.brand)}">
          <span class="rank">#${card.rank}</span>
          <strong>${escapeHtml(card.brand)}</strong>
          <span class="bar"><i style="width:${width}%"></i></span>
          <span class="card-meta">${formatPct(card.value_share_pct)} value / ${formatPct(card.volume_share_pct)} volume</span>
        </button>
      `;
    })
    .join("");

  els.brandCards.querySelectorAll("[data-brand]").forEach((button) => {
    button.addEventListener("click", () => {
      state.brand = button.dataset.brand;
      state.customer = "";
      state.region = "";
      persistState();
      updateUrlParams();
      loadDashboard();
    });
  });
}

function renderMonthCards() {
  if (!els.monthCards) return;
  const periods = dashboardData.periods || [];
  const isAllBrand = isAllBrandSelection();
  els.monthCards.innerHTML = periods
    .map((period) => {
      const active = period.key === state.period;
      const metricLabel = isAllBrand ? "Market value" : "Value share";
      const metricValue = isAllBrand ? formatMoney(period.market_value) : formatPct(period.value_share);
      const growthLabel = isAllBrand ? "Market growth" : "Growth";
      return `
        <button type="button" class="month-card ${active ? "active" : ""}" data-period="${escapeAttr(period.key)}">
          <strong>${escapeHtml(period.short)}</strong>
          <span>${escapeHtml(String(period.year))}</span>
          <small>${escapeHtml(metricLabel)}: ${escapeHtml(metricValue)}</small>
          <small>${formatGrowth(period.growth)} ${escapeHtml(growthLabel.toLowerCase())}</small>
        </button>
      `;
    })
    .join("");
}

function renderTrend() {
  const isAllBrand = isAllBrandSelection();
  const brandLabel = getBrandLabel();
  if (els.trendTitle) els.trendTitle.textContent = `${isAllBrand ? "Market" : brandLabel} trend`;
  if (!els.monthTrend) return;
  const periods = dashboardData.periods || [];
  const valueSeries = periods.map((period) => (isAllBrand ? period.market_value || 0 : period.value_share || 0));
  const volumeSeries = periods.map((period) => (isAllBrand ? period.market_volume || 0 : period.volume_share || 0));
  const activeIndex = state.period ? Math.max(0, periods.findIndex((period) => period.key === state.period)) : Math.max(0, periods.length - 1);
  els.monthTrend.innerHTML = buildSparkline({
    labels: periods.map((period) => period.short),
    valueSeries,
    volumeSeries,
    activeIndex,
  });
  if (els.monthLegend) {
    els.monthLegend.innerHTML = `
      <span><i class="dot red"></i>${isAllBrand ? "Market value" : "Value share"}</span>
      <span><i class="dot black"></i>${isAllBrand ? "Market volume" : "Volume share"}</span>
    `;
  }
}

function renderPath() {
  if (isAskPage()) {
    if (els.breadcrumb) {
      els.breadcrumb.innerHTML = `
        <span>Prompt-only mode</span>
        <span>Header filters are ignored</span>
      `;
    }
    return;
  }
  const chips = [getBrandLabel(), getPeriodDisplayLabel(), getChannelLabel(state.channel), state.customer, state.region].filter(Boolean);
  const html = chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("");
  if (els.breadcrumb) els.breadcrumb.innerHTML = html;
}

function renderChannelSwitcher() {
  if (!els.channelSwitcher) return;

  const pageKey = String(document.body.dataset.page || "");
  const allowedPages = ["channels", "dashboard", "analysis", "customer", "regional", "root"];
  if (!allowedPages.includes(pageKey)) return;

  const channels = dashboardData.filters?.channels || [];
  const currentChannel = state.channel || "TEG";

  els.channelSwitcher.innerHTML = channels
    .map((channel) => {
      const channelKey = channel.key;
      const isActive = getChannelKey(channelKey) === getChannelKey(currentChannel);
      const href = buildChannelHrefWithState(channelKey);

      return `
        <a class="header-pill channel-switch ${isActive ? "active" : ""}" 
           href="${escapeAttr(href)}" 
           data-channel="${escapeAttr(channelKey)}"
           ${isActive ? 'aria-current="page"' : ''}>
          ${escapeHtml(channel.label)}
        </a>
      `;
    })
    .join("");

  els.channelSwitcher.querySelectorAll(".channel-switch").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const channelKey = link.dataset.channel;
      if (channelKey && getChannelKey(channelKey) !== getChannelKey(currentChannel)) {
        state.channel = channelKey;
        state.customer = "";
        state.region = "";
        persistState();
        updateUrlParams();
        loadDashboard();
      }
    });
  });
}

function buildChannelHrefWithState(channel) {
  const params = new URLSearchParams();

  if (state.brand) appendParam(params, "brand", state.brand);
  if (state.period) appendParam(params, "period", state.period);
  if (state.year) appendParam(params, "year", state.year);
  if (state.customer) appendParam(params, "customer", state.customer);
  if (state.region) appendParam(params, "region", state.region);

  const queryString = params.toString();
  const channelKey = getChannelKey(channel);

  let basePath;
  if (channelKey === "PFM") basePath = "/analysis/pfm";
  else if (channelKey === "L&T") basePath = "/analysis/lt";
  else if (channelKey === "HORECA") basePath = "/analysis/horeca";
  else basePath = "/analysis/channels/teg";

  return queryString ? `${basePath}?${queryString}` : basePath;
}

function renderChannelHero() {
  const selected = getSelectedChannelData();
  const channelLabel = getChannelLabel(state.channel);
  const periodLabel = getPeriodDisplayLabel();
  if (els.channelHeroTitle) {
    els.channelHeroTitle.textContent = `${channelLabel} share drilldown`;
  }

  if (!selected || !hasChannelData(selected)) {
    if (els.channelHeroSummary) {
      els.channelHeroSummary.textContent = `${channelLabel} has no mapped rows in the selected workbook.`;
    }
    if (els.channelHeroMetrics) {
      els.channelHeroMetrics.innerHTML = `<div class="empty-state channel-empty">No mapped data is available for this channel in the current workbook.</div>`;
    }
    return;
  }

  if (els.channelHeroSummary) {
    els.channelHeroSummary.textContent = `${channelLabel} contributes ${formatPct(selected.value_share)} value share and ${formatPct(selected.volume_share)} volume share in ${periodLabel}. Revenue is ${formatMoney(selected.revenue)} with ${formatGrowth(selected.growth)} growth versus the previous period. Use the customer list to find the retailer or account driving the move, then click a region to check whether distribution, pricing, or competitor pressure is behind the drop.`;
  }
  if (els.channelHeroMetrics) {
    els.channelHeroMetrics.innerHTML = [
      ["Value share", formatPct(selected.value_share), "Within the selected market slice"],
      ["Volume share", formatPct(selected.volume_share), "Units contribution in the cut"],
      ["Growth", formatGrowth(selected.growth), "Versus the previous period"],
      ["Revenue", formatMoney(selected.revenue), "Selected channel revenue"],
      ["Share of brand", formatPct(selected.share_of_brand), "Channel contribution to the brand"],
    ]
      .map(
        ([label, value, note]) => `
          <article class="metric-card">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
            <small>${escapeHtml(note)}</small>
          </article>
        `
      )
      .join("");
  }
}

function renderChannels() {
  if (!els.channelCards) return;
  const channels = dashboardData.channels || [];
  const currentChannel = state.channel || "TEG";
  const periods = dashboardData.periods || [];

  // If state.period is empty (All Months), use the latest period from recent trends
  const activePeriodKey = state.period || (periods.length > 0 ? periods[periods.length - 1].key : "");
  // Find the label for the active period to display
  const activePeriod = periods.find(p => p.key === activePeriodKey) || (periods.length > 0 ? periods[periods.length - 1] : null);
  const activePeriodLabel = activePeriod ? activePeriod.label : "All Months";

  els.channelCards.innerHTML = channels
    .map((channel) => {
      const channelKey = channel.key;
      const isActive = getChannelKey(channelKey) === getChannelKey(currentChannel);
      const hasData = hasChannelData(channel);

      return `
        <button type="button" 
                class="channel-tab ${isActive ? "active" : ""} ${hasData ? "" : "is-empty"}" 
                data-channel="${escapeAttr(channelKey)}"
                aria-pressed="${isActive}">
          <span class="focus-badge">${escapeHtml(activePeriodLabel)}</span>
          <strong>${hasData ? formatPct(channel.value_share) : "—"}</strong>
          <small>${escapeHtml(channel.title)}</small>
          <em>${hasData ? escapeHtml(channel.description) : "No mapped data in this workbook."}</em>
          <span class="channel-meta">${hasData ? `${formatGrowth(channel.growth)} / ${formatMoney(channel.revenue)}` : "No channel rows"}</span>
        </button>
      `;
    })
    .join("");

  els.channelCards.querySelectorAll("[data-channel]").forEach((button) => {
    button.addEventListener("click", () => {
      const newChannel = button.dataset.channel;
      if (newChannel && getChannelKey(newChannel) !== getChannelKey(currentChannel)) {
        state.channel = newChannel;
        state.customer = "";
        state.region = "";
        persistState();
        updateUrlParams();
        loadDashboard();
      }
    });
  });
}

function renderCustomers() {
  if (els.customerTitle) els.customerTitle.textContent = `${getChannelLabel(state.channel)} customers`;
  if (!els.customerCards) return;
  const rows = dashboardData.customers || [];
  els.customerCards.innerHTML = rows.length
    ? rows.map((row) => renderDataRow(row, "customer", row.name === state.customer)).join("")
    : `<div class="empty-state">No customer rows for this cut.</div>`;
}

function renderRegions() {
  if (els.regionTitle) els.regionTitle.textContent = `${state.customer || "Selected customer"} regions`;
  if (!els.regionCards) return;
  const rows = dashboardData.regions || [];
  els.regionCards.innerHTML = rows.length
    ? rows.map((row) => renderDataRow(row, "region", row.name === state.region)).join("")
    : `<div class="empty-state">No regional rows for this cut.</div>`;
}

function renderDataRow(row, type, active) {
  const metricLabel = type === "region" ? "Share" : "Value share";
  const metric = type === "region" ? row.market_share : row.value_share;
  const dataAttr = type === "region" ? "data-region" : "data-customer";
  return `
    <button type="button" class="data-row ${active ? "active" : ""}" ${dataAttr}="${escapeAttr(row.name)}">
      <span>
        <strong>${escapeHtml(row.name)}</strong>
        <small>${metricLabel}: ${formatPct(metric)} / Growth: ${formatGrowth(row.growth)}</small>
      </span>
      <span>
        <b>${formatMoney(row.revenue)}</b>
        <small>${type === "region" ? `Distribution ${formatPct(row.distribution)}` : `Volume ${formatValue(row.volume)}`}</small>
      </span>
    </button>
  `;
}

function renderRootCause() {
  const root = dashboardData.root_cause || {};
  if (els.rootTitle) {
    els.rootTitle.textContent = `${state.region || "Region"} root cause`;
  }
  if (els.rootCauseChip) {
    els.rootCauseChip.textContent = `${getChannelLabel(state.channel)} / ${state.customer || "-"} / ${state.region || "-"}`;
  }
  if (els.rootCauseSummary) {
    els.rootCauseSummary.textContent = root.summary || "Select a customer and region to generate the root-cause view.";
  }
  if (els.rootCauseMetrics) {
    els.rootCauseMetrics.innerHTML = (root.metrics || [])
      .map(
        (metric) => `
          <article class="metric-card">
            <span>${escapeHtml(metric.label)}</span>
            <strong>${escapeHtml(metric.current)}</strong>
            <small>${escapeHtml(metric.delta)} vs ${escapeHtml(metric.previous)}</small>
          </article>
        `
      )
      .join("");
  }
  renderInsightList(els.rootCauseReasons, root.reasons || [], "impact");
  renderInsightList(els.rootCauseDrivers, root.drivers || [], "driver");
  renderInsightList(els.rootCauseActions, root.actions || [], "action");
}

function renderInsightList(target, rows, kind) {
  if (!target) return;
  target.innerHTML = rows.length
    ? rows
      .map(
        (row) => `
            <article class="insight ${kind}">
              <strong>${escapeHtml(row.label)}</strong>
              <small>${escapeHtml(row.detail || row.impact || "")}</small>
            </article>
          `
      )
      .join("")
    : `<div class="empty-state">No items for this cut.</div>`;
}

function renderMonthBreakdown() {
  if (!els.monthChannelBreakdown) return;

  const channels = dashboardData.channels || [];
  const hasData = channels.some(c => hasChannelData(c));
  const periods = dashboardData.periods || [];

  if (!hasData) {
    if (els.monthEmptyState) els.monthEmptyState.style.display = "block";
    els.monthChannelBreakdown.innerHTML = "";
    return;
  }

  // If state.period is empty (All Months), use the latest period from dashboardData.periods if available
  const activePeriodKey = state.period || (periods.length > 0 ? periods[periods.length - 1].key : "");
  // Find the label for the active period
  const activePeriod = periods.find(p => p.key === activePeriodKey) || (periods.length > 0 ? periods[periods.length - 1] : null);
  const activePeriodLabel = activePeriod ? activePeriod.label : "All Months";

  if (els.monthEmptyState) els.monthEmptyState.style.display = "none";

  const brandLabel = getBrandLabel();

  els.monthChannelBreakdown.innerHTML = channels
    .map((channel) => {
      const isNegative = Number(channel.growth) < 0;
      return `
        <article class="metric-card breakdown-card">
          <div class="breakdown-head">
            <span class="breakdown-label">${escapeHtml(channel.label)}</span>
            <span class="breakdown-rank">${formatPct(channel.value_share)} share</span>
          </div>
          <div class="breakdown-body">
            <strong>${formatGrowth(channel.growth)}</strong>
            <small>Growth in ${escapeHtml(activePeriodLabel)}</small>
          </div>
          <div class="breakdown-footer">
            <span>of ${escapeHtml(brandLabel)}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

async function submitPrompt(prompt) {
  const cachedKey = getAskCacheKey(prompt);
  const cached = getAskCache();
  const cachedEntry = findAskCacheEntry(cached, cachedKey, prompt);
  if (cachedEntry?.message) {
    persistAskDraft(prompt);
    showAssistantMessage(cachedEntry.message);
    cached.lastKey = cachedKey;
    cached.draft = String(prompt || "");
    setAskCache(cached);
    return;
  }

  showAssistantMessage("Analyzing...");
  const form = new FormData();
  form.append("prompt", prompt);
  if (isAskPage()) {
    form.append("mode", "ask");
  } else {
    appendForm(form, "brand", state.brand);
    appendForm(form, "month", state.period);
    appendForm(form, "year", state.year);
    appendForm(form, "channel", state.channel);
    appendForm(form, "customer", state.customer);
    appendForm(form, "region", state.region);
    appendForm(form, "country", state.country || dashboardData.country);
  }

  try {
    const response = await fetch("/api/query", { method: "POST", body: form });
    const json = await response.json();
    const message = formatAssistantResponse(json);
    showAssistantMessage(message);
    persistAskDraft(prompt);
    persistAskResponse(prompt, message);
  } catch (error) {
    showAssistantMessage(`The AI assistant is currently unavailable. Please check your connection or try again later.`);
    console.error("AI Query Error:", error);
  }
}

function appendForm(form, key, value) {
  if (value !== undefined && value !== null && String(value).length) {
    form.append(key, value);
  }
}

function isAllBrandSelection() {
  const value = String(state.brand || "").trim().toUpperCase();
  return !value || value === "ALL";
}

function getBrandLabel() {
  return state.brand_label || (isAllBrandSelection() ? "All Brands" : String(state.brand || ""));
}

function getBrandSubject() {
  return state.brand_subject || (isAllBrandSelection() ? "the market" : getBrandLabel());
}

function getCountryLabel() {
  return state.country || dashboardData.country || "the market";
}

function normalizeChannelToken(value) {
  return String(value ?? "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "");
}

function getChannelDefinition(value) {
  const target = normalizeChannelToken(value);
  const channels = dashboardData.filters?.channels || [];
  return (
    channels.find((channel) => {
      const key = normalizeChannelToken(channel.key);
      const label = normalizeChannelToken(channel.label);
      return target && (target === key || target === label);
    }) || channels[0] || null
  );
}

function getChannelKey(value) {
  return getChannelDefinition(value)?.key || "TEG";
}

function getChannelLabel(value) {
  return getChannelDefinition(value)?.label || String(value || "TEG");
}

function getSelectedChannelData() {
  const channels = dashboardData.channels || [];
  const selectedKey = getChannelKey(state.channel);
  return (
    channels.find((channel) => getChannelKey(channel.key) === selectedKey || normalizeChannelToken(channel.key) === normalizeChannelToken(selectedKey)) ||
    channels[0] ||
    null
  );
}

function hasChannelData(channel) {
  if (!channel) return false;
  return ["value_share", "volume_share", "revenue", "share_of_brand"].some((key) => Math.abs(Number(channel[key]) || 0) > 0);
}

function buildDefaultPrompt() {
  const brandSubject = getBrandSubject();
  const countryLabel = getCountryLabel();
  return `How is ${brandSubject} performing in ${countryLabel} and what are the draggers and drivers?`;
}

function buildBrandDetailHref(brand) {
  const params = new URLSearchParams();
  appendParam(params, "period", state.period);
  appendParam(params, "year", state.year);
  appendParam(params, "channel", state.channel);
  appendParam(params, "customer", state.customer);
  appendParam(params, "region", state.region);
  const query = params.toString();
  const brandPath = encodeURIComponent(String(brand || ""));
  return query ? `/brand-performance/${brandPath}?${query}` : `/brand-performance/${brandPath}`;
}

function formatAssistantResponse(json) {
  if (json.ask_mode) {
    const lines = [];
    const answer = json.pandasai_answer || json.summary || "No answer was generated.";
    lines.push(answer);
    if (json.ai_status && !json.ai_status.gemini_configured) {
      lines.push("", "Note: AI analysis is currently running in basic mode using workbook data only.");
    }
    return lines.join("\n");
  }

  const lines = [];
  if (json.summary) lines.push(json.summary);
  if (json.root_cause) lines.push("", json.root_cause);
  addList(lines, "Draggers", json.draggers);
  addList(lines, "Drivers", json.drivers);
  addList(
    lines,
    "Recommended actions",
    (json.actions || []).map((item) => (typeof item === "string" ? item : `${item.label}: ${item.detail}`))
  );
  if (json.pandasai_answer) lines.push("", "AI assistant:", json.pandasai_answer);
  if (json.ai_status && !json.ai_status.gemini_configured) {
    lines.push("", "Note: This response uses automated workbook analytics as the AI service is not yet configured.");
  }
  return lines.join("\n");
}

function addList(lines, label, items) {
  if (!Array.isArray(items) || !items.length) return;
  lines.push("", `${label}:`);
  items.forEach((item, index) => lines.push(`${index + 1}. ${item}`));
}

function showAssistantMessage(message) {
  if (els.nlAnswer) els.nlAnswer.textContent = message;
}

function formatPct(value) {
  return `${formatDecimal(value)}%`;
}

function formatGrowth(value) {
  const numeric = Number(value) || 0;
  return `${numeric > 0 ? "+" : ""}${formatDecimal(numeric)}%`;
}

function formatMoney(value) {
  return `R${compactFormat.format(Number(value) || 0)}`;
}

function formatValue(value) {
  return compactFormat.format(Number(value) || 0);
}

function formatDecimal(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0.0";
  return numeric.toFixed(1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function buildSparkline({ labels, valueSeries, volumeSeries, activeIndex }) {
  if (!labels.length) return `<div class="empty-state">No trend data.</div>`;
  const width = 720;
  const height = 170;
  const pad = 28;
  const values = [...valueSeries, ...volumeSeries];
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const x = (index) => pad + (index * (width - pad * 2)) / Math.max(labels.length - 1, 1);
  const y = (value) => height - pad - ((value - min) / range) * (height - pad * 2);
  const points = (series) => series.map((value, index) => [x(index), y(value)]);
  const toPath = (coords) => coords.map(([px, py], index) => `${index ? "L" : "M"} ${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
  const valuePoints = points(valueSeries);
  const volumePoints = points(volumeSeries);
  const activeX = x(activeIndex);

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trend chart">
      <line x1="${pad}" x2="${width - pad}" y1="${height - pad}" y2="${height - pad}" class="axis"></line>
      <line x1="${activeX}" x2="${activeX}" y1="${pad}" y2="${height - pad}" class="focus-line"></line>
      <path d="${toPath(valuePoints)}" class="value-line"></path>
      <path d="${toPath(volumePoints)}" class="volume-line"></path>
      ${valuePoints.map(([px, py], index) => `<circle cx="${px}" cy="${py}" r="${index === activeIndex ? 5 : 3}" class="value-dot"></circle>`).join("")}
      ${labels.map((label, index) => `<text x="${x(index)}" y="${height - 6}" text-anchor="middle">${escapeHtml(label)}</text>`).join("")}
    </svg>
  `;
}