# Continuar o Leonida Studio em outra conta do Codex

O repositório é [EDIMILSONDACUNHANOGUEIRA/sw-codex](https://github.com/EDIMILSONDACUNHANOGUEIRA/sw-codex).
O código, as regras, os prompts e o histórico podem ser retomados em outra conta abrindo o mesmo
checkout. A mudança de conta não transfere automaticamente este chat, a rotina agendada, as
permissões nem as conexões dos serviços. Não há garantia de continuidade enquanto a conta ou
o serviço estiver indisponível. Os arquivos locais permanecem independentes do histórico do chat.

## Antes de trocar a conta

1. Confira `git status` e preserve alterações existentes. Confirme que a versão atual está no
   repositório/branch que pretende abrir. Só considere uma sincronização concluída depois de
   verificar o push; um arquivo local novo ainda não existe no GitHub.
2. Preserve `posts/`, `state/seen.json` e `state/publicados.json` para evitar repetir notícias.
   `seen.json` guarda IDs, títulos e tokens; o radar também compara títulos parecidos por um período
   limitado. Por isso a comparação com todo o histórico dos `post.yaml` continua necessária.
   Não confunda entregue com publicado e não apague o histórico ao trocar de conta.
3. Mantenha os vídeos entregues em `prontos/` e os pacotes locais de saída. Preserve as faixas
   autorizadas de `assets/music/`, o cache e o ambiente virtual no PC: eles são ignorados pelo Git.
   Um clone novo exige recriar dependências, mas abrir o mesmo checkout pode reutilizá-las.
4. Não versionar nem compartilhar `.env`, chaves, senhas, tokens, cookies ou arquivos pessoais.
   Se uma integração opcional for necessária, configure-a localmente pela conta nova sem expor
   as credenciais em prompts, logs ou documentação.

## Na conta nova

1. Abra o mesmo aplicativo Codex e adicione/abra a pasta deste repositório. Se usar outro computador,
   clone o repositório e escolha o branch com a versão atual. O branch deste checkout é
   `claude/gta6-content-automation-app-bubnzu`; confira se ele ainda é o branch adequado.
2. Peça ao agente para ler `AGENTS.md`, `docs/PROMPT-DIARIO.md`, `docs/AUTOMACAO-GTA.md`,
   `config/brand.yaml`, `config/sources.yaml` e o histórico em `posts/` e `state/`.
3. Recrie a rotina na conta nova para **11h e 17h, America/Cuiaba**, usando o prompt de
   `docs/AUTOMACAO-GTA.md`. A presença do prompt no GitHub não ativa o agendamento. Confira a
   rotina na interface e faça uma execução de teste. Para evitar duplicidade, mantenha apenas
   uma rotina ativa para esta pasta; pause a antiga quando a substituta estiver pronta.
4. Verifique Python/dependências, FFmpeg/ffprobe, música local e permissões de acesso. Se faltar
   algo, o agente deve informar a pendência e preservar os arquivos anteriores. Não considere uma
   pesquisa sem acesso às fontes, nem um render interrompido, como execução bem sucedida.

Prompt curto para iniciar na conta nova:

```text
Continue o Leonida Studio neste repositório. Leia AGENTS.md, docs/PROMPT-DIARIO.md e
docs/AUTOMACAO-GTA.md e preserve os arquivos e o histórico existentes. Configure uma rotina
neste chat às 11h e 17h, America/Cuiaba, para pesquisar notícias novas verificadas de GTA VI
e da franquia GTA. Produza até dois vídeos de 30–60 segundos por rodada, padrão 45 segundos,
em português do Brasil. Inglês somente quando eu pedir explicitamente. Entregue os vídeos,
capas e legendas aqui para eu publicar no TikTok e YouTube Shorts. Não publique, agende nas
redes nem faça deploy automaticamente. Confira a rotina criada e avise qualquer pendência.
Sem novidade relevante, fique quieto. Compare sempre com posts/ e state/ para evitar repetição.
```

## Arquivos que mantêm as preferências

| Arquivo | Conteúdo a preservar |
|---|---|
| `AGENTS.md` | Regras editoriais, segurança, idioma e revisão |
| `config/brand.yaml` | Marca, português padrão e duração padrão de 45 segundos |
| `config/sources.yaml` | Feeds e termos de busca de GTA |
| `docs/AUTOMACAO-GTA.md` | Prompt e referência do agendamento a recriar |
| `docs/PROMPT-DIARIO.md` | Fluxo da pesquisa, produção e entrega |
| `posts/*/post.yaml` | Temas, fontes e versões já produzidas |
| `state/seen.json` | Histórias já vistas/entregues e descarte |
| `state/publicados.json` | Registro de publicação real, quando houver |

Notícias descobertas em fontes inglesas também são redigidas em português. O pedido explícito de
um vídeo em inglês vale para aquela entrega; não muda o padrão dos vídeos seguintes. A rotina
prepara arquivos compatíveis com TikTok e Shorts, sem depender de conectores de publicação.
