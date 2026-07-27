# Fase 8: registra una tarea diaria en el Task Scheduler de Windows que
# corre el pipeline de scraping (src/db/run_pipeline.py).
#
# Uso: ejecutar una vez, a mano, desde una consola normal:
#   powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1
#
# Para desregistrarla: Unregister-ScheduledTask -TaskName "PokemonChampionsPipeline"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "No se encontro $Python -- crea antes el venv (.venv) del proyecto."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m src.db.run_pipeline" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "09:00"

Register-ScheduledTask -TaskName "PokemonChampionsPipeline" -Action $Action -Trigger $Trigger -Force | Out-Null
Write-Host "Tarea 'PokemonChampionsPipeline' registrada: corre a diario a las 09:00 con working dir $ProjectRoot."
