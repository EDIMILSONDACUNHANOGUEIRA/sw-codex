# Leonida Cortes

Aplicativo de gameplay: recebe um link ou arquivo de vídeo, sugere momentos,
permite revisar os intervalos e gera vídeo horizontal de até 11 minutos e shorts
de 30–60 segundos. Não carrega o radar, os rascunhos ou o histórico de notícias.

No Windows, abra `scripts/abrir-gameplay.bat`, ou execute da raiz:

```powershell
.venv\Scripts\python.exe -m uvicorn apps.gameplay.app:app --host 127.0.0.1 --port 8769
```

Endereço: <http://127.0.0.1:8769/>. O conteúdo permanece no computador:

- `apps/gameplay/uploads/`: arquivos enviados pelo formulário; nomes internos únicos.
- `apps/gameplay/prontos/<projeto>/`: plano, storyboard e exports versionados.
- `apps/gameplay/prontos/revisoes/`: revisões manuais de vídeos já entregues.

Essas pastas não entram no GitHub. Não há publicação automática. Os projetos antigos
em `prontos/gameplay/` e as entregas anteriores permanecem nos caminhos originais.

Escolha **Tema do GTA 6**, **Sem música adicional** ou **Outra música** no formulário.
Outra música é um arquivo de áudio enviado por você (até 512 MB), aplicado aos
vídeos exportados com volume ajustável de 0 a 100% (padrão 10%). O som original
permanece, e a trilha adicional reduz o volume durante as falas. Sem música adicional
mantém também qualquer música que já esteja gravada no áudio da fonte.

A seção **Vídeos revisados prontos** permite baixar as revisões manuais, com
vídeo, capa, SRT e texto para publicação. Guia completo: [Cortes de gameplay](../../docs/CORTES-GAMEPLAY.md).

Para outro disco, defina `LEONIDA_GAMEPLAY_HOME` (projetos/exports) e, se necessário,
`LEONIDA_GAMEPLAY_UPLOADS` (fontes) antes de iniciar o app. Isso não altera a pasta
de saída das notícias. O CLI legado mantém os caminhos anteriores quando essa
variável não é definida.

As legendas de fala precisam transcrever o áudio do narrador/comentarista, inclusive
quando ele está fora da câmera; o texto mostrado pelo jogo não substitui a fala.
O formulário oferece idioma da fala e SRT revisado. Preserve a voz original e revise
o texto antes da entrega. Sem transcrição disponível, a exportação deve informar a
pendência em vez de dizer que o comentarista foi legendado.

O app aceita uploads até 20 GB. O formato e a duração são conferidos na análise.
Um link bloqueado pelo serviço pode ser substituído pelo MP4 autorizado do usuário.
As sugestões por áudio/movimento exigem revisão do contexto e não garantem viralização.
