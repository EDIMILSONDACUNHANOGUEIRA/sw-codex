# Agenda o radar automático no Agendador de Tarefas do Windows (a cada 1 hora)
# e o post de contagem regressiva todo dia às 08:00.
# Uso (PowerShell, na pasta do projeto):  powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$radar = New-ScheduledTaskAction -Execute $py -Argument "-m leonida auto --min-score 110 --max 3" -WorkingDirectory $root
$radarTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "LeonidaRadar" -Action $radar -Trigger $radarTrigger -Force | Out-Null

$count = New-ScheduledTaskAction -Execute $py -Argument "-m leonida contagem --enviar" -WorkingDirectory $root
$countTrigger = New-ScheduledTaskTrigger -Daily -At 8am
Register-ScheduledTask -TaskName "LeonidaContagem" -Action $count -Trigger $countTrigger -Force | Out-Null

Write-Host "Pronto: tarefas 'LeonidaRadar' (1/1h) e 'LeonidaContagem' (08:00) criadas."
Write-Host "Defina TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (e ANTHROPIC_API_KEY, se quiser redação automática)"
Write-Host "nas variáveis de ambiente do Windows para receber os posts no celular."
