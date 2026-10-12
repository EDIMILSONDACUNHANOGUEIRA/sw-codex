# AGENTS.md — instruções para o Codex (e Claude Code) neste projeto

Este repositório é o **Leonida Studio**: produção de notícias de **GTA VI e da franquia GTA**
para TikTok e YouTube Shorts, com prioridade para GTA VI. O padrão é **português do Brasil**, perfil
**@leonidawirebrz** (`idiomas: [pt]` em `config/brand.yaml`). Só produza em inglês quando o usuário
pedir explicitamente; nesse caso use **@leonidawireusa** no post solicitado, mantendo o padrão PT
para as próximas rodadas. O agente pesquisa, confirma os fatos, escreve e edita os vídeos.

**Entrega atual: arquivos locais neste chat para o usuário publicar.** Não agende nem publique em
redes sociais, não envie notificações externas e não faça deploy do site sem autorização explícita
para essa ação. A rotina pesquisa às **11h e 17h, America/Cuiaba**; sem novidade relevante, fica quieta.
A rotina do Codex precisa ser recriada na outra conta; veja
[`docs/CONTINUAR-EM-OUTRA-CONTA.md`](docs/CONTINUAR-EM-OUTRA-CONTA.md). Código, prompts e histórico no
GitHub são portáveis; a sessão e as conexões da conta não são. Prompt da automação:
[`docs/AUTOMACAO-GTA.md`](docs/AUTOMACAO-GTA.md).

## Aplicativos separados no mesmo repositório

- **Leonida Notícias**: `apps/noticias/`, `scripts/abrir-noticias.bat`, porta **8768**.
  Mantém rascunhos em `posts/`, histórico em `state/` e saídas em `prontos/<data>/`.
- **Leonida Cortes**: `apps/gameplay/`, `scripts/abrir-gameplay.bat`, porta **8769**.
  Fontes do formulário ficam em `apps/gameplay/uploads/`; planos e exports em
  `apps/gameplay/prontos/`. Revisões manuais novas podem usar `apps/gameplay/prontos/revisoes/`.

Preserve o fluxo e a automação das notícias ao trabalhar em cortes. Não mova entregas anteriores:
os projetos legados em `prontos/gameplay/` e outros pacotes continuam nos caminhos originais.
As pastas locais de fontes e exports do Cortes não entram no GitHub.

No Cortes, respeite a escolha do usuário entre **Tema de GTA VI**, **Sem música adicional** e
**Outra música**, feita na importação ou revisão e aplicada à exportação. O áudio original é
preservado; a faixa adicional é misturada com volume de 0–100% (padrão 10%) e redução durante
a fala. O formulário aceita MP3, WAV, M4A, AAC, FLAC e OGG até 512 MB. **Sem música adicional**
não remove música já gravada na fonte nem separa as vozes e trilhas. Use somente a faixa local
escolhida, sem substituir por uma faixa aleatória. A música tema continua obrigatória nas notícias
diárias; essa escolha é específica do editor de cortes.

## Fluxo padrão ("faz os posts de hoje")

Prompt completo e modelo do relatório de entrega: [`docs/PROMPT-DIARIO.md`](docs/PROMPT-DIARIO.md).
Use `--sem-video` para pular só a capa animada (HyperFrames); o vídeo de publicação
`br/tiktok/post.mp4`, com a música tema, é gerado do mesmo jeito.

1. `python -m leonida radar --hours 72` — lista as histórias do momento (já agrupadas e ranqueadas).
   Também grava `state/radar.json` e `prontos/RADAR.md`.
2. Para cada história relevante e ainda não coberta (veja `posts/` e `state/seen.json`):
   - Consulte TecMundo/Voxel, Flow Games, IGN e as demais fontes de `config/sources.yaml`.
     Leia a matéria original e confira a data do fato e a data da publicação. RSS/Google são descoberta,
     não prova: valide na Rockstar/Take-Two, na entrevista original ou em duas fontes independentes.
   - Compare o assunto com `posts/*/post.yaml`, `state/seen.json` e `state/publicados.json`.
     A mesma notícia em outro site ou idioma não é nova. Só refaça um assunto com fato novo relevante.
   - Crie `posts/<AAAA-MM-DD>-<slug>/post.yaml` (modelo abaixo ou `python -m leonida novo "título"`).
     Faça até dois vídeos por rodada, priorizando a relevância; deixe as demais pautas novas para a
     próxima rodada. Cada vídeo novo tem **30–60 segundos**, padrão **45 s**, definido explicitamente
     em `video_segundos` pelo tempo de leitura. Não aumente a duração de vídeos antigos ao refazê-los.
   - Escolha a imagem: prefira **screenshots oficiais da Rockstar** (`python -m leonida biblioteca`
     lista todas; URLs do tipo `https://www.rockstargames.com/VI/_next/static/media/...`) ou a
     `og:image` da matéria se for oficial e tiver ≥ 1200 px de largura.
3. `python -m leonida build <post-id> --sem-video` — gera capa, carrossel, vídeo e legendas em
   `prontos/<data>/<post-id>/{br,us}/`. Use `--sem-video` para iterar rápido.
   Para um pedido explícito em inglês, use `post.build('<id>', langs=('en',), video=False, estilo='v2')`
   pela API Python; o comando CLI padrão continua em português.
4. **Abra as imagens geradas e revise** (texto cortado, palavra gigante ilegível, rosto escondido).
   Ajuste `zoom`, `focus`, `layout` ou o texto e rode de novo. Preserve anatomia e rosto do material
   oficial; se o recorte falhar, use `layout: card`. Confira a capa e as transições no vídeo exportado,
   texto legível entre movimentos, áreas seguras, duração real, resolução e áudio. Nunca declare QA
   que não foi executada. Preserve as entregas existentes; crie uma versão nova para revisões.
5. `python -m leonida galeria` atualiza `prontos/index.html`. Só depois de exportação e revisão bem
   sucedidas, marque as histórias entregues com `radar.mark_seen(['<id>'], 'entregue')`.
   `published` ou `state/publicados.json` exige evidência de publicação real, não apenas geração.
   Falha de pesquisa/render/QA deve continuar pendente e ser relatada, sem anunciar sucesso.
6. Entregue links locais dos MP4, capas e legendas, com fontes verificadas. Commit/push só com
   autorização; antes, revise `git diff` e os arquivos selecionados. Não inclua segredos, dados
   pessoais, músicas, cookies, `.env`, caches ou modelos. Preserve os trabalhos anteriores.

Post diário de contagem regressiva: `python -m leonida contagem`.
**Música nas notícias: SEMPRE a música tema de GTA VI, em toda publicação da rotina diária.** Nunca música aleatória e nunca a
"música automática" do TikTok (`autoAddMusic: false`). Por isso o post é publicado como VÍDEO
(`br/tiktok/post.mp4`, gerado no build com a música tema embutida), não como post de fotos. As faixas
ficam em `assets/music/`, fora do git: `python -m leonida musica <url-do-trailer> --inicio 0:12 --nome
trailer-2` e `python -m leonida musica --listar`. Sem música tema, não publique: avise e peça a música.
Downloads de vídeo: sempre via **yt-dlp**.
Perfil padrão: BR **@leonidawirebrz**. O MP4 vertical serve para TikTok e YouTube Shorts;
`python -m leonida publicacao <id>` prepara o pacote do TikTok, não comprova publicação. A integração
do YouTube Shorts não está implementada nesse comando. Publicação externa exige autorização explícita.
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

Para **gameplay longa e melhores momentos**, abra **Leonida Cortes** na porta 8769 ou use
`python -m leonida gameplay URL` (CLI legado).
Leia `docs/CORTES-GAMEPLAY.md`: aceite fontes de 30 minutos ou mais; vídeo horizontal até 11 minutos,
shorts 30–60 s (três de 45 s por padrão), capas de quadros reais. Analise, confira a fonte nos momentos
sugeridos, ajuste títulos e intervalos no plano e só então exporte uma versão nova. Não confunda scores
de movimento/áudio com compreensão da cena ou garantia de viralização. PT por padrão, crédito obrigatório,
rostos preservados, entregue aqui, sem publicação externa. `--lang en` somente por pedido explícito.

No Leonida Cortes, as legendas da voz estão ativadas por padrão. Transcreva o áudio original
antes de adicionar a música do editor; o texto visível do jogo não recupera a voz do criador.
O idioma da fala é independente dos títulos e capas, com PT padrão. O reconhecimento é local,
com `requirements-speech.txt` e runtime compatível, ou com SRT revisado fornecido pelo usuário.
Um SRT fornecido tem prioridade e usa os tempos da fonte, remapeados aos cortes selecionados.
Quando o áudio mistura comentarista e personagens, revise os erros e sobreposições: não prometa
separação perfeita dos falantes nem preencha palavras incertas. Preserve a transcrição editável
e informe a pendência se a voz não puder ser legendada. Veja a instalação em
`docs/CORTES-GAMEPLAY.md`.

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
# video_segundos: 45    # rotina de notícias novas: 30–60 s; padrão 45 s, a 30 fps.
#                       # se faltar tempo para leitura, o build falha e preserva a entrega anterior
# estilo: v2            # padrão (config/brand.yaml → video.estilo_padrao): textos animados, transições
#                       # zoom/whip/luz, ritmo na batida e loop na capa (leonida/motion.py).
#                       # dinamico = slideshow com itens um a um; classico = slideshow antigo
# foto_limpa: true      # força o slide da imagem limpa (ex.: arte oficial hospedada fora da Rockstar)
# credito_imagem: "LOVE Magazine / Rockstar Games"   # crédito no slide da imagem limpa
# site: false           # não vira matéria no site (use para análise/especulação)
# fontes: [{name: ..., url: ...}]                    # várias fontes (aparecem no fim da matéria)
source: { name: "Rockstar Games", url: "https://www.rockstargames.com/VI/music" }
pt:
  kicker: RÁDIOS        # 1 palavra (até ~9 letras) que fica gigante atrás do personagem
  # selo: "A Rockstar confirmou"   # troca o texto do selo da capa por um gancho (só se for verdade)
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
# en: (só se o usuário pedir inglês; build explícito com langs=('en',))
```

## Regras editoriais (obrigatórias)

- **Só fatos verificados nas fontes.** Nunca invente data, preço, nome, número ou "fontes dizem".
- Vazamento/rumor: tag `vazamento`/`rumor` e deixar claro que **não é oficial**.
- **Nada explícito** (nudez, sexo, violência gráfica) — mesmo que a matéria cite. O TikTok derruba.
  Não use imagens vazadas; use screenshots oficiais.
- Sempre credite a fonte (`source`). A legenda ganha "Fonte: X" automaticamente.
- Português do Brasil por padrão, tom de gamer, direto e empolgado, sem exagero. Inglês apenas
  por pedido explícito do usuário, sem mudar `idiomas: [pt]` para futuras rodadas.
- Manchete ≤ 70 caracteres, 2–4 palavras em `*destaque*`. "GTA VI" nunca quebra linha (automático).
- Legenda: gancho na 1ª linha, fatos em linhas curtas, pergunta no final, no máx. 3 emojis.
  **Sem hashtags dentro da legenda** (vão no campo `hashtags`).
- Data/plataformas de lançamento, preço e edições: confirme na fonte oficial atual antes de citar.
  `release_date` em `config/brand.yaml` é o valor do contador, não prova de que a data continua válida.

## Estilo visual (não mude sem pedir)

Acabamento fotográfico (config `acabamento` no brand.yaml): sem contorno neon no personagem, sombra
do personagem na palavra gigante, luz do fundo na borda do recorte, grão de filme e halação. Isso
evita a cara de "arte gerada por IA". `neon: true` volta ao visual antigo.

Paleta "Vice" (pôr do sol de Leonida): night `#0B0614`, pink `#FF2E88`, orange `#FF8A3D`,
gold `#FFC857`, purple `#7B2FF7`, cyan `#22D3EE`. Fontes: Anton (manchetes), Inter (texto),
Yellowtail (assinatura antiga). Assinatura da marca: **palavra gigante atrás do personagem recortado**,
color grading roxo/quente, cantos estilo "mira", contador "X DIAS PARA O GTA VI" no topo.
Logo v2 (`config/brand.yaml → logo`): "sol de Vice" + LEONIDA WIRE + ponto "ao vivo"; a mesma marca grande
fecha o vídeo no "siga". Se existir `assets/brand/logo.png` (ex.: a foto de perfil), ela entra no lugar do sol.
Vídeo v2: a capa é legível desde o 1º quadro (miniatura e ponto do loop); os outros slides têm textos entrando
(máscara, pop, deslize), as trocas são zoom punch / whip pan / luz quente e o vídeo termina na capa.
Tudo é configurável em `config/brand.yaml` (nome, @ dos perfis, paleta, selos, áreas seguras).

## Mapa do código

| Arquivo | Função |
|---|---|
| `leonida/radar.py` | feeds RSS (`config/sources.yaml`), filtro, agrupamento PT/EN, ranking |
| `leonida/render.py` + `gfx.py` | artes 9:16 (capa, grade, lista, CTA) e camadas para vídeo |
| `leonida/cutout.py` | recorte do personagem (rembg) |
| `leonida/motion.py` | vídeo de publicação v2: camadas animadas, transições, batidas, loop (Pillow + FFmpeg) |
| `leonida/postvideo.py` | vídeo de publicação dos estilos antigos (dinamico/classico) |
| `leonida/video.py` | capa animada em HyperFrames (só nos estilos antigos; fallback FFmpeg) |
| `leonida/clips.py` | cortes 9:16 de vídeos (yt-dlp + FFmpeg + legendas faster-whisper) |
| `leonida/edit.py` | edição de vídeo por link: cenas, reenquadramento, movimentos de câmera, transições (HyperFrames) |
| `leonida/writer.py` | redação automática via Claude API (opcional) |
| `leonida/post.py` | `post.yaml` → `prontos/` (+ README.md por post) |
| `apps/noticias/` | app de notícias, porta 8768, com as saídas e o histórico existentes |
| `apps/gameplay/` | app de cortes, porta 8769, com uploads e saídas próprios |
| `leonida/gameplay.py` + `gameplay_render.py` | análise de momentos, planos e exports de gameplay |
| `leonida/speech_captions.py` | reconhecimento local do áudio, SRT/ASS editáveis e remapeamento de falas |
| `leonida/server.py` + `web/` | app web legado (`python -m leonida serve`) |
| `leonida/notify.py` | envio para Telegram/Discord |

Antes de commitar mudanças de código: `python -m leonida build <um-post> --sem-video` e confira a imagem.
