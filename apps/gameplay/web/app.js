// Leonida Cortes — editor independente do radar de notícias
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

async function loadStatus() {
  const status = await api("/api/status");
  const mark = (value) => value ? "🟢" : "⚪";
  $("#sys").innerHTML = `<span>${mark(status.ffmpeg)} Exportação de vídeo</span><span>${mark(status.music)} Música tema</span><span>${mark(status.captions)} Legendas por áudio</span>`;
  // Legenda automática só vem marcada quando o reconhecimento de voz está instalado.
  $("#gameplay-subtitles").checked = Boolean(status.captions);
  $("#gameplay-captions-missing").classList.toggle("hidden", Boolean(status.captions));
}

let gameplayProject = null;
let gameplayUploadSource = "";
let gameplayMusicSource = "";
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
  $$("#gameplay-review input, #gameplay-review select, #gameplay-review textarea, #gameplay-form input, #gameplay-form select, #gameplay-project-list button").forEach((element) => { element.disabled = busy; });
}

function updateGameplayMusic() {
  const mode = $("#gameplay-music-mode").value;
  $("#gameplay-music-custom").classList.toggle("hidden", mode !== "custom");
  $("#gameplay-music-volume-label").classList.toggle("hidden", mode === "none");
  $("#gameplay-music-hint").textContent = mode === "none"
    ? "Mantém somente o áudio original, inclusive qualquer música que já esteja nele."
    : mode === "custom" ? "A música enviada será misturada aos vídeos, com a voz e o som do jogo preservados."
    : "O tema será aplicado aos vídeos, abaixo da voz e do som do jogo.";
}
$("#gameplay-music-mode").addEventListener("change", updateGameplayMusic);
$("#gameplay-music-upload").addEventListener("change", (event) => {
  gameplayMusicSource = "";
  const file = event.target.files[0];
  $("#gameplay-music-state").textContent = file ? "Selecionada: " + file.name : "Nenhuma música escolhida.";
});

async function selectedGameplayMusic() {
  const mode = $("#gameplay-music-mode").value;
  const volume = Number($("#gameplay-music-volume").value);
  if (!Number.isFinite(volume) || volume < 0 || volume > 100) throw new Error("Use um volume de música entre 0 e 100%.");
  if (mode === "custom" && !gameplayMusicSource) {
    const file = $("#gameplay-music-upload").files[0];
    if (!file) throw new Error("Escolha o arquivo da outra música antes de gerar.");
    $("#gameplay-music-state").textContent = "Importando a música…";
    const body = new FormData(); body.append("file", file);
    const response = await fetch("/api/gameplay/music-upload", {method:"POST", body});
    const imported = await response.json();
    if (!response.ok) throw new Error(imported.detail || "A música não pôde ser importada.");
    gameplayMusicSource = imported.source;
    $("#gameplay-music-state").textContent = "Importada: " + imported.filename;
  }
  return {music_mode:mode, music_volume:volume / 100, music_source: mode === "custom" ? gameplayMusicSource : null};
}
let gameplayJob = null;
$("#gameplay-cancel").addEventListener("click", async () => {
  if (!gameplayJob) return;
  $("#gameplay-cancel").disabled = true;
  try { await api(`/api/jobs/${encodeURIComponent(gameplayJob)}/cancel`, { method: "POST" }); }
  catch (error) { toast("Erro: " + error.message); $("#gameplay-cancel").disabled = false; }
});
async function followGameplayJob(id, onDone) {
  const log = $("#gameplay-log");
  log.classList.remove("hidden");
  log.textContent = "Trabalhando…";
  gameplayJob = id;
  $("#gameplay-cancel").disabled = false;
  $("#gameplay-cancel").classList.remove("hidden");
  try {
    let completed = false;
    while (!completed) {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      log.textContent = (job.log || []).join("\n") + (job.status === "running" ? "\n…" : job.status === "done" ? "\nConcluído." : "");
      log.scrollTop = log.scrollHeight;
      if (job.status === "error") throw new Error("A tarefa falhou. Confira o detalhe no registro acima.");
      if (job.status === "cancelled") throw new Error("Tarefa cancelada.");
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
  } finally {
    gameplayJob = null;
    $("#gameplay-cancel").classList.add("hidden");
    setGameplayBusy(false);
  }
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
  const selectedFile = $("#gameplay-upload").files[0];
  if (!data.source && !selectedFile && !gameplayUploadSource) { toast("Cole um link ou escolha um arquivo de vídeo."); return; }
  gameplayLongLimit = data.max_long_minutes * 60;
  gameplayError("");
  setGameplayBusy(true);
  try {
    if (!data.source) {
      if (selectedFile && !gameplayUploadSource) {
        $("#gameplay-upload-state").textContent = "Importando o arquivo…";
        const body = new FormData(); body.append("file", selectedFile);
        const upload = await fetch("/api/gameplay/upload", { method: "POST", body });
        const imported = await upload.json();
        if (!upload.ok) throw new Error(imported.detail || "O arquivo não pôde ser importado.");
        gameplayUploadSource = imported.source;
        $("#gameplay-upload-state").textContent = "Importado: " + imported.filename;
      }
      data.source = gameplayUploadSource;
    }
    const response = await api("/api/gameplay/analyze", { method: "POST", body: JSON.stringify(data) });
    await followGameplayJob(response.job, (result) => { renderGameplayPlan(result); toast("Análise pronta. Revise os momentos sugeridos."); });
  } catch (error) {
    setGameplayBusy(false);
    $("#gameplay-log").classList.remove("hidden");
    $("#gameplay-log").textContent += "\n" + error.message;
    toast("Erro: " + error.message);
  }
});
function gameplayResultCard(item, title, vertical = false, revised = false) {
  const video = gameplayAsset(item?.video_url);
  const cover = gameplayAsset(item?.cover_url);
  const caption = gameplayAsset(item?.caption_url);
  const subtitles = gameplayAsset(item?.subtitles_url);
  return `<article class="gameplay-result ${vertical ? "vertical" : "horizontal"}"><h3>${esc(item?.title || title)}</h3>
    ${video ? `<video controls preload="none" ${cover ? `poster="${esc(cover)}"` : ""} src="${esc(video)}"></video>` : cover ? `<img src="${esc(cover)}" alt="Capa do vídeo">` : ""}
    ${item?.duration ? `<p class="hint">${gameplayTime(item.duration)} · ${vertical ? "9:16" : "16:9"}</p>` : ""}
    <div class="actions">${video && revised ? `<a class="btn" href="${esc(video)}" target="_blank" rel="noopener">Ver vídeo</a>` : ""}${video ? `<a class="btn" href="${esc(video)}" download>Baixar MP4</a>` : ""}${cover ? `<a class="btn" href="${esc(cover)}" download>Baixar capa</a>` : ""}${subtitles ? `<a class="btn" href="${esc(subtitles)}" download>Baixar legendas SRT</a>` : ""}${caption ? `<a class="btn" href="${esc(caption)}" download>Texto da publicação</a>` : ""}</div></article>`;
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
    const selectedMusic = await selectedGameplayMusic();
    const response = await api("/api/gameplay/render", { method: "POST", body: JSON.stringify({
      project_id: gameplayProject, plan, ...selectedMusic,
      // Um SRT colado já é pedido de legenda, mesmo sem reconhecimento de voz instalado.
      subtitles: $("#gameplay-subtitles").checked || Boolean($("#gameplay-creator-srt").value.trim()),
      speech_language: $("#gameplay-speech-language").value,
      creator_srt: $("#gameplay-creator-srt").value.trim(),
    }) });
    await followGameplayJob(response.job, (result) => { renderGameplayResult(result); toast("Vídeos e capas exportados."); });
  } catch (error) { setGameplayBusy(false); gameplayError(error.message); toast("Erro: " + error.message); }
});
async function loadGameplayProjects() {
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
}
$("#gameplay-refresh").addEventListener("click", loadGameplayProjects);

async function loadGameplayRevisions() {
  const button = $("#gameplay-revisions-refresh");
  button.disabled = true;
  try {
    const revisions = await api("/api/gameplay/revisions");
    $("#gameplay-revision-list").innerHTML = Array.isArray(revisions) && revisions.length
      ? revisions.map((item) => gameplayResultCard(item, item.id, item.height > item.width, true)).join("")
      : `<p class="hint">As versões revisadas aparecerão aqui quando estiverem prontas.</p>`;
    $("#gameplay-revisions").classList.remove("hidden");
  } catch (error) { toast("Erro: " + error.message); }
  finally { button.disabled = false; }
}
$("#gameplay-revisions-refresh").addEventListener("click", loadGameplayRevisions);

$("#gameplay-upload").addEventListener("change", (event) => {
  const file = event.target.files[0];
  gameplayUploadSource = "";
  if (file) $("[name=source]", $("#gameplay-form")).value = "";
  $("#gameplay-upload-state").textContent = file ? file.name : "Nenhum arquivo escolhido.";
});
loadStatus().catch((error) => toast("Erro: " + error.message));
updateGameplayMusic();
loadGameplayProjects();
loadGameplayRevisions();
