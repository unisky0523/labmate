[CmdletBinding()]
param([string]$PortName = 'COM6')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$task = Join-Path $root 'work\sweep_response_20261103'
$binary = Join-Path $task 'labassistant'
$bytes = [IO.File]::ReadAllBytes($binary)
if ($bytes.Length -lt 20 -or $bytes[0] -ne 127 -or $bytes[4] -ne 1 -or [BitConverter]::ToUInt16($bytes,18) -ne 40 -or -not [Text.Encoding]::ASCII.GetString($bytes).Contains('LABMATE_UI_RESPONSE_V1')) {
    throw 'The compiled ARM sweep-response executable is missing or invalid.'
}
Write-Host '1/4 Back up the current board application and close the old UI.'
& (Join-Path $PSScriptRoot 'board_serial_command.ps1') -CommandFile (Join-Path $task 'prepare_command.txt') -PortName $PortName -KeepDtrLow -TimeoutSeconds 60 -LogFile (Join-Path $task 'backup.log')
if (-not ([IO.File]::ReadAllText((Join-Path $task 'backup.log')).Contains('__SWEEP_BACKUP__'))) { throw 'Board backup was not confirmed; upload cancelled.' }
Copy-Item -LiteralPath $binary -Destination (Join-Path $root 'dist\armhf\labassistant')
Write-Host '2/4 Upload the new ARM UI and matching backend.'
& (Join-Path $PSScriptRoot 'upload_ui_serial.ps1') -PortName $PortName -RealAsr -SweepResponse
Write-Host '3/4 Start the updated application.'
& (Join-Path $PSScriptRoot 'board_serial_command.ps1') -CommandFile (Join-Path $task 'restart_command.txt') -PortName $PortName -KeepDtrLow -TimeoutSeconds 40 -LogFile (Join-Path $task 'restart.log')
if (-not ([IO.File]::ReadAllText((Join-Path $task 'restart.log')).Contains('__LM_INSTRUMENT_SESSION__'))) { throw 'New application startup was not confirmed.' }
Start-Sleep -Seconds 5
Write-Host '4/4 Verify both processes, old history and executable hash.'
& (Join-Path $PSScriptRoot 'board_serial_command.ps1') -CommandFile (Join-Path $task 'verify_command.txt') -PortName $PortName -KeepDtrLow -TimeoutSeconds 30 -LogFile (Join-Path $task 'verify.log')
$log = [IO.File]::ReadAllText((Join-Path $task 'verify.log'))
if ($log -match 'Traceback' -or -not ($log -match '__FFT_FINAL__([^\r\n]+)')) { throw 'Board verification failed; see verify.log.' }
$report = $Matches[1] | ConvertFrom-Json
$expected = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
if (-not $report.old_records_unchanged -or $report.binary_sha256 -ne $expected -or $report.processes.Count -ne 2) { throw 'Installed version/history/process verification failed.' }
Write-Host 'DEPLOY_OK: new sweep-response application running; old records preserved.' -ForegroundColor Green
