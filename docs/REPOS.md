# Pesquisa de repositórios (o que usamos e por quê)

Pedido: ferramentas open-source que façam o que **HyperFrames**, **Higgsfield** e editores parecidos fazem,
para editar imagem e vídeo dos posts. Resultado da pesquisa (outubro/2026):

## Em uso no projeto

| Repositório | O que faz | Como usamos |
|---|---|---|
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) (Apache-2.0) | Framework da HeyGen que transforma HTML + GSAP em MP4 determinístico (Chrome + FFmpeg). Feito para agentes como Codex/Claude Code. | `leonida/video.py` monta uma composição HTML com as camadas da capa (fundo, palavra gigante, personagem, manchete linha a linha) e renderiza o vídeo 9:16 de 8 s. |
| [danielgatis/rembg](https://github.com/danielgatis/rembg) (MIT) | Remoção de fundo com U²-Net. | `leonida/cutout.py` recorta o personagem para o efeito "palavra atrás do personagem" + contorno neon. |
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) | O baixador de vídeos mais usado (sucessor do youtube-dl): YouTube, X, Reddit, TikTok etc. | `leonida/clips.py` baixa o vídeo dos cortes; `leonida/music.py` baixa o áudio da música tema. |
| [FFmpeg](https://ffmpeg.org) | Edição/encode de vídeo. | Cortes 9:16 (fundo desfocado + janela do vídeo + moldura), fallback de vídeo. |
| [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (BSD-3) — opcional | Upscale de imagens com IA. | `leonida/upscale.py` usa o `realesrgan-ncnn-vulkan` se estiver instalado, para fotos abaixo de 1080×1920. |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) — opcional | Transcrição rápida com timestamps por palavra. | Legenda automática estilo TikTok nos cortes (`--legendas`). |
| [python-pillow/Pillow](https://github.com/python-pillow/Pillow) + NumPy | Imagem. | Todo o motor gráfico (`gfx.py`, `render.py`): grading, gradientes, brilho neon, tipografia. |
| [kurtmckee/feedparser](https://github.com/kurtmckee/feedparser) | RSS/Atom. | Radar de notícias. |
| [GSAP](https://gsap.com) | Animação. | Timeline das animações dentro do HyperFrames. |
| Fontes Google: Anton (OFL), Inter (OFL), Yellowtail (Apache-2.0) | Tipografia. | Manchetes, texto e assinatura — em `assets/fonts/`. |

## Edição de vídeo "estilo Higgsfield" (`python -m leonida editar URL`)

O Higgsfield é conhecido pelos **presets de câmera** (crash zoom, dolly, travelling, câmera na mão,
dutch, snap zoom, câmera lenta) e pelas transições fortes. Pesquisa em out/2026:

- Os clones abertos ("Open-Higgsfield-AI": Autom8AI, Anil-matcha, absalan, forks) são só a interface;
  a geração roda na API paga do **Muapi**. Não servem para editar o seu vídeo de graça.
- Geração de vídeo com controle de câmera que roda **local** existe ([Wan2.2](https://github.com/Wan-Video/Wan2.2),
  [LTX-Video](https://github.com/Lightricks/LTX-Video)), mas cria cenas novas (não edita o trailer),
  precisa de placa de vídeo NVIDIA com 12 GB+ e leva minutos por segundo de vídeo.

Por isso o `leonida/edit.py` aplica os **mesmos movimentos de câmera do Higgsfield sobre o vídeo real**,
de forma determinística, no **HyperFrames** (GSAP anima a "câmera" sobre cada trecho):

| Preset | O que faz |
|---|---|
| `push_in` / `pull_out` | dolly in / dolly out |
| `snap_zoom` | entra com zoom rápido e desfoque de movimento |
| `crash_zoom` | segura e dá um zoom violento no fim do plano (emenda com o próximo corte) |
| `truck_left` / `truck_right` / `tilt_up` | travelling lateral / vertical |
| `handheld` | câmera na mão (oscilação suave) |
| `dutch` | câmera inclinada girando |
| `impact` | tremida curta de impacto + push |
| `slowmo` | câmera lenta (0,5×) |
| transições | `whip` (chicote com desfoque), `zoom` (zoom-through), `flash`, `corte` |

Outras peças: detecção de cena do FFmpeg (onde cortar), rembg para reenquadrar 9:16 no personagem,
grão de filme animado e grade de cor no acabamento.

## Avaliados (opcionais / para o futuro)

| Repositório | Observação |
|---|---|
| [Anil-matcha/Open-Higgsfield-AI](https://github.com/Anil-matcha/Open-Higgsfield-AI) (MIT) | Interface aberta parecida com o Higgsfield (text-to-image, image-to-video, lip sync). A geração roda via API paga (Muapi). Útil só para criar b-roll novo com IA. |
| [Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2) / [Lightricks/LTX-Video](https://github.com/Lightricks/LTX-Video) | Geração de vídeo local com controle de câmera. Precisa de GPU NVIDIA forte; cria cena nova, não edita o vídeo. |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | Vídeo em React. Ótimo, mas licença paga para empresas; HyperFrames cobre o caso. |
| [mifi/editly](https://github.com/mifi/editly) | Edição declarativa sobre FFmpeg. |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | Edição de vídeo em Python. |
| [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) | Pipelines de IA (upscale, inpainting). Pesado; precisa de GPU. |

## Fontes de notícia monitoradas

IGN, IGN Brasil, Flow Games, TecMundo/Voxel, GameSpot, Game Informer, Kotaku, Eurogamer, PC Gamer,
Push Square, Insider Gaming, Polygon, TheGamer, Google Notícias (BR e US), Reddit r/GTA6 (hot e top do dia),
YouTube da Rockstar e a página oficial da Rockstar. Edite em `config/sources.yaml`.
