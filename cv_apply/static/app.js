"use strict";

let PROFILE = null;
let LAST_JOBS = [];
let CURRENT_PAGE = 1;
const PAGE_SIZE = 10;
let SORT_KEY = "score";
let ONLY_FAVORITES = false;

const FILTERS_KEY = "vagamatch.filters";
const FAVORITES_KEY = "vagamatch.favorites";
const APPLIED_KEY = "vagamatch.applied";
const THEME_KEY = "vagamatch.theme";
const SAVED_KEY = "vagamatch.savedSearches";

/* ---------- helpers ---------- */
function $(id) { return document.getElementById(id); }
function getChecked(id) { return Array.from(document.querySelectorAll("#" + id + " input:checked")).map(e => e.value); }
function scoreClass(s) { return s >= 65 ? "high" : (s >= 45 ? "mid" : "low"); }
function esc(s) { return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function lsGet(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
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

function toast(msg, type) {
  const t = document.createElement("div");
  t.className = "toast " + (type || "");
  t.setAttribute("role", "status");
  t.textContent = msg;
  $("toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 3800);
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* ---------- theme ---------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = $("themeBtn");
  if (btn) {
    btn.textContent = theme === "light" ? "🌙" : "☀️";
    btn.setAttribute("aria-label", theme === "light" ? "Ativar tema escuro" : "Ativar tema claro");
  }
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  const next = cur === "dark" ? "light" : "dark";
  lsSet(THEME_KEY, next);
  applyTheme(next);
}
applyTheme(lsGet(THEME_KEY, "dark"));

/* ---------- upload ---------- */
const drop = $("drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", e => {
  const f = e.dataTransfer.files[0];
  if (f) { $("file").files = e.dataTransfer.files; upload(); }
});

async function upload() {
  const f = $("file").files[0];
  if (!f) return;
  $("fileName").textContent = "Enviando " + f.name + "...";
  const fd = new FormData(); fd.append("resume", f);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const d = await r.json();
    if (d.error) { $("fileName").textContent = d.error; toast(d.error, "error"); return; }
    PROFILE = d.profile;
    showProfile();
    toast("Currículo analisado!", "success");
  } catch (e) {
    $("fileName").textContent = "Erro ao enviar. Tente novamente.";
    toast("Erro ao enviar o currículo.", "error");
  }
}

function profileInfo() {
  const bits = [];
  if (PROFILE.seniority) bits.push(PROFILE.seniority);
  if (PROFILE.years_experience) bits.push(PROFILE.years_experience + " anos");
  bits.push((PROFILE.skills || []).length + " skills");
  return bits.join(" · ");
}

function showProfile() {
  $("uploadView").classList.add("hidden");
  $("appView").classList.remove("hidden");
  $("resetBtn").classList.remove("hidden");
  $("dashBtn").classList.remove("hidden");
  $("pName").textContent = PROFILE.name || "Perfil carregado";
  $("pInfo").textContent = profileInfo();
  const v = PROFILE.format_score == null ? 0 : PROFILE.format_score;
  $("ring").style.setProperty("--v", v);
  $("ringv").textContent = PROFILE.format_score == null ? "--" : v;
  $("seniority").value = PROFILE.seniority || "";
  restoreFilters();
  renderSavedSearches();
  if (!$("keywords").value && PROFILE.job_hint) $("keywords").value = PROFILE.job_hint;
}

async function saveSeniority() {
  const val = $("seniority").value;
  try {
    await postJSON("/api/profile", { seniority: val });
    if (PROFILE) PROFILE.seniority = val;
    $("pInfo").textContent = profileInfo();
  } catch (e) { toast("Não foi possível salvar a senioridade.", "error"); }
}

function resetProfile() {
  PROFILE = null;
  $("appView").classList.add("hidden");
  $("uploadView").classList.remove("hidden");
  $("resetBtn").classList.add("hidden");
  $("dashBtn").classList.add("hidden");
  $("fileName").textContent = "";
  $("file").value = "";
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

/* ---------- filters persistence ---------- */
function collectFilters() {
  return {
    keywords: $("keywords").value, location: $("location").value,
    workplace: getChecked("workplace"), job_type: getChecked("job_type"),
    experience: getChecked("experience"), date_posted: $("date_posted").value,
    sources: getChecked("sources"), limit: parseInt($("limit").value) || 20,
  };
}

function saveFilters() { lsSet(FILTERS_KEY, collectFilters()); }

function setChecks(id, values) {
  document.querySelectorAll("#" + id + " input").forEach(e => { e.checked = values.includes(e.value); });
}

function applyFilterObject(f) {
  if (!f) return;
  if (f.keywords != null) $("keywords").value = f.keywords;
  if (f.location != null) $("location").value = f.location;
  if (f.date_posted) $("date_posted").value = f.date_posted;
  if (f.limit) $("limit").value = f.limit;
  if (f.workplace) setChecks("workplace", f.workplace);
  if (f.job_type) setChecks("job_type", f.job_type);
  if (f.experience) setChecks("experience", f.experience);
  if (f.sources && f.sources.length) setChecks("sources", f.sources);
}

function restoreFilters() { applyFilterObject(lsGet(FILTERS_KEY, null)); }

function toggleAllSources() {
  const boxes = document.querySelectorAll("#sources input");
  const allOn = Array.from(boxes).every(b => b.checked);
  boxes.forEach(b => { b.checked = !allOn; });
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
  const btn = $("go"); btn.disabled = true; btn.textContent = "Buscando...";
  $("results").innerHTML = skeletons(4);
  const payload = collectFilters();
  saveFilters();
  if (!payload.sources.length) { toast("Selecione ao menos uma fonte.", "error"); btn.disabled = false; btn.textContent = "Buscar vagas"; return; }
  try {
    const d = await postJSON("/api/search", payload);
    if (d.error) { $("results").innerHTML = '<div class="empty"><div class="big">⚠️</div>' + esc(d.error) + "</div>"; }
    else {
      LAST_JOBS = (d.jobs || []).map(j => ({ ...j, applied: j.applied || isApplied(j.id) }));
      CURRENT_PAGE = 1;
      COMPARE.clear();
      updateCompareBar();
      renderResults();
    }
  } catch (e) {
    $("results").innerHTML = '<div class="empty"><div class="big">⚠️</div>Erro na busca. Tente novamente.</div>';
    toast("Erro na busca.", "error");
  }
  btn.disabled = false; btn.textContent = "Buscar vagas";
}

function visibleJobs() {
  let jobs = LAST_JOBS.slice();
  if (ONLY_FAVORITES) jobs = jobs.filter(j => isFav(j.id));
  const cmp = {
    score: (a, b) => b.score - a.score,
    ats: (a, b) => (b.ats || 0) - (a.ats || 0),
    title: (a, b) => (a.title || "").localeCompare(b.title || ""),
  }[SORT_KEY] || ((a, b) => b.score - a.score);
  jobs.sort(cmp);
  return jobs;
}

function renderResults() {
  const el = $("results");
  const jobs = visibleJobs();
  if (!LAST_JOBS.length) { el.innerHTML = '<div class="empty"><div class="big">🤷</div>Nenhuma vaga encontrada. Tente outras palavras-chave ou fontes.</div>'; return; }
  if (!jobs.length) { el.innerHTML = toolbar(0) + '<div class="empty"><div class="big">★</div>Nenhuma vaga favoritada ainda.</div>'; return; }

  const pages = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));
  if (CURRENT_PAGE > pages) CURRENT_PAGE = pages;
  const start = (CURRENT_PAGE - 1) * PAGE_SIZE;
  const pageJobs = jobs.slice(start, start + PAGE_SIZE);

  let html = toolbar(jobs.length);
  for (const j of pageJobs) html += jobCard(j);
  html += pager(pages);
  el.innerHTML = html;
}

function toolbar(total) {
  const favCount = LAST_JOBS.filter(j => isFav(j.id)).length;
  return '<div class="count">'
    + '<span>' + total + ' vaga(s)</span>'
    + '<span class="toolbar">'
    + '<label class="tb-label">Ordenar: '
    + '<select onchange="setSort(this.value)" aria-label="Ordenar resultados">'
    + '<option value="score"' + (SORT_KEY === "score" ? " selected" : "") + '>Compatibilidade</option>'
    + '<option value="ats"' + (SORT_KEY === "ats" ? " selected" : "") + '>ATS</option>'
    + '<option value="title"' + (SORT_KEY === "title" ? " selected" : "") + '>Título</option>'
    + '</select></label>'
    + '<button class="btn small ' + (ONLY_FAVORITES ? "primary" : "ghost") + '" onclick="toggleOnlyFavorites()">★ Favoritas (' + favCount + ')</button>'
    + '<button class="btn small ghost" onclick="exportJobs(\'csv\')">⬇ CSV</button>'
    + '<button class="btn small ghost" onclick="exportJobs(\'json\')">⬇ JSON</button>'
    + '</span></div>';
}

function jobCard(j) {
  const tags = (j.skills || []).map(s => '<span class="tag">' + esc(s) + "</span>").join("");
  const pills = [];
  if (j.easy_apply) pills.push('<span class="pill easy">⚡ Easy Apply</span>');
  if (j.posted_at) pills.push('<span class="pill">' + esc(j.posted_at) + "</span>");
  const fav = isFav(j.id);
  const cmp = COMPARE.has(j.id);
  return '<div class="card' + (j.applied ? " applied" : "") + '" id="card-' + j.id + '">'
    + '<div class="card-top"><div>'
    + '<div class="src">' + esc(j.source) + "</div>"
    + "<h3>" + esc(j.title) + "</h3>"
    + '<div class="meta">' + esc(j.company) + (j.location ? " · " + esc(j.location) : "") + "</div>"
    + "</div>"
    + '<div class="badges">'
    + '<button class="fav' + (fav ? " on" : "") + '" title="Favoritar" aria-label="Favoritar vaga" onclick="toggleFavorite(\'' + j.id + "')\">" + (fav ? "★" : "☆") + "</button>"
    + '<span class="atsb">ATS ' + Math.round(j.ats || 0) + '%</span>'
    + '<span class="score ' + scoreClass(j.score) + '">' + Math.round(j.score) + "</span></div>"
    + "</div>"
    + (pills.length ? '<div class="tags">' + pills.join("") + "</div>" : "")
    + (j.description ? '<div class="desc">' + esc(j.description) + "</div>" : "")
    + (tags ? '<div class="tags">' + tags + "</div>" : "")
    + (j.reasons ? '<div class="reasons">' + esc(j.reasons) + "</div>" : "")
    + '<div class="actions">'
    + '<a class="btn primary" href="' + j.url + '" target="_blank" rel="noopener" onclick="markApplied(\'' + j.id + "',true)\">Aplicar</a>"
    + '<button class="btn" onclick="atsDetail(\'' + j.id + "')\">Análise ATS</button>"
    + '<button class="btn" onclick="tailor(\'' + j.id + "')\">Adaptar currículo</button>"
    + '<button class="btn" onclick="cover(\'' + j.id + "')\">Carta</button>"
    + '<button class="btn ghost" onclick="toggleApplied(\'' + j.id + "')\">" + (j.applied ? "Desmarcar" : "Já apliquei") + "</button>"
    + '<label class="cmp-check"><input type="checkbox" ' + (cmp ? "checked" : "") + " onchange=\"toggleCompare('" + j.id + "')\"> comparar</label>"
    + "</div></div>";
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

function exportJobs(fmt) {
  if (!LAST_JOBS.length) { toast("Busque vagas primeiro.", "error"); return; }
  window.location.href = "/api/export?format=" + fmt;
}

/* ---------- favorites ---------- */
function toggleFavorite(id) {
  if (isFav(id)) {
    delete FAVORITES[id];
  } else {
    const job = LAST_JOBS.find(j => j.id === id);
    FAVORITES[id] = job ? jobMeta(job) : { id };
  }
  saveFav();
  renderResults();
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
  openModal("Análise ATS", '<div class="spinner"></div>');
  try {
    const d = await postJSON("/api/ats", { id });
    if (d.error) { $("modalBody").innerHTML = esc(d.error); return; }
    let html = "<p>Compatibilidade da vaga: <b>" + Math.round(d.coverage) + "%</b> · ATS estimado <b>" + Math.round(d.ats_score) + "/100</b></p>";
    html += '<div class="barwrap"><div style="width:' + Math.round(d.coverage) + '%"></div></div>';
    html += "<p><b>Você tem:</b><br>" + (d.present.map(k => '<span class="kw">' + esc(k) + "</span>").join("") || "—") + "</p>";
    html += "<p><b>Faltando na vaga:</b><br>" + (d.missing.map(k => '<span class="kw miss">' + esc(k) + "</span>").join("") || "—") + "</p>";
    if (d.suggestions && d.suggestions.length) html += "<p><b>Sugestões:</b></p><ul>" + d.suggestions.map(s => "<li>" + esc(s) + "</li>").join("") + "</ul>";
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
async function markApplied(id, val) {
  const job = LAST_JOBS.find(j => j.id === id);
  if (val) {
    const meta = job ? jobMeta(job) : { id };
    meta.applied_at = Date.now();
    APPLIED[id] = meta;
  } else {
    delete APPLIED[id];
  }
  saveApplied();
  if (job) job.applied = val;
  try { await postJSON("/api/applied", { id, applied: val }); } catch (e) {}
}

async function toggleApplied(id) {
  const job = LAST_JOBS.find(j => j.id === id);
  const wasApplied = job ? job.applied : isApplied(id);
  await markApplied(id, !wasApplied);
  renderResults();
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

  let html = '<div class="stats">'
    + statCard("📮", applied.length, "Candidaturas")
    + statCard("★", favs.length, "Favoritos")
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
  openModal("Painel", html);
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
