# Leonida Notícias

Aplicativo das notícias diárias de GTA VI e da franquia GTA. Mantém o radar, os
rascunhos, a biblioteca e as entregas existentes. Não oferece os projetos de gameplay.

No Windows, abra `scripts/abrir-noticias.bat`, ou execute da raiz:

```powershell
.venv\Scripts\python.exe -m uvicorn apps.noticias.app:app --host 127.0.0.1 --port 8768
```

Endereço: <http://127.0.0.1:8768/>. Se uma versão anterior já estiver usando a porta,
feche o servidor anterior pelo terminal antes de abrir este; o script não encerra
outros processos.

Os rascunhos continuam em `posts/`, o histórico em `state/` e os vídeos de notícias
em `prontos/<data>/`. A rotina de pesquisa às 11h e 17h de Cuiabá permanece separada
do editor de cortes. Os arquivos são entregues localmente para publicação manual.

O segundo aplicativo está em [`../gameplay/`](../gameplay/), com porta e saídas próprias.
