// Leonida Studio — front-end (vanilla JS)
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (url, opts = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.blob();
};
const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2600); };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------------------------------------------------------- abas
function showTab(name) {
  $$("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("on", t.id === "tab-" + name));
  if (name === "prontos") $("#gallery").src = "/prontos/index.html?t=" + Date.now();
  if (name === "editor") loadPostList();
}
$$("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// ---------------------------------------------------------------- status
async function loadStatus() {
  const s = await api("/api/status");
  $("#countdown").innerHTML = s.days > 0 ? `<b>${s.days}</b><small>DIAS PARA O GTA VI</small>` : `<b>VI</b><small>JÁ DISPONÍVEL</small>`;
  const ok = (v) => (v ? "🟢" : "⚪️");
  $("#sys").innerHTML = `<span>${ok(s.claude)} Redator IA (Claude)</span><span>${ok(s.cutout)} Recorte (rembg)</span>
    <span>${ok(s.node)} Vídeo (HyperFrames)</span><span>${ok(s.ffmpeg)} FFmpeg</span><span>${ok(s.music)} Música tema</span><span>${ok(s.telegram)} Telegram</span>`;
  const ms = $("#music-state"); if (ms) ms.textContent = s.music ? "✅ Música tema configurada — todos os vídeos saem com ela." : "⚪️ Nenhuma música tema ainda. Cole a URL do trailer abaixo.";
}

// ---------------------------------------------------------------- radar
function renderRadar(data) {
  const list = $("#radar-list");
  if (!data.stories?.length) { list.innerHTML = `<p class="hint">Nada ainda — clique em "Atualizar radar".</p>`; return; }
  list.innerHTML = data.stories.map((s, i) => {
    const pills = (s.official ? `<span class="pill off">OFICIAL</span>` : "") + (s.video ? `<span class="pill vid">VÍDEO</span>` : "") +
      (s.is_new && !s.status ? `<span class="pill new">NOVO</span>` : "") + (s.status ? `<span class="pill st">${esc(s.status)}</span>` : "");
    const srcs = s.sources.slice(0, 4).map((x) => `<a href="${esc(x.url)}" target="_blank">${esc(x.name)}</a>`).join(" · ");
    return `<article class="story ${s.is_new && !s.status ? "new" : ""}">
      <div class="score">${Math.round(s.score)}<small>#${i + 1}</small></div>
      <div><div>${pills}</div><h3>${esc(s.title)}</h3>${s.title_pt && s.title_pt !== s.title ? `<div class="pt">🇧🇷 ${esc(s.title_pt)}</div>` : ""}
        <div class="src">${s.coverage} matérias · ${srcs}</div></div>
      <div class="go">${s.blocked ? `<button disabled title="O perfil só publica notícia oficial ou confirmada">Bloqueada (${esc(s.kind)})</button>` : `<button class="primary" data-draft="${s.id}">Criar post</button>`}<button data-ignore="${s.id}">Ignorar</button></div>
    </article>`;
  }).join("");
  $$("[data-draft]").forEach((b) => b.addEventListener("click", () => draftFromStory(b.dataset.draft, b)));
  $$("[data-ignore]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/radar/${b.dataset.ignore}/ignore`, { method: "POST" }); b.closest(".story").remove(); }));
}
async function loadRadar() { renderRadar(await api("/api/radar")); }
$("#btn-scan").addEventListener("click", async (e) => {
  e.target.disabled = true; e.target.textContent = "Buscando…";
  try { renderRadar(await api(`/api/radar/scan?hours=${$("#radar-hours").value}`, { method: "POST" })); toast("Radar atualizado"); }
  catch (err) { toast("Erro: " + err.message); }
  e.target.disabled = false; e.target.textContent = "Atualizar radar";
});
async function draftFromStory(id, btn) {
  btn.disabled = true; btn.textContent = "Redigindo…";
  try {
    const r = await api(`/api/posts/from-story/${id}`, { method: "POST" });
    toast(r.needs_review ? "Rascunho criado (sem IA) — revise o texto" : "Post redigido pela IA");
    showTab("editor"); await loadPostList(r.id);
  } catch (err) { toast("Erro: " + err.message); }
  btn.disabled = false; btn.textContent = "Criar post";
}
$("#btn-count").addEventListener("click", async () => { const r = await api("/api/contagem?video=true", { method: "POST" }); followJob(r.job, $("#job-log")); toast("Gerando post de contagem…"); });

// ---------------------------------------------------------------- editor
let current = null;
async function loadPostList(select) {
  const posts = await api("/api/posts");
  const sel = $("#post-select");
  sel.innerHTML = `<option value="">— escolha um post —</option>` + posts.map((p) =>
    `<option value="${esc(p.id)}"${p.error ? ` title="${esc(p.error)}"` : ""}>${p.error ? "❌" : p.built ? "✅" : p.needs_review ? "⚠️" : "📝"} ${esc(p.id)}</option>`).join("");
  const target = select || current?.id;
  if (target) { sel.value = target; await openPost(target); }
}
$("#post-select").addEventListener("change", (e) => e.target.value && openPost(e.target.value));
$("#btn-new").addEventListener("click", async () => {
  const title = prompt("Título curto do post (vira o nome da pasta):"); if (!title) return;
  const r = await api("/api/posts/new", { method: "POST", body: JSON.stringify({ title }) });
  await loadPostList(r.id);
});

function setField(name, v) { const el = $(`[name="${name}"]`, $("#post-form")); if (!el) return; if (el.type === "checkbox") el.checked = v !== false; else el.value = v ?? ""; }
async function openPost(id) {
  current = await api(`/api/posts/${encodeURIComponent(id)}`);
  $("#editor").classList.remove("hidden");
  const p = current;
  setField("tag", p.tag || "oficial"); setField("date", String(p.date || "").slice(0, 10)); setField("layout", p.layout || "cover");
  setField("image", p.image); setField("zoom", p.zoom || ""); setField("cutout", p.cutout); setField("cta", p.cta);
  setField("source_name", p.source?.name); setField("source_url", p.source?.url);
  for (const l of ["pt", "en"]) {
    const loc = p[l] || {};
    ["kicker", "headline", "summary", "caption"].forEach((k) => setField(`${l}.${k}`, loc[k]));
    setField(`${l}.hashtags`, (loc.hashtags || []).join(" "));
    setField(`${l}.slides`, loc.slides?.length ? JSON.stringify(loc.slides, null, 1) : "");
  }
  $("#preview-img").removeAttribute("src");
  if (p.needs_review) toast("⚠️ Rascunho sem IA: revise manchete, resumo e legenda");
}
function collect() {
  const f = $("#post-form"); const g = (n) => $(`[name="${n}"]`, f);
  const p = { ...current, tag: g("tag").value, date: g("date").value, layout: g("layout").value, image: g("image").value.trim(),
    cutout: g("cutout").checked, cta: g("cta").checked, source: { name: g("source_name").value, url: g("source_url").value }, _reviewed: true };
  const z = parseFloat(g("zoom").value); if (z) p.zoom = z; else delete p.zoom;
  for (const l of ["pt", "en"]) {
    const loc = { ...(current[l] || {}) };
    ["kicker", "headline", "summary", "caption"].forEach((k) => (loc[k] = g(`${l}.${k}`).value));
    loc.hashtags = g(`${l}.hashtags`).value.split(/[\s,]+/).filter(Boolean);
    const sl = g(`${l}.slides`).value.trim();
    if (sl) { try { loc.slides = JSON.parse(sl); } catch (_) { throw new Error(`Slides ${l.toUpperCase()}: JSON inválido`); } } else delete loc.slides;
    p[l] = loc;
  }
  return p;
}
async function save() {
  const p = collect();
  const r = await api(`/api/posts/${encodeURIComponent(current.id)}`, { method: "PUT", body: JSON.stringify(p) });
  current = { ...p }; delete current._reviewed;
  if (r.errors?.length) toast("Salvo — falta: " + r.errors.join(", ")); else toast("Salvo");
  return r;
}
$("#btn-save").addEventListener("click", () => save().catch((e) => toast(e.message)));
async function preview(lang, btn) {
  try {
    await save(); btn.disabled = true; btn.textContent = "Renderizando…";
    const blob = await api(`/api/posts/${encodeURIComponent(current.id)}/preview?lang=${lang}`, { method: "POST" });
    $("#preview-img").src = URL.createObjectURL(blob);
  } catch (e) { toast("Erro: " + e.message); }
  btn.disabled = false; btn.textContent = lang === "pt" ? "Prévia BR" : "Prévia US";
}
$("#btn-prev-pt").addEventListener("click", (e) => preview("pt", e.target));
$("#btn-prev-en").addEventListener("click", (e) => preview("en", e.target));
$("#btn-build").addEventListener("click", async (e) => {
  try {
    const s = await save(); if (s.errors?.length) return;
    const r = await api(`/api/posts/${encodeURIComponent(current.id)}/build?video=${$("#with-video").checked}`, { method: "POST" });
    followJob(r.job, $("#job-log"), () => { toast("Post pronto! Veja em Prontos"); loadPostList(current.id); });
  } catch (err) { toast("Erro: " + err.message); }
});
$("#btn-send").addEventListener("click", async () => {
  try { const r = await api(`/api/posts/${encodeURIComponent(current.id)}/send`, { method: "POST" }); toast(r.sent.length ? "Enviado: " + r.sent.join(", ") : "Configure TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID"); }
  catch (e) { toast("Erro: " + e.message); }
});
$("#upload").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file || !current) return;
  const fd = new FormData(); fd.append("file", file);
  const r = await fetch(`/api/posts/${encodeURIComponent(current.id)}/upload`, { method: "POST", body: fd }).then((x) => x.json());
  setField("image", r.image); toast("Imagem enviada");
});

function followJob(id, logEl, onDone) {
  logEl.classList.remove("hidden"); logEl.textContent = "Trabalhando…";
  const t = setInterval(async () => {
    let j;
    try { j = await api(`/api/jobs/${id}`); }
    catch (error) {
      // Servidor reiniciado ou tarefa perdida: para de consultar e libera a tela.
      clearInterval(t);
      logEl.textContent += `\n❌ ${error.message || "tarefa perdida"} — gere de novo.`;
      return;
    }
    logEl.textContent = j.log.join("\n") + (j.status === "running" ? "\n…" : j.status === "done" ? `\n✅ ${j.result}` : "");
    logEl.scrollTop = logEl.scrollHeight;
    if (j.status !== "running") { clearInterval(t); if (j.status === "done" && onDone) onDone(j); }
  }, 1500);
}

// ---------------------------------------------------------------- biblioteca oficial
let library = [];
$("#btn-lib").addEventListener("click", async () => {
  $("#lib-modal").classList.remove("hidden");
  if (!library.length) { $("#lib-grid").innerHTML = "<p class='hint'>Carregando…</p>"; library = await api("/api/library"); }
  drawLib();
});
$("#lib-close").addEventListener("click", () => $("#lib-modal").classList.add("hidden"));
$("#lib-filter").addEventListener("input", drawLib);
function drawLib() {
  const q = $("#lib-filter").value.toLowerCase();
  $("#lib-grid").innerHTML = library.filter((i) => !q || i.name.toLowerCase().includes(q)).map((i) =>
    `<figure data-url="${esc(i.url)}"><img loading="lazy" src="/api/thumb?url=${encodeURIComponent(i.url)}"><figcaption>${esc(i.name)}</figcaption></figure>`).join("");
  $$("#lib-grid figure").forEach((f) => f.addEventListener("click", () => { setField("image", f.dataset.url); $("#lib-modal").classList.add("hidden"); toast("Imagem escolhida"); }));
}

// ---------------------------------------------------------------- cortes
$("#clip-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target; const d = Object.fromEntries(new FormData(f)); d.subtitles = !!f.subtitles.checked; d.music = !!f.music.checked;
  try { const r = await api("/api/clips", { method: "POST", body: JSON.stringify(d) }); followJob(r.job, $("#clip-log"), () => toast("Corte pronto! Veja em Prontos")); }
  catch (err) { toast("Erro: " + err.message); }
});

$("#music-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  try { const r = await api("/api/music", { method: "POST", body: JSON.stringify(d) }); followJob(r.job, $("#music-log"), () => { toast("Música tema salva"); loadStatus(); }); }
  catch (err) { toast("Erro: " + err.message); }
});

// ---------------------------------------------------------------- gameplay longa
let gameplayProject = null;
let gameplayPlan = null;
let gameplayBusy = false;
let gameplayLongLimit = 660;

function gameplayTime(seconds) {
  const numeric = Number(seconds);
  const value = Math.round(Math.max(0, Number.isFinite(numeric) ? numeric : 0) * 100);
  const hours = Math.floor(value / 360000);
  const minutes = Math.floor(value % 360000 / 6000);
  const whole = Math.floor(value % 6000 / 100);
  const decimals = value % 100;
  const tail = String(whole).padStart(2, "0") + (decimals ? "." + String(decimals).padStart(2, "0").replace(/0$/, "") : "");
  return (hours ? String(hours).padStart(2, "0") + ":" : "") + String(minutes).padStart(2, "0") + ":" + tail;
}
function gameplaySeconds(value) {
  const text = String(value).trim();
  if (!/^\d+(?:\.\d+)?$|^\d+:\d{1,2}(?:\.\d+)?$|^\d+:\d{1,2}:\d{1,2}(?:\.\d+)?$/.test(text)) {
    throw new Error("Use um tempo válido, como 00:42 ou 01:12:30.");
  }
  const parts = text.split(":").map(Number);
  if (parts.length > 1 && parts.slice(1).some((part) => part >= 60)) {
    throw new Error("Minutos e segundos após os dois-pontos devem ser menores que 60.");
  }
  const seconds = parts.reduce((total, part) => total * 60 + part, 0);
  if (!Number.isFinite(seconds)) throw new Error("Tempo inválido.");
  return seconds;
}
function gameplayAsset(value) {
  if (!value) return "";
  try {
    const url = new URL(String(value), window.location.origin);
    return url.origin === window.location.origin && ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch (_) { return ""; }
}
function gameplayError(message) {
  const element = $("#gameplay-validation");
  element.textContent = message || "";
  element.classList.toggle("hidden", !message);
}
function setGameplayBusy(busy) {
  gameplayBusy = busy;
  ["#gameplay-analyze", "#gameplay-render", "#gameplay-refresh"].forEach((selector) => { $(selector).disabled = busy; });
  $$("#gameplay-review input, #gameplay-form input, #gameplay-form select, #gameplay-project-list button").forEach((element) => { element.disabled = busy; });
}
async function followGameplayJob(id, onDone) {
  const log = $("#gameplay-log");
  log.classList.remove("hidden");
  log.textContent = "Trabalhando…";
  try {
    let completed = false;
    while (!completed) {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      log.textContent = (job.log || []).join("\n") + (job.status === "running" ? "\n…" : job.status === "done" ? "\nConcluído." : "");
      log.scrollTop = log.scrollHeight;
      if (job.status === "error") throw new Error("A tarefa falhou. Confira o detalhe no registro acima.");
      if (job.status === "done") {
        let result = job.result;
        if (typeof result === "string") { try { result = JSON.parse(result); } catch (_) { throw new Error("A tarefa terminou sem retornar os dados do projeto."); } }
        await onDone(result);
        completed = true;
      } else if (job.status !== "running") {
        throw new Error("A tarefa retornou um estado desconhecido.");
      } else {
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
  } finally { setGameplayBusy(false); }
}
function gameplayMomentRows(items, kind) {
  if (!items?.length) return `<p class="hint">Nenhum momento sugerido para este formato.</p>`;
  return items.map((item, index) => `<article class="gameplay-moment" data-kind="${kind}" data-index="${index}">
    <div class="gameplay-moment-top"><label class="check"><input data-field="selected" type="checkbox" ${item.enabled === false || item.selected === false ? "" : "checked"}> Usar ${kind === "long" ? "trecho" : "corte"} ${index + 1}</label>
      <span class="hint" data-duration>${gameplayTime(Math.max(0, Number(item.end) - Number(item.start)))}</span></div>
    <div class="row"><label>Início <input data-field="start" value="${esc(gameplayTime(item.start))}" inputmode="decimal" aria-label="Início do ${kind === "long" ? "trecho" : "corte"} ${index + 1}"></label>
      <label>Fim <input data-field="end" value="${esc(gameplayTime(item.end))}" inputmode="decimal" aria-label="Fim do ${kind === "long" ? "trecho" : "corte"} ${index + 1}"></label>
      <label class="gameplay-moment-title">Título da capa <input data-field="title" maxlength="100" value="${esc(item.title || `Momento ${index + 1}`)}"></label></div>
    ${item.reason ? `<p class="hint gameplay-reason">${esc(item.reason)}</p>` : ""}
  </article>`).join("");
}
function renderGameplayPlan(data) {
  if (!data || !data.project_id || !data.plan) throw new Error("A análise não retornou um plano de cortes.");
  gameplayProject = data.project_id;
  gameplayPlan = JSON.parse(JSON.stringify(data.plan));
  gameplayLongLimit = Math.min(660, Number(gameplayPlan.max_long_seconds || gameplayPlan.settings?.max_long_seconds || gameplayPlan.options?.max_long_seconds) || gameplayLongLimit);
  $("#gameplay-review").classList.remove("hidden");
  $("#gameplay-output").classList.add("hidden");
  $("#gameplay-plan-title").value = gameplayPlan.title || data.title || "Melhores momentos da gameplay";
  const sourceDuration = gameplayPlan.source?.duration ?? gameplayPlan.source_meta?.duration ?? gameplayPlan.duration;
  $("#gameplay-source-info").textContent = sourceDuration ? `Fonte: ${gameplayTime(sourceDuration)} · ${(gameplayPlan.language || gameplayPlan.lang) === "en" ? "@leonidawireusa" : "@leonidawirebrz"}` : "";
  const storyboard = gameplayAsset(data.storyboard_url || gameplayPlan.storyboard_url);
  $("#gameplay-storyboard-link").classList.toggle("hidden", !storyboard);
  if (storyboard) { $("#gameplay-storyboard").src = storyboard; $("#gameplay-storyboard-link").href = storyboard; }
  $("#gameplay-long").innerHTML = gameplayMomentRows(gameplayPlan.long, "long");
  $("#gameplay-shorts").innerHTML = gameplayMomentRows(gameplayPlan.shorts, "shorts");
  gameplayError("");
  updateGameplayDurations();
}
function collectGameplayPlan(validate = true) {
  if (!gameplayPlan || !gameplayProject) throw new Error("Analise uma gameplay primeiro.");
  const plan = JSON.parse(JSON.stringify(gameplayPlan));
  plan.title = $("#gameplay-plan-title").value.trim() || gameplayPlan.title;
  for (const kind of ["long", "shorts"]) {
    plan[kind] = $$(".gameplay-moment", $("#gameplay-" + kind)).filter((row) => $("[data-field=selected]", row).checked).map((row) => {
      const item = { ...gameplayPlan[kind][Number(row.dataset.index)] };
      item.start = gameplaySeconds($("[data-field=start]", row).value);
      item.end = gameplaySeconds($("[data-field=end]", row).value);
      item.title = $("[data-field=title]", row).value.trim();
      if (validate && item.end <= item.start) throw new Error("O fim de cada trecho precisa ser maior que o início.");
      if (validate && !item.title) throw new Error("Preencha o título de cada momento selecionado.");
      if (validate && kind === "shorts" && (item.end - item.start < 30 || item.end - item.start > 60)) {
        throw new Error("Cada corte vertical deve ter entre 30 e 60 segundos. Ajuste os tempos ou desmarque o trecho.");
      }
      delete item.enabled; delete item.selected;
      return item;
    });
  }
  if (validate && !plan.long.length && !plan.shorts.length) throw new Error("Selecione pelo menos um trecho ou corte.");
  const longDuration = plan.long.reduce((total, item) => total + item.end - item.start, 0);
  if (validate && longDuration > gameplayLongLimit + 0.01) {
    throw new Error(`A seleção horizontal soma ${gameplayTime(longDuration)}. Ajuste para até ${gameplayTime(gameplayLongLimit)}.`);
  }
  const sourceDuration = Number(plan.source?.duration ?? plan.source_meta?.duration ?? plan.duration);
  if (validate && sourceDuration && [...plan.long, ...plan.shorts].some((item) => item.end > sourceDuration + 0.01)) {
    throw new Error("Um dos trechos termina depois do fim do vídeo original.");
  }
  return plan;
}
function updateGameplayDurations() {
  $$("#gameplay-review .gameplay-moment").forEach((row) => {
    try {
      const length = gameplaySeconds($("[data-field=end]", row).value) - gameplaySeconds($("[data-field=start]", row).value);
      $("[data-duration]", row).textContent = length > 0 ? gameplayTime(length) : "Ajuste os tempos";
    } catch (_) { $("[data-duration]", row).textContent = "Tempo inválido"; }
    row.classList.toggle("gameplay-unselected", !$("[data-field=selected]", row).checked);
  });
  try {
    const plan = collectGameplayPlan(false);
    const length = plan.long.reduce((total, item) => total + Math.max(0, item.end - item.start), 0);
    $("#gameplay-long-duration").textContent = `${plan.long.length} trechos selecionados · ${gameplayTime(length)} de até ${gameplayTime(gameplayLongLimit)}. A duração final considera as transições.`;
  } catch (_) { $("#gameplay-long-duration").textContent = "Ajuste os tempos para calcular a duração da seleção."; }
}
$("#gameplay-review").addEventListener("input", updateGameplayDurations);
$("#gameplay-review").addEventListener("change", updateGameplayDurations);

$("#gameplay-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (gameplayBusy) return;
  const form = event.target;
  const data = Object.fromEntries(new FormData(form));
  ["max_long_minutes", "short_count", "short_seconds"].forEach((key) => { data[key] = Number(data[key]); });
  data.source = data.source.trim(); data.title = data.title.trim(); data.credit = data.credit.trim();
  gameplayLongLimit = data.max_long_minutes * 60;
  gameplayError("");
  setGameplayBusy(true);
  try {
    const response = await api("/api/gameplay/analyze", { method: "POST", body: JSON.stringify(data) });
    await followGameplayJob(response.job, (result) => { renderGameplayPlan(result); toast("Análise pronta. Revise os momentos sugeridos."); });
  } catch (error) {
    setGameplayBusy(false);
    $("#gameplay-log").classList.remove("hidden");
    $("#gameplay-log").textContent += "\n" + error.message;
    toast("Erro: " + error.message);
  }
});
function gameplayResultCard(item, title, vertical = false) {
  const video = gameplayAsset(item?.video_url);
  const cover = gameplayAsset(item?.cover_url);
  const caption = gameplayAsset(item?.caption_url);
  return `<article class="gameplay-result ${vertical ? "vertical" : "horizontal"}"><h3>${esc(item?.title || title)}</h3>
    ${video ? `<video controls preload="none" ${cover ? `poster="${esc(cover)}"` : ""} src="${esc(video)}"></video>` : cover ? `<img src="${esc(cover)}" alt="Capa do vídeo">` : ""}
    ${item?.duration ? `<p class="hint">${gameplayTime(item.duration)} · ${vertical ? "9:16" : "16:9"}</p>` : ""}
    <div class="actions">${video ? `<a class="btn" href="${esc(video)}" download>Baixar MP4</a>` : ""}${cover ? `<a class="btn" href="${esc(cover)}" download>Baixar capa</a>` : ""}${caption ? `<a class="btn" href="${esc(caption)}" download>Baixar legenda</a>` : ""}</div></article>`;
}
function renderGameplayResult(result) {
  if (!result || (!result.long && !result.shorts?.length)) throw new Error("A exportação não retornou os arquivos dos vídeos.");
  const panel = $("#gameplay-output");
  const qa = gameplayAsset(result.qa_url);
  const plan = gameplayAsset(result.plan_url);
  panel.innerHTML = `<header class="bar"><h2>Vídeos e capas prontos</h2><div class="actions">${plan ? `<a class="btn" href="${esc(plan)}" download>Plano de edição</a>` : ""}${qa ? `<a class="btn" href="${esc(qa)}" target="_blank" rel="noopener">Verificação técnica</a>` : ""}</div></header>
    <p class="hint">Confira o vídeo completo e o áudio antes de publicar. Os arquivos ficam salvos no computador para sua publicação manual.</p>
    <div class="gameplay-results">${result.long ? gameplayResultCard(result.long, "Gameplay · melhores momentos") : ""}${(result.shorts || []).map((item, index) => gameplayResultCard(item, `Corte ${index + 1}`, true)).join("")}</div>`;
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}
$("#gameplay-render").addEventListener("click", async () => {
  if (gameplayBusy) return;
  gameplayError("");
  try {
    const plan = collectGameplayPlan();
    setGameplayBusy(true);
    const response = await api("/api/gameplay/render", { method: "POST", body: JSON.stringify({ project_id: gameplayProject, plan, music: true, subtitles: false }) });
    await followGameplayJob(response.job, (result) => { renderGameplayResult(result); toast("Vídeos e capas exportados."); });
  } catch (error) { setGameplayBusy(false); gameplayError(error.message); toast("Erro: " + error.message); }
});
$("#gameplay-refresh").addEventListener("click", async () => {
  if (gameplayBusy) return;
  const button = $("#gameplay-refresh");
  button.disabled = true;
  try {
    const response = await api("/api/gameplay/projects");
    const projects = Array.isArray(response) ? response : response.projects || [];
    $("#gameplay-projects").classList.remove("hidden");
    $("#gameplay-project-list").innerHTML = projects.length ? projects.map((project, index) => `<article><div><b>${esc(project.title || project.plan?.title || project.project_id)}</b><small class="hint">${esc(project.project_id)}</small></div><button type="button" data-gameplay-open="${index}">${project.result ? "Abrir arquivos" : "Revisar seleção"}</button></article>`).join("") : `<p class="hint">Nenhum projeto salvo ainda. Comece com um link acima.</p>`;
    $$("[data-gameplay-open]", $("#gameplay-project-list")).forEach((element) => {
      element.addEventListener("click", () => {
        const project = projects[Number(element.dataset.gameplayOpen)];
        try {
          if (project.plan) renderGameplayPlan(project);
          if (project.result) renderGameplayResult(project.result);
          if (!project.plan && !project.result) toast("Este projeto ainda não tem uma seleção disponível.");
        } catch (error) { toast("Erro: " + error.message); }
      });
    });
  } catch (error) { toast("Erro: " + error.message); }
  finally { button.disabled = false; }
});

loadStatus(); loadRadar();
