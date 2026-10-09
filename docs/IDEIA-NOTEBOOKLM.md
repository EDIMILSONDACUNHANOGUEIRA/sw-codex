# Leonida Wire: a ideia completa (para pesquisa e melhoria)

Documento de contexto do projeto, escrito em 09/10/2026. Serve de fonte para o NotebookLM: descreve o que existe,
as regras, o que já deu certo ou errado e o que queremos melhorar.

## 1. O que é

O **Leonida Wire** é um sistema que acha, confere, edita e publica **notícias oficiais de GTA VI** em português do Brasil,
quase sem trabalho manual.

- **Perfil no TikTok:** @leonidawirebrz (só Brasil, em português). Hoje tem cerca de 60 seguidores.
- **Site de notícias:** https://leonida-wire-sage.vercel.app (estático, publicado na Vercel). O link vai na bio do TikTok.
- **Contexto:** GTA VI é lançado em **19 de novembro de 2026** (PS5 e Xbox Series X|S). A procura por notícia é enorme,
  e o objetivo é ser um perfil confiável: só o que é oficial, sempre com fonte.

## 2. Regras definidas pelo dono (valem sempre)

1. **Só notícia oficial.** Rockstar, entrevistas oficiais com a equipe e o que os grandes sites confirmam. **Vazamento e
   rumor não entram em lugar nenhum** (nem TikTok, nem site).
2. **Imagem nova do jogo:** primeiro a arte editada (capa), depois a **imagem limpa oficial** da Rockstar, sem texto por cima.
3. **Música tema de GTA VI em toda publicação**, embutida no vídeo. Nunca música aleatória do TikTok.
4. **As imagens não podem ter cara de IA.** A arte é montada com as imagens oficiais, recorte do personagem, texto grande
   atrás, grão de filme e acabamento. Nada de gerar cena do jogo com IA.
5. **Horários fixos:** 11:00 e 17:00 (fuso de Cuiabá), 2 por dia, até acabar a cota gratuita do Metricool (20 posts por mês).
6. **Posts oficiais e virais saem sozinhos**, sem revisão. Posts postados à mão pelo dono não gastam a cota.
7. Sem conteúdo explícito. O repositório do projeto precisa ficar público (o Metricool baixa as mídias de lá).

## 3. Como funciona (passo a passo)

1. **Radar:** lê feeds (Rockstar Newswire, Google Notícias, sites de games, Reddit) e ranqueia as histórias das últimas 72 h.
2. **Checagem:** cada fato precisa estar na fonte oficial ou em pelo menos duas fontes confiáveis. Frases entre aspas são
   conferidas na entrevista original.
3. **Post:** um arquivo `post.yaml` guarda manchete, resumo, legenda, slides, imagem oficial e fontes.
4. **Arte:** capa 1080×1920 com recorte do personagem, depois o slide da imagem limpa e os slides de lista.
5. **Vídeo:** os slides viram um vídeo vertical de cerca de 16 s com a música tema. É esse vídeo que vai ao TikTok
   (post de fotos não deixa escolher a música, por isso tudo vai como vídeo).
6. **Publicação:** o pacote vai para o **Metricool**, que agenda no TikTok com título e legenda. A mídia é lida do GitHub
   por um endereço fixo no commit.
7. **Site:** cada post vira uma matéria (imagem oficial no topo, texto, fontes, galeria) e a Vercel publica.
8. **Rotina automática:** roda às 9:53 e às 15:53 (Cuiabá) para preparar os posts das 11:00 e das 17:00.
9. **Pedido sob demanda:** o dono pede "ache uma notícia nova" e recebe o vídeo e a legenda para postar à mão.

**Também existe:** um editor de vídeo a partir de link (corta cenas, reenquadra em 9:16, movimentos de câmera, transições,
legenda, música tema).

**Tecnologias:** Python, Pillow, FFmpeg, remoção de fundo por IA (rembg), HyperFrames, Metricool, Vercel, GitHub, Playwright.

## 4. Situação em 09/10/2026

- **Publicados:** loja oficial da Rockstar (automático), entrevista da IGN com Rob Nelson (à mão), Rockstar explica o Jason,
  entrevista da LOVE Magazine (à mão, versão em inglês também gerada).
- **Agendado:** 17:00 de hoje, as novas músicas da trilha oficial (Cardi B "Don't Chart" e Fuerza Regida "Suzuki").
- **Cota do mês:** 2 de 20 usadas.
- **Site:** 8 matérias, páginas Início, Notícias, Imagens oficiais e Sobre, feed RSS, mapa do site, contador de dias,
  botão de compartilhar no WhatsApp. Cada atualização é publicada à mão na Vercel (a produção está ligada ao branch `main`).

## 5. Problemas que já aconteceram (lições)

- Post de fotos no TikTok não deixa escolher música, por isso tudo é vídeo.
- O TikTok recusou imagens PNG, então são enviadas em JPEG.
- O Metricool recusou mídia de repositório privado e passou a exigir **título** nos vídeos do TikTok.
- Capa com personagem escuro some no fundo. É preciso escolher a imagem oficial com rosto bem iluminado.
- Muita "notícia" é a mesma história reciclada. O radar precisa descartar o que já foi coberto.
- Com 60 seguidores o TikTok provavelmente não libera link clicável na bio (talvez só em conta comercial).

## 6. Ideias em estudo

- **ElevenLabs:** narração em português por cima da música tema, efeitos sonoros, vinheta animada da marca.
  Evitar cenas falsas do jogo e clonar voz de pessoas reais. Marcar conteúdo de IA. O plano gratuito não dá uso comercial.
- **Vídeo de atmosfera de 30 s** (estilo Miami anos 80, sem cena do jogo), feito com IA e rotulado como IA.
- **Biografia do TikTok** com o endereço do site.
- Voltar a fazer o perfil dos EUA (@leonidawireusa) ou publicar também em Reels e YouTube Shorts.

## 7. O que queremos pesquisar e melhorar (perguntas para o NotebookLM)

**Crescimento no TikTok**
- O que faz um perfil de notícias de games sair de 60 para 1.000 seguidores no Brasil? Duração do vídeo, gancho nos
  primeiros 2 segundos, frequência, horários, hashtags.
- Vídeo de 15 s com música, carrossel ou vídeo narrado: qual retém mais? Legenda na tela ajuda?
- Postar sempre às 11:00 e 17:00 é o melhor? Como testar horários?

**Regras e riscos**
- Música tema oficial usada por upload: risco de direitos autorais, silenciamento ou queda de alcance? Há alternativa legal
  (biblioteca comercial de sons)? Conta comercial muda isso?
- Uso das imagens oficiais da Rockstar e da Take-Two: o que a política de conteúdo de fãs permite? Crédito basta?
- Regras do TikTok sobre IA, conteúdo repetido e postagem automatizada por ferramentas como o Metricool. Perde alcance?

**Site**
- Como entrar no Google Notícias e no Discover? Search Console, domínio próprio, SEO para "GTA 6" em português.
- Monetização possível e honesta: anúncios, afiliados, patrocínio. O que exige CNPJ?

**Concorrência e diferencial**
- O que os perfis brasileiros de GTA VI (Flow Games, Voxel, IGN Brasil, outros) fazem bem e mal? Onde há espaço?
- Que formatos o público pede: contagem regressiva, "o que muda", comparações, resumo semanal?

**Qualidade e automação**
- Como deixar a arte mais autoral e menos "de template", sem parecer IA?
- Que fontes oficiais adicionar ao radar (contas oficiais, calendários de eventos, embargos de prévias e análises)?
- Que métricas acompanhar por post (retenção, compartilhamentos, cliques no site) e como virar decisão?

## 8. Fontes sugeridas para adicionar no NotebookLM

- O site: https://leonida-wire-sage.vercel.app
- O código e o prompt diário: https://github.com/EDIMILSONDACUNHANOGUEIRA/sw-codex/tree/claude/gta6-content-automation-app-bubnzu
  (arquivos `docs/PROMPT-DIARIO.md` e `AGENTS.md`)
- Políticas do TikTok (diretrizes da comunidade, conteúdo gerado por IA, programa de recompensas) e a política de
  conteúdo de fãs da Rockstar/Take-Two.
