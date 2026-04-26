# =============================================================================
# install_autostart.ps1 -- Register AutonomusAI to start on Windows boot
# Run once as Administrator:
#   Right-click this file -> "Run with PowerShell"
# =============================================================================

$TaskName   = "AutonomusAI_WebTrader"
$BackendDir = "C:\Users\Tshepo Ayto\OneDrive\Documents\Visual studio code projects\html+css web\AutonomusAI_Web\backend"
$PythonExe  = (Get-Command python).Source
$UvicornExe = (Get-Command uvicorn -ErrorAction SilentlyContinue).Source

# Fall back to pip-installed uvicorn path
if (-not $UvicornExe) {
    $UvicornExe = "$env:APPDATA\Python\Python311\Scripts\uvicorn.exe"
}

$Action  = New-ScheduledTaskAction `
    -Execute $UvicornExe `
    -Argument "main:app --host 0.0.0.0 --port 8000" `
    -WorkingDirectory $BackendDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "✅ AutonomusAI registered as a startup task!" -ForegroundColor Green
Write-Host "   It will start automatically every time you log into Windows."
Write-Host ""
Write-Host "Manual controls:"
Write-Host "  Start:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Stop:   Stop-ScheduledTask  -TaskName '$TaskName'"
Write-Host "  Remove: Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
