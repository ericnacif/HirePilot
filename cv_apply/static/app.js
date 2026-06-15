"use strict";

let PROFILE = null;
const FILTERS_KEY = "vagamatch.filters";

/* ---------- helpers ---------- */
function $(id) { return document.getElementById(id); }
function getChecked(id) { return Array.from(document.querySelectorAll("#" + id + " input:checked")).map(e => e.value); }
function scoreClass(s) { return s >= 65 ? "high" : (s >= 45 ? "mid" : "low"); }
function esc(s) { return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function toast(msg, type) {
  const t = document.createElement("div");
  t.className = "toast " + (type || "");
  t.textContent = msg;
  $("toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 3800);
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

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
  $("pName").textContent = PROFILE.name || "Perfil carregado";
  $("pInfo").textContent = profileInfo();
  const v = PROFILE.format_score == null ? 0 : PROFILE.format_score;
  $("ring").style.setProperty("--v", v);
  $("ringv").textContent = PROFILE.format_score == null ? "--" : v;
  $("seniority").value = PROFILE.seniority || "";
  restoreFilters();
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

function saveFilters() {
  try { localStorage.setItem(FILTERS_KEY, JSON.stringify(collectFilters())); } catch (e) {}
}

function setChecks(id, values) {
  document.querySelectorAll("#" + id + " input").forEach(e => { e.checked = values.includes(e.value); });
}

function restoreFilters() {
  let f;
  try { f = JSON.parse(localStorage.getItem(FILTERS_KEY) || "null"); } catch (e) { f = null; }
  if (!f) return;
  if (f.keywords) $("keywords").value = f.keywords;
  if (f.location) $("location").value = f.location;
  if (f.date_posted) $("date_posted").value = f.date_posted;
  if (f.limit) $("limit").value = f.limit;
  if (f.workplace) setChecks("workplace", f.workplace);
  if (f.job_type) setChecks("job_type", f.job_type);
  if (f.experience) setChecks("experience", f.experience);
  if (f.sources && f.sources.length) setChecks("sources", f.sources);
}

function toggleAllSources() {
  const boxes = document.querySelectorAll("#sources input");
  const allOn = Array.from(boxes).every(b => b.checked);
  boxes.forEach(b => { b.checked = !allOn; });
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
    render(d);
  } catch (e) {
    $("results").innerHTML = '<div class="empty"><div class="big">⚠️</div>Erro na busca. Tente novamente.</div>';
    toast("Erro na busca.", "error");
  }
  btn.disabled = false; btn.textContent = "Buscar vagas";
}

function render(data) {
  const el = $("results");
  if (data.error) { el.innerHTML = '<div class="empty"><div class="big">⚠️</div>' + esc(data.error) + "</div>"; return; }
  const jobs = data.jobs || [];
  if (!jobs.length) { el.innerHTML = '<div class="empty"><div class="big">🤷</div>Nenhuma vaga encontrada. Tente outras palavras-chave ou fontes.</div>'; return; }
  let html = '<div class="count"><span>' + jobs.length + " vagas (ordenadas por compatibilidade)</span></div>";
  for (const j of jobs) {
    const tags = (j.skills || []).map(s => '<span class="tag">' + esc(s) + "</span>").join("");
    const pills = [];
    if (j.easy_apply) pills.push('<span class="pill easy">⚡ Easy Apply</span>');
    if (j.posted_at) pills.push('<span class="pill">' + esc(j.posted_at) + "</span>");
    html += '<div class="card' + (j.applied ? " applied" : "") + '" id="card-' + j.id + '">'
      + '<div class="card-top"><div>'
      + '<div class="src">' + esc(j.source) + "</div>"
      + "<h3>" + esc(j.title) + "</h3>"
      + '<div class="meta">' + esc(j.company) + (j.location ? " · " + esc(j.location) : "") + "</div>"
      + "</div>"
      + '<div class="badges"><span class="atsb">ATS ' + Math.round(j.ats || 0) + '%</span>'
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
      + "</div></div>";
  }
  el.innerHTML = html;
}

/* ---------- modal ---------- */
function openModal(title, html, leftHtml) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  $("modalLeft").innerHTML = leftHtml || "";
  $("modal").showModal();
}

function copyModalText(btn) {
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
  try { await postJSON("/api/applied", { id, applied: val }); } catch (e) {}
}

async function toggleApplied(id) {
  const card = $("card-" + id);
  const isApplied = card.classList.contains("applied");
  await markApplied(id, !isApplied);
  card.classList.toggle("applied");
  const btn = card.querySelector(".actions .btn:last-child");
  btn.textContent = isApplied ? "Já apliquei" : "Desmarcar";
}
