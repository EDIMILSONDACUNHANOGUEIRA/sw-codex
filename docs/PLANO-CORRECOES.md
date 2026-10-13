# Plano de correções (auditoria de 13/10/2026)

Branch: `codex/gta-rotina-2026-10-12`. Ordem de trabalho: os 4 graves primeiro, depois o resto.
Ao retomar: `git pull`, ler este arquivo, continuar do primeiro item sem ✅, rodar
`pytest tests -q`, commitar e dar push a cada item concluído, marcar ✅ aqui.

## Graves

1. [✅] Radar: classificar história (oficial / confirmada / rumor / vazamento); barrar rumor e vazamento
   no `auto`, `from-story` e `story_to_post`; não fundir oficial com vazamento em `merge_by_topic`;
   "oficial" só com domínio da Rockstar/Take-Two; `_score_item` por palavra inteira; data futura/ausente.
2. [✅] Vídeo de notícia: padrão de 45 s com cena de no máx. 7 s quebra posts sem fotos extras
   (inclusive `contagem`). Ajustar a duração ao conteúdo em vez de falhar, e checar antes de renderizar.
3. [✅] Cortes: trecho sem fala sai sem legenda (não derruba a exportação); legenda desligada quando o
   reconhecimento de voz não está instalado; idioma automático por padrão.
4. [✅] Segurança dos apps locais: só aceitar Host/Origin do próprio app (CSRF / DNS rebinding);
   validar `pid`/`date`; limite e extensões no upload; `/api/thumb` sem caminho local.

## Depois

5. [✅] Cortes: cancelar job, limpar pastas órfãs/staging na inicialização, QA que reprova vídeo preto/mudo,
   títulos únicos por corte, análise mais rápida (`-skip_frame noref`; `nokey` criaria buracos na amostra de 2 s).
6. [✅] Legendas: blocos por palavra (`words[]`), duração mínima, sem sobreposição, tags de SRT removidas,
   música limitada abaixo da voz.
7. [✅] Radar: fonte real do Google News, YouTube por `channel_id`, gravação atômica do estado,
   `_clean_title` sem cortar conteúdo, testes do radar.
8. [✅] Música: validar duração/volume da faixa, ignorar `*.tmp.*`.
9. [ ] Servidor: `post.yaml` ruim não derruba a lista; job perdido não trava a tela; erros 4xx/JSON.
10. [ ] Instalação Windows: `scipy`/`httpx` no requirements, .bat espera o servidor subir.
