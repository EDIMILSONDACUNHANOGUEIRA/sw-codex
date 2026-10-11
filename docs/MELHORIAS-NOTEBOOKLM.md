# Melhorias sugeridas pelo NotebookLM (10/10/2026) e o que já foi feito

O dono passou a ideia do projeto para o NotebookLM (`docs/IDEIA-NOTEBOOKLM.md`) e trouxe as recomendações abaixo.
Status: ✅ feito · 🧪 em teste (só com `estilo: dinamico` no post.yaml) · ⏳ falta.

## Vídeo

- 🧪 **Zoom na capa nos primeiros segundos** (Ken Burns 1.0 → 1.08).
- 🧪 **Movimento a cada 1,5–3 s**: os itens das listas aparecem um a um, e as transições entre slides deslizam.
- 🧪 **Loop perfeito**: o "siga" ficou mais curto (2,2 s) e o vídeo termina voltando para a capa, então o último
  quadro emenda no primeiro.
- 🧪 **Música com fade de 0,5 s no fim** (antes 1,2 s).
- ✅ **H.264 perfil High, 30 fps, 1080×1920** em todo vídeo de publicação.
- ✅ **Duração configurável**: `video_segundos` no post.yaml (padrão ~16 s).
- ⏳ **Narração com voz (ElevenLabs)** e música baixando enquanto a voz fala. Precisa de chave da API guardada como
  segredo do ambiente e de plano com uso comercial. Marcar o vídeo como conteúdo de IA no TikTok.
- ⏳ **Legenda palavra por palavra** na tela (depende da narração).

## Arte

- ✅ **Gancho no selo da capa**: `selo: "A Rockstar postou"` troca o texto do selo (só quando for verdade).
- ✅ **Rosto escuro**: se a cabeça do personagem recortado estiver escura, o gerador clareia só o personagem
  (ganho de exposição, sem lavar o preto e sem salto). Sem recorte, só clareia se um rosto for detectado
  (precisa do OpenCV instalado; sem ele, a foto fica como está, para não clarear cenário noturno).
- ✅ **Camadas**: fundo, palavra gigante, personagem recortado, acabamento (grão, halação) — já era assim.
- ✅ **JPEG para o TikTok** e área segura (texto fora dos 20% de baixo e dos botões da direita).

## Distribuição e busca

- ⏳ **Reels e YouTube Shorts**: o mesmo `post.mp4` serve; falta conectar as contas no Metricool.
- ✅ **Busca do TikTok**: legenda com termos diretos ("GTA 6", "Rockstar", "lançamento 19/11"), já usada.

## Como testar

Coloque `estilo: dinamico` no post.yaml e rode `python -m leonida build <id> --sem-video`. Exemplo:
`posts/2026-10-10-gta6-capa-love-magazine/post.yaml`. Se o dono aprovar, o estilo vira padrão.

## Atualização 11/10 — estilo v2 é o padrão

O pedido do dono ("melhore a logo, as transições dos textos e o estilo de editar") virou o **estilo v2**
(`leonida/motion.py`), que já é o padrão (`config/brand.yaml → video.estilo_padrao: v2`):

- ✅ Logo nova no topo (sol de Vice + LEONIDA WIRE + ponto "ao vivo") e a mesma marca grande no "siga".
- ✅ Textos entrando animados (linhas sobem da máscara, selos com pop, itens da lista um por batida).
- ✅ Transições de verdade: zoom punch com flash (capa → próximo), whip pan com borrão (entre slides) e
  luz quente (para o "siga" e no loop final).
- ✅ Ritmo na batida da música (125 BPM detectado na faixa atual), pulso leve do fundo a cada 2 batidas.
- ✅ Capa legível desde o 1º quadro e loop perfeito (o último quadro emenda no primeiro).
- ✅ Nenhuma cena parada demais: com poucas cenas o vídeo sai mais curto (ex.: contagem ~12 s).

`estilo: dinamico` e `estilo: classico` continuam funcionando para quem quiser o slideshow antigo.
