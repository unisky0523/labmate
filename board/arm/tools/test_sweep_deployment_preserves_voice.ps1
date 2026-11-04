$ErrorActionPreference = 'Stop'
$output = & (Join-Path $PSScriptRoot 'upload_ui_serial.ps1') -PrepareOnly -RealAsr -SweepResponse
$names = @($output | ForEach-Object { if ($_ -match '^Archive entry: (.+), [0-9]+ bytes$') { $Matches[1] } })
$expected = @('labassistant','record_store.py','command_executor.py','instrument_adapter.py',
              'generator_control.py','generator_runner.py','sweep_response.py','fft_protocol.py','scope_waveform.py')
if (@(Compare-Object ($names | Sort-Object) ($expected | Sort-Object)).Count -ne 0) {
    throw ('Sweep package violates the allowed file list: ' + ($names -join ', '))
}
if ($names | Where-Object { $_ -match '(^asr_|^audio_|^run_ui_|^backend\.py$|^instruments\.json$)' }) {
    throw 'Sweep update must not package voice/audio/runtime/launch configuration.'
}
Write-Output 'PASS: only 9 UI/measurement files; no voice, audio, runtime or launch files.'
