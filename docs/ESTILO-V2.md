# Validação do estilo v2

O motor e a identidade visual implementados pelo Claude foram mantidos. Esta
revisão corrige duração, leitura, margens e preservação das entregas existentes.
O vídeo usa Pillow/NumPy e FFmpeg; não depende de Chrome ou de chaves de API.

```powershell
python -m leonida musica --listar
python -m leonida build 2026-10-11-gta6-classificacao-18-anos --sem-video
```

`--sem-video` pula apenas a antiga capa HyperFrames dos estilos legados. O arquivo
`br/tiktok/post.mp4` contém a sequência completa, com a música tema obrigatória.
`config/brand.yaml → video.estilo_padrao` define o padrão; `estilo` do post tem
prioridade. `build --estilo v2|dinamico|classico` permite validar um motor sem
alterar o conteúdo editorial do YAML.

## Duração e leitura

`video_segundos` é a duração exata a 30 fps. O padrão é 20 segundos, configurável
em `video.segundos`. Antes desta revisão, o motor podia encurtar ou estender esse
alvo. Agora, conteúdo que não cabe com tempo suficiente para leitura gera erro;
nenhum item é omitido. Nesse caso, aumente a duração ou distribua o conteúdo.

Listas entram em intervalos de 0,45–0,7 s. Batidas detectadas na mesma faixa e
trecho do encode podem deslocar entradas e trocas em até 0,25 s, respeitando as
reservas. A lista completa permanece pelo menos 2,5 s antes da saída de 0,25 s.

O zoom punch escala as camadas de mídia. Textos mantêm suas margens, começam a
entrar depois do whip e saem antes da transição. O contador dá seu pop mantendo
a borda direita. O ponto ao vivo continua piscando.

## Composição e saída

O acabamento fotográfico é calculado uma vez no fundo. PNG, JPEG e vídeo usam
as mesmas camadas, sem aplicar grão ou halação novamente sobre a composição.
A câmera retorna suavemente ao enquadramento da arte e segura a composição
completa por 0,15 s antes da saída dos textos. Esse último trecho legível tem
pixels idênticos ao PNG; depois vêm a saída de 0,25 s e a transição de 0,4 s.

Primeiro e último quadros fonte são idênticos. H.264 usa compressão com perdas,
então os quadros decodificados podem diferir ligeiramente. O encode usa H.264
High, CRF 18, 1080×1920, 30 fps, cores BT.709, AAC e `+faststart`, com fades
de áudio de 0,5 s. Quatro threads e `veryfast` limitam memória e tempo.

O build completo é preparado em uma pasta temporária. Só substitui a entrega
anterior após sucesso; falhas de vídeo ou música são propagadas nos três estilos.
O encoder usa temporários exclusivos e preserva o MP4 anterior em caso de erro.
Execute em série para o mesmo post, inclusive entre o app e a linha de comando.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes verificam composição, nomes que não devem quebrar linha, zonas seguras,
tempo de leitura, batidas, loop, metadados e fades de um encode real pequeno,
além da preservação dos arquivos em falhas. Imagens e áudio sintéticos existem
somente nas pastas temporárias dos testes; nunca viram posts.
