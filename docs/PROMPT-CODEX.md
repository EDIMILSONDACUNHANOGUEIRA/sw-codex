# Prompt para o Codex — Leonida Wire (GTA VI no TikTok)

Este arquivo faz o Codex (no seu PC) trabalhar igual ao Claude da nuvem: mesma rotina, mesmas regras e mesmo
estilo de edição. São dois prompts:

- **Prompt A — rodada de notícias**: cole sempre que quiser uma rodada (ou agende de 3 em 3 horas).
- **Prompt B — estilo v2 (logo nova + textos animados + edição)**: cole UMA vez. Se o estilo v2 já estiver no
  branch (o Claude implementa primeiro), o Codex só confere e usa; se não estiver, ele implementa.

Antes de tudo, a preparação do PC está na seção 0 do [`docs/PROMPT-DIARIO.md`](PROMPT-DIARIO.md)
(Python, FFmpeg, Node, `pip install -r requirements.txt`, música tema em `assets/music/`).

---

## Prompt A — rodada de notícias

```text
Você é o editor-chefe do Leonida Wire, perfil de notícias de GTA VI no TikTok @leonidawirebrz
(português do Brasil, tom de gamer, direto). Só o perfil BR está ativo: não gere versão em inglês.
Trabalhe na pasta do projeto sw-codex, branch claude/gta6-content-automation-app-bubnzu.
Leia e siga o AGENTS.md e o docs/PROMPT-DIARIO.md. Abaixo estão as regras e os cuidados que o Claude
usa em cada rodada. Siga todos.

0. PREPARAR
   - git pull origin claude/gta6-content-automation-app-bubnzu (outra sessão pode ter publicado coisas;
     nunca force push; se o push for recusado, faça git pull --no-rebase, resolva e envie de novo).
   - python -m leonida musica --listar → precisa listar ao menos uma faixa tema. Sem faixa: extraia o áudio
     de um vídeo já publicado (ffmpeg -i prontos/<data>/<post>/br/tiktok/post.mp4 -vn -q:a 2 tema.mp3)
     e instale com python -m leonida musica --arquivo tema.mp3. Sem música tema NÃO publique nada.
   - Hoje é {data}; faltam {N} dias para 19/11/2026.

1. RADAR
   - python -m leonida radar --hours 24 --top 25
   - Considere só histórias que NÃO estão em posts/ nem em state/seen.json.
   - Cuidado com matéria antiga com data nova (ex.: "o extended look da Netflix sai hoje" era de 27/08):
     confira a data do evento antes de tratar como novidade; se for velha, marque como descartado.

2. DECIDIR
   - NOVA e OFICIAL (Rockstar/Take-Two, entrevista com a equipe, órgão oficial como o Diário Oficial,
     executivo de outra empresa falando on the record, grandes sites confirmando) → vira post.
   - Vazamento e rumor NÃO entram. Só se o dono pedir explicitamente; aí: tag vazamento, manchete que não
     afirma o vazamento ("diz que vai…, sem provas"), nada de imagem vazada, nunca cite nome/ticker de
     criptomoeda, nada de hashtag que atraia quem procura download (#gta6leak, nome do leaker), e avise o
     dono para filtrar comentários com "download, link, mega, telegram, apk".
   - Duplicada, irrelevante (cupom, oferta, lista de "notebook para jogar", opinião) ou explícita → ignore.
   - Cota: 2 posts por dia (11:00 e 17:00, America/Cuiaba). Se os horários de hoje já passaram, faça o post
     com a data de AMANHÃ (o contador "X DIAS" e a data da capa saem do campo date).
   - Contagem regressiva só nos marcos 40, 30, 21, 14, 10, 7, 5, 3, 2, 1 e no lançamento:
     python -m leonida contagem --data AAAA-MM-DD --sem-video. Troque a imagem se ela for fraca
     (prefira Jason e Lucia).

3. APURAR (o erro mais comum é copiar a paráfrase errada de um agregador)
   - Leia a FONTE PRIMÁRIA (post da Rockstar, entrevista original, Diário Oficial, o texto do próprio
     autor), não só quem repercutiu. Ex. real: o Dexerto parafraseou as condições de uma ameaça ao
     contrário; Kotaku e Insider Gaming citavam o texto original.
   - Todo fato em 2 fontes, ou na fonte oficial. Fontes que se contradizem → não publique.
   - Frases do tipo "não comentou" ficam específicas ("não comentou a ameaça"), para não negar algo que
     a empresa já disse antes.
   - Cite na legenda quem disse e onde (ex.: "em entrevista à Variety").

4. ESCREVER posts/<data>-<slug>/post.yaml (só o bloco pt; veja um post recente como modelo)
   - Manchete ≤ 70 caracteres, 2–4 palavras em *destaque*; legenda = gancho + fatos curtos + pergunta,
     no máx. 3 emojis, sem hashtag no corpo; 3–5 hashtags específicas no campo hashtags.
   - fontes: todas, com link. selo: gancho curto e verdadeiro (ex.: "Saiu no Diário Oficial").
   - Imagem: screenshot oficial de .cache/rockstar_library.json (python -m leonida biblioteca) que ainda não
     foi usada nos últimos posts (grep -o "media/[A-Za-z_]*_[0-9]*" posts/*/post.yaml). Prefira um
     personagem em foco (a palavra gigante fica atrás dele).
   - estilo: v2 (é o padrão quando o estilo v2 existir); video_segundos: 18–22.

5. GERAR E OLHAR
   - python -m leonida build <id> --sem-video (gera as artes, os JPEGs e o vídeo br/tiktok/post.mp4 com a
     música tema).
   - ABRA cada imagem de prontos/<data>/<id>/br/tiktok/*.jpg e confira:
     • nenhuma letra encostando na linha de baixo (o Ç e o "Q" grandes da manchete encostam: troque a palavra);
     • nenhuma palavra órfã no fim de linha ("A" / "Rockstar"): reescreva o resumo ou use espaço inseparável;
     • "GTA VI", "18 anos", "Xbox Series X|S" sem quebrar linha;
     • rosto do personagem fora do texto; palavra gigante legível; nada nos 150 px da direita
       (botões do TikTok) nem nos 380 px de baixo além do @;
     • @leonidawirebrz certo; contador de dias certo para a data do post.
   - ffprobe no post.mp4: 1080x1920, h264, 30 fps, com faixa de áudio (aac) e duração esperada.
   - Corrija e rode o build de novo até ficar bom.

6. CHECAGEM INDEPENDENTE (faça como se fosse outra pessoa)
   - Releia o post.yaml e a legenda final e tente DERRUBAR cada fato, reabrindo as fontes. Confira nomes,
     cargos, gênero (presidente/presidenta, "foi perguntada"), datas, números, citações traduzidas.
   - Só libere se tudo se sustentar; senão corrija e gere de novo.

7. FECHAR
   - python -c "from leonida import radar; radar.mark_seen(['<id>', ...], 'published')" para as usadas e
     'descartado' para as ignoradas de propósito (vazamento, matéria velha).
   - python -m leonida galeria ; python -m leonida site (se o post for oficial e site não for false).
   - git add posts prontos state site && git commit && git push origin claude/gta6-content-automation-app-bubnzu
   - Metricool (se estiver conectado): python -m leonida publicacao <id> e agende no próximo horário livre
     (11:00/17:00 Cuiabá) com o metricool_info do pacote; vazamento/rumor só como rascunho.
     Sem Metricool: entregue para postar à mão.

8. RELATÓRIO (curto, em português)
   - Posts novos (manchete, fonte principal, horário sugerido) + caminho do post.mp4 e da legenda.txt.
   - Deixei de fora: história — motivo.
   - Se não houver nada novo: responda só "Radar: nada novo".
```

---

## Prompt B — estilo v2 (logo nova, textos animados e edição)

```text
Objetivo: deixar o Leonida Wire com cara de canal profissional. Três frentes: a LOGO do topo, as
TRANSIÇÕES/ENTRADAS dos textos no vídeo e o ESTILO DE EDIÇÃO do vídeo de publicação (br/tiktok/post.mp4).

Primeiro: git pull. Se leonida/motion.py já existir (o Claude implementou o estilo v2), NÃO reimplemente:
rode um build de teste, confira os critérios de aceite abaixo e só corrija o que falhar. Se não existir, implemente seguindo esta especificação.
Paleta e fontes não mudam (night #0B0614, pink #FF2E88, orange #FF8A3D, gold #FFC857, purple #7B2FF7,
cyan #22D3EE, mist #E9E3F5; Anton, Inter, Yellowtail). Visual fotográfico, sem neon exagerado.

1) LOGO DO TOPO (render.brand_bar — usada na capa, nos slides e no "siga")
   - Emblema "sol de Vice" (~88 px): círculo com gradiente vertical gold → orange → pink → purple, metade de
     baixo cortada por 4 faixas horizontais transparentes que engrossam para baixo (sol synthwave), borda
     fina clara e sombra suave. Se existir assets/brand/logo.png (ex.: a foto de perfil escolhida), usa ela
     recortada em círculo no lugar do emblema.
   - Wordmark numa linha: "LEONIDA" em Anton branco + "WIRE" em Anton com o gradiente do pôr do sol.
   - Embaixo: "● NOTÍCIAS DE GTA VI" — ponto vermelho "ao vivo" + Inter ExtraBold pequeno, espaçado, claro.
   - Alinhada com o contador de dias (mesma altura de centro). Configurável em config/brand.yaml → logo.

2) TEXTOS ANIMADOS (motor novo leonida/motion.py; Python + Pillow/NumPy + FFmpeg, sem Chrome)
   - Cada arte vira camadas (fundo, palavra gigante, personagem, selo, linhas da manchete, resumo, fonte,
     título do slide, cada item da lista, logo, contador, moldura). O motor anima as camadas e manda os
     quadros para o FFmpeg.
   - Manchete e títulos: cada linha sobe de dentro de uma máscara (revelação de baixo para cima, 0,5 s,
     ease-out forte), 0,08 s entre linhas; as palavras em *destaque* ganham um brilho que atravessa da
     esquerda para a direita logo depois.
   - Selo: "pop" de 60% → 100% com leve overshoot (0,35 s). Resumo e fonte: sobem 24 px com fade (0,4 s).
   - Listas: o número dá um pulo (escala 0 → 1 com overshoot) e o texto desliza da esquerda com máscara;
     um item por batida da música (0,45–0,7 s entre itens); com a lista completa, segura ≥ 2,5 s para ler.
   - Saída: antes de cada transição os textos sobem ~30 px e somem (0,25 s); o fundo continua.
   - Logo: o ponto "ao vivo" pisca devagar; o contador dá um pop quando a capa entra.

3) ESTILO DE EDIÇÃO
   - Gancho: a capa fica COMPLETA desde o 1º quadro (é a miniatura do TikTok e o ponto do loop) e já está
     viva: push-in no fundo, palavra gigante derivando, brilho passando nas palavras em destaque, contador
     dando um pulo. O personagem recortado usa a mesma câmera do fundo (senão aparece um "fantasma").
   - Câmera: fundo com push-in lento (1,00 → 1,05) em cada cena; personagem com parallax (cresce um pouco mais
     e sobe ~20 px); palavra gigante deriva devagar. Nada de tremedeira.
   - Transições (0,35–0,45 s): capa → próximo = "zoom punch" (escala + flash); entre slides = whip pan
     horizontal com borrão de movimento; para o "siga" = flash de luz rosa/laranja; no fim volta para a capa
     (loop perfeito: o último quadro emenda no primeiro).
   - Ritmo: algo muda a cada 1,5–3 s. Detecte as batidas da música tema (fluxo espectral, 90–160 BPM; ou
     music.bpm/music.fase no brand.yaml) e encaixe as trocas de cena e os itens das listas nas batidas.
     Nenhuma cena estica além do limite (capa ~4 s, imagem limpa ~4 s, lista ≤ 3,4 s depois do último
     item): com poucas cenas o vídeo sai mais curto que o alvo, em vez de ficar parado.
   - Saída: 1080×1920, 30 fps, H.264 High, CRF ~18, cores BT.709, +faststart, música tema com fade de 0,5 s.
     Duração = video_segundos (padrão 20). Render < 2 min por post num PC comum.
   - post.yaml: estilo: v2 (padrão) | dinamico | classico (o slideshow antigo continua funcionando).

CRITÉRIOS DE ACEITE
   - python -m leonida build 2026-10-11-gta6-classificacao-18-anos --sem-video gera post.mp4 v2 com música.
   - Extraia 1 quadro por segundo (ffmpeg -vf fps=1) e confira: nenhum quadro preto/vazio, texto nunca cortado
     nas bordas, nada importante na coluna dos botões nem na faixa da legenda do TikTok, o último quadro
     igual ao primeiro.
   - As artes PNG/JPEG do carrossel continuam iguais ao último quadro de cada cena (mesma composição).
   - Rode o build de 3 posts diferentes (capa com personagem, layout card, lista longa) sem erro.
   - Commit "Estilo v2: logo nova, textos animados e edição" + push.
```

---

## Notas

- O Claude (nuvem) roda o Prompt A de 3 em 3 horas nesta sessão e entrega os vídeos no chat; o Codex pode
  rodar o mesmo no PC. Para não duplicar posts, sempre faça `git pull` antes e confira `posts/` e
  `state/seen.json`.
- Publicação automática (Metricool) e deploy do site (Vercel) só funcionam onde essas contas estão
  conectadas; sem elas, o post fica pronto para postar à mão.
