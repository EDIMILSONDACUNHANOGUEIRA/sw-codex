# Transições suaves e renderização leve

O estilo `v2` usa dissoluções de **0,50 s (15 quadros a 30 fps)** entre as páginas.
A manchete seguinte começa a aparecer dentro da troca. A página anterior mantém
o texto até a dissolução, evitando o intervalo de fundo vazio que havia entre
a saída dos itens e a entrada da próxima manchete.

A curva senoidal começa e termina com velocidade zero. A troca não aplica flash,
borrão horizontal ou ampliação abrupta. Logo, contador e assinatura são compostos
uma vez por quadro e permanecem estáveis. A câmera da imagem foi reduzida para
2,5%, com retorno gradual de 1 s à arte original. O pulso musical tem ataque e
retorno suaves, limitado a 0,4% de escala; imagem e personagem usam a mesma câmera.
Entradas de linhas e itens usam aceleração cúbica suave e deslocamentos menores.

O motor continua com Pillow, NumPy e FFmpeg já usados pelo projeto. Não exige
GPU, navegador, modelos de interpolação, MoviePy ou uma nova instalação. A mistura
da troca usa `Image.blend`, sem arrays de ponto flutuante do tamanho do vídeo.
O H.264 continua em 1080 × 1920, 30 fps, CRF 18, preset `veryfast` e quatro threads.

## Duração e validação

`video_segundos` continua sendo a duração exata. O planejamento reserva pelo menos
2,5 s para leitura de uma lista depois que todos os itens entram. Uma duração
insuficiente falha antes da renderização e preserva o vídeo anterior. O primeiro
e último quadros continuam idênticos à composição da capa. Não é preciso aumentar
a duração para incluir as dissoluções, pois a agenda considera a sobreposição.

Validação focada: `python -m unittest tests.test_motion -v`. Há verificações dos
extremos e continuidade da troca, ausência de flashes/quadros vazios, manchete
presente durante a troca, HUD estável, área segura, pulso contínuo, loops de
30/40/60 s e leitura mínima. O teste de integração também codifica um pequeno
vídeo com áudio sintético e confere duração, H.264, AAC e fades de áudio.
A revisão visual de cada vídeo real permanece necessária antes de entregar.

## Referências consultadas

- [FFmpeg no GitHub](https://github.com/FFmpeg/FFmpeg), filtros
  [xfade](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_xfade.c) e
  [documentação de xfade](https://ffmpeg.org/ffmpeg-filters.html#xfade): referências
  para mistura entre quadros. O executável já presente continua fazendo o encode;
  nenhum código C foi copiado. A licença base é LGPL 2.1 ou posterior, com partes
  opcionais GPL; a licença efetiva depende do build instalado
  ([referência oficial](https://ffmpeg.org/legal.html)).
- [gl-transitions](https://github.com/gl-transitions/gl-transitions),
  [fade.glsl](https://github.com/gl-transitions/gl-transitions/blob/master/transitions/fade.glsl):
  referência visual de crossfade, de gre, sob MIT. Não foi copiado um shader nem
  incorporado um runtime WebGL; a implementação usa o blend do Pillow e easing
  já disponível no motor.
- [minterpolate no FFmpeg](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_minterpolate.c)
  e [documentação](https://ffmpeg.org/ffmpeg-filters.html#minterpolate): interpolação
  disponível para futuros trechos reais. As páginas atuais são animadas diretamente
  em 30 fps e não precisam desse processamento adicional. Slow motion de footage
  deve ser usado em trechos curtos; repetir quadros é barato, e compensação de
  movimento custa mais CPU e requer revisão de artefatos. Nenhum modelo pesado de
  interpolação foi instalado nem slow motion aplicado à música ou aos textos.
