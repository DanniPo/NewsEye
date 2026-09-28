# Register the Newseye passive tier as a Windows scheduled task.
#
# One task, not three: ingest -> cluster -> summarise are ordered and must not
# overlap. Clustering truncates and rebuilds the cluster tables, so an ingest
# running underneath it would be clustered inconsistently.
#
#   powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_ingestion.ps1
#
# Remove with:  Unregister-ScheduledTask -TaskName Newseye-Passive -Confirm:$false
# Run now with: Start-ScheduledTask -TaskName Newseye-Passive
# Check on it:  Get-ScheduledTaskInfo -TaskName Newseye-Passive
# Watch it:     Get-Content logs\passive.log -Wait -Tail 20

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# pythonw.exe is the windowless launcher: no console is created at all, which
# is what keeps a terminal from appearing on the desktop every two hours.
# Registering an S4U principal would also hide it but needs administrator rights.
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $python)) { throw "python not found at $python" }
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

# called directly, with no shell in between: pythonw writes the log itself via
# --log, because with no console there is no stdout for a shell to redirect
$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m backend.passive --log `"$logDir\passive.log`"" `
    -WorkingDirectory $root

# every two hours: the feeds carry 10-30 items and turn over in 4-25 hours, so
# this captures essentially everything without hammering anyone
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 2)

# -Priority 4 is the important one. Task Scheduler defaults to 7, which is
# BELOW_NORMAL *and* puts the process in background I/O mode. The passive tier
# pages in ~2GB of torch CUDA DLLs on startup, and throttled I/O stretched that
# from 139 seconds to over eleven minutes. 4 is normal priority, not elevated.
#
# -AllowStartIfOnBatteries is needed as well as -DontStopIfGoingOnBatteries:
# the latter only stops the scheduler killing a run that is already going. Without
# the former the task simply never starts on battery, which on a laptop means the
# unattended tier quietly does nothing all day.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -Priority 4 `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "Newseye-Passive" -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Newseye passive tier: ingest, cluster, summarise" `
    -Force | Out-Null

Write-Host "registered Newseye-Passive - runs hidden, every 2 hours"
Write-Host "logs: $logDir\passive.log"
$t = Get-ScheduledTask -TaskName "Newseye-Passive"
$t | Select-Object TaskName, State | Format-Table -AutoSize
$t.Actions | Select-Object Execute | Format-Table -AutoSize
$x = [xml](Export-ScheduledTask -TaskName "Newseye-Passive")
Write-Host "priority $($x.Task.Settings.Priority) (4 = normal), battery-start $(-not [bool]::Parse($x.Task.Settings.DisallowStartIfOnBatteries))"
