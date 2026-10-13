# Abre o app no navegador só depois de o servidor responder (até 60 s).
# Usado pelos .bat: o servidor fica na janela principal e este script roda em segundo plano.
param([Parameter(Mandatory = $true)][string]$Url)
$status = $Url.TrimEnd('/') + '/api/status'
for ($i = 0; $i -lt 120; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $status | Out-Null
        Start-Process $Url
        exit 0
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
Write-Host "O servidor nao respondeu em 60 s. Veja a mensagem de erro nesta janela."
exit 1
