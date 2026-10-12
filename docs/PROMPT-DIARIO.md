# Rotina diária — Leonida Wire

A rotina pesquisa notícias de GTA VI e da franquia GTA às **11h e 17h, America/Cuiaba**.
Entrega até dois vídeos por rodada neste chat para o usuário publicar no TikTok ou YouTube Shorts.
O idioma padrão é português. Só gere inglês quando houver um pedido explícito.

O prompt do agendamento está em [AUTOMACAO-GTA.md](AUTOMACAO-GTA.md). Para trocar de conta sem
perder o fluxo e o histórico, siga [CONTINUAR-EM-OUTRA-CONTA.md](CONTINUAR-EM-OUTRA-CONTA.md).
Esta documentação descreve a rotina; criar estes arquivos não ativa um agendamento por si só.

## Preparação local

Abra o mesmo repositório no Codex. Se precisar de outro checkout:

```powershell
git clone https://github.com/EDIMILSONDACUNHANOGUEIRA/sw-codex.git
cd sw-codex
git checkout codex/gta-rotina-2026-10-12
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

O branch acima é o branch deste projeto; confira se ele contém a versão atual antes de continuar.
FFmpeg e ffprobe precisam estar no PATH. Node.js/HyperFrames são opcionais para os estilos antigos;
o motor v2 de notícias usa Pillow, NumPy e FFmpeg. O primeiro recorte pode baixar o modelo rembg,
que fica no cache local. Não exclua o cache ao trocar apenas de conta.

As faixas em `assets/music/` ficam só no PC e não acompanham o GitHub. Reuse uma faixa tema já
existente e autorizada. Confirme com `python -m leonida musica --listar`. Se precisar preparar uma
faixa local, use `python -m leonida musica --arquivo "caminho/da/faixa.mp3"`. Não envie músicas,
cookies, credenciais ou `.env` ao GitHub. A redação pelo agente do Codex dispensa uma chave Claude;
`ANTHROPIC_API_KEY` só é usada pelo redator API opcional. Não copie chaves para prompts ou arquivos
públicos. Sem música disponível, relate a pendência e preserve os arquivos anteriores.

Antes de atualizar o checkout, confira `git status`: preserve mudanças locais. Não use reset,
clean ou descarte de arquivos para preparar a rotina. Um `git pull` deve respeitar essas mudanças.

## Prompt para uma execução manual

```text
Você é o editor do Leonida Wire, @leonidawirebrz. Pesquise novidades de GTA VI e da franquia GTA,
com prioridade para GTA VI, e entregue neste chat até dois vídeos prontos para TikTok e YouTube
Shorts. Use português do Brasil; inglês somente quando o usuário pedir explicitamente.

Leia AGENTS.md, config/sources.yaml, config/brand.yaml e o histórico em posts/ e state/.
Rode python -m leonida radar --hours 72. Consulte TecMundo/Voxel, Flow Games, IGN, Rockstar,
Take-Two, GamesRadar+, VGC e os demais portais configurados. Quando um feed falhar, faça busca
na web pelos portais originais. Um RSS vazio ou indisponível não prova ausência de novidades.

Para cada pauta, leia a matéria original e confira as datas da publicação e do fato. Confirme
na fonte primária oficial, na entrevista original ou em duas fontes independentes. Matérias que
apenas repetem a mesma entrevista contam como uma origem. Nunca trate rumor como confirmação.
Na rotina padrão, só produza fatos verificados; relatos não confirmados aguardam revisão.

Compare a pauta com posts/*/post.yaml, state/seen.json e state/publicados.json. A notícia em outro
idioma ou site não é nova. Uma atualização só vira vídeo quando há um fato novo relevante,
explicando o que mudou. Não use a palavra novidade para informação antiga só porque saiu um
artigo novo. Priorize até dois assuntos diferentes por rodada e deixe o restante na fila.

Crie um post.yaml novo para cada vídeo, somente com pt, source/fontes e video_segundos de 30 a
60; use 45 como padrão e ajuste pelo tempo de leitura. Escolha imagens oficiais, preserve a
anatomia dos personagens, revise os recortes e use layout card quando necessário. Os vídeos
anteriores e as versões já entregues devem ser preservados. Para pedido explícito em inglês,
use o bloco en e post.build com langs=('en',), mantendo idiomas: [pt] no config.

Rode .venv/Scripts/python.exe -B -u -X utf8 scripts/produzir_rotina.py <id>. Esse comando gera
br/tiktok/post.mp4 e a subpasta br/qa com as verificações e imagens para revisão. Use música tema
local autorizada. Não substitua a trilha por uma escolha aleatória nem por música automática da plataforma.

Abra as capas e quadros das transições e revise os MP4 exportados: textos legíveis, rosto íntegro,
áreas seguras, movimentos suaves, áudio, resolução 1080x1920, 30 fps e duração real entre 30 e 60 s.
Rode as verificações apropriadas ao que foi alterado e registre apenas testes realmente executados.
Se o build/QA falhar, corrija ou relate a pendência; não marque a história como entregue.

Depois da exportação e revisão, registre a entrega em state/entregas.json e marque o item do radar
como entregue com radar.mark_seen quando a pauta estiver no radar.
Não marque published nem registre em state/publicados.json sem evidência de publicação real.
Atualize a galeria local. Entregue neste chat os links dos MP4, capas e legendas em português,
com as fontes e uma confirmação curta da duração e das verificações feitas.

Não publique nem agende nas redes, não faça deploy, não envie mensagens a serviços externos e
não faça push automático. Se o usuário autorizar sincronização do repositório, revise os arquivos
selecionados antes de commit/push: exclua segredos, dados pessoais, músicas, cookies, .env e caches.

Sem novidade relevante e verificável, não produza vídeo. Na rotina agendada, fique quieto; informe
somente entrega nova, mudança relevante, falha ou necessidade de ação do usuário. Não prometa que
a rotina continuará funcionando sem conta ativa, disponibilidade do serviço e computador acessível.
```

## Entrega

Use uma resposta curta com até dois itens: assunto, vídeo MP4, legenda e fonte. Inclua a duração
verificada e qualquer pendência real. Não diga que foi publicado quando o arquivo foi só entregue.
Os MP4 verticais podem ser usados nas duas plataformas; `leonida publicacao` prepara apenas um
pacote do TikTok. Não há publicação no YouTube Shorts implementada nesse comando.

O comando legado `python -m leonida auto` não é o fluxo desta rotina: ele depende do redator API e
pode enviar notificações ou marcar itens como `published` ao gerar arquivos. Use a pesquisa,
redação e revisão pelo agente conforme o prompt acima. Contagem regressiva diária também não
substitui notícia nova; só faça quando solicitada e depois de conferir a data oficial atual.
