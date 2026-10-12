// Leonida Notícias — front-end dedicado aos posts diários
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
  $("#countdown").innerHTML = s.days > 0 ? `<b>${s.days}</b><small>DIAS PARA O GTA VI</small>` : `<b>VI</b><small>CONTAGEM GTA VI</small>`;
  const ok = (v) => (v ? "🟢" : "⚪️");
  $("#sys").innerHTML = `<span>${ok(s.claude)} Redator IA (Claude)</span><span>${ok(s.cutout)} Recorte (rembg)</span>
    <span>${ok(s.node)} Vídeo (HyperFrames)</span><span>${ok(s.ffmpeg)} FFmpeg</span><span>${ok(s.music)} Música tema</span>`;
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
let selectedVisuals = [];
let coverPreviewObject = null;
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
  setField("tag", p.tag || "oficial"); setField("date", String(p.date || "").slice(0, 10)); setField("layout", p.layout || "card");
  setField("image", p.image); setField("zoom", p.zoom || ""); setField("cutout", p.cutout === true || (p.layout === "cover" && p.cutout !== false)); setField("cta", p.cta);
  setField("source_name", p.source?.name); setField("source_url", p.source?.url);
  for (const l of ["pt", "en"]) {
    const loc = p[l] || {};
    ["kicker", "headline", "summary", "caption"].forEach((k) => setField(`${l}.${k}`, loc[k]));
    setField(`${l}.hashtags`, (loc.hashtags || []).join(" "));
    setField(`${l}.slides`, loc.slides?.length ? JSON.stringify(loc.slides, null, 1) : "");
  }
  selectedVisuals = (Array.isArray(p.visuals) ? p.visuals : []).map((v) => typeof v === "string" ? { image: v } : { ...v }).filter((v) => typeof v.image === "string" && v.image.trim());
  clearCoverPreview(); drawSelectedCover(); drawSelectedVisuals();
  if (p.needs_review) toast("⚠️ Rascunho sem IA: revise manchete, resumo e legenda");
}
function collect() {
  const f = $("#post-form"); const g = (n) => $(`[name="${n}"]`, f);
  const p = { ...current, tag: g("tag").value, date: g("date").value, layout: g("layout").value, image: g("image").value.trim(),
    cutout: g("cutout").checked, cta: g("cta").checked, visuals: selectedVisuals.map((v) => ({ ...v })), source: { name: g("source_name").value, url: g("source_url").value }, _reviewed: true };
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
    clearCoverPreview(); coverPreviewObject = URL.createObjectURL(blob); $("#preview-img").src = coverPreviewObject;
    $("#preview-state").textContent = "Capa editada. Confira o rosto, o enquadramento e o texto antes de gerar o vídeo.";
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
$("#upload").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file || !current) return;
  const fd = new FormData(); fd.append("file", file);
  try {
    const response = await fetch(`/api/posts/${encodeURIComponent(current.id)}/upload`, { method: "POST", body: fd });
    if (!response.ok) throw new Error("Não foi possível enviar a imagem");
    const r = await response.json(); chooseCover(r.image); toast("Foto da capa enviada");
  } catch (err) { toast("Erro: " + err.message); }
});

function clearCoverPreview() {
  if (coverPreviewObject) URL.revokeObjectURL(coverPreviewObject);
  coverPreviewObject = null; $("#preview-img").removeAttribute("src");
  $("#preview-state").textContent = "Use \"Prévia BR\" para conferir a capa editada com a foto e o texto atuais.";
}
function imageThumb(ref) {
  if (typeof ref !== "string" || !ref.trim()) return "";
  ref = ref.trim();
  if (/^https?:\/\//i.test(ref)) {
    try { const url = new URL(ref); if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password) return ""; }
    catch (_) { return ""; }
  } else {
    // Relative image references are limited to this post or project assets.
    if (ref.includes("\\") || ref.includes(":") || ref.startsWith("/") || ref.split("/").some((part) => part === "..")) return "";
    if (!ref.includes("/")) ref = `posts/${current?.id}/${ref}`;
  }
  return "/api/thumb?url=" + encodeURIComponent(ref);
}
function drawSelectedCover() {
  const ref = $('[name="image"]', $("#post-form")).value.trim();
  const image = $("#selected-cover"), thumb = imageThumb(ref);
  image.classList.toggle("hidden", !thumb);
  if (thumb) image.src = thumb; else image.removeAttribute("src");
  const whole = $('[name="layout"]', $("#post-form")).value === "card";
  $("#cover-state").textContent = !ref ? "Escolha uma imagem na biblioteca oficial para ver o enquadramento." : whole ? "Foto inteira, com proporções preservadas. Use Prévia BR para conferir a capa final." : "Modo personagem recortado. Confira o rosto e o recorte na Prévia BR.";
}
function chooseCover(ref) {
  setField("image", ref); setField("layout", "card"); setField("cutout", false); setField("zoom", "");
  clearCoverPreview(); drawSelectedCover(); drawSelectedVisuals();
}
$('[name="image"]', $("#post-form")).addEventListener("input", () => { clearCoverPreview(); drawSelectedCover(); });
$('[name="layout"]', $("#post-form")).addEventListener("change", () => { clearCoverPreview(); drawSelectedCover(); });
function drawSelectedVisuals() {
  const count = selectedVisuals.length;
  $("#visual-count").textContent = `${count} ${count === 1 ? "imagem selecionada" : "imagens selecionadas"}`;
  $("#visual-empty").classList.toggle("hidden", count > 0);
  $("#visual-grid").innerHTML = selectedVisuals.map((v, index) => {
    const thumb = imageThumb(v.image);
    const title = v.name || v.label || "Imagem de apoio";
    return `<article class="visual-item">${thumb ? `<img loading="lazy" src="${esc(thumb)}" alt="${esc(title)}">` : '<div class="visual-placeholder">Imagem salva</div>'}<div class="visual-info"><b>${index + 1}. ${esc(title)}</b><small>${esc(v.credit || "Rockstar Games")}</small><label>Texto desta cena <small>(opcional)</small><input type="text" data-visual-text="${index}" maxlength="160" value="${esc(v.text || "")}" placeholder="Um fato ou detalhe da notícia"></label><button type="button" data-remove-visual="${index}" aria-label="Remover imagem ${index + 1} do vídeo">Remover do vídeo</button></div></article>`;
  }).join("");
  $$("[data-visual-text]").forEach((input) => input.addEventListener("input", () => {
    const visual = selectedVisuals[Number(input.dataset.visualText)];
    if (visual) visual.text = input.value.slice(0, 160);
  }));
  $$("[data-remove-visual]").forEach((b) => b.addEventListener("click", () => {
    selectedVisuals.splice(Number(b.dataset.removeVisual), 1); drawSelectedVisuals(); drawLib();
  }));
}

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
function officialLibraryImage(item) {
  if (!item || typeof item.name !== "string" || typeof item.url !== "string") return false;
  try {
    const url = new URL(item.url);
    return url.protocol === "https:" && !url.username && !url.password && (url.hostname === "rockstargames.com" || url.hostname.endsWith(".rockstargames.com")) && url.pathname.startsWith("/VI/");
  } catch (_) { return false; }
}
async function openLibrary(mode) {
  if (!current) return;
  $("#lib-use").value = mode; $("#lib-modal").classList.remove("hidden");
  try {
    if (!library.length) {
      $("#lib-grid").innerHTML = "<p class='hint'>Carregando imagens oficiais…</p>";
      const items = await api("/api/library"); library = (Array.isArray(items) ? items : []).filter(officialLibraryImage);
    }
    drawLib();
  } catch (err) { $("#lib-grid").textContent = "Não foi possível abrir a biblioteca. Tente novamente."; toast("Erro: " + err.message); }
}
$("#btn-lib").addEventListener("click", () => openLibrary("cover"));
$("#btn-video-lib").addEventListener("click", () => openLibrary("video"));
$("#lib-close").addEventListener("click", () => $("#lib-modal").classList.add("hidden"));
$("#lib-filter").addEventListener("input", drawLib);
$("#lib-use").addEventListener("change", drawLib);
function drawLib() {
  const q = $("#lib-filter").value.toLowerCase(), mode = $("#lib-use").value;
  const cover = $('[name="image"]', $("#post-form")).value.trim();
  $("#lib-state").textContent = mode === "cover" ? "Escolha a foto da capa. Ela será preservada inteira." : `Adicione fotos diferentes ao vídeo. ${selectedVisuals.length} de 6 selecionadas; clique em Fechar quando terminar.`;
  const shown = library.filter((i) => !q || `${i.name} ${i.group || ""}`.toLowerCase().includes(q));
  $("#lib-grid").innerHTML = shown.length ? shown.map((i) => {
    const selected = selectedVisuals.some((v) => v.image === i.url), isCover = cover === i.url;
    const label = isCover ? "Foto da capa" : selected ? "No vídeo ✓" : mode === "video" ? "Adicionar ao vídeo" : "Usar como capa";
    const disabled = mode === "video" && (selected || isCover || selectedVisuals.length >= 6);
    return `<figure class="${selected || isCover ? "selected" : ""}"><img loading="lazy" src="${esc(imageThumb(i.url))}" alt="${esc(i.name)}"><figcaption><b>${esc(i.name.replace(/_/g, " "))}</b><small>Rockstar Games</small><button type="button" data-library-image="${esc(i.url)}"${disabled ? " disabled" : ""}>${label}</button></figcaption></figure>`;
  }).join("") : "<p class='hint'>Nenhuma imagem oficial corresponde ao filtro.</p>";
  $$("[data-library-image]").forEach((button) => button.addEventListener("click", () => {
    const ref = button.dataset.libraryImage, item = library.find((i) => i.url === ref);
    if (!item) return;
    if (mode === "cover") {
      chooseCover(ref); $("#lib-modal").classList.add("hidden"); toast("Foto da capa escolhida — confira a Prévia BR");
    } else {
      if (selectedVisuals.length >= 6 || ref === cover || selectedVisuals.some((v) => v.image === ref)) return;
      selectedVisuals.push({ image: ref, credit: "Rockstar Games", label: "Imagem oficial ilustrativa", name: item.name.replace(/_/g, " ") });
      drawSelectedVisuals(); drawLib(); toast("Imagem adicionada ao vídeo");
    }
  }));
}


$("#music-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  try { const r = await api("/api/music", { method: "POST", body: JSON.stringify(d) }); followJob(r.job, $("#music-log"), () => { toast("Música tema salva"); loadStatus(); }); }
  catch (err) { toast("Erro: " + err.message); }
});


loadStatus().catch((error) => toast("Erro: " + error.message));
loadRadar().catch((error) => toast("Erro: " + error.message));
