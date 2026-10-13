# Rotina de pesquisa e produção GTA

Preferências confirmadas em 12/10/2026: pesquisar às **11h e 17h, America/Cuiaba**,
produzir em **português** e **entregar os arquivos no chat**. Inglês somente quando
solicitado. A rotina prepara vídeos para TikTok e YouTube Shorts; a publicação é manual.

A rotina foi criada no aplicativo com o nome **GTA: pesquisa e vídeos em português**.
Confira o agendamento na interface. O computador precisa permanecer ligado, com
o aplicativo aberto e acesso ao projeto. A execução depende do acesso e dos limites
da conta. O GitHub guarda o fluxo e os arquivos versionados, mas não transfere o
agendamento nem garante geração de vídeos quando a conta estiver indisponível.
Referência: [documentação oficial de tarefas agendadas](https://learn.chatgpt.com/docs/automations?surface=app).

## Prompt para recriar a rotina na outra conta

Use este texto no chat do projeto e peça para agendar às 11h e 17h no fuso America/Cuiaba:

> Pesquise notícias novas verificadas de GTA VI e da franquia GTA, com prioridade
> para GTA VI. Leia AGENTS.md, docs/PROMPT-DIARIO.md e config/sources.yaml.
> Consulte Rockstar, Take-Two, TecMundo/Voxel, Flow Games, IGN Brasil e IGN,
> GamesRadar, VGC, Game Informer e outros portais configurados. Confira o conteúdo
> das matérias e compare a data da publicação com a data do acontecimento.
> Confira posts/, state/seen.json e state/entregas.json para evitar repetição.
> Produza até dois vídeos por rodada, de 30 a 60 segundos, padrão 45 segundos,
> em português do Brasil, 1080x1920, rodapé @leonidawirebrz e legenda para publicar.
> Inglês apenas quando eu pedir explicitamente, usando @leonidawireusa naquela entrega.
> Se houver mais notícias, guarde uma fila local para a próxima rodada.
> Escreva os post.yaml com fontes e imagens oficiais pertinentes à pauta. Preserve os arquivos
> anteriores e crie uma versão nova para qualquer revisão. Prefira layout: card para rostos e
> fotografias horizontais, preservando a imagem inteira. Escolha 3–6 fotos oficiais de apoio
> diferentes em visuals: [{image, credit, label}], com URLs reais e créditos. Imagens ilustrativas
> devem ter esse rótulo; não são prova da notícia nem quadros de um vazamento. Na Biblioteca oficial,
> Foto da capa escolhe a miniatura principal; Imagem do vídeo adiciona apoio com miniaturas.
> Abra com a capa, alterne as fotos de apoio e slides curtos de fatos verificados e termine com
> a CTA, quando ativada. Notícias v2 de 30 s ou mais usam max_scene_seconds=7: fotos distintas
> podem retornar espaçadas, sem repetir capa e CTA para completar o tempo. Listas extensas
> preservam a leitura mínima e registram exceção acima de 7 s; prefira dividi-las. Se faltam
> imagens ou slides, corrija a seleção indicada no erro, sem esticar uma capa por 30 s.
> Rode scripts/produzir_rotina.py com os IDs escolhidos. Revise todas as capas e o
> contato de quadros gerado no QA, incluindo variedade das imagens e transições. Confira duração,
> resolução, decodificação completa e presença de áudio. Entregue aqui os MP4,
> legendas e fontes locais. Registre os IDs e temas entregues em state/entregas.json;
> entregue não significa publicado. Não publique em redes, não envie notificações
> externas, não faça deploy nem push automático de vídeos ou dados pessoais.
> Só notícia oficial ou confirmada vira post: vazamento e rumor ficam fora (o radar marca
> e o redator bloqueia). Nunca usar imagens vazadas. Sem novidade relevante verificada,
> fique quieto e não gere conteúdo repetido. Avise quando houver vídeo pronto, falha
> ou ação necessária. Preserve os trabalhos existentes e não instale modelos pesados.

## Produzir e verificar uma entrega

Na raiz do repositório, depois de checar as fontes e escrever o post:

```powershell
.\.venv\Scripts\python.exe -B -u -X utf8 scripts\produzir_rotina.py <post-id>
```

O comando gera vídeo, capa, legenda e QA dentro de `prontos/<data>/<id>/br/`.
Ele valida o intervalo de 30–60 segundos, a composição das camadas, o tempo de
leitura, 1080x1920/H.264/AAC/30 fps, todos os quadros e a presença de áudio.
As imagens de revisão e `validacao.json` ficam na subpasta `qa/`.
O campo `visual_review` começa em `false`: somente marcar depois de abrir as imagens.

Para um pedido explícito em inglês, acrescente `--lang en`. Isso não muda o padrão PT.
O script não pesquisa ou inventa o texto: a apuração e a redação ficam com o agente.
Não usa API de redação, conectores de publicação nem credenciais para renderizar.

As dependências, FFmpeg, música e modelos/cache locais precisam existir. Em outro
computador, restaure os arquivos locais autorizados e instale `requirements.txt`.
As faixas de música, segredos, modelos e cache não devem ir ao GitHub.
Veja também [como continuar em outra conta](CONTINUAR-EM-OUTRA-CONTA.md) e
[as melhorias de transição](TRANSICOES.md).

## Radar no GitHub

O workflow `.github/workflows/radar.yml` pesquisa apenas feeds públicos às 15h e
21h UTC (11h e 17h de Cuiabá), sem API de redação, músicas ou notificações externas.
Ele atualiza `state/radar.json` e `prontos/RADAR.md`. A geração e revisão dos vídeos
ficam na rotina local. O agendamento do Actions depende de o workflow estar no
branch padrão e de o Actions estar habilitado; pode haver atrasos de execução.

A versão desta rotina está no branch `codex/gta-rotina-2026-10-12`. O agendamento
local já foi criado no aplicativo. O workflow do GitHub fica preparado nesse branch;
sua agenda de feeds só será ativada se for integrado ao branch padrão `main`.
