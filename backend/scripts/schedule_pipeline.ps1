# Register the whole Newseye pipeline as one Windows scheduled task: collect and
# group (passive tier), compare (active tier), and once a day the people pages
# (backend/pipeline.py). It replaces Newseye-Passive, which ran the first part only
# and left new stories uncompared.
#
#   powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_pipeline.ps1           # registered, switched off
#   powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_pipeline.ps1 -Enable   # registered and running
#
# Switching it on adds new articles to the database, which changes every count
# taken from it since 27 October 2026. It is registered switched off for that reason.
#
# Switch on later: Enable-ScheduledTask -TaskName Newseye-Pipeline
# Run once now:    Start-ScheduledTask -TaskName Newseye-Pipeline
# Check on it:     Get-ScheduledTaskInfo -TaskName Newseye-Pipeline
# Watch it:        Get-Content logs\pipeline.log -Wait -Tail 30
# Remove:          Unregister-ScheduledTask -TaskName Newseye-Pipeline -Confirm:$false
param([switch]$Enable)

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# pythonw.exe: no console window every two hours (see schedule_ingestion.ps1)
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $python)) { throw "python not found at $python" }
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
if (-not $env:DB_PASSWORD -and -not [Environment]::GetEnvironmentVariable("DB_PASSWORD", "User")) {
    Write-Warning "DB_PASSWORD is not set for this user: the task will find the database unreachable"
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m backend.pipeline --log `"$logDir\pipeline.log`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours 2)

# Priority 4 and the battery settings: see schedule_ingestion.ps1. The time limit
# is just under the interval; the pipeline's own lock also stops a late run from
# overlapping the next.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -Priority 4 `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1 -Minutes 50)

Register-ScheduledTask -TaskName "Newseye-Pipeline" -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Newseye: collect, group, compare, and daily people pages" `
    -Force | Out-Null

# never both: the old task would collect without comparing
if (Get-ScheduledTask -TaskName "Newseye-Passive" -ErrorAction SilentlyContinue) {
    Disable-ScheduledTask -TaskName "Newseye-Passive" | Out-Null
}

if ($Enable) {
    Enable-ScheduledTask -TaskName "Newseye-Pipeline" | Out-Null
    Write-Host "Newseye-Pipeline registered and switched on: first run in about 5 minutes, then every 2 hours"
} else {
    Disable-ScheduledTask -TaskName "Newseye-Pipeline" | Out-Null
    Write-Host "Newseye-Pipeline registered, switched off. Switch on with: Enable-ScheduledTask -TaskName Newseye-Pipeline"
}
Write-Host "logs: $logDir\pipeline.log"
Get-ScheduledTask -TaskName "Newseye-Pipeline", "Newseye-Passive" -ErrorAction SilentlyContinue |
    Select-Object TaskName, State | Format-Table -AutoSize
