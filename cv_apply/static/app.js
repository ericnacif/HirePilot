"use strict";

const LS_PREFIX = "hirepilot.";
const LS_LEGACY_PREFIX = "vagamatch.";

let PROFILE = null;
let GUEST_MODE = false;
let LAST_JOBS = [];
let LAST_SOURCES = [];
let LAST_META = {};
let CURRENT_PAGE = 1;
const PAGE_SIZE = 10;
let SORT_KEY = "score";
let ONLY_FAVORITES = false;
let FILTER_SOURCE = "";
let HIDE_APPLIED = false;
let SEARCH_ABORT = null;
let SEARCH_GEN = 0;
let SEARCH_LIVE = {};

const PORTAL_WIZARD_KEY = LS_PREFIX + "portalWizardDismissed";
const BROWSER_SOURCE_KEYS = new Set(["linkedin", "catho", "vagascom", "infojobs", "trabalhabrasil"]);
let APP_META = {};
let AUTH_REQUIRED = false;
const PIPELINE_COLUMNS = [
  { id: "interesse", label: "Interesse" },
  { id: "candidatado", label: "Candidatado" },
  { id: "entrevista", label: "Entrevista" },
  { id: "oferta", label: "Oferta" },
  { id: "recusado", label: "Recusado" },
];

function migrateLegacyLocalStorage() {
  if (localStorage.getItem(LS_PREFIX + "migrated")) return;
  const keys = [
    "filters", "favorites", "applied", "theme", "savedSearches",
    "onboarded", "updateDismiss",
  ];
  for (const k of keys) {
    const oldKey = LS_LEGACY_PREFIX + k;
    const newKey = LS_PREFIX + k;
    const val = localStorage.getItem(oldKey);
    if (val === null) continue;
    if (localStorage.getItem(newKey) === null) localStorage.setItem(newKey, val);
    localStorage.removeItem(oldKey);
  }
  localStorage.setItem(LS_PREFIX + "migrated", "1");
}
migrateLegacyLocalStorage();

const FILTERS_KEY = LS_PREFIX + "filters";
const FAVORITES_KEY = LS_PREFIX + "favorites";
const APPLIED_KEY = LS_PREFIX + "applied";
const THEME_KEY = LS_PREFIX + "theme";
const SAVED_KEY = LS_PREFIX + "savedSearches";
const SIMPLE_MODE_KEY = LS_PREFIX + "simpleMode";
const LAST_SEARCH_KEY = LS_PREFIX + "lastSearch";
const ONBOARD_KEY = LS_PREFIX + "onboarded";
const API_ONLY_SOURCES = ["gupy", "indeed", "solides", "trampos", "jooble", "careerjet", "empregoscom"];

const SENIORITY_PRO = [
  { value: "", label: "Não informado" },
  { value: "estagiário", label: "Estagiário" },
  { value: "júnior", label: "Júnior" },
  { value: "pleno", label: "Pleno" },
  { value: "sênior", label: "Sênior" },
];
const SENIORITY_SIMPLE = [
  { value: "", label: "Não sei / tanto faz" },
  { value: "estagiário", label: "Primeiro emprego ou aprendiz" },
  { value: "júnior", label: "Já trabalhei antes" },
  { value: "pleno", label: "Alguns anos de experiência" },
  { value: "sênior", label: "Muita experiência" },
];

function isSimpleMode() {
  const v = localStorage.getItem(SIMPLE_MODE_KEY);
  if (v === null) return true;
  return v === "1" || v === "true";
}

function searchBtnLabel() {
  return isSimpleMode() ? "Buscar vagas agora" : "Buscar vagas";
}

function simpleScoreLabel(score) {
  const s = Math.round(score || 0);
  if (s >= 65) return "Combina bastante";
  if (s >= 45) return "Combina um pouco";
  return "Combina pouco";
}

function renderSeniorityOptions() {
  const sel = $("seniority");
  if (!sel) return;
  const cur = sel.value;
  const opts = isSimpleMode() ? SENIORITY_SIMPLE : SENIORITY_PRO;
  sel.innerHTML = opts.map(o =>
    '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>"
  ).join("");
  if (opts.some(o => o.value === cur)) sel.value = cur;
}

function applySimpleDefaults() {
  const sectorEl = $("sector");
  if (sectorEl && (!sectorEl.value || sectorEl.value === "tec_all")) {
    if (sectorEl.querySelector('option[value="emprego_geral"]')) sectorEl.value = "emprego_geral";
  }
  document.querySelectorAll("#sources input").forEach(b => {
    if (b.closest(".pro-only")) { b.checked = false; return; }
    b.checked = ["gupy", "indeed", "solides", "trampos", "catho"].includes(b.value);
  });
  if ($("broad")) $("broad").checked = true;
  if ($("semantic")) $("semantic").checked = false;
  if ($("only_new")) $("only_new").checked = false;
  if ($("locationScope")) $("locationScope").value = "city";
  if ($("locationCity")) $("locationCity").value = "";
  if ($("locationState")) $("locationState").value = "";
  if ($("locationIncludeRemote")) $("locationIncludeRemote").checked = false;
  onLocationScopeChange();
}

const MOBILE_BP = 880;

function isMobileLayout() {
  return window.innerWidth <= MOBILE_BP;
}

function setAppShellVisible(inApp) {
  document.body.classList.toggle("in-app", !!inApp);
  document.body.classList.toggle("in-mobile", isMobileLayout());
  const nav = $("mobileNav");
  if (nav) nav.classList.toggle("hidden", !inApp || !isMobileLayout());
  ["topNav", "headerSearchWrap", "cvHeaderBtn", "repeatSearchBtn"].forEach(id => {
    const el = $(id);
    if (el) el.classList.toggle("hidden", !inApp);
  });
  const apiBtn = $("apiPresetBtn");
  if (apiBtn) apiBtn.classList.toggle("hidden", !inApp || isSimpleMode());
}

function getKeywords() {
  const main = ($("keywordsMain") && $("keywordsMain").value) || "";
  const hdr = ($("keywords") && $("keywords").value) || "";
  return (main || hdr).trim();
}

function setKeywords(val) {
  const v = val || "";
  if ($("keywordsMain")) $("keywordsMain").value = v;
  if ($("keywords")) $("keywords").value = v;
}

function syncKeywordInputs(fromEl) {
  setKeywords(fromEl ? fromEl.value : getKeywords());
}

function openFilters() {
  const d = $("filtersModal");
  if (d && d.showModal) d.showModal();
}

function closeFilters() {
  const d = $("filtersModal");
  if (d && d.close) d.close();
}

function applyFiltersAndSearch() {
  closeFilters();
  saveFilters();
  search();
}

function applySimpleModeUI() {
  const simple = isSimpleMode();
  document.body.classList.toggle("simple-mode", simple);
  const btn = $("modeBtn");
  if (btn) {
    const txt = btn.querySelector(".hdr-txt");
    const label = simple ? "Modo completo" : "Modo simples";
    if (txt) txt.textContent = label;
    else btn.textContent = label;
    btn.title = simple
      ? "Ver opções avançadas (ATS, match profundo…)"
      : "Voltar ao modo simples para buscar emprego perto de você";
  }
  renderSeniorityOptions();
  if ($("headerSub")) $("headerSub").textContent = simple ? "Ache emprego perto de você" : "Sua jornada. Nossa inteligência.";
  if ($("statCompatLabel")) $("statCompatLabel").textContent = simple ? "Combina com você" : "Compatibilidade geral";
  if ($("seniorityLabel")) {
    $("seniorityLabel").innerHTML = simple
      ? 'Experiência <span class="hint-inline">(filtra vagas do seu nível)</span>'
      : 'Senioridade <span class="hint-inline">(perfil + filtro de busca)</span>';
  }
  if ($("levelFilterHint")) {
    $("levelFilterHint").textContent = simple
      ? "Marque seu nível ou deixe em branco — usamos a experiência do perfil acima."
      : "Se nada marcado, usamos seu nível do perfil acima.";
  }
  if ($("uploadBadge")) $("uploadBadge").textContent = simple ? "✦ EMPREGO MAIS PERTO DE VOCÊ" : "✦ SUA JORNADA. NOSSA INTELIGÊNCIA.";
  if ($("uploadLead")) {
    $("uploadLead").innerHTML = simple
      ? 'Encontre vaga <span class="grad">sem complicação</span>'
      : 'Seu copiloto <span class="grad">pra vaga ideal</span>';
  }
  if ($("uploadSub")) {
    $("uploadSub").innerHTML = simple
      ? "Mande seu currículo em PDF ou Word. A gente busca vagas e mostra quais combinam mais com você."
      : 'Envie seu currículo, busque em várias plataformas e veja o <b>match %</b> de cada vaga — você decide onde aplicar.';
  }
  if ($("dashBtn") && PROFILE) $("dashBtn").classList.toggle("hidden", simple);
  if (PROFILE) syncExperienceFromSeniority();
  updateStatCards();
}

function toggleSimpleMode() {
  const next = !isSimpleMode();
  localStorage.setItem(SIMPLE_MODE_KEY, next ? "1" : "0");
  if (next) applySimpleDefaults();
  applySimpleModeUI();
  saveFilters();
  updateFilterCount();
  if (LAST_JOBS.length) renderResults();
  toast(next ? "Modo simples — linguagem clara e busca na sua região." : "Modo completo — todas as ferramentas.", "");
}

/* ---------- localização ---------- */
const LOCATION_HINTS = {
  city: "Informe sua cidade e estado — buscamos vagas aí perto (ex.: Manhuaçu, MG).",
  state: "Escolha o estado — mostramos vagas de qualquer cidade dentro dele.",
  br: "Vagas em todo o Brasil. Remotas incluídas; fora do país excluídas.",
  remote: "Apenas vagas remotas ou home office.",
  foreign: "Vagas fora do Brasil.",
};
let CITY_SUGGEST_TIMER = null;

function locationScope() {
  return ($("locationScope") && $("locationScope").value) || "city";
}

function buildLocationLegacyString() {
  const scope = locationScope();
  const city = ($("locationCity") && $("locationCity").value || "").trim();
  const state = ($("locationState") && $("locationState").value || "").trim();
  if (scope === "city" && city) return state ? city + ", " + state : city;
  if (scope === "state" && state) return state;
  if (scope === "br") return "Brasil";
  if (scope === "remote") return "Remoto";
  if (scope === "foreign") return "Exterior";
  return "";
}

function syncLocationHidden() {
  const hidden = $("location");
  if (hidden) hidden.value = buildLocationLegacyString();
}

function collectLocationFields() {
  let scope = locationScope();
  let city = ($("locationCity") && $("locationCity").value || "").trim();
  let state = ($("locationState") && $("locationState").value || "").trim();
  if (isGuestMode() && scope === "city" && !city) {
    return {
      location_scope: "br",
      location_city: "",
      location_state: "",
      location_include_remote: false,
      location: "Brasil",
    };
  }
  syncLocationHidden();
  return {
    location_scope: scope,
    location_city: city,
    location_state: state,
    location_include_remote: !!($("locationIncludeRemote") && $("locationIncludeRemote").checked),
    location: buildLocationLegacyString(),
  };
}

function validateLocation() {
  const scope = locationScope();
  const city = ($("locationCity") && $("locationCity").value || "").trim();
  const state = ($("locationState") && $("locationState").value || "").trim();
  if (isGuestMode() && scope === "city" && !city) {
    return null;
  }
  if (scope === "city" && !city) {
    return "Informe sua cidade — é assim que achamos vagas perto de você.";
  }
  if (scope === "city" && !state) {
    return "Selecione o estado (UF) da sua cidade.";
  }
  if (scope === "state" && !state) {
    return "Selecione seu estado para buscar vagas na região.";
  }
  return null;
}

function onLocationScopeChange() {
  const scope = locationScope();
  const block = $("locationCityBlock");
  const cityField = $("locationCity");
  const remoteWrap = $("locationRemoteWrap");
  if (block) {
    const hideAll = scope === "br" || scope === "remote" || scope === "foreign";
    block.classList.toggle("hidden", hideAll);
    if (cityField) cityField.classList.toggle("hidden", scope === "state");
  }
  if (remoteWrap) {
    remoteWrap.classList.toggle("hidden", scope === "remote" || scope === "foreign" || scope === "br");
  }
  const hint = $("locationHint");
  if (hint) hint.textContent = LOCATION_HINTS[scope] || "";
  syncLocationHidden();
  saveFilters();
  updateFilterCount();
}

function onLocationStateChange() {
  syncCityDatalist();
  onLocationFieldsChange();
}

function onLocationFieldsChange() {
  syncLocationHidden();
  clearTimeout(CITY_SUGGEST_TIMER);
  CITY_SUGGEST_TIMER = setTimeout(syncCityDatalist, 220);
  saveFilters();
  updateFilterCount();
}

async function syncCityDatalist() {
  const dl = $("cityDatalist");
  const state = ($("locationState") && $("locationState").value || "").trim();
  const q = ($("locationCity") && $("locationCity").value || "").trim();
  if (!dl || locationScope() !== "city") return;
  if (!state && q.length < 2) { dl.innerHTML = ""; return; }
  try {
    const params = new URLSearchParams();
    if (state) params.set("state", state);
    if (q) params.set("q", q);
    const cities = await fetch("/api/locations/cities?" + params).then(r => r.json());
    dl.innerHTML = cities.map(c => "<option value=\"" + esc(c) + "\">").join("");
  } catch (e) { /* offline */ }
}

function applyLocationFields(f) {
  if (!f) return;
  if (f.location_scope && $("locationScope")) $("locationScope").value = f.location_scope;
  else if (f.location && $("locationScope")) {
    const loc = String(f.location).trim().toLowerCase();
    if (loc === "brasil" || loc === "brazil") $("locationScope").value = "br";
    else if (loc === "remoto" || loc === "remote") $("locationScope").value = "remote";
    else if (loc === "exterior" || loc === "foreign") $("locationScope").value = "foreign";
    else if (/^[a-z]{2}$/i.test(loc)) $("locationScope").value = "state";
    else $("locationScope").value = "city";
  }
  if (f.location_city != null && $("locationCity")) $("locationCity").value = f.location_city;
  if (f.location_state != null && $("locationState")) $("locationState").value = f.location_state;
  if (f.location_include_remote != null && $("locationIncludeRemote")) {
    $("locationIncludeRemote").checked = !!f.location_include_remote;
  } else if (f.location_scope === "city" && f.location && !f.location_city) {
    const parts = String(f.location).split(",").map(s => s.trim());
    if (parts.length >= 2 && $("locationCity")) $("locationCity").value = parts.slice(0, -1).join(", ");
    if (parts.length >= 2 && $("locationState")) $("locationState").value = parts[parts.length - 1].slice(0, 2).toUpperCase();
  }
  onLocationScopeChange();
  syncCityDatalist();
}

function locationBanner() {
  const label = LAST_META.location_label;
  if (!label) return "";
  const scope = LAST_META.location_scope || "";
  const scopeTxt = {
    city: "na cidade", state: "no estado", br: "no Brasil",
    remote: "remotas", foreign: "no exterior",
  }[scope] || "em";
  return "<div class=\"location-banner\">📍 Vagas " + esc(scopeTxt) + ": <b>" + esc(label) + "</b></div>";
}

/* ---------- helpers ---------- */
function $(id) { return document.getElementById(id); }
function getChecked(id) { return Array.from(document.querySelectorAll("#" + id + " input:checked")).map(e => e.value); }
function scoreClass(s) { return s >= 65 ? "high" : (s >= 45 ? "mid" : "low"); }
function esc(s) { return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function lsGet(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) ?? fallback;
  } catch (e) {
    const raw = localStorage.getItem(key);
    return raw != null ? raw : fallback;
  }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
}

/* Favoritos e candidaturas guardam os detalhes da vaga (não só o id),
   para alimentar o painel/histórico mesmo após nova busca. */
function _toMap(raw) {
  if (Array.isArray(raw)) { const m = {}; raw.forEach(id => { m[id] = { id }; }); return m; }
  return raw && typeof raw === "object" ? raw : {};
}
let FAVORITES = _toMap(lsGet(FAVORITES_KEY, {}));
let APPLIED = _toMap(lsGet(APPLIED_KEY, {}));
let COMPARE = new Set();

function isFav(id) { return !!FAVORITES[id]; }
function isApplied(id) { return !!APPLIED[id]; }
function jobMeta(j) {
  return {
    id: j.id, title: j.title, company: j.company, url: j.url,
    score: j.score, ats: j.ats, source: j.source, location: j.location,
  };
}
function saveFav() { lsSet(FAVORITES_KEY, FAVORITES); }
function saveApplied() { lsSet(APPLIED_KEY, APPLIED); }

const TOAST_ICONS = { success: "✓", error: "✕", warn: "!", "": "›" };
function toast(msg, type) {
  const wrap = $("toasts");
  // mantém no máximo 4 toasts visíveis
  while (wrap.children.length >= 4) wrap.firstElementChild.remove();
  const t = document.createElement("div");
  t.className = "toast " + (type || "");
  t.setAttribute("role", "status");
  t.title = "Clique para dispensar";
  t.innerHTML = '<span class="toast-ic">' + (TOAST_ICONS[type || ""] || "›") + "</span><span>" + esc(msg) + "</span>";
  const dismiss = () => { t.classList.add("out"); setTimeout(() => t.remove(), 280); };
  t.addEventListener("click", dismiss);
  wrap.appendChild(t);
  setTimeout(dismiss, 3800);
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await r.json(); } catch (e) { /* ignore */ }
  if (r.status === 401 && data && data.auth_required) {
    showPinModal();
    throw new Error("PIN necessário.");
  }
  if (!r.ok) {
    const msg = (data && data.error) ? data.error : ("HTTP " + r.status);
    throw new Error(msg);
  }
  return data;
}

/* ---------- theme ---------- */
const THEME_ICONS = { moon: "theme-icon--moon", sun: "theme-icon--sun" };

function applyTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "dark" ? "#1b1f23" : "#FFFFFF");
  const btn = $("themeBtn");
  if (btn) {
    btn.setAttribute("aria-label", t === "light" ? "Ativar modo escuro" : "Ativar modo claro");
    btn.title = t === "light" ? "Modo escuro" : "Modo claro";
    btn.dataset.theme = t;
  }
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "light";
  const next = cur === "dark" ? "light" : "dark";
  lsSet(THEME_KEY, next);
  applyTheme(next);
}

/* ---------- abas Buscar / Vagas ---------- */
function switchTab(name) {
  const tab = $("searchTab");
  if (tab) {
    tab.classList.remove("tab-search-only", "tab-results", "tab-pipeline");
    if (name === "search") tab.classList.add("tab-search-only");
    else if (name === "pipeline") tab.classList.add("tab-pipeline");
    else tab.classList.add("tab-results");
  }
  if ($("resultsTab")) $("resultsTab").classList.toggle("on", name !== "pipeline");
  if ($("pipelineTab")) {
    $("pipelineTab").classList.toggle("on", name === "pipeline");
    if (name === "pipeline") renderPipelineBoard();
  }
  document.querySelectorAll(".top-nav-item[data-nav], .hp-nav-btn[data-nav]").forEach(el => {
    el.classList.toggle("on", el.dataset.nav === name);
  });
  document.querySelectorAll(".mob-item[data-mob]").forEach(el => {
    el.classList.toggle("on", el.dataset.mob === name);
  });
  if (name === "results") {
    const r = $("results");
    if (r) r.scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (name === "pipeline") {
    const p = $("pipelineTab");
    if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function updateResultBadge() {
  const n = LAST_JOBS.length;
  ["resultBadgeHdr", "resultBadge", "resultBadgeSb", "resultBadgeMob"].forEach(id => {
    const b = $(id);
    if (!b) return;
    b.textContent = n;
    b.classList.toggle("hidden", !n);
  });
  updatePipelineBadge();
}

function updatePipelineBadge() {
  const n = Object.keys(APPLIED).length;
  ["pipelineBadgeHdr"].forEach(id => {
    const b = $(id);
    if (!b) return;
    b.textContent = n;
    b.classList.toggle("hidden", !n);
  });
}

function pipelineStatus(meta) {
  return (meta && meta.pipeline_status) || "candidatado";
}

function initSearchLive(sources) {
  SEARCH_LIVE = {};
  (sources || []).forEach(s => {
    SEARCH_LIVE[s] = { status: "pending", count: 0, hint: "" };
  });
}

function renderSearchLivePanel() {
  const keys = Object.keys(SEARCH_LIVE);
  if (!keys.length) return "";
  let chips = keys.map(s => {
    const st = SEARCH_LIVE[s];
    const label = SOURCE_LABELS[s] || s;
    const cls = st.status || "pending";
    let txt = label;
    if (st.status === "running") txt += "…";
    else if (st.status === "done") txt += ": " + (st.count || 0);
    if (st.status === "done" && !st.count && st.hint) txt += " ⚠";
    return '<span class="search-live-chip ' + cls + '" title="' + esc(st.hint || "") + '">'
      + '<span class="dot"></span>' + esc(txt) + "</span>";
  }).join("");
  return '<div id="searchLivePanel" class="search-live-panel"><div class="search-live-title">Fontes na busca</div>'
    + '<div class="search-live-grid">' + chips + "</div></div>";
}

function refreshSearchLivePanel() {
  const el = $("searchLivePanel");
  if (!el) return;
  el.outerHTML = renderSearchLivePanel();
}

function setSearchLiveSource(source, patch) {
  if (!SEARCH_LIVE[source]) SEARCH_LIVE[source] = { status: "pending", count: 0, hint: "" };
  Object.assign(SEARCH_LIVE[source], patch);
  refreshSearchLivePanel();
}

function needsPortalWizard(sources) {
  if (lsGet(PORTAL_WIZARD_KEY, false)) return false;
  return (sources || []).some(s => BROWSER_SOURCE_KEYS.has(s));
}

function renderPortalWizardSteps(sources) {
  const el = $("portalWizardSteps");
  if (!el) return;
  const bySource = {};
  SOURCE_HEALTH.forEach(s => { bySource[s.source] = s; });
  const list = (sources || []).filter(s => BROWSER_SOURCE_KEYS.has(s));
  if (!list.length) {
    el.innerHTML = '<p class="muted">Nenhum portal com login selecionado.</p>';
    return;
  }
  const hints = {
    linkedin: "Marque LinkedIn e busque — uma janela abrirá para login.",
    catho: "Marque Catho e busque — faça login ou cadastro grátis na janela do Chrome.",
    vagascom: "Marque Vagas.com — login de candidato obrigatório na 1ª busca.",
    infojobs: "InfoJobs usa navegador; geralmente funciona sem login.",
  };
  el.innerHTML = list.map(s => {
    const h = bySource[s] || {};
    const st = h.status || "browser";
    const stLabel = HEALTH_STATUS_LABEL[st] || st;
    return '<div class="portal-step"><div class="portal-step-head"><b>' + esc(SOURCE_LABELS[s] || s)
      + '</b><span class="portal-step-status ' + esc(st) + '">' + esc(stLabel) + "</span></div>"
      + "<p>" + esc(h.message || hints[s] || "Disponível via navegador.") + "</p></div>";
  }).join("");
}

async function refreshPortalWizard() {
  await refreshSourceHealth(true);
  const sources = collectFilters().sources.filter(s => BROWSER_SOURCE_KEYS.has(s));
  renderPortalWizardSteps(sources.length ? sources : Array.from(BROWSER_SOURCE_KEYS));
}

function showPortalWizard(sources) {
  return new Promise(resolve => {
    renderPortalWizardSteps(sources.filter(s => BROWSER_SOURCE_KEYS.has(s)));
    const d = $("portalWizardModal");
    if (!d || !d.showModal) { resolve(true); return; }
    d._resolve = resolve;
    d.showModal();
  });
}

function dismissPortalWizard() {
  lsSet(PORTAL_WIZARD_KEY, true);
  const d = $("portalWizardModal");
  if (d) { d.close(); if (d._resolve) d._resolve(true); }
}

function finishPortalWizard() {
  lsSet(PORTAL_WIZARD_KEY, true);
  const d = $("portalWizardModal");
  if (d) { d.close(); if (d._resolve) d._resolve(true); }
}

function renderPipelineBoard() {
  const board = $("pipelineBoard");
  if (!board) return;
  const byCol = {};
  PIPELINE_COLUMNS.forEach(c => { byCol[c.id] = []; });
  Object.entries(APPLIED).forEach(([id, meta]) => {
    const st = pipelineStatus(meta);
    if (!byCol[st]) byCol[st] = [];
    byCol[st].push({ id, ...meta });
  });
  let html = "";
  PIPELINE_COLUMNS.forEach(col => {
    const items = (byCol[col.id] || []).slice().sort((a, b) => (b.applied_at || 0) - (a.applied_at || 0));
    html += '<div class="kanban-col" data-col="' + col.id + '"><div class="kanban-col-head"><span>' + esc(col.label)
      + '</span><span class="muted">' + items.length + "</span></div><div class=\"kanban-col-body\">";
    if (!items.length) {
      html += '<p class="muted kanban-empty">Arraste cards aqui</p>';
    } else {
      items.forEach(item => {
        html += '<div class="kanban-card" draggable="true" data-id="' + esc(item.id) + '"><b>' + esc(item.title || item.id) + "</b>"
          + '<div class="muted">' + esc(item.company || "") + "</div>"
          + '<div class="kanban-card-actions">'
          + (item.url ? '<a class="btn small ghost" href="' + item.url + '" target="_blank" rel="noopener">Abrir</a> ' : "")
          + '<select onchange="setPipelineStatus(\'' + item.id + "', this.value)\">"
          + PIPELINE_COLUMNS.map(c => '<option value="' + c.id + '"' + (col.id === c.id ? " selected" : "") + ">"
          + esc(c.label) + "</option>").join("") + "</select></div></div>";
      });
    }
    html += "</div></div>";
  });
  board.innerHTML = html;
  bindKanbanDragDrop(board);
}

function bindKanbanDragDrop(board) {
  let dragId = "";
  board.querySelectorAll(".kanban-card").forEach(card => {
    card.addEventListener("dragstart", e => {
      dragId = card.dataset.id || "";
      e.dataTransfer.effectAllowed = "move";
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      board.querySelectorAll(".kanban-col-body").forEach(b => b.classList.remove("drag-over"));
    });
  });
  board.querySelectorAll(".kanban-col-body").forEach(body => {
    body.addEventListener("dragover", e => {
      e.preventDefault();
      body.classList.add("drag-over");
    });
    body.addEventListener("dragleave", () => body.classList.remove("drag-over"));
    body.addEventListener("drop", e => {
      e.preventDefault();
      body.classList.remove("drag-over");
      const col = body.closest(".kanban-col");
      const status = col && col.dataset.col;
      if (dragId && status) setPipelineStatus(dragId, status);
      dragId = "";
    });
  });
}

async function setPipelineStatus(id, status) {
  const meta = APPLIED[id] || { id };
  meta.pipeline_status = status;
  meta.pipeline_updated_at = Date.now();
  APPLIED[id] = meta;
  saveApplied();
  updatePipelineBadge();
  try {
    await postJSON("/api/pipeline", { id, status });
  } catch (e) { /* local ok */ }
  renderPipelineBoard();
  const job = LAST_JOBS.find(j => j.id === id);
  if (job) job.applied = true;
  renderResults();
}

function addToPipeline(id) {
  const job = LAST_JOBS.find(j => j.id === id);
  const meta = job ? jobMeta(job) : { id };
  meta.pipeline_status = "interesse";
  meta.pipeline_updated_at = Date.now();
  APPLIED[id] = meta;
  saveApplied();
  updatePipelineBadge();
  postJSON("/api/pipeline", { id, status: "interesse" }).catch(() => {});
  toast("Adicionado ao pipeline ✓", "success");
}

function isGuestMode() {
  return GUEST_MODE && !PROFILE;
}

function avatarInitials(name) {
  const parts = (name || "?").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return (parts[0] || "?").slice(0, 2).toUpperCase();
}

function dismissOnboard() {
  try { lsSet(ONBOARD_KEY, true); } catch (e) { /* ignore */ }
  const d = $("onboardModal");
  if (d && d.open) d.close();
}

function updateIdentityCard() {
  const guest = isGuestMode();
  const hasProfile = !!PROFILE;
  const addBtn = $("cvAddBtn");
  const added = $("cvAdded");
  if (addBtn) addBtn.classList.toggle("hidden", hasProfile);
  if (added) added.classList.toggle("hidden", !hasProfile);
  const avatar = $("idAvatar");
  if (avatar) {
    avatar.classList.toggle("guest", guest);
    if (guest) avatar.textContent = "👤";
    else if (hasProfile) avatar.textContent = avatarInitials(PROFILE.name);
    else avatar.textContent = "?";
  }
  const hint = $("cvFileHint");
  if (hint) {
    if (hasProfile && PROFILE.resume_filename) hint.textContent = PROFILE.resume_filename;
    else if (!hasProfile) hint.textContent = "—";
  }
}

function updateGuestUI() {
  const guest = isGuestMode();
  document.body.classList.toggle("guest-mode", guest);
  const bar = $("profileBar");
  if (bar) bar.classList.toggle("hidden", guest);
  if ($("resetBtn")) $("resetBtn").textContent = guest ? "Sair" : "Trocar CV";
  updateIdentityCard();
}

function startGuestSearch() {
  dismissOnboard();
  GUEST_MODE = true;
  PROFILE = null;
  lsSet("hp_guest", "1");
  applyGuestSearchDefaults();
  enterAppShell();
  toast("Busca livre — envie o currículo quando quiser ver compatibilidade.", "");
}

function applyGuestSearchDefaults() {
  const scopeEl = $("locationScope");
  const city = ($("locationCity") && $("locationCity").value || "").trim();
  if (scopeEl && !city && scopeEl.value === "city") {
    scopeEl.value = "br";
    onLocationScopeChange();
  }
  if (isSimpleMode() && !lsGet(FILTERS_KEY, null)) applySimpleDefaults();
}

function promptUpload() {
  dismissOnboard();
  if ($("file")) $("file").click();
}

async function bootstrapApp() {
  if (AUTH_REQUIRED) return;
  try {
    const d = await fetch("/api/profile").then(r => r.json());
    if (d.profile) {
      PROFILE = d.profile;
      GUEST_MODE = false;
      lsSet("hp_guest", "0");
      dismissOnboard();
      showProfile();
      return;
    }
  } catch (e) { /* offline */ }
  if (lsGet(ONBOARD_KEY, false) && lsGet("hp_guest", "1") !== "0") {
    startGuestSearch();
  }
}

function enterAppShell() {
  const uploadView = $("uploadView");
  const appView = $("appView");
  if (!uploadView || !appView) return;
  uploadView.classList.add("hidden");
  appView.classList.remove("hidden");
  setAppShellVisible(true);
  updateGuestUI();
  if (isGuestMode()) {
    const pName = $("pName");
    const pInfo = $("pInfo");
    const statCompat = $("statCompat");
    const statAts = $("statAts");
    const statJobs = $("statJobs");
    if (pName) pName.textContent = "Visitante";
    if (pInfo) pInfo.textContent = "Busca livre · adicione currículo para match e ATS";
    if (statCompat) statCompat.textContent = "—";
    if (statAts) statAts.textContent = "—";
    if (statJobs) statJobs.textContent = "0";
  }
  if ($("resetBtn")) $("resetBtn").classList.remove("hidden");
  if ($("dashBtn") && PROFILE) $("dashBtn").classList.toggle("hidden", isSimpleMode());
  const tab = $("searchTab");
  if (tab && !tab.classList.contains("tab-results") && !tab.classList.contains("tab-pipeline")) {
    tab.classList.add("tab-search-only");
  }
  restoreFilters();
  enableConfiguredApiSources();
  if (!isGuestMode() && !$("sector").value) suggestSector();
  updateFilterCount();
  renderSavedSearches();
  loadServerState();
  refreshSourceHealth(false);
}

function updateStatCards() {
  const n = LAST_JOBS.length;
  const statJobs = $("statJobs");
  if (statJobs) statJobs.textContent = String(n);
  if (isGuestMode()) {
    const statCompat = $("statCompat");
    const statAts = $("statAts");
    if (statCompat) statCompat.textContent = "—";
    if (statAts) statAts.textContent = "—";
    return;
  }
  if (!PROFILE) return;
  const ats = PROFILE.format_score;
  const statAts = $("statAts");
  if (statAts) statAts.textContent = ats == null ? "--" : ats + "/100";
  const statCompat = $("statCompat");
  if (!statCompat) return;
  if (n) {
    const avg = Math.round(LAST_JOBS.reduce((s, j) => s + (j.score || 0), 0) / n);
    statCompat.textContent = isSimpleMode() ? simpleScoreLabel(avg) : avg + "%";
  } else {
    statCompat.textContent = ats != null ? ats + "%" : "--";
  }
}

function firstName(name) {
  return (name || "candidato").trim().split(/\s+/)[0];
}

/* ---------- upload ---------- */
const drop = $("drop");
if (drop) {
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", e => {
    const f = e.dataTransfer.files[0];
    if (f) { $("file").files = e.dataTransfer.files; upload(); }
  });
}

async function upload() {
  const f = $("file").files[0];
  if (!f) return;
  dismissOnboard();
  if ($("fileName")) $("fileName").textContent = "Enviando " + f.name + "...";
  const fd = new FormData(); fd.append("resume", f);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    let d = null;
    try { d = await r.json(); } catch (e) { /* ignore */ }
    if (!r.ok || !d) {
      const msg = (d && d.error) ? d.error : "Erro ao enviar o currículo.";
      if ($("fileName")) $("fileName").textContent = msg;
      toast(msg, "error");
      return;
    }
    if (d.error) {
      if ($("fileName")) $("fileName").textContent = d.error;
      toast(d.error, "error");
      return;
    }
    if (!d.profile) {
      toast("Resposta inválida do servidor.", "error");
      return;
    }
    PROFILE = d.profile;
    PROFILE.resume_filename = f.name;
    GUEST_MODE = false;
    lsSet("hp_guest", "0");
    lsSet(ONBOARD_KEY, true);
    showProfile();
    toast("Currículo analisado!", "success");
    if (d.profile.suggested_keywords && !getKeywords()) {
      setKeywords(d.profile.suggested_keywords);
      saveFilters();
    }
  } catch (e) {
    if ($("fileName")) $("fileName").textContent = "Erro ao enviar. Tente novamente.";
    toast("Erro ao enviar o currículo.", "error");
  } finally {
    if ($("file")) $("file").value = "";
  }
}

function profileInfo() {
  const bits = [];
  if (PROFILE.seniority) bits.push(PROFILE.seniority);
  if (PROFILE.years_experience) bits.push(PROFILE.years_experience + " anos");
  bits.push((PROFILE.skills || []).length + " skills");
  return bits.join(" · ");
}

function syncExperienceFromSeniority() {
  const map = { "estagiário": "estagio", "júnior": "junior", "pleno": "pleno", "sênior": "senior" };
  const sen = ($("seniority") && $("seniority").value) || "";
  const level = map[sen];
  const chips = document.querySelectorAll("#experience input");
  if (!chips.length) return;
  const anyChecked = Array.from(chips).some(inp => inp.checked);
  if (anyChecked && !isSimpleMode()) return;
  chips.forEach(inp => { inp.checked = level ? inp.value === level : false; });
}

function showProfile() {
  if (!PROFILE) return;
  GUEST_MODE = false;
  lsSet("hp_guest", "0");
  dismissOnboard();
  enterAppShell();
  const resetBtn = $("resetBtn");
  if (resetBtn) resetBtn.classList.remove("hidden");
  if ($("dashBtn")) $("dashBtn").classList.toggle("hidden", isSimpleMode());
  const pName = $("pName");
  if (pName) pName.textContent = firstName(PROFILE.name);
  const pInfo = $("pInfo");
  if (pInfo) pInfo.textContent = profileInfo();
  const sen = $("seniority");
  if (sen) sen.value = PROFILE.seniority || "";
  syncExperienceFromSeniority();
  updateGuestUI();
  updateIdentityCard();
  updateStatCards();
}

async function confirmRemoveProfile() {
  if (!PROFILE) return;
  if (!confirm("Remover currículo? Você continua buscando vagas no modo visitante.")) return;
  try {
    await fetch("/api/profile", { method: "DELETE" });
  } catch (e) { /* offline */ }
  PROFILE = null;
  GUEST_MODE = true;
  lsSet("hp_guest", "1");
  $("file").value = "";
  $("pName").textContent = "Visitante";
  $("pInfo").textContent = "Busca livre · adicione currículo para match e ATS";
  $("seniority").value = "";
  updateGuestUI();
  updateStatCards();
  if (LAST_JOBS.length) renderResults();
  toast("Currículo removido.", "");
}

async function loadServerState() {
  try {
    const d = await fetch("/api/state").then(r => r.json());
    if (d.favorites) {
      FAVORITES = { ...FAVORITES, ...d.favorites };
      saveFav();
    }
    if (d.applied) {
      APPLIED = { ...APPLIED, ...d.applied };
      saveApplied();
      updatePipelineBadge();
    }
    renderAlerts(d.alerts || []);
    checkAlertHits();
  } catch (e) { /* offline / primeira vez */ }
}

async function requestNotifyPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    try { await Notification.requestPermission(); } catch (e) { /* ignore */ }
  }
}

async function checkAlertHits() {
  try {
    const d = await fetch("/api/alerts/hits").then(r => r.json());
    if (!(d.hits || []).length) return;
    await requestNotifyPermission();
    (d.hits || []).forEach(h => {
      const msg = h.new_count + " vaga(s) nova(s)";
      toast("Alerta «" + h.name + "»: " + msg, "success");
      if ("Notification" in window && Notification.permission === "granted") {
        try {
          new Notification("HirePilot — " + h.name, { body: msg, tag: "hp-alert-" + (h.id || h.name) });
        } catch (e) { /* ignore */ }
      }
    });
  } catch (e) { /* ignore */ }
}

function renderAlerts(alerts) {
  const wrap = $("alertsList");
  if (!wrap) return;
  if (!alerts.length) {
    wrap.innerHTML = '<span class="muted" style="font-size:12px">Nenhum alerta</span>';
    return;
  }
  wrap.innerHTML = alerts.map(a => {
    const on = a.enabled !== false;
    const cls = on ? "" : " off";
    return '<span class="chip' + cls + '" title="Última: ' + esc(a.last_run || "nunca") + '">'
      + '<span class="alert-toggle" onclick="toggleAlert(' + a.id + ',' + (!on) + ')">' + (on ? "🔔" : "🔕") + "</span> "
      + esc(a.name) + (a.last_new_count ? " (" + a.last_new_count + " novas)" : "")
      + ' <span class="x" onclick="deleteAlert(' + a.id + ')">×</span></span>';
  }).join("");
}

function openAlertModal() {
  const nameEl = $("alertName");
  if (nameEl) nameEl.value = "";
  $("alertModal").showModal();
}

async function confirmSaveAlert() {
  const name = ($("alertName").value || "").trim();
  if (!name) { toast("Informe um nome para o alerta.", "warn"); return; }
  await requestNotifyPermission();
  const filters = collectFilters();
  try {
    await postJSON("/api/alerts", { name, filters });
    $("alertModal").close();
    toast("Alerta criado.", "success");
    loadServerState();
  } catch (e) { toast(e.message || "Erro ao criar alerta.", "error"); }
}

async function saveAlert() { openAlertModal(); }

async function toggleAlert(id, enabled) {
  try {
    await postJSON("/api/alerts/toggle", { id, enabled });
    loadServerState();
  } catch (e) { toast("Erro ao atualizar alerta.", "error"); }
}

async function deleteAlert(id) {
  try {
    await fetch("/api/alerts", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    loadServerState();
  } catch (e) { toast("Erro ao remover alerta.", "error"); }
}

/* Heurística: sugere um setor a partir do cargo/skills detectados no currículo. */
const SECTOR_HINTS = [
  ["varejo", ["vendedor", "vendedora", "caixa", "loja", "balconista"]],
  ["operacional", ["operador", "produção", "estoque", "almoxarifado", "fábrica"]],
  ["limpeza", ["limpeza", "faxina", "zelador"]],
  ["motorista", ["motorista", "entregador", "cnh", "motoboy"]],
  ["cozinha", ["cozinheiro", "cozinheira", "restaurante"]],
  ["primeiro_emprego", ["aprendiz", "jovem aprendiz", "primeiro emprego"]],
  ["atendimento", ["atendente", "telefonista", "call center", "sac"]],
  ["administrativo", ["administrativo", "auxiliar administrativo", "recepcionista", "escritório"]],
  ["servicos", ["serviços gerais", "manutenção", "porteiro", "zelador"]],
  ["emprego_geral", ["auxiliar", "assistente", "operador"]],
  ["tec_dados", ["cientista de dados", "engenheiro de dados", "analista de dados", "data scientist", "data engineer", "bi", "power bi", "etl"]],
  ["tec_devops", ["devops", "sre", "infraestrutura", "cloud", "kubernetes", "terraform"]],
  ["tec_qa", ["qa", "quality assurance", "analista de testes", "tester"]],
  ["tec_seguranca", ["segurança da informação", "cybersecurity", "pentest", "soc"]],
  ["tec_suporte", ["suporte", "help desk", "técnico de ti", "service desk"]],
  ["tec_dev", ["desenvolvedor", "developer", "programador", "engenheiro de software", "full stack", "backend", "frontend", "software"]],
  ["design", ["designer", "ux", "ui", "product design"]],
  ["produto", ["product manager", "product owner", "gerente de produto"]],
  ["marketing", ["marketing", "growth", "mídias sociais", "seo"]],
  ["vendas", ["vendas", "comercial", "executivo de contas", "sdr"]],
  ["rh", ["recursos humanos", "recrutamento", "departamento pessoal"]],
  ["financeiro", ["financeiro", "controladoria", "contas a pagar"]],
  ["fiscal", ["fiscal", "tributário"]],
  ["contabil", ["contábil", "contabilidade", "contador"]],
  ["juridico", ["jurídico", "advogado", "direito"]],
  ["logistica", ["logística", "supply chain", "estoque"]],
];

function suggestSector() {
  const hay = ((PROFILE.job_hint || "") + " " + (PROFILE.skills || []).join(" ")).toLowerCase();
  if (!hay.trim()) return;
  for (const [id, terms] of SECTOR_HINTS) {
    if (terms.some(t => hay.includes(t))) {
      $("sector").value = id;
      saveFilters();
      return;
    }
  }
}

async function saveSeniority() {
  const val = $("seniority").value;
  try {
    await postJSON("/api/profile", { seniority: val });
    if (PROFILE) PROFILE.seniority = val;
    $("pInfo").textContent = profileInfo();
    syncExperienceFromSeniority();
    saveFilters();
  } catch (e) { toast("Não foi possível salvar a senioridade.", "error"); }
}

function resetProfile() {
  const wasGuest = isGuestMode();
  PROFILE = null;
  GUEST_MODE = false;
  $("file").value = "";
  if ($("fileName")) $("fileName").textContent = "";
  if (wasGuest) {
    setAppShellVisible(false);
    $("appView").classList.add("hidden");
    $("uploadView").classList.remove("hidden");
    $("resetBtn").classList.add("hidden");
    if ($("dashBtn")) $("dashBtn").classList.add("hidden");
    return;
  }
  startGuestSearch();
}

function exitGuestMode() {
  resetProfile();
}

function showFormat() {
  if (!PROFILE) return;
  let html = '<p>Nota de formato: <b>' + (PROFILE.format_score ?? "--") + '/100</b></p>';
  html += '<div class="barwrap"><div style="width:' + (PROFILE.format_score || 0) + '%"></div></div>';
  for (const c of (PROFILE.format_checks || [])) {
    html += '<div class="check"><span class="' + (c.passed ? "ok" : "no") + '">' + (c.passed ? "✓" : "✕") + "</span>"
      + "<span><b>" + esc(c.name) + "</b> — " + esc(c.detail) + "</span></div>";
  }
  openModal("Compatibilidade ATS do currículo", html);
}

/* ---------- setores ---------- */
function onSectorChange() { saveFilters(); }

/* ---------- filters persistence ---------- */
function collectExperienceFilter() {
  const chips = getChecked("experience");
  if (chips.length) return chips;
  const sen = ($("seniority") && $("seniority").value) || "";
  const map = { "estagiário": "estagio", "júnior": "junior", "pleno": "pleno", "sênior": "senior" };
  return map[sen] ? [map[sen]] : [];
}

function collectFilters() {
  const salMin = parseInt($("salary_min").value, 10);
  const salMax = parseInt($("salary_max").value, 10);
  const simple = isSimpleMode();
  const limit = simple
    ? (parseInt($("limitSimple")?.value, 10) || 50)
    : (parseInt($("limit").value, 10) || 40);
  const capField = parseInt($("global_cap").value, 10);
  return {
    sector: $("sector").value, keywords: getKeywords(),
    ...collectLocationFields(),
    workplace: getChecked("workplace"), job_type: getChecked("job_type"),
    experience: collectExperienceFilter(), date_posted: $("date_posted").value,
    sources: getChecked("sources"), limit,
    global_cap: simple ? null : (capField > 0 ? capField : null),
    no_cache: $("no_cache") ? $("no_cache").checked : false,
    broad: $("broad") ? $("broad").checked : true,
    only_new: simple ? false : ($("only_new") ? $("only_new").checked : false),
    semantic: simple ? false : ($("semantic") ? $("semantic").checked : true),
    salary_min: salMin > 0 ? salMin : null,
    salary_max: salMax > 0 ? salMax : null,
  };
}

function saveFilters() { lsSet(FILTERS_KEY, collectFilters()); }

function setChecks(id, values) {
  document.querySelectorAll("#" + id + " input").forEach(e => { e.checked = values.includes(e.value); });
}

function applyFiltersPayload(f) {
  applyFilterObject(f);
  updateFilterCount();
}

function applyFilterObject(f) {
  if (!f) return;
  if (f.sector != null) $("sector").value = f.sector;
  if (f.keywords != null) setKeywords(f.keywords);
  applyLocationFields(f);
  if (f.location != null && !f.location_scope && $("location")) $("location").value = f.location;
  if (f.date_posted) $("date_posted").value = f.date_posted;
  if (f.limit) $("limit").value = f.limit;
  if (f.global_cap) $("global_cap").value = f.global_cap;
  if (f.salary_min) $("salary_min").value = f.salary_min;
  if (f.salary_max) $("salary_max").value = f.salary_max;
  if (f.workplace) setChecks("workplace", f.workplace);
  if (f.job_type) setChecks("job_type", f.job_type);
  if (f.experience) setChecks("experience", f.experience);
  if (f.sources && f.sources.length) setChecks("sources", f.sources);
  if (f.broad != null && $("broad")) $("broad").checked = !!f.broad;
  if (f.only_new != null && $("only_new")) $("only_new").checked = !!f.only_new;
  if (f.semantic != null && $("semantic")) $("semantic").checked = !!f.semantic;
  if (f.no_cache != null && $("no_cache")) $("no_cache").checked = !!f.no_cache;
}

function restoreFilters() { applyFilterObject(lsGet(FILTERS_KEY, null)); updateFilterCount(); }

/* Conta filtros "ativos" (diferentes do padrão) para o indicador. */
function countActiveFilters() {
  let n = 0;
  const sector = $("sector").value;
  const defaultSector = isSimpleMode() ? "emprego_geral" : "tec_all";
  if (sector && sector !== defaultSector) n++;
  if (getKeywords()) n++;
  const locScope = locationScope();
  if (locScope !== "city") n++;
  else if (($("locationCity").value || "").trim() || ($("locationState").value || "").trim()) n++;
  if ($("locationIncludeRemote") && $("locationIncludeRemote").checked) n++;
  if (getChecked("workplace").length) n++;
  if (getChecked("job_type").length) n++;
  if (getChecked("experience").length) n++;
  if ($("date_posted").value !== "qualquer") n++;
  if ($("broad") && !$("broad").checked) n++;
  return n;
}

function updateFilterCount() {
  const badge = $("filterCount");
  if (!badge) return;
  const n = countActiveFilters();
  badge.textContent = n;
  badge.classList.toggle("hidden", n === 0);
}

function clearFilters() {
  $("sector").value = isSimpleMode() ? "emprego_geral" : "tec_all";
  setKeywords("");
  if ($("locationScope")) $("locationScope").value = isSimpleMode() ? "city" : "br";
  if ($("locationCity")) $("locationCity").value = "";
  if ($("locationState")) $("locationState").value = "";
  if ($("locationIncludeRemote")) $("locationIncludeRemote").checked = false;
  onLocationScopeChange();
  $("date_posted").value = "qualquer";
  $("limit").value = "40";
  if ($("broad")) $("broad").checked = true;
  if ($("only_new")) $("only_new").checked = false;
  if ($("semantic")) $("semantic").checked = !isSimpleMode();
  $("salary_min").value = "";
  $("salary_max").value = "";
  $("global_cap").value = "";
  setChecks("workplace", []);
  setChecks("job_type", []);
  setChecks("experience", []);
  saveFilters();
  updateFilterCount();
  toast("Filtros limpos.", "");
}

function toggleAllSources() {
  const boxes = document.querySelectorAll("#sources input");
  const allOn = Array.from(boxes).every(b => b.checked);
  selectAllSources(!allOn);
}

function selectAllSources(on) {
  document.querySelectorAll("#sources input").forEach(b => { b.checked = !!on; });
  saveFilters();
  updateFilterCount();
  if (on) toast("Todas as fontes marcadas (Catho/Vagas.com/LinkedIn usam navegador).", "");
}

/* ---------- saved searches ---------- */
function renderSavedSearches() {
  const wrap = $("savedSearches");
  if (!wrap) return;
  const saved = lsGet(SAVED_KEY, []);
  if (!saved.length) { wrap.innerHTML = '<span class="muted" style="font-size:12px">Nenhuma busca salva</span>'; return; }
  wrap.innerHTML = saved.map((s, i) =>
    '<span class="chip" role="button" tabindex="0" onclick="loadSavedSearch(' + i + ')">'
    + esc(s.name) + ' <span class="x" title="Remover" onclick="event.stopPropagation();removeSavedSearch(' + i + ')">×</span></span>'
  ).join("");
}

function saveCurrentSearch() {
  const name = (prompt("Nome para esta busca:") || "").trim();
  if (!name) return;
  const saved = lsGet(SAVED_KEY, []);
  saved.push({ name, filters: collectFilters() });
  lsSet(SAVED_KEY, saved);
  renderSavedSearches();
  toast("Busca salva.", "success");
}

function loadSavedSearch(i) {
  const saved = lsGet(SAVED_KEY, []);
  if (saved[i]) { applyFilterObject(saved[i].filters); toast("Busca carregada.", "success"); }
}

function removeSavedSearch(i) {
  const saved = lsGet(SAVED_KEY, []);
  saved.splice(i, 1);
  lsSet(SAVED_KEY, saved);
  renderSavedSearches();
}

/* ---------- search ---------- */
function skeletons(n) {
  let h = "";
  for (let i = 0; i < n; i++) h += '<div class="skeleton"><div class="line short"></div><div class="line mid"></div><div class="line"></div></div>';
  return h;
}

async function search() {
  const btn = $("go");
  const label = searchBtnLabel();
  const restore = () => { btn.disabled = false; btn.classList.remove("loading"); btn.textContent = label; };
  if (isGuestMode()) applyGuestSearchDefaults();
  const payload = collectFilters();
  saveFilters();
  if (!payload.sources.length) { toast("Selecione ao menos um site para buscar.", "error"); return; }
  lsSet(LAST_SEARCH_KEY, payload);
  LAST_REQUESTED_SOURCES = (payload.sources || []).slice();
  const locErr = validateLocation();
  if (locErr) { toast(locErr, "warn"); return; }
  if (!payload.sector && !getKeywords()) {
    toast(isSimpleMode() ? "Escolha a área ou digite um cargo." : "Escolha um setor ou informe palavras-chave.", "error");
    return;
  }

  btn.disabled = true; btn.classList.add("loading");
  btn.innerHTML = '<span class="btn-spin"></span> Buscando…';
  initSearchLive(payload.sources);
  $("results").innerHTML = skeletons(4) + renderSearchLivePanel();
  switchTab("results");

  if (needsPortalWizard(payload.sources)) {
    const cont = await showPortalWizard(payload.sources);
    if (!cont) { restore(); return; }
  }

  try {
    await searchStream(payload);
  } catch (e) {
    if (e.name === "AbortError") return;
    const msg = e.message || "Erro na busca.";
    $("results").innerHTML = '<div class="empty"><div class="big">⚠️</div>' + esc(msg) + "</div>";
    toast(msg, "error");
  }
  restore();
}

let LAST_REQUESTED_SOURCES = [];

function applySearchResult(d, opts) {
  opts = opts || {};
  if (d.error) {
    $("results").innerHTML = '<div class="empty"><div class="big">⚠️</div>' + esc(d.error) + "</div>";
    return;
  }
  LAST_JOBS = (d.jobs || []).map(j => ({
    ...j,
    applied: j.applied || isApplied(j.id),
    reasons_text: Array.isArray(j.reasons) ? j.reasons.join("; ") : (j.reasons_short || j.reasons || ""),
  }));
  LAST_SOURCES = d.sources || [];
  LAST_META = d.meta || {};
  if (LAST_META.requested_sources && LAST_META.requested_sources.length) {
    LAST_REQUESTED_SOURCES = LAST_META.requested_sources.slice();
  }
  if (!opts.partial) {
    FILTER_SOURCE = "";
    CURRENT_PAGE = 1;
    COMPARE.clear();
    updateCompareBar();
  }
  renderResults();
  updateResultBadge();
  if (!opts.partial) {
    const n = LAST_JOBS.length;
    const newN = LAST_META.new_count || 0;
    let msg = n
      ? (isSimpleMode() ? n + " vaga(s) encontradas" : n + " vaga(s) ranqueadas")
      : (isSimpleMode() ? "Nenhuma vaga por enquanto — tente outra área ou cidade" : "Nenhuma vaga encontrada");
    if (newN) msg += " · " + newN + " nova(s)";
    toast(msg, n ? "success" : "warn");
    scrollToResults();
  }
}

async function repeatLastSearch() {
  const saved = lsGet(LAST_SEARCH_KEY, null);
  if (!saved) { toast("Nenhuma busca anterior salva.", "warn"); return; }
  applyFiltersPayload(saved);
  await search();
}

function applyApiOnlyPreset() {
  document.querySelectorAll("#sources input").forEach(b => {
    b.checked = API_ONLY_SOURCES.includes(b.value);
  });
  toast("Preset «só APIs» — sem navegador/login.", "success");
  updateFilterCount();
}

async function refreshSource(source) {
  const payload = collectFilters();
  payload.sources = [source];
  payload.no_cache = true;
  toast("Atualizando " + (SOURCE_LABELS[source] || source) + "…", "");
  try {
    await postJSON("/api/sources/invalidate", { source });
  } catch (e) { /* ok */ }
  initSearchLive([source]);
  $("results").innerHTML = skeletons(2) + renderSearchLivePanel();
  switchTab("results");
  try {
    await searchStream(payload);
  } catch (e) {
    toast(e.message || "Erro ao atualizar fonte.", "error");
  }
}

async function openScoreExplain(id) {
  const job = LAST_JOBS.find(j => j.id === id);
  if (!job) return;
  openModal("Por que " + Math.round(job.score || 0) + "%?", '<div class="spinner"></div>');
  if (isGuestMode() || !PROFILE) {
    let html = "<p><b>Relevância:</b> " + esc(job.reasons_text || "Termos da busca e filtros aplicados.") + "</p>";
    if (job.also_in && job.also_in.length) {
      html += "<p class=\"muted\">Também listada em: " + job.also_in.map(s => esc(SOURCE_LABELS[s] || s)).join(", ") + "</p>";
    }
    $("modalBody").innerHTML = html;
    return;
  }
  try {
    const d = await postJSON("/api/ats", { id });
    let html = "<p><b>Match:</b> " + Math.round(job.score || 0) + "%</p>";
    if (d.ats_score != null) html += "<p><b>ATS:</b> " + Math.round(d.ats_score) + "%</p>";
    if (job.reasons_text) html += "<p>" + esc(job.reasons_text) + "</p>";
    if (d.present && d.present.length) html += "<p><b>No seu CV:</b> " + d.present.slice(0, 12).map(s => '<span class="tag">' + esc(s) + "</span>").join(" ") + "</p>";
    if (d.missing && d.missing.length) html += "<p><b>Falta destacar:</b> " + d.missing.slice(0, 10).map(s => '<span class="tag">' + esc(s) + "</span>").join(" ") + "</p>";
    if (d.suggestions && d.suggestions.length) html += "<ul>" + d.suggestions.slice(0, 4).map(s => "<li>" + esc(s) + "</li>").join("") + "</ul>";
    $("modalBody").innerHTML = html;
  } catch (e) {
    $("modalBody").innerHTML = "<p>" + esc(job.reasons_text || "Sem detalhes.") + "</p>";
  }
}

let INLINE_JOB_ID = "";

async function showJobInline(id) {
  INLINE_JOB_ID = id;
  const pane = $("jobDetailInline");
  if (!pane) { openJobPreview(id); return; }
  pane.classList.remove("hidden");
  pane.innerHTML = '<div class="spinner"></div>';
  try {
    const d = await postJSON("/api/job/detail", { id });
    if (d.error) { pane.innerHTML = esc(d.error); return; }
    let html = '<button type="button" class="hp-link inline-close" onclick="hideJobInline()">← Voltar à lista</button>';
    html += "<h3>" + esc(d.title) + "</h3>";
    html += '<p class="muted">' + esc(d.company) + (d.location ? " · " + esc(d.location) : "") + "</p>";
    if (d.salary) html += "<p><b>Salário:</b> " + esc(d.salary) + "</p>";
    html += '<div class="job-preview">' + esc(d.description || "Sem descrição.") + "</div>";
    html += '<p style="margin-top:12px"><a class="hp-btn hp-btn--primary" href="' + d.url + '" target="_blank" rel="noopener">Candidatar-se</a></p>';
    pane.innerHTML = html;
    pane.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    pane.innerHTML = "Erro ao carregar vaga.";
  }
}

function hideJobInline() {
  INLINE_JOB_ID = "";
  const pane = $("jobDetailInline");
  if (pane) { pane.classList.add("hidden"); pane.innerHTML = ""; }
}

async function searchStream(payload) {
  if (SEARCH_ABORT) SEARCH_ABORT.abort();
  const gen = ++SEARCH_GEN;
  SEARCH_ABORT = new AbortController();
  const signal = SEARCH_ABORT.signal;

  const r = await fetch("/api/search/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!r.ok) {
    let msg = "HTTP " + r.status;
    try {
      const err = await r.json();
      if (err.error) msg = err.error;
      if (r.status === 401 && err.auth_required) showPinModal();
    } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const prog = () => $("searchProgress");

  while (true) {
    const { done, value } = await reader.read();
    if (done || gen !== SEARCH_GEN) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const block of parts) {
      const line = block.split("\n").find(l => l.startsWith("data: "));
      if (!line) continue;
      if (gen !== SEARCH_GEN) return;
      const ev = JSON.parse(line.slice(6));
      if (ev.event === "source_start") {
        setSearchLiveSource(ev.source, { status: "running", count: 0, hint: "" });
      } else if (ev.event === "source") {
        setSearchLiveSource(ev.source, {
          status: "done",
          count: ev.fetched ?? ev.count ?? 0,
          hint: ev.hint || "",
        });
        const el = prog();
        if (el) {
          const label = SOURCE_LABELS[ev.source] || ev.source;
          el.textContent = label + ": " + (ev.fetched ?? ev.count) + " coletada(s)…";
        }
      } else if (ev.event === "partial") {
        applySearchResult(ev, { partial: true });
        const el = prog();
        if (el && ev.meta) {
          el.textContent = (ev.meta.shown || 0) + " vaga(s) exibidas até agora…";
        }
      } else if (ev.event === "complete") {
        applySearchResult(ev);
        return;
      } else if (ev.event === "error") {
        applySearchResult({ error: ev.error });
        return;
      }
    }
  }
}

function renderPartialResults() { /* legado — partial via SSE */ }

function progEl() { return $("searchProgress"); }

function visibleJobs() {
  let jobs = LAST_JOBS.slice();
  if (FILTER_SOURCE) jobs = jobs.filter(j => j.source === FILTER_SOURCE);
  if (ONLY_FAVORITES) jobs = jobs.filter(j => isFav(j.id));
  if (HIDE_APPLIED) jobs = jobs.filter(j => !j.applied && !isApplied(j.id));
  const cmp = {
    score: (a, b) => b.score - a.score,
    ats: (a, b) => (b.ats || 0) - (a.ats || 0),
    title: (a, b) => (a.title || "").localeCompare(b.title || ""),
    date: (a, b) => (b.posted_sort || 0) - (a.posted_sort || 0),
  }[SORT_KEY] || ((a, b) => b.score - a.score);
  jobs.sort(cmp);
  return jobs;
}

const SOURCE_LABELS = {
  gupy: "Gupy", remotive: "Remotive", remoteok: "RemoteOK",
  infojobs: "InfoJobs", linkedin: "LinkedIn",
  greenhouse: "Greenhouse", indeed: "Indeed", solides: "Sólides",
  trampos: "Trampos.co", jooble: "Jooble",
  catho: "Catho", vagascom: "Vagas.com",
  careerjet: "CareerJet", trabalhabrasil: "Trabalha Brasil", empregoscom: "Empregos.com.br",
};

const HEALTH_STATUS_LABEL = {
  ok: "OK",
  degraded: "Instável",
  down: "Indisponível",
  needs_login: "Login",
  browser: "Navegador",
  unavailable: "Indisponível",
};

let SOURCE_HEALTH = [];
let SOURCE_HEALTH_LOADING = false;

function dismissPrivacyBanner() {
  const el = $("privacyBanner");
  if (el) el.classList.add("hidden");
  localStorage.setItem(LS_PREFIX + "privacyDismiss", "1");
}

function initPrivacyBanner() {
  const el = $("privacyBanner");
  if (!el) return;
  if (localStorage.getItem(LS_PREFIX + "privacyDismiss") === "1") {
    el.classList.add("hidden");
  }
}

function applyHealthToSourceChips() {
  if (!SOURCE_HEALTH.length) return;
  const bySource = {};
  SOURCE_HEALTH.forEach(s => { bySource[s.source] = s; });
  document.querySelectorAll("#sources label.chip").forEach(label => {
    const input = label.querySelector("input");
    if (!input) return;
    const item = bySource[input.value];
    label.dataset.health = item ? item.status : "";
    if (item && item.message) {
      const prev = label.getAttribute("title") || "";
      const base = prev.split(" — ")[0];
      label.setAttribute("title", base + " — " + item.message);
    }
  });
}

function renderSourceHealth() {
  const el = $("sourceHealth");
  if (!el) return;
  if (SOURCE_HEALTH_LOADING) {
    el.innerHTML = '<span class="health-chip loading">Verificando fontes…</span>';
    return;
  }
  if (!SOURCE_HEALTH.length) {
    el.innerHTML = '<span class="health-chip loading">Sem dados — clique em atualizar</span>';
    return;
  }
  const visible = isSimpleMode()
    ? SOURCE_HEALTH.filter(s => s.source === "gupy" || s.source === "indeed" || s.source === "solides")
    : SOURCE_HEALTH;
  el.innerHTML = visible.map(s => {
    const label = SOURCE_LABELS[s.source] || s.label || s.source;
    const st = HEALTH_STATUS_LABEL[s.status] || s.status;
    const title = esc(label + ": " + (s.message || st));
    return '<span class="health-chip ' + esc(s.status) + '" title="' + title + '">'
      + esc(label) + ": " + esc(st) + "</span>";
  }).join("");
  applyHealthToSourceChips();
}

async function refreshSourceHealth(force) {
  const el = $("sourceHealth");
  if (!el || SOURCE_HEALTH_LOADING) return;
  SOURCE_HEALTH_LOADING = true;
  renderSourceHealth();
  try {
    const url = "/api/sources/health" + (force ? "?refresh=1" : "");
    const d = await fetch(url).then(r => r.json());
    SOURCE_HEALTH = d.sources || [];
  } catch (e) {
    if (el) el.innerHTML = '<span class="health-chip down">Não foi possível verificar as fontes</span>';
    SOURCE_HEALTH_LOADING = false;
    return;
  }
  SOURCE_HEALTH_LOADING = false;
  renderSourceHealth();
}

function setSourceFilter(src) {
  FILTER_SOURCE = src || "";
  CURRENT_PAGE = 1;
  renderResults();
}

function sourceFilterBar() {
  if (!LAST_JOBS.length) return "";
  const allowed = LAST_REQUESTED_SOURCES.length
    ? new Set(LAST_REQUESTED_SOURCES)
    : new Set(LAST_SOURCES.map(s => s.source));
  const shownMap = LAST_META.by_source || {};
  const counts = {};
  LAST_JOBS.forEach(j => {
    const s = j.source || "—";
    if (!allowed.has(s)) return;
    counts[s] = (counts[s] || 0) + 1;
  });
  const keys = Object.keys({ ...counts, ...shownMap })
    .filter(k => k && k !== "—" && allowed.has(k))
    .sort();
  if (!keys.length && !LAST_JOBS.length) return "";
  let html = '<div class="src-filter-bar" role="group" aria-label="Filtrar por fonte">';
  html += '<span class="src-filter-label">Exibidas:</span>';
  html += '<button type="button" class="src-filter-chip' + (!FILTER_SOURCE ? " on" : "")
    + '" onclick="setSourceFilter(\'\')">Todas <b>' + LAST_JOBS.length + "</b></button>";
  keys.forEach(s => {
    const label = SOURCE_LABELS[s] || s;
    const n = counts[s] || shownMap[s] || 0;
    html += '<button type="button" class="src-filter-chip' + (FILTER_SOURCE === s ? " on" : "")
      + '" onclick="setSourceFilter(\'' + s + "')\">" + esc(label) + " <b>" + n + "</b></button>";
  });
  html += "</div>";
  return html;
}

function sourcesStrip() {
  if (!LAST_SOURCES.length && !LAST_META.fetched) return "";
  const shownMap = LAST_META.by_source || {};
  const fetchedMap = LAST_META.by_source_fetched || {};
  const chips = LAST_SOURCES.map(s => {
    const label = SOURCE_LABELS[s.source] || s.source;
    const fetched = s.fetched ?? fetchedMap[s.source] ?? s.count ?? 0;
    const shown = s.shown ?? shownMap[s.source] ?? 0;
    const cls = fetched > 0 ? "ok" : "zero";
    let countLabel = String(fetched);
    if (shown && shown !== fetched) countLabel = fetched + "→" + shown;
    else if (shown) countLabel = String(shown);
    const hint = s.hint ? " — " + s.hint : "";
    const cacheTag = s.cached ? " · cache" : "";
    return '<span class="src-chip ' + cls + '" title="' + esc(label + hint + cacheTag) + '">'
      + esc(label) + ": " + countLabel + (fetched === 0 && s.hint ? " ⚠" : "")
      + ' <button type="button" class="src-refresh" title="Atualizar ' + esc(label) + '" onclick="event.stopPropagation();refreshSource(\'' + s.source + "')\">↻</button></span>";
  }).join("");
  const metaParts = [];
  if (LAST_META.fetched != null && LAST_META.shown != null && LAST_META.fetched !== LAST_META.shown) {
    let truncHint = "";
    if (LAST_META.truncation === "global_cap" && LAST_META.global_cap) {
      truncHint = " (teto total: " + LAST_META.global_cap + ")";
    } else if (LAST_META.truncation === "per_source" && LAST_META.limit_per_source) {
      truncHint = " (até " + LAST_META.limit_per_source + " por fonte)";
    } else if (LAST_META.after_filters != null && LAST_META.after_filters !== LAST_META.shown) {
      truncHint = " (após filtros/ranking)";
    }
    metaParts.push(LAST_META.fetched + " coletadas → " + LAST_META.shown + " exibidas" + truncHint);
    if (LAST_META.broad !== false && LAST_META.fetched > LAST_META.shown * 3) {
      metaParts.push("modo amplo: use palavras-chave para focar");
    }
  } else if (LAST_META.shown != null) {
    metaParts.push(LAST_META.shown + " vaga(s)");
  }
  if (LAST_META.elapsed_ms) metaParts.push((LAST_META.elapsed_ms / 1000).toFixed(1) + "s");
  if (LAST_META.broad === false) metaParts.push("modo focado");
  if (LAST_META.cached) metaParts.push("do cache");
  if (LAST_META.new_count) metaParts.push(LAST_META.new_count + " nova(s)");
  const metaHtml = metaParts.length
    ? '<span class="search-meta">' + esc(metaParts.join(" · ")) + "</span>"
    : "";
  const prefix = LAST_SOURCES.length ? "Fontes: " + chips : "";
  return '<div class="sources-strip">' + prefix + metaHtml + "</div>";
}

function renderResults() {
  const el = $("results");
  if (LAST_JOBS.length) {
    const p = $("searchProgress");
    if (p) p.remove();
    const live = $("searchLivePanel");
    if (live) live.remove();
  }
  const jobs = visibleJobs();
  if (!LAST_JOBS.length) {
    el.innerHTML = sourcesStrip() + smartEmptyState();
    return;
  }
  if (!jobs.length) {
    let msg = "Nenhuma vaga neste filtro.";
    if (ONLY_FAVORITES) msg = "Nenhuma vaga favoritada.";
    else if (HIDE_APPLIED) msg = "Nenhuma vaga pendente (ocultando já aplicadas).";
    else if (FILTER_SOURCE) msg = "Nenhuma vaga desta fonte na lista.";
    el.innerHTML = sourcesStrip() + sourceFilterBar() + toolbar(0)
      + '<div class="empty"><div class="big">🔍</div>' + esc(msg) + "</div>";
    return;
  }

  const pages = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));
  if (CURRENT_PAGE > pages) CURRENT_PAGE = pages;
  const start = (CURRENT_PAGE - 1) * PAGE_SIZE;
  const pageJobs = jobs.slice(start, start + PAGE_SIZE);

  let html = locationBanner() + sourcesStrip() + sourceFilterBar() + toolbar(jobs.length);
  pageJobs.forEach((j, i) => { html += jobCard(j, i); });
  html += pager(pages);
  el.innerHTML = html;
  updateStatCards();
  bindCardGlow(el);
}

function bindCardGlow(root) {
  if (!root) return;
  root.querySelectorAll(".card").forEach(card => {
    card.addEventListener("mousemove", e => {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
    });
  });
}

function smartEmptyState() {
  const totalRaw = LAST_SOURCES.reduce((n, s) => n + (s.fetched ?? s.count ?? 0), 0);
  const responded = LAST_SOURCES.filter(s => s.count > 0).map(s => SOURCE_LABELS[s.source] || s.source);
  const empty = LAST_SOURCES.filter(s => s.count === 0).map(s => SOURCE_LABELS[s.source] || s.source);

  let msg, hint = "";
  if (LAST_META.location_hint) {
    msg = LAST_META.location_hint;
  } else if (totalRaw > 0) {
    msg = "As fontes retornaram " + totalRaw + " vaga(s), mas nenhuma ficou na sua região ou filtros.";
    hint = '<div class="muted" style="margin-top:8px">Tente marcar <b>Incluir vagas remotas</b>, ampliar para o estado inteiro, ou mudar a área.</div>';
  } else {
    msg = "Nenhuma vaga encontrada nas fontes selecionadas.";
    if (empty.length) hint = '<div class="muted" style="margin-top:8px">Sem retorno de: ' + esc(empty.join(", ")) + ". Tente outras fontes ou amplie a busca.</div>";
  }
  if (responded.length && totalRaw > 0) {
    hint += '<div class="muted" style="margin-top:4px">Fontes com retorno: ' + esc(responded.join(", ")) + ".</div>";
  }
  return '<div class="empty"><div class="big">🤷</div>' + esc(msg) + hint + "</div>";
}

function toolbar(total) {
  const favCount = LAST_JOBS.filter(j => isFav(j.id)).length;
  const appliedCount = LAST_JOBS.filter(j => j.applied || isApplied(j.id)).length;
  return '<div class="count">'
    + '<span><b>' + total + '</b> vaga(s)'
    + (FILTER_SOURCE || ONLY_FAVORITES || HIDE_APPLIED ? " (filtradas)" : (isGuestMode() ? " · busca livre" : (isSimpleMode() ? " · na sua região" : " · ranqueadas por compatibilidade")))
    + "</span>"
    + '<span class="toolbar">'
    + '<label class="tb-label">Ordenar: '
    + '<select onchange="setSort(this.value)" aria-label="Ordenar resultados">'
    + '<option value="score"' + (SORT_KEY === "score" ? " selected" : "") + ">" + (isGuestMode() ? "Relevância" : "Compatibilidade") + "</option>"
    + '<option value="date"' + (SORT_KEY === "date" ? " selected" : "") + '>Mais recentes</option>'
    + '<option value="ats"' + (SORT_KEY === "ats" ? " selected" : "") + '>ATS</option>'
    + '<option value="title"' + (SORT_KEY === "title" ? " selected" : "") + '>Título</option>'
    + '</select></label>'
    + '<button id="favToggle" class="btn small ' + (ONLY_FAVORITES ? "primary" : "ghost") + '" onclick="toggleOnlyFavorites()">★ Favoritas (' + favCount + ')</button>'
    + '<button id="hideAppliedBtn" class="btn small ' + (HIDE_APPLIED ? "primary" : "ghost") + '" onclick="toggleHideApplied()">✓ Ocultar aplicadas (' + appliedCount + ')</button>'
    + '<button class="btn small ghost" onclick="exportJobs(\'csv\')" title="Exporta o que está visível nos filtros atuais">⬇ CSV</button>'
    + '<button class="btn small ghost" onclick="exportJobs(\'json\')">⬇ JSON</button>'
    + '</span></div>';
}

function toggleHideApplied() {
  HIDE_APPLIED = !HIDE_APPLIED;
  CURRENT_PAGE = 1;
  renderResults();
}

function exportJobs(fmt) {
  const jobs = visibleJobs();
  if (!jobs.length) { toast("Nada para exportar com os filtros atuais.", "warn"); return; }
  const params = new URLSearchParams({ format: fmt });
  if (FILTER_SOURCE) params.set("source", FILTER_SOURCE);
  if (ONLY_FAVORITES) params.set("favorites", "1");
  if (HIDE_APPLIED) params.set("hide_applied", "1");
  window.location.href = "/api/export?" + params.toString();
}

function scoreBar(score, label) {
  const pct = Math.max(0, Math.min(100, Math.round(score || 0)));
  const cls = scoreClass(pct);
  return '<div class="score-meter ' + cls + '" title="' + esc(label) + '">'
    + '<div class="score-meter-fill" style="width:' + pct + '%"></div>'
    + '<span class="score-meter-val">' + pct + "%</span></div>";
}

function scoreBarSimple(score) {
  const pct = Math.max(0, Math.min(100, Math.round(score || 0)));
  const cls = scoreClass(pct);
  const label = simpleScoreLabel(pct);
  return '<div class="score-meter ' + cls + '" title="' + esc(label) + '">'
    + '<div class="score-meter-fill" style="width:' + pct + '%"></div>'
    + '<span class="score-meter-val">' + esc(label) + "</span></div>";
}

function scoreRing(score) {
  const s = Math.round(score || 0);
  const cls = s >= 65 ? "high" : s >= 45 ? "mid" : "low";
  return '<div class="score-ring ' + cls + '" style="--v:' + s + '" title="Match ' + s + '%"><span>' + s + '</span></div>';
}

function companyInitials(name) {
  const parts = (name || "?").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0] || "?").slice(0, 2).toUpperCase();
}

function jobCard(j, index) {
  const simple = isSimpleMode();
  const guest = isGuestMode();
  const tags = (j.skills || []).map(s => '<span class="tag">' + esc(s) + "</span>").join("");
  const pills = [];
  if (j.is_new) pills.push('<span class="pill new">Nova</span>');
  if (!simple && j.easy_apply) pills.push('<span class="pill easy">Easy Apply</span>');
  if (j.salary) pills.push('<span class="pill">' + esc(j.salary) + "</span>");
  if (j.posted_at) pills.push('<span class="pill">' + esc(j.posted_at) + "</span>");
  const fav = isFav(j.id);
  const cmp = COMPARE.has(j.id);
  const delay = index != null ? ' style="animation-delay:' + Math.min(index * 40, 320) + 'ms"' : "";
  const reasons = j.reasons_text || (Array.isArray(j.reasons) ? j.reasons.join("; ") : (j.reasons || ""));
  const whyTitle = simple ? "Por que apareceu?" : "Por que essa vaga?";
  const reasonsHtml = reasons
    ? '<details class="why-job"><summary>' + whyTitle + "</summary><p>" + esc(reasons) + "</p></details>"
    : "";
  const tips = (j.cv_tips || []).slice(0, 2);
  const tipsHtml = simple && tips.length
    ? '<p class="cv-tip hint"><b>Dica:</b> ' + esc(tips.join(" ")) + "</p>"
    : "";

  const score = Math.round(j.score || 0);
  const matchCls = score >= 65 ? "high" : score >= 45 ? "mid" : "low";
  const matchLabel = guest ? "Relevância " + score + "%" : (simple ? simpleScoreLabel(score) : "Match " + score + "%");
  const matchHtml = '<span class="job-card__match ' + matchCls + '">' + esc(matchLabel) + "</span>";

  const scoreBarsHtml = !simple && !guest
    ? '<div class="score-bars pro-only">'
      + '<span class="score-bar-label">Match</span>' + scoreBar(j.score, "Match")
      + (j.ats != null ? '<span class="score-bar-label">ATS</span>' + scoreBar(j.ats, "ATS") : "")
      + "</div>"
    : "";

  const loc = [j.location, SOURCE_LABELS[j.source] || j.source].filter(Boolean).join(" · ");
  const alsoHtml = (j.also_in && j.also_in.length)
    ? '<p class="also-in muted">Também em: ' + j.also_in.map(s => esc(SOURCE_LABELS[s] || s)).join(" · ") + "</p>"
    : "";

  return '<article class="job-card' + (j.applied ? " is-applied" : "") + '" id="card-' + j.id + '"' + delay + ">"
    + '<div class="job-card__logo" aria-hidden="true">' + esc(companyInitials(j.company)) + "</div>"
    + '<div class="job-card__body">'
    + '<div class="job-card__head">'
    + "<div>"
    + '<h3 class="job-card__title" onclick="openJobPreview(\'' + j.id + "')\">" + esc(j.title) + "</h3>"
    + '<p class="job-card__company">' + esc(j.company || "Empresa") + "</p>"
    + '<p class="job-card__meta">' + esc(loc) + "</p>"
    + alsoHtml
    + "</div>"
    + '<button type="button" class="job-card__save fav' + (fav ? " on" : "") + '" title="Salvar" onclick="toggleFavorite(\'' + j.id + "')\">" + (fav ? "★" : "☆") + "</button>"
    + "</div>"
    + '<div class="job-card__tags">' + matchHtml
    + ' <button type="button" class="hp-link score-explain" onclick="openScoreExplain(\'' + j.id + "')\">Por quê?</button>"
    + pills.join("") + "</div>"
    + scoreBarsHtml
    + (j.description ? '<div class="desc">' + esc(j.description.slice(0, 180)) + (j.description.length > 180 ? "…" : "") + "</div>" : "")
    + reasonsHtml + tipsHtml
    + (tags && !simple ? '<div class="tags">' + tags + "</div>" : "")
    + '<div class="job-card__actions">'
    + '<a class="hp-btn hp-btn--primary btn primary" href="' + j.url + '" target="_blank" rel="noopener">Candidatar-se</a>'
    + '<button type="button" class="hp-btn hp-btn--ghost btn" onclick="showJobInline(\'' + j.id + "')\">Detalhes</button>"
    + (simple ? "" : '<button type="button" class="hp-btn hp-btn--ghost btn pro-only" onclick="atsDetail(\'' + j.id + "')\">" + (guest ? "Requisitos" : "ATS") + "</button>"
      + '<button type="button" class="hp-btn hp-btn--ghost btn pro-only" onclick="tailor(\'' + j.id + "')\">Adaptar CV</button>"
      + '<label class="cmp-check pro-only"><input type="checkbox" ' + (cmp ? "checked" : "") + " onchange=\"toggleCompare('" + j.id + "')\"> comparar</label>")
    + '<button type="button" class="hp-btn hp-btn--ghost btn ghost" onclick="addToPipeline(\'' + j.id + "')\">+ Pipeline</button>"
    + '<button type="button" class="hp-btn hp-btn--ghost btn ghost" onclick="toggleApplied(\'' + j.id + "')\">" + (j.applied ? "Desmarcar" : "Já apliquei") + "</button>"
    + "</div></div></article>";
}

function pager(pages) {
  if (pages <= 1) return "";
  return '<div class="pager">'
    + '<button class="btn small" ' + (CURRENT_PAGE <= 1 ? "disabled" : "") + ' onclick="goPage(' + (CURRENT_PAGE - 1) + ')">‹ Anterior</button>'
    + '<span class="muted">Página ' + CURRENT_PAGE + ' de ' + pages + '</span>'
    + '<button class="btn small" ' + (CURRENT_PAGE >= pages ? "disabled" : "") + ' onclick="goPage(' + (CURRENT_PAGE + 1) + ')">Próxima ›</button>'
    + '</div>';
}

function goPage(p) { CURRENT_PAGE = p; renderResults(); window.scrollTo({ top: 0, behavior: "smooth" }); }
function setSort(k) { SORT_KEY = k; CURRENT_PAGE = 1; renderResults(); }
function toggleOnlyFavorites() { ONLY_FAVORITES = !ONLY_FAVORITES; CURRENT_PAGE = 1; renderResults(); }

/* ---------- atualização in-place (sem re-render total) ---------- */
function replaceCard(id) {
  const job = LAST_JOBS.find(j => j.id === id);
  const el = $("card-" + id);
  if (!job || !el) return null;
  const tmp = document.createElement("div");
  tmp.innerHTML = jobCard(job);
  const fresh = tmp.firstElementChild;
  fresh.style.animation = "none";  // evita re-disparar a entrada
  el.replaceWith(fresh);
  return fresh;
}

function updateToolbarCounts() {
  const btn = $("favToggle");
  if (btn) {
    const favCount = LAST_JOBS.filter(j => isFav(j.id)).length;
    btn.innerHTML = "★ Favoritas (" + favCount + ")";
  }
}

function pulse(el, cls) {
  if (!el) return;
  el.classList.remove(cls);
  void el.offsetWidth;  // reflow para reiniciar a animação
  el.classList.add(cls);
}

/* ---------- favorites ---------- */
function toggleFavorite(id) {
  const wasFav = isFav(id);
  if (wasFav) {
    delete FAVORITES[id];
    postJSON("/api/state/favorite", { id, favorite: false }).catch(() => {});
  } else {
    const job = LAST_JOBS.find(j => j.id === id);
    FAVORITES[id] = job ? jobMeta(job) : { id };
    postJSON("/api/state/favorite", { id, favorite: true, meta: FAVORITES[id] }).catch(() => {});
  }
  saveFav();
  if (ONLY_FAVORITES) {
    renderResults();  // a vaga sai/entra da lista filtrada
    return;
  }
  const card = replaceCard(id);
  updateToolbarCounts();
  if (card && !wasFav) pulse(card.querySelector(".fav"), "pop");
}

/* ---------- modal ---------- */
function openModal(title, html, leftHtml) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  $("modalLeft").innerHTML = leftHtml || "";
  $("modal").showModal();
}

function copyModalText() {
  const ta = $("modalBody").querySelector("textarea");
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(() => toast("Copiado!", "success"));
}

function downloadModalText(name) {
  const ta = $("modalBody").querySelector("textarea");
  if (!ta) return;
  const blob = new Blob([ta.value], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}

async function atsDetail(id) {
  openModal(isGuestMode() ? "Requisitos da vaga" : "Análise ATS", '<div class="spinner"></div>');
  try {
    const d = await postJSON("/api/ats", { id });
    if (d.error) { $("modalBody").innerHTML = esc(d.error); return; }
    let html;
    if (d.needs_resume) {
      html = "<p><b>Modo visitante</b> — envie seu currículo para ver compatibilidade ATS.</p>";
      if (d.seniority) html += "<p>Nível indicado na vaga: <b>" + esc(d.seniority) + "</b></p>";
      html += "<p><b>Palavras-chave detectadas na vaga:</b><br>"
        + (d.job_keywords && d.job_keywords.length
          ? d.job_keywords.map(k => '<span class="kw miss">' + esc(k) + "</span>").join("")
          : "—") + "</p>";
      html += '<p class="muted"><button type="button" class="btn small primary" onclick="closeModal();document.getElementById(\'file\').click()">Enviar currículo</button></p>';
    } else {
      html = "<p>Cobertura de keywords: <b>" + Math.round(d.coverage) + "%</b> · ATS <b>" + Math.round(d.ats_score) + "/100</b></p>";
      if (d.format_score != null) html += "<p>Formato do CV: <b>" + Math.round(d.format_score) + "/100</b> · Cargo: <b>" + Math.round(d.title_alignment || 0) + "/100</b> · Nível: <b>" + Math.round(d.seniority_alignment || 0) + "/100</b></p>";
      html += '<div class="barwrap"><div style="width:' + Math.round(d.ats_score) + '%"></div></div>';
      html += "<p><b>Você tem:</b><br>" + (d.present.map(k => '<span class="kw">' + esc(k) + "</span>").join("") || "—") + "</p>";
      html += "<p><b>Faltando na vaga:</b><br>" + (d.missing.map(k => '<span class="kw miss">' + esc(k) + "</span>").join("") || "—") + "</p>";
      if (d.suggestions && d.suggestions.length) html += "<p><b>Sugestões:</b></p><ul>" + d.suggestions.map(s => "<li>" + esc(s) + "</li>").join("") + "</ul>";
    }
    $("modalBody").innerHTML = html;
  } catch (e) { $("modalBody").innerHTML = "Erro ao analisar."; }
}

async function tailor(id) {
  openModal("Currículo adaptado (rascunho)", '<div class="spinner"></div>',
    '<button class="btn small" onclick="copyModalText()">Copiar</button> <button class="btn small" onclick="downloadModalText(\'curriculo_adaptado.md\')">Baixar .md</button>');
  try {
    const d = await postJSON("/api/tailor", { id });
    if (d.error) { $("modalBody").innerHTML = esc(d.error); return; }
    $("modalBody").innerHTML = "<textarea>" + esc(d.markdown) + "</textarea>";
  } catch (e) { $("modalBody").innerHTML = "Erro ao gerar."; }
}

async function cover(id, lang) {
  openModal("Carta de apresentação", '<div class="spinner"></div>',
    '<button class="btn small" onclick="copyModalText()">Copiar</button> <button class="btn small" onclick="downloadModalText(\'carta.txt\')">Baixar</button>');
  try {
    const d = await postJSON("/api/cover", { id, lang: lang || "" });
    if (d.error) { $("modalBody").innerHTML = esc(d.error); return; }
    const bar = '<div class="lang-bar"><span class="muted" style="font-size:12px">Idioma:</span>'
      + '<button class="btn small" onclick="cover(\'' + id + "','')\">Auto</button>"
      + '<button class="btn small" onclick="cover(\'' + id + "','pt')\">Português</button>"
      + '<button class="btn small" onclick="cover(\'' + id + "','en')\">English</button></div>";
    $("modalBody").innerHTML = bar + "<textarea>" + esc(d.letter) + "</textarea>";
  } catch (e) { $("modalBody").innerHTML = "Erro ao gerar."; }
}

/* ---------- applied ---------- */
async function markApplied(id, val, skipRender) {
  const job = LAST_JOBS.find(j => j.id === id);
  if (val) {
    const meta = job ? jobMeta(job) : { id };
    meta.applied_at = Date.now();
    meta.pipeline_status = meta.pipeline_status || "candidatado";
    APPLIED[id] = meta;
  } else {
    delete APPLIED[id];
  }
  saveApplied();
  updatePipelineBadge();
  if (job) job.applied = val;
  if (!skipRender) replaceCard(id);
  try {
    await postJSON("/api/applied", { id, applied: val, meta: APPLIED[id] });
    await postJSON("/api/state/applied", { id, applied: val, meta: APPLIED[id] || {} });
  } catch (e) {}
}

async function openJobPreview(id) {
  openModal("Detalhes da vaga", '<div class="spinner"></div>');
  try {
    const d = await postJSON("/api/job/detail", { id });
    if (d.error) { $("modalBody").innerHTML = esc(d.error); return; }
    let html = "<h3>" + esc(d.title) + "</h3>";
    html += '<p class="muted">' + esc(d.company) + (d.location ? " · " + esc(d.location) : "") + "</p>";
    if (d.salary) html += '<p><b>Salário:</b> ' + esc(d.salary) + "</p>";
    if (d.posted_at) html += '<p class="muted">' + esc(d.posted_at) + "</p>";
    html += '<div class="job-preview">' + esc(d.description || "Sem descrição disponível.") + "</div>";
    html += '<p style="margin-top:12px"><a class="btn primary" href="' + d.url + '" target="_blank" rel="noopener">Abrir vaga</a></p>';
    $("modalBody").innerHTML = html;
  } catch (e) { $("modalBody").innerHTML = "Erro ao carregar vaga."; }
}

async function toggleApplied(id) {
  const job = LAST_JOBS.find(j => j.id === id);
  const wasApplied = job ? job.applied : isApplied(id);
  await markApplied(id, !wasApplied);
  if (!wasApplied) toast("Marcada como aplicada ✓", "success");
}

/* ---------- comparar vagas ---------- */
function toggleCompare(id) {
  if (COMPARE.has(id)) {
    COMPARE.delete(id);
  } else {
    if (COMPARE.size >= 3) { toast("Compare no máximo 3 vagas.", "warn"); renderResults(); return; }
    COMPARE.add(id);
  }
  updateCompareBar();
}

function updateCompareBar() {
  const bar = $("compareBar");
  if (!bar) return;
  if (COMPARE.size === 0) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  bar.querySelector(".cmp-count").textContent = COMPARE.size + " selecionada(s)";
}

function clearCompare() {
  COMPARE.clear();
  updateCompareBar();
  renderResults();
}

function openCompare() {
  const jobs = Array.from(COMPARE).map(id => LAST_JOBS.find(j => j.id === id)).filter(Boolean);
  if (jobs.length < 2) { toast("Selecione ao menos 2 vagas.", "warn"); return; }
  const rows = [
    ["Vaga", j => "<b>" + esc(j.title) + "</b>"],
    ["Empresa", j => esc(j.company || "—")],
    ["Local", j => esc(j.location || "—")],
    ["Fonte", j => esc(j.source || "—")],
    ["Score", j => '<span class="score ' + scoreClass(j.score) + '">' + Math.round(j.score) + "</span>"],
    ["ATS", j => Math.round(j.ats || 0) + "%"],
    ["Skills", j => (j.skills || []).map(s => '<span class="tag">' + esc(s) + "</span>").join("") || "—"],
    ["", j => '<a class="btn small primary" href="' + j.url + '" target="_blank" rel="noopener">Abrir</a>'],
  ];
  let html = '<div class="cmp-table"><table><tbody>';
  for (const [label, fn] of rows) {
    html += "<tr><th>" + esc(label) + "</th>" + jobs.map(j => "<td>" + fn(j) + "</td>").join("") + "</tr>";
  }
  html += "</tbody></table></div>";
  openModal("Comparar vagas", html);
}

/* ---------- painel / histórico ---------- */
function openDashboard() {
  const applied = Object.values(APPLIED);
  const favs = Object.values(FAVORITES);
  const scores = applied.map(a => a.score).filter(s => typeof s === "number");
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  const bySource = {};
  applied.forEach(a => { bySource[a.source || "—"] = (bySource[a.source || "—"] || 0) + 1; });
  const searched = LAST_JOBS.length;
  const favN = favs.length;
  const appliedN = applied.length;

  let html = '<div class="funnel">'
    + '<div class="funnel-step"><b>' + searched + '</b><span>Buscadas</span></div>'
    + '<div class="funnel-arrow">→</div>'
    + '<div class="funnel-step"><b>' + favN + '</b><span>Favoritas</span></div>'
    + '<div class="funnel-arrow">→</div>'
    + '<div class="funnel-step"><b>' + appliedN + '</b><span>Aplicadas</span></div>'
    + "</div>";

  html += '<div class="stats">'
    + statCard("📮", appliedN, "Candidaturas")
    + statCard("★", favN, "Favoritos")
    + statCard("🎯", avg, "Score médio")
    + "</div>";

  const srcKeys = Object.keys(bySource);
  if (srcKeys.length) {
    html += '<h4>Por fonte</h4><div class="tags">'
      + srcKeys.map(k => '<span class="tag">' + esc(k) + ": " + bySource[k] + "</span>").join("") + "</div>";
  }

  const sorted = applied.slice().sort((a, b) => (b.applied_at || 0) - (a.applied_at || 0));
  html += "<h4>Histórico de candidaturas</h4>";
  if (!sorted.length) {
    html += '<p class="muted">Nenhuma candidatura registrada ainda.</p>';
  } else {
    html += '<div class="hist">' + sorted.map(a => {
      const when = a.applied_at ? new Date(a.applied_at).toLocaleDateString() : "";
      return '<div class="hist-row"><div><b>' + esc(a.title || a.id) + "</b><div class=\"muted\">"
        + esc(a.company || "") + (a.location ? " · " + esc(a.location) : "") + "</div></div>"
        + '<div class="hist-meta"><span class="muted">' + esc(when) + "</span>"
        + (a.url ? ' <a class="btn small" href="' + a.url + '" target="_blank" rel="noopener">Abrir</a>' : "")
        + ' <button class="btn small ghost" onclick="removeApplied(\'' + a.id + "')\">Remover</button></div></div>";
    }).join("") + "</div>";
  }
  openModal("Dashboard HirePilot", html);
}

function statCard(icon, value, label) {
  return '<div class="stat"><div class="stat-icon">' + icon + '</div><div class="stat-val">'
    + value + '</div><div class="stat-label">' + esc(label) + "</div></div>";
}

function removeApplied(id) {
  delete APPLIED[id];
  saveApplied();
  const job = LAST_JOBS.find(j => j.id === id);
  if (job) job.applied = false;
  openDashboard();
  renderResults();
}

/* ---------- micro-interações globais ---------- */
// Efeito ripple em botões
document.addEventListener("pointerdown", e => {
  const btn = e.target.closest(".btn, .go");
  if (!btn || btn.disabled) return;
  const r = btn.getBoundingClientRect();
  const ink = document.createElement("span");
  ink.className = "ripple";
  const size = Math.max(r.width, r.height);
  ink.style.width = ink.style.height = size + "px";
  ink.style.left = (e.clientX - r.left - size / 2) + "px";
  ink.style.top = (e.clientY - r.top - size / 2) + "px";
  btn.appendChild(ink);
  setTimeout(() => ink.remove(), 600);
});

// Atalhos de teclado
document.addEventListener("keydown", e => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  // "/" foca a busca
  if (e.key === "/" && !typing) {
    const kw = $("keywords");
    if (kw && !$("appView").classList.contains("hidden")) { e.preventDefault(); kw.focus(); kw.select(); }
    return;
  }
  // Enter dispara a busca quando focado em campos de filtro de texto
  if (e.key === "Enter" && (document.activeElement.id === "keywords" || document.activeElement.id === "location")) {
    e.preventDefault();
    if (typeof search === "function") search();
    return;
  }
  // Esc limpa a seleção de comparação (quando não há modal aberto)
  if (e.key === "Escape" && !$("modal").open && COMPARE.size) {
    clearCompare();
  }
});

// Botão "voltar ao topo"
const toTop = $("toTop");
if (toTop) {
  window.addEventListener("scroll", () => {
    toTop.classList.toggle("show", window.scrollY > 600);
  }, { passive: true });
  toTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
}

// Rola até os resultados após a busca (útil no mobile)
function scrollToResults() {
  if (window.innerWidth <= 880) {
    const el = $("results");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// Atualiza o indicador de filtros ativos sempre que algo muda no painel
(function () {
  const panel = document.querySelector(".panel");
  if (!panel) return;
  panel.addEventListener("input", updateFilterCount);
  panel.addEventListener("change", updateFilterCount);
})();

/* ---------- versão, atualização, onboarding ---------- */
const UPDATE_DISMISS_KEY = LS_PREFIX + "updateDismiss";
let APP_VERSION = "0.0.0";

function finishOnboard() {
  dismissOnboard();
  if (!PROFILE) startGuestSearch();
}

function maybeShowOnboard() {
  if (lsGet(ONBOARD_KEY, false)) return;
  const d = $("onboardModal");
  if (d && d.showModal) {
    d.showModal();
    // Não bloqueia a landing: cliques na welcome fecham o modal via dismissOnboard()
    d.addEventListener("click", (e) => {
      if (e.target === d) dismissOnboard();
    }, { once: true });
  }
}

function parseSemver(v) {
  return String(v || "0").replace(/^v/i, "").split(".").map(n => parseInt(n, 10) || 0);
}

function semverGt(a, b) {
  const av = parseSemver(a);
  const bv = parseSemver(b);
  for (let i = 0; i < 3; i++) {
    if (av[i] !== bv[i]) return av[i] > bv[i];
  }
  return false;
}

function dismissUpdate() {
  const b = $("updateBanner");
  if (b) b.classList.add("hidden");
  lsSet(UPDATE_DISMISS_KEY, APP_VERSION);
}

function showUpdateBanner(url, ver) {
  if (lsGet(UPDATE_DISMISS_KEY, "") === ver) return;
  const b = $("updateBanner");
  if (!b) return;
  const el = $("updateVer");
  if (el) el.textContent = "v" + ver;
  const link = $("updateLink");
  if (link) link.href = url;
  b.classList.remove("hidden");
}

async function checkForUpdates(fallbackUrl) {
  try {
    const r = await fetch("https://api.github.com/repos/ericnacif/HirePilot/releases/latest");
    if (!r.ok) return;
    const d = await r.json();
    const latest = (d.tag_name || "").replace(/^v/i, "");
    if (latest && semverGt(latest, APP_VERSION)) {
      showUpdateBanner(d.html_url || fallbackUrl, latest);
    }
  } catch (e) { /* offline */ }
}

function enableConfiguredApiSources() {
  const saved = lsGet(FILTERS_KEY, null);
  if (saved && saved.sources && saved.sources.length) return;
  if (APP_META.jooble_configured) {
    const el = document.querySelector('#sources input[value="jooble"]');
    if (el) el.checked = true;
  }
  if (APP_META.careerjet_configured) {
    const el = document.querySelector('#sources input[value="careerjet"]');
    if (el) el.checked = true;
  }
}

function showPinModal() {
  const d = $("pinModal");
  if (d && d.showModal) d.showModal();
}

async function submitPin() {
  const inp = $("pinInput");
  const pin = (inp && inp.value || "").trim();
  if (!pin) { toast("Informe o PIN.", "warn"); return; }
  try {
    const r = await fetch("/api/auth/pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "PIN incorreto.");
    AUTH_REQUIRED = false;
    const d = $("pinModal");
    if (d) d.close();
    if (inp) inp.value = "";
    toast("Acesso liberado.", "success");
    bootstrapApp();
  } catch (e) {
    toast(e.message || "PIN incorreto.", "error");
  }
}

async function loadAppMeta() {
  try {
    const d = await fetch("/api/meta").then(r => r.json());
    APP_META = d;
    APP_VERSION = d.version || "0.0.0";
    AUTH_REQUIRED = !!d.auth_required;
    const verEl = $("appVersion");
    if (verEl) verEl.textContent = "v" + APP_VERSION;
    const varEl = $("appVariant");
    if (varEl) varEl.textContent = d.variant === "full" ? "· Edição Completa" : "· Edição Leve";
    if (AUTH_REQUIRED) showPinModal();
    checkForUpdates(d.release_url);
  } catch (e) {
    checkForUpdates("https://github.com/ericnacif/HirePilot/releases/latest");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(lsGet(THEME_KEY, "light"));
  applySimpleModeUI();
  initPrivacyBanner();
  if (isSimpleMode() && !lsGet(FILTERS_KEY, null)) applySimpleDefaults();
  onLocationScopeChange();
  loadAppMeta();
  ["keywords", "keywordsMain"].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener("input", () => syncKeywordInputs(el));
  });
  if (!lsGet(ONBOARD_KEY, false)) {
    maybeShowOnboard();
  }
  bootstrapApp();
  refreshSourceHealth(false);
  document.querySelectorAll("#experience input").forEach(inp => {
    inp.addEventListener("change", saveFilters);
  });
});
window.addEventListener("resize", () => {
  if (PROFILE || isGuestMode()) setAppShellVisible(true);
});
