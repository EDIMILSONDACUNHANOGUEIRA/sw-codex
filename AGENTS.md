# AGENTS.md — instruções para o Codex (e Claude Code) neste projeto

Este repositório é o **Leonida Studio**: uma fábrica de posts de notícias de **GTA VI** para TikTok,
com dois perfis — **BR** (português do Brasil) e **US** (inglês americano). O agente é o redator e
editor-chefe: encontra a notícia, escreve o post nos dois idiomas, gera as artes e entrega pronto.

## Fluxo padrão ("faz os posts de hoje")

Prompt completo e modelo do relatório de entrega: [`docs/PROMPT-DIARIO.md`](docs/PROMPT-DIARIO.md).
Por enquanto o vídeo está desligado: use sempre `--sem-video`.

1. `python -m leonida radar` — lista as histórias do momento (já agrupadas e ranqueadas).
   Também grava `state/radar.json` e `prontos/RADAR.md`.
2. Para cada história relevante e ainda não coberta (veja `posts/` e `state/seen.json`):
   - Leia 1–2 matérias das fontes listadas para **confirmar os fatos**.
   - Crie `posts/<AAAA-MM-DD>-<slug>/post.yaml` (modelo abaixo ou `python -m leonida novo "título"`).
   - Escolha a imagem: prefira **screenshots oficiais da Rockstar** (`python -m leonida biblioteca`
     lista todas; URLs do tipo `https://www.rockstargames.com/VI/_next/static/media/...`) ou a
     `og:image` da matéria se for oficial e tiver ≥ 1200 px de largura.
3. `python -m leonida build <post-id>` — gera capa, carrossel, vídeo e legendas em
   `prontos/<data>/<post-id>/{br,us}/`. Use `--sem-video` para iterar rápido.
4. **Abra as imagens geradas e revise** (texto cortado, palavra gigante ilegível, rosto escondido).
   Ajuste `zoom`, `focus`, `layout` ou o texto e rode de novo.
5. `python -m leonida galeria` atualiza `prontos/index.html`. Marque as histórias usadas:
   `python -c "from leonida import radar; radar.mark_seen(['<id>'], 'published')"`.
6. Commit + push (a galeria e os arquivos ficam visíveis no GitHub).

Post diário de contagem regressiva: `python -m leonida contagem`.
Música tema: `python -m leonida musica <url-youtube> --inicio 0:12` (todos os vídeos e cortes usam
automaticamente; arquivo em `assets/music/`, fora do git). Downloads de vídeo: sempre via **yt-dlp**.
Perfis: BR **@leonidawirebrz**, US **@leonidawireusa** (em `config/brand.yaml`).
Cortes de vídeo: `python -m leonida corte <url|arquivo> 0:10 0:25 --pt "..." --en "..." --credito "..."`.

## Modelo de `post.yaml`

```yaml
id: 2026-10-08-gta6-radios-reveladas
date: "2026-10-08"
tag: oficial            # oficial | urgente | vazamento | rumor | viral | contagem | analise
image: "https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_06....jpg"
# layout: card          # use 'card' para cenários/prints sem personagem em destaque
# zoom: 0.85            # recua o enquadramento (o recuo automático costuma acertar)
# focus: [0.6, 0.5]     # ponto de foco do recorte 9:16
source: { name: "Rockstar Games", url: "https://www.rockstargames.com/VI/music" }
pt:
  kicker: RÁDIOS        # 1 palavra (até ~9 letras) que fica gigante atrás do personagem
  headline: "GTA VI revela suas primeiras *6 rádios* com *Bad Bunny*"   # *x* = destaque
  summary: "Uma frase de contexto, até ~115 caracteres."
  caption: |
    Gancho forte na primeira linha.

    2–4 linhas curtas com os fatos.

    Pergunta para gerar comentários? 👇
  hashtags: ["#gta6radio", "#vicecity"]          # 3–5 específicas (as gerais entram sozinhas)
  slides:                                          # opcional — vira carrossel
    - type: list
      title: "O que *sabemos*"
      items: ["fato 1", "fato 2", "fato 3"]
    - type: grid                                   # grade de imagens (logos, prints)
      title: "As 6 *rádios*"
      items: [{ image: "URL", label: "Cocoteo FM", sub: "Bad Bunny & RaiNao" }]
en:
  # mesmos campos, em inglês americano
```

## Regras editoriais (obrigatórias)

- **Só fatos verificados nas fontes.** Nunca invente data, preço, nome, número ou "fontes dizem".
- Vazamento/rumor: tag `vazamento`/`rumor` e deixar claro que **não é oficial**.
- **Nada explícito** (nudez, sexo, violência gráfica) — mesmo que a matéria cite. O TikTok derruba.
  Não use imagens vazadas; use screenshots oficiais.
- Sempre credite a fonte (`source`). A legenda ganha "Fonte: X" automaticamente.
- BR: português do Brasil, tom de gamer, direto e empolgado, sem exagero. US: inglês americano, punchy.
- Manchete ≤ 70 caracteres, 2–4 palavras em `*destaque*`. "GTA VI" nunca quebra linha (automático).
- Legenda: gancho na 1ª linha, fatos em linhas curtas, pergunta no final, no máx. 3 emojis.
  **Sem hashtags dentro da legenda** (vão no campo `hashtags`).
- Lançamento oficial: **19/11/2026**, PS5 e Xbox Series X|S (sem PC anunciado). Preço e edições:
  confirme na fonte do dia antes de citar.

## Estilo visual (não mude sem pedir)

Paleta "Vice" (pôr do sol de Leonida): night `#0B0614`, pink `#FF2E88`, orange `#FF8A3D`,
gold `#FFC857`, purple `#7B2FF7`, cyan `#22D3EE`. Fontes: Anton (manchetes), Inter (texto),
Yellowtail (assinatura). Assinatura da marca: **palavra gigante atrás do personagem recortado**,
color grading roxo/quente, cantos neon estilo "mira", contador "X DIAS PARA O GTA VI" no topo.
Tudo é configurável em `config/brand.yaml` (nome, @ dos perfis, paleta, selos, áreas seguras).

## Mapa do código

| Arquivo | Função |
|---|---|
| `leonida/radar.py` | feeds RSS (`config/sources.yaml`), filtro, agrupamento PT/EN, ranking |
| `leonida/render.py` + `gfx.py` | artes 9:16 (capa, grade, lista, CTA) e camadas para vídeo |
| `leonida/cutout.py` | recorte do personagem (rembg) |
| `leonida/video.py` | vídeo animado (HyperFrames; fallback FFmpeg) |
| `leonida/clips.py` | cortes 9:16 de vídeos (yt-dlp + FFmpeg + legendas faster-whisper) |
| `leonida/writer.py` | redação automática via Claude API (opcional) |
| `leonida/post.py` | `post.yaml` → `prontos/` (+ README.md por post) |
| `leonida/server.py` + `web/` | app web (`python -m leonida serve`) |
| `leonida/notify.py` | envio para Telegram/Discord |

Antes de commitar mudanças de código: `python -m leonida build <um-post> --sem-video` e confira a imagem.
