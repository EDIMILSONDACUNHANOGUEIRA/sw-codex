# AGENTS.md — instruções para o Codex (e Claude Code) neste projeto

Este repositório é o **Leonida Studio**: uma fábrica de posts de notícias de **GTA VI** para TikTok,
para o perfil **BR @leonidawirebrz** (português do Brasil). O perfil US está desativado
(`idiomas: [pt]` em `config/brand.yaml`): não escreva a parte `en`. O agente é o redator e
editor-chefe: encontra a notícia, escreve o post, gera as artes e agenda no TikTok pelo Metricool.

## Fluxo padrão ("faz os posts de hoje")

Prompt completo e modelo do relatório de entrega: [`docs/PROMPT-DIARIO.md`](docs/PROMPT-DIARIO.md).
Use `--sem-video` para pular só a capa animada (HyperFrames); o vídeo de publicação
`br/tiktok/post.mp4`, com a música tema, é gerado do mesmo jeito.

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
**Música: SEMPRE a música tema de GTA VI, em toda publicação.** Nunca música aleatória e nunca a
"música automática" do TikTok (`autoAddMusic: false`). Por isso o post é publicado como VÍDEO
(`br/tiktok/post.mp4`, gerado no build com a música tema embutida), não como post de fotos. As faixas
ficam em `assets/music/`, fora do git: `python -m leonida musica <url-do-trailer> --inicio 0:12 --nome
trailer-2` e `python -m leonida musica --listar`. Sem música tema, não publique: avise e peça a música.
Downloads de vídeo: sempre via **yt-dlp**.
Perfil ativo: BR **@leonidawirebrz** (Metricool, marca 7317240). Publicação: passo 10 de
`docs/PROMPT-DIARIO.md` e `python -m leonida publicacao <id>`.
Cortes de vídeo: `python -m leonida corte <url|arquivo> 0:10 0:25 --pt "..." --en "..." --credito "..."`.

## Site (Leonida Wire) e imagens oficiais

- `python -m leonida site` gera o site estático em `site/` (versionado) a partir de `posts/*/post.yaml`.
  A Vercel (projeto `leonida-wire`) publica essa pasta (`vercel.json`). Só entram notícias oficiais:
  posts com tag `vazamento`/`rumor`/`contagem` ou `site: false` ficam de fora, e o gerador barra
  qualquer post que fale em vazamento/leak/rumor. Para escrever um texto próprio para o site, use
  `site: {texto: "markdown"}` no post.yaml (senão o texto vem da legenda + slides que não repetem a
  legenda). Mais de uma fonte: `fontes: [{name: ..., url: ...}, ...]` (aparece como "Fontes: a · b").
- As fontes do site são WOFF2 recortadas (latim) em `leonida/site_assets/fonts/`; se trocar a fonte,
  gere de novo com `pyftsubset ... --flavor=woff2`.
- Vazamentos e rumores não são publicados em lugar nenhum.
- Imagem nova da Rockstar: o carrossel/vídeo mostra a capa EDITADA e logo depois a imagem LIMPA
  (slide `imagem-limpa`, automático para imagens de rockstargames.com; `foto_limpa: false` desliga;
  `fotos_limpas: [urls]` para várias imagens novas).

## Quando chegar um link de vídeo ("edita esse vídeo")

1. Descubra do que se trata (título/canal do vídeo, matéria relacionada) e **confirme os fatos** como
   num post normal. Escreva a manchete BR (≤ 70 caracteres, `*destaque*`) e escolha a tag.
2. Rode a edição:
   ```bash
   python -m leonida editar "URL" --pt "Manchete *BR*" --tag oficial \
       --estilo hype --duracao 20            # --inicio 0:30 --fim 2:00 para usar só um trecho
   ```
   - `--estilo hype` (padrão): cortes de ~1 s, snap/crash zoom, câmera na mão, whip pan, flash.
   - `--estilo cinema`: planos longos, dolly/travelling lentos, cortes secos (trailers).
   - `--estilo noticia`: ritmo médio, movimentos discretos.
   - `--formato janela`: vídeo 16:9 inteiro com fundo desfocado (quando cortar as laterais estraga).
   - `--legendas`: legenda automática (precisa de `pip install faster-whisper`).
   - Crédito: o canal do YouTube entra sozinho; use `--credito` para trocar.
3. Abra `prontos/<data>/<id>/br/previa.jpg` (8 quadros da edição) e revise: personagem fora do
   quadro, texto em cima de rosto, trecho com conteúdo explícito. Ajuste e rode de novo.
4. A legenda em `legenda.txt` sai só com manchete + crédito: **reescreva no formato de
   legenda do post** (gancho, fatos, pergunta) antes de entregar.
5. Regras: trechos curtos de vídeo de terceiros, sempre com crédito e com edição/comentário próprio.
   Nada de vídeo vazado com conteúdo explícito.

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
# en: (só se o perfil US for reativado em brand.yaml -> idiomas)
```

## Regras editoriais (obrigatórias)

- **Só fatos verificados nas fontes.** Nunca invente data, preço, nome, número ou "fontes dizem".
- Vazamento/rumor: tag `vazamento`/`rumor` e deixar claro que **não é oficial**.
- **Nada explícito** (nudez, sexo, violência gráfica) — mesmo que a matéria cite. O TikTok derruba.
  Não use imagens vazadas; use screenshots oficiais.
- Sempre credite a fonte (`source`). A legenda ganha "Fonte: X" automaticamente.
- Português do Brasil, tom de gamer, direto e empolgado, sem exagero.
- Manchete ≤ 70 caracteres, 2–4 palavras em `*destaque*`. "GTA VI" nunca quebra linha (automático).
- Legenda: gancho na 1ª linha, fatos em linhas curtas, pergunta no final, no máx. 3 emojis.
  **Sem hashtags dentro da legenda** (vão no campo `hashtags`).
- Lançamento oficial: **19/11/2026**, PS5 e Xbox Series X|S (sem PC anunciado). Preço e edições:
  confirme na fonte do dia antes de citar.

## Estilo visual (não mude sem pedir)

Acabamento fotográfico (config `acabamento` no brand.yaml): sem contorno neon no personagem, sombra
do personagem na palavra gigante, luz do fundo na borda do recorte, grão de filme e halação. Isso
evita a cara de "arte gerada por IA". `neon: true` volta ao visual antigo.

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
| `leonida/edit.py` | edição de vídeo por link: cenas, reenquadramento, movimentos de câmera, transições (HyperFrames) |
| `leonida/writer.py` | redação automática via Claude API (opcional) |
| `leonida/post.py` | `post.yaml` → `prontos/` (+ README.md por post) |
| `leonida/server.py` + `web/` | app web (`python -m leonida serve`) |
| `leonida/notify.py` | envio para Telegram/Discord |

Antes de commitar mudanças de código: `python -m leonida build <um-post> --sem-video` e confira a imagem.
