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
      <div class="go"><button class="primary" data-draft="${s.id}">Criar post</button><button data-ignore="${s.id}">Ignorar</button></div>
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
    `<option value="${esc(p.id)}">${p.built ? "✅" : p.needs_review ? "⚠️" : "📝"} ${esc(p.id)}</option>`).join("");
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
    const j = await api(`/api/jobs/${id}`);
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

loadStatus(); loadRadar();
