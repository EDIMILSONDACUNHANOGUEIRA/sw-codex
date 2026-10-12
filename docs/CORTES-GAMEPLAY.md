# Cortes de gameplay por link

O Leonida Studio agora separa gameplays longas em um vídeo horizontal de até **11 minutos** e
cortes verticais de **30 a 60 segundos** para TikTok e YouTube Shorts. O padrão é **três shorts
de 45 segundos**, português e **@leonidawirebrz**. Uma fonte de 30 minutos ou mais é aceita;
30 minutos não é um limite máximo de entrada. A duração, o download e a resolução da fonte
determinam o tempo de processamento e o espaço necessário.

## Pelo aplicativo

1. Abra `python -m leonida serve` e a aba **Gameplay**.
2. Cole o link do vídeo, título e crédito. Escolha a duração máxima do vídeo longo e dos shorts.
3. Clique **Analisar**. O app mostra os timestamps propostos e um storyboard de quadros reais.
4. Confira a gameplay fonte nos timestamps. Ajuste início, fim e título e selecione os momentos.
   Preserve o começo e o desfecho da ação; não escreva um título que o trecho não demonstra.
5. Clique **Gerar vídeos**. Baixe o MP4 horizontal, os verticais, as capas e as legendas de publicação.

Os resultados e os planos ficam em `prontos/gameplay/<projeto>/`. Cada nova exportação cria uma
versão em `exports/`, preservando as anteriores. O histórico local aparece na aba Gameplay.
Nada é enviado nem publicado automaticamente nas redes.

## Pelo terminal ou pelo Codex

```powershell
python -m leonida gameplay "URL" --titulo "Melhores momentos da gameplay" --credito "Canal fonte"
```

O comando informa o ID do projeto. Revise `plan.json` e `storyboard.jpg` e então exporte:

```powershell
python -m leonida gameplay "ID-DO-PROJETO" --render
# Plano editado em outro arquivo (a fonte original deve permanecer igual):
python -m leonida gameplay "ID-DO-PROJETO" --render --plano "plano-revisado.json"
```

Também funciona com um arquivo local no lugar do link. Para analisar e exportar de uma vez,
use `--gerar`; a revisão do conteúdo continua necessária antes da publicação.

Opções: `--minutos 11`, `--shorts 3`, `--segundos 45`, `--lang en` **somente quando você pedir inglês**,
`--legendas` para transcrever a fala com `faster-whisper` instalado e `--sem-musica`
para manter apenas o áudio original. Sem essa opção, o tema local de GTA VI deve estar configurado.
Não se baixa uma faixa aleatória. A fala da fonte permanece no idioma original; mudar o idioma
das artes não faz dublagem automática.

Para apontar momentos específicos, crie um JSON e passe `--marcadores momentos.json`:

```json
[
  {"start": "00:04:10", "end": "00:05:20", "title": "Título que descreve a ação"},
  {"start": "00:18:00", "end": "00:18:45", "title": "Outro momento da gameplay"}
]
```

## Edição e seleção

A análise local usa amostras visuais pequenas e variações de áudio para encontrar candidatos
com atividade, incluindo contexto antes e depois do pico. Evita sobreposição no vídeo longo e
distribui as sugestões pela fonte. Esses sinais podem destacar explosões, perseguições ou reações,
mas também menus animados ou ruído: **não reconhecem sozinhos a história nem garantem viralização**.
O storyboard e o plano existem para revisar essas escolhas. Marcadores humanos têm prioridade.

A exportação usa cortes discretos, fades curtos de áudio, a identidade Leonida Wire e o áudio
original com o tema abaixo. No horizontal, a gameplay permanece inteira; no vertical, uma janela
preserva o HUD, com fundo desfocado e textos fora da ação. As capas usam quadros reais da própria
fonte, sem gerar ou reconstruir rostos. Não invente que um vídeo é GTA VI apenas pelo título do link:
confira a origem e o jogo antes de entregar.

O motor usa Python, NumPy, Pillow, FFmpeg e yt-dlp já presentes no projeto. Sem modelo de
interpolação de movimento obrigatório ou upload do vídeo para análise externa.
Referências técnicas: [filtros FFmpeg](https://ffmpeg.org/ffmpeg-filters.html) e
[yt-dlp](https://github.com/yt-dlp/yt-dlp#usage-and-options).

## Verificação e continuidade

Cada exportação verifica duração, resolução, codecs, áudio e decodificação real dos arquivos.
O pacote inclui prévias e relatório técnico. Isso não comprova que o trecho seja engraçado,
verdadeiro ou adequado ao público; o conteúdo e as capas precisam de revisão visual.

Em outra conta, abra esta mesma pasta ou clone a branch de trabalho e leia este documento.
Código, fontes e instruções são portáveis; `.venv`, cache, vídeos fonte, músicas, modelos e
credenciais ficam locais. Nunca versione cookies, `.env`, vídeos de terceiros ou dados pessoais.
Se um site impedir o download, envie o arquivo original que você tem disponível.
