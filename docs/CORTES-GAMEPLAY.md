# Cortes de gameplay por link

O Leonida Studio agora separa gameplays longas em um vídeo horizontal de até **11 minutos** e
cortes verticais de **30 a 60 segundos** para TikTok e YouTube Shorts. O padrão é **três shorts
de 45 segundos**, português e **@leonidawirebrz**. Uma fonte de 30 minutos ou mais é aceita;
30 minutos não é um limite máximo de entrada. A duração, o download e a resolução da fonte
determinam o tempo de processamento e o espaço necessário.

## Pelo aplicativo

1. Abra **Leonida Cortes** com `scripts/abrir-gameplay.bat`: <http://127.0.0.1:8769/>.
   Pelo terminal, na raiz do repositório:

   ```powershell
   .venv\Scripts\python.exe -m uvicorn apps.gameplay.app:app --host 127.0.0.1 --port 8769
   ```
2. Cole o link ou escolha um vídeo do computador, título e crédito. Escolha a duração máxima
   do vídeo longo e dos shorts. O formulário aceita arquivos de até 20 GB. Selecione também
   **Tema de GTA VI**, **Sem música adicional** ou **Outra música** e o volume; essa escolha
   pode ser ajustada na revisão, antes da exportação.
3. Clique **Analisar**. O app mostra os timestamps propostos e um storyboard de quadros reais.
4. Confira a gameplay fonte nos timestamps. Ajuste início, fim e título e selecione os momentos.
   Preserve o começo e o desfecho da ação; não escreva um título que o trecho não demonstra.
5. Mantenha **Legendar a voz do criador** ativado. Confira o idioma da fala e, se tiver um SRT
   revisado, cole-o na opção **Usar legendas revisadas do criador**. Os tempos são da fonte original.
6. Clique **Gerar vídeos e capas**. Baixe o MP4 horizontal, os verticais, as capas, o SRT da fala
   e o texto de publicação. Revise a fala legendada e o vídeo antes de publicar.

Os resultados e os planos do app ficam em `apps/gameplay/prontos/<projeto>/`. Cada nova
exportação cria uma versão em `exports/`, preservando as anteriores. Os arquivos escolhidos
no formulário ficam em `apps/gameplay/uploads/`; revisões manuais podem ficar em
`apps/gameplay/prontos/revisoes/`. Essas pastas são locais e ignoradas pelo Git. O botão
**Projetos salvos** mostra o histórico do app. Nada é publicado automaticamente nas redes.

As notícias diárias usam **Leonida Notícias**, `apps/noticias/`, porta **8768** e
`scripts/abrir-noticias.bat`. Elas continuam com `posts/`, `state/` e `prontos/<data>/`.
Projetos antigos em `prontos/gameplay/` e vídeos já entregues permanecem nos caminhos originais.
Para usar outro disco, defina `LEONIDA_GAMEPLAY_HOME` para projetos/exports e
`LEONIDA_GAMEPLAY_UPLOADS` para fontes antes de iniciar o Cortes.

## Pelo terminal ou pelo Codex

```powershell
python -m leonida gameplay "URL" --titulo "Melhores momentos da gameplay" --credito "Canal fonte"
```

O comando informa o ID do projeto. Revise `plan.json` e `storyboard.jpg` e então exporte:

```powershell
python -m leonida gameplay "ID-DO-PROJETO" --render --legendas --idioma-fala pt
# Plano editado em outro arquivo (a fonte original deve permanecer igual):
python -m leonida gameplay "ID-DO-PROJETO" --render --plano "plano-revisado.json" --legendas
# Texto corrigido com os tempos da fonte; substitui a transcrição automática:
python -m leonida gameplay "ID-DO-PROJETO" --render --legendas --srt-fala "fala-revisada.srt"
```

Também funciona com um arquivo local no lugar do link. Para analisar e exportar de uma vez,
use `--gerar`; a revisão do conteúdo continua necessária antes da publicação.

O CLI mantém `prontos/gameplay/` quando `LEONIDA_GAMEPLAY_HOME` não está definido. Para usar
as mesmas pastas do app em uma sessão do terminal:

```powershell
$env:LEONIDA_GAMEPLAY_HOME = Join-Path (Get-Location) 'apps\gameplay\prontos'
```

Opções: `--minutos 11`, `--shorts 3`, `--segundos 45`, `--lang en` **somente quando você pedir inglês**,
`--legendas` para transcrever a fala com o reconhecimento local configurado. A fala da fonte permanece no idioma original; mudar o idioma
das artes não faz dublagem automática.

No CLI legado, `--legendas` é necessário para ativar as legendas. `--idioma-fala pt|auto|en`
seleciona o idioma do reconhecimento, e `--srt-fala arquivo.srt` usa o texto revisado em vez do
modelo. No app, as legendas estão ativadas por padrão.

Para escolher a música pelo CLI, use `--musica tema|nenhuma|outra` e `--volume-musica 10`
(0–100%). **Outra** exige `--arquivo-musica caminho`; esse argumento só é válido com
`--musica outra`. A opção legada `--sem-musica` equivale a `--musica nenhuma` e não pode
ser combinada com uma escolha conflitante.

```powershell
python -m leonida gameplay "ID-DO-PROJETO" --render --legendas --musica tema --volume-musica 10
python -m leonida gameplay "ID-DO-PROJETO" --render --legendas --musica nenhuma
python -m leonida gameplay "ID-DO-PROJETO" --render --legendas --musica outra --arquivo-musica "minha-faixa.mp3" --volume-musica 10
```

Para apontar momentos específicos, crie um JSON e passe `--marcadores momentos.json`:

```json
[
  {"start": "00:04:10", "end": "00:05:20", "title": "Título que descreve a ação"},
  {"start": "00:18:00", "end": "00:18:45", "title": "Outro momento da gameplay"}
]
```

## Música dos cortes

A importação e a revisão oferecem três escolhas: **Tema de GTA VI**, usando a faixa local
configurada; **Sem música adicional**; ou **Outra música**, usando um arquivo escolhido pelo
usuário. O upload aceita **MP3, WAV, M4A, AAC, FLAC e OGG**, com limite de **512 MB**. A escolha
é aplicada ao vídeo exportado, tanto horizontal quanto vertical.

O som original da gameplay e a voz do criador permanecem. Quando uma faixa adicional é escolhida,
ela é misturada por baixo, com volume ajustável de **0 a 100%**, padrão **10%**, e redução durante
a fala. Confira a mixagem no vídeo final. Se a opção for tema, a faixa local precisa estar
configurada; outra música usa o arquivo escolhido, sem substituir por uma faixa aleatória.

**Sem música adicional** conserva todo o áudio da fonte, inclusive música que já esteja gravada
nele. Essa opção não remove uma trilha já misturada com voz ou som do jogo; o editor não separa
essas faixas. A regra de música tema das notícias diárias continua independente desta escolha.

## Legendas da fala

O Cortes usa o **áudio original antes de acrescentar a música**. Isso inclui o comentário de quem
está jogando, mesmo fora da câmera. OCR ou a legenda que já aparece na imagem do jogo não
substituem essa transcrição. O idioma da fala é separado do idioma da capa: o padrão é português,
com opção de detecção automática ou inglês. Essa seleção não traduz nem dubla a voz.

O modelo reconhece a mistura de áudio existente. Quando criador e personagens falam juntos,
ou há vozes em idiomas diferentes, ele pode omitir ou trocar palavras; não há separação perfeita
dos falantes. Confira a transcrição nos trechos de fala. As exportações guardam `legendas.json`,
`legendas.srt` e `legendas.ass`, além do texto da publicação em arquivo próprio.

Um **SRT revisado do criador** substitui a transcrição automática. Use os tempos do vídeo original;
o exportador ajusta as falas aos momentos selecionados. Com esse SRT, não é necessário executar
o reconhecimento. Não complete uma palavra incerta por suposição. Se o modelo estiver indisponível,
o app informa a pendência; forneça um SRT revisado ou configure as dependências abaixo.

No Windows, use Python **3.12** para as dependências opcionais de reconhecimento. Se o ambiente
principal já usa essa versão, basta `python -m pip install -r requirements-speech.txt`. Caso use
outro Python, crie um ambiente local separado, ignorado pelo Git:

```powershell
py -3.12 -m venv .cache\speech\runtime
.cache\speech\runtime\Scripts\python.exe -m pip install -r requirements-speech.txt
$env:LEONIDA_STT_PYTHON = (Resolve-Path '.cache\speech\runtime\Scripts\python.exe').Path
scripts\abrir-gameplay.bat
```

`LEONIDA_STT_DEPS` só é necessário se os pacotes forem instalados em uma pasta com `pip --target`.
`LEONIDA_STT_MODELS` permite escolher a pasta local dos modelos. O primeiro uso pode baixar o
modelo; o vídeo e o áudio são processados no computador. Para usar `LEONIDA_STT_OFFLINE=1`, o
modelo escolhido deve estar disponível no cache. Modelos, cache e fontes não entram no GitHub.

## Edição e seleção

A análise local usa amostras visuais pequenas e variações de áudio para encontrar candidatos
com atividade, incluindo contexto antes e depois do pico. Evita sobreposição no vídeo longo e
distribui as sugestões pela fonte. Esses sinais podem destacar explosões, perseguições ou reações,
mas também menus animados ou ruído: **não reconhecem sozinhos a história nem garantem viralização**.
O storyboard e o plano existem para revisar essas escolhas. Marcadores humanos têm prioridade.

A exportação usa cortes discretos, fades curtos de áudio, a identidade Leonida Wire e o áudio
original com a música adicional escolhida, quando houver. No horizontal, a gameplay permanece inteira; no vertical, uma janela
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
