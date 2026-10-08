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

## Avaliados (opcionais / para o futuro)

| Repositório | Observação |
|---|---|
| [Anil-matcha/Open-Higgsfield-AI](https://github.com/Anil-matcha/Open-Higgsfield-AI) (MIT) | Alternativa open-source ao Higgsfield: estúdio de imagem/vídeo com IA (text-to-image, image-to-video, lip sync). A geração roda via API paga (Muapi) — útil se quiser criar b-rolls/thumbnails com IA. Não é necessário para notícias (usamos imagens oficiais). |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | Vídeo em React. Ótimo, mas licença paga para empresas; HyperFrames cobre o caso. |
| [mifi/editly](https://github.com/mifi/editly) | Edição declarativa sobre FFmpeg. |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | Edição de vídeo em Python. |
| [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) | Pipelines de IA (upscale, inpainting). Pesado; precisa de GPU. |

## Fontes de notícia monitoradas

IGN, IGN Brasil, Flow Games, TecMundo/Voxel, GameSpot, Game Informer, Kotaku, Eurogamer, PC Gamer,
Push Square, Insider Gaming, Polygon, TheGamer, Google Notícias (BR e US), Reddit r/GTA6 (hot e top do dia),
YouTube da Rockstar e a página oficial da Rockstar. Edite em `config/sources.yaml`.
