[CmdletBinding()]
param([string]$PortName = 'COM6', [int]$BaudRate = 115200, [switch]$RealAsr, [switch]$PrepareOnly,
      [switch]$RecordsOnly, [switch]$RestoreVoiceBaseline, [switch]$InstallAsrRuntime, [switch]$Instruments, [switch]$PcmLittle,
      [switch]$VoiceConfirm, [switch]$DesktopEntry, [switch]$UpdateAsrAdapter, [switch]$BatchRecording, [switch]$MeasurementUnits,
      [switch]$GeneratorControl, [switch]$FftAnalysis, [switch]$SweepResponse)

# Transfers the test files only. Does not stop the desktop or launch the UI.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$binary = Join-Path $root 'dist\armhf\labassistant'
$launcher = Join-Path $PSScriptRoot 'run_ui_test.sh'
$receiver = Join-Path $PSScriptRoot 'ui_serial_receiver.py'
if (($RecordsOnly -or $RestoreVoiceBaseline -or $InstallAsrRuntime -or $Instruments -or $PcmLittle -or $VoiceConfirm -or $DesktopEntry -or $UpdateAsrAdapter -or $BatchRecording -or $MeasurementUnits) -and -not $RealAsr) { throw 'These options require -RealAsr.' }
if ($MeasurementUnits -and $RestoreVoiceBaseline) { throw 'Measurement units require the current ASR parser and vocabulary.' }
if ($BatchRecording -and $RestoreVoiceBaseline) { throw 'Batch recording cannot restore the older voice vocabulary.' }
if ($UpdateAsrAdapter -and $RestoreVoiceBaseline) { throw 'Do not combine a new ASR adapter with restoring the old adapter.' }
if ($VoiceConfirm -and ($RecordsOnly -or $RestoreVoiceBaseline)) { throw 'Voice confirmation requires the matching new GUI and cannot restore the older voice adapter.' }
if ($PcmLittle -and $RestoreVoiceBaseline) { throw 'Updating PCM cannot be combined with restoring the old voice baseline.' }
if ($InstallAsrRuntime -and ($RecordsOnly -or $RestoreVoiceBaseline)) { throw 'Installing ASR cannot be combined with a records-only update or voice restoration.' }
$files = [ordered]@{}
if ($GeneratorControl -and (-not $RealAsr -or $RestoreVoiceBaseline)) { throw 'Generator control requires current RealAsr and cannot restore the old parser.' }
if ($FftAnalysis -and (-not $RealAsr -or $RestoreVoiceBaseline)) { throw 'FFT requires the current RealAsr parser.' }
if ($SweepResponse -and (-not $RealAsr -or $RecordsOnly -or $RestoreVoiceBaseline -or $InstallAsrRuntime -or $PcmLittle -or $VoiceConfirm -or $DesktopEntry -or $UpdateAsrAdapter -or $BatchRecording -or $MeasurementUnits -or $GeneratorControl -or $FftAnalysis -or $Instruments)) {
    throw 'Use -RealAsr -SweepResponse alone: this mode preserves ASR, audio and launch settings.'
}
if (-not $RecordsOnly) {
$bytes = [IO.File]::ReadAllBytes($binary)
if ($bytes.Length -lt 20 -or $bytes[0] -ne 127 -or $bytes[1] -ne 69 -or $bytes[2] -ne 76 -or $bytes[3] -ne 70 -or $bytes[4] -ne 1 -or [BitConverter]::ToUInt16($bytes,18) -ne 40) {
    throw 'The file must be a compiled ARM ELF32 executable.'
}
if (-not [Text.Encoding]::ASCII.GetString($bytes).Contains('LABMATE_UI_RECORDS_V2')) {
    if ($PrepareOnly) { Write-Warning 'Executable predates records V2: packaging check only; recompile before an actual upload.' }
    else { throw 'This executable predates records V2. Recompile the updated Qt project in Ubuntu and replace dist\armhf\labassistant first.' }
}
$files['labassistant'] = $bytes
if ($SweepResponse -and -not [Text.Encoding]::ASCII.GetString($bytes).Contains('LABMATE_UI_RESPONSE_V1')) {
    throw 'Compile the sweep-response Qt interface before uploading.'
}
if ($FftAnalysis -and -not [Text.Encoding]::ASCII.GetString($bytes).Contains('LABMATE_UI_FFT_V1')) {
    throw 'Compile the FFT Qt interface before uploading with -FftAnalysis.'
}
if ($VoiceConfirm -and -not [Text.Encoding]::ASCII.GetString($bytes).Contains('LABMATE_UI_VOICE_CONFIRM_V1')) {
    throw 'Compile the voice-confirmation Qt interface before uploading with -VoiceConfirm.'
}
if (-not $SweepResponse) {
    $files['run_ui_test.sh'] = [Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($launcher).Replace("`r`n","`n"))
}
}
if ($SweepResponse) {
    foreach ($name in @('record_store.py','command_executor.py','instrument_adapter.py','generator_control.py','generator_runner.py','sweep_response.py','fft_protocol.py','scope_waveform.py')) {
        $files[$name] = [IO.File]::ReadAllBytes((Join-Path $root ('work\labmate_ui\'+$name)))
    }
}
if ($RealAsr -and -not $SweepResponse) {
    foreach ($name in @('backend.py','record_store.py','instrument_adapter.py','command_executor.py','audio_frontend.py','generator_control.py','generator_runner.py','sweep_response.py')) {
        $files[$name] = [IO.File]::ReadAllBytes((Join-Path $root ("work\labmate_ui\"+$name)))
    }
    $files['asr_runtime/generator_commands.py'] = [IO.File]::ReadAllBytes((Join-Path $root 'work\labmate_ui\asr_runtime\generator_commands.py'))
    if ($FftAnalysis) {
        foreach ($name in @('fft_control.py','fft_protocol.py','scope_waveform.py')) {
            $files[$name] = [IO.File]::ReadAllBytes((Join-Path $root ('work\labmate_ui\'+$name)))
        }
    }
    $files['run_ui_voice.sh'] = [Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'run_ui_voice.sh')).Replace("`r`n","`n"))
    if ($Instruments) {
        $files['instruments.json'] = [IO.File]::ReadAllBytes((Join-Path $root 'work\labmate_ui\instruments.json'))
        $files['run_ui_instruments.sh'] = [Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'run_ui_instruments.sh')).Replace("`r`n","`n"))
    }
    if ($PcmLittle) {
        $files['asr_runtime/board_listen.py'] = [IO.File]::ReadAllBytes((Join-Path $root 'work\labmate_ui\asr_runtime\board_listen.py'))
    }
    if ($BatchRecording) {
        foreach ($name in @('asr_runtime/main.py', 'asr_runtime/text_cli.py', 'asr_runtime/asr_grammar.py')) {
            $files[$name] = [IO.File]::ReadAllBytes((Join-Path $root ('work\labmate_ui\' + $name)))
        }
    }
    # These modules now share quantity/unit constants and the review keyword;
    # always deploy their matching versions together when updating recognition.
    if ($MeasurementUnits -or $VoiceConfirm -or $UpdateAsrAdapter -or $BatchRecording -or $GeneratorControl -or $FftAnalysis) {
        foreach ($name in @('asr_adapter.py', 'asr_runtime/main.py', 'asr_runtime/text_cli.py', 'asr_runtime/asr_grammar.py', 'asr_runtime/asr_cli.py', 'asr_runtime/generator_commands.py')) {
            $files[$name] = [IO.File]::ReadAllBytes((Join-Path $root ('work\labmate_ui\' + $name)))
        }
    }
    if ($GeneratorControl) {
        $driverRoot = Join-Path $root 'work\labmate_ui\dg4102_driver'
        foreach ($item in Get-ChildItem -LiteralPath $driverRoot -Recurse -File) {
            if ($item.FullName -match '[\\/]__pycache__[\\/]' -or $item.Extension -eq '.pyc') { continue }
            $relative = $item.FullName.Substring($driverRoot.Length + 1).Replace('\','/')
            $files['dg4102_driver/' + $relative] = [IO.File]::ReadAllBytes($item.FullName)
        }
    }
    if ($DesktopEntry) {
        $desktopBytes = [IO.File]::ReadAllBytes((Join-Path $root 'work\desktop_entry_20261102\QMainApp'))
        if ($desktopBytes.Length -lt 20 -or $desktopBytes[0] -ne 127 -or $desktopBytes[1] -ne 69 -or $desktopBytes[2] -ne 76 -or $desktopBytes[3] -ne 70 -or $desktopBytes[4] -ne 1 -or [BitConverter]::ToUInt16($desktopBytes,18) -ne 40 -or -not [Text.Encoding]::ASCII.GetString($desktopBytes).Contains('LABMATE_DESKTOP_ENTRY_V1')) {
            throw 'Compile the ARM desktop with the LabMate entry first.'
        }
        $files['QMainApp'] = $desktopBytes
        foreach ($name in @('run_ui_desktop.sh', 'run_ui_test.sh', 'install_desktop_entry.py')) {
            $files[$name] = [Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText((Join-Path $PSScriptRoot $name)).Replace("`r`n","`n"))
        }
    }
    if ($InstallAsrRuntime) {
    $files['asr_adapter.py'] = [IO.File]::ReadAllBytes((Join-Path $root 'work\labmate_ui\asr_adapter.py'))
    $runtime = Join-Path $root 'work\labmate_ui\asr_runtime'
    foreach ($item in Get-ChildItem -LiteralPath $runtime -File) {
        $files['asr_runtime/'+$item.Name] = [IO.File]::ReadAllBytes($item.FullName)
    }
    }
    if ($RestoreVoiceBaseline) {
        $files['restore_ui_voice_baseline.py'] = [IO.File]::ReadAllBytes((Join-Path $root 'tools\restore_ui_voice_baseline.py'))
    }
}
Add-Type -AssemblyName System.IO.Compression
$memory = [IO.MemoryStream]::new()
$archive = [IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Create,$true)
try {
    foreach ($name in $files.Keys) {
        $entry = $archive.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal)
        $stream = $entry.Open()
        try { $stream.Write($files[$name],0,$files[$name].Length) } finally { $stream.Dispose() }
    }
} finally { $archive.Dispose() }
$payload = $memory.ToArray()
$memory.Dispose()
$hash = [Security.Cryptography.SHA256]::Create()
try { $digest = ([BitConverter]::ToString($hash.ComputeHash($payload))).Replace('-','').ToLowerInvariant() } finally { $hash.Dispose() }
$encoded = [Convert]::ToBase64String($payload)
$chunkSize = 1536
$count = [int][Math]::Ceiling($encoded.Length / [double]$chunkSize)
$receiverMemory = [IO.MemoryStream]::new()
$receiverGzip = [IO.Compression.GZipStream]::new($receiverMemory,[IO.Compression.CompressionMode]::Compress,$true)
try {
    $receiverBytes = [IO.File]::ReadAllBytes($receiver)
    $receiverGzip.Write($receiverBytes,0,$receiverBytes.Length)
} finally { $receiverGzip.Dispose() }
$receiver64 = [Convert]::ToBase64String($receiverMemory.ToArray())
$receiverMemory.Dispose()
$command = "python3 -u -c `"import base64,gzip;exec(gzip.decompress(base64.b64decode('$receiver64')))`" $count $digest"
if ($command.Length -gt 4000) { throw 'Receiver command exceeds terminal line limit.' }
if ($PrepareOnly) {
    $checkStream = [IO.MemoryStream]::new($payload,$false)
    $checkZip = [IO.Compression.ZipArchive]::new($checkStream,[IO.Compression.ZipArchiveMode]::Read)
    try {
        foreach ($entry in $checkZip.Entries) { Write-Output ("Archive entry: {0}, {1} bytes" -f $entry.FullName,$entry.Length) }
        if (-not $RecordsOnly) {
        $inputStream = $checkZip.GetEntry('labassistant').Open()
        $roundTrip = [IO.MemoryStream]::new()
        try {
            $inputStream.CopyTo($roundTrip)
            if ([Convert]::ToBase64String($roundTrip.ToArray()) -cne [Convert]::ToBase64String($bytes)) { throw 'Archive round-trip mismatch.' }
        } finally { $inputStream.Dispose(); $roundTrip.Dispose() }
        }
    } finally { $checkZip.Dispose(); $checkStream.Dispose() }
    Write-Output ("Preparation OK: {0} compressed bytes, {1} chunks, receiver command {2} chars. No serial port opened." -f $payload.Length,$count,$command.Length)
    return
}
$port = [IO.Ports.SerialPort]::new($PortName,$BaudRate,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.Handshake = [IO.Ports.Handshake]::None
$port.Encoding = [Text.UTF8Encoding]::new($false)
$port.WriteTimeout = 5000
$port.NewLine = "`n"
function Wait-BoardText([string]$Pattern,[int]$Seconds) {
    $text = [Text.StringBuilder]::new()
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $Seconds) {
        $part = $port.ReadExisting()
        if ($part) { [void]$text.Append($part) }
        if ($text.ToString() -match '__LM_UPLOAD_ERROR__') { throw $text.ToString() }
        if ($text.ToString() -match $Pattern) { return $text.ToString() }
        Start-Sleep -Milliseconds 20
    }
    throw ("Timed out. Board response: " + $text.ToString())
}
$receiving = $false
try {
    $port.Open()
    Start-Sleep -Milliseconds 200
    [void]$port.ReadExisting()
    $port.Write("`r")
    [void](Wait-BoardText 'root@ATK-ZYNQ:[^\r\n]*#\s*$' 8)
    Write-Host ("Uploading {0:N0} bytes through {1}. Keep this window open." -f $payload.Length,$PortName)
    # Pace the shell command to stay within the UART driver's input buffer.
    for ($offset=0; $offset -lt $command.Length; $offset+=96) {
        $port.Write($command.Substring($offset,[Math]::Min(96,$command.Length-$offset)))
        Start-Sleep -Milliseconds 20
    }
    $port.Write("`r")
    [void](Wait-BoardText '__LM_RX_READY__' 10)
    $receiving = $true
    for ($index=0; $index -lt $count; $index++) {
        $offset = $index * $chunkSize
        $line = $encoded.Substring($offset,[Math]::Min($chunkSize,$encoded.Length-$offset))
        # One ACK per line prevents overrunning the board's serial input queue.
        $port.WriteLine($line)
        $response = Wait-BoardText ("__LM_ACK_{0}__" -f $index) 12
        Write-Progress -Activity 'Transfer LabMate UI to board' -Status ("{0}/{1}" -f ($index+1),$count) -PercentComplete (100*($index+1)/$count)
    }
    # The final ACK may arrive together with the completion marker.
    if ($response -notmatch '__LM_UPLOAD_OK__') { $response += Wait-BoardText '__LM_UPLOAD_OK__' 20 }
    $receiving = $false
    Write-Progress -Activity 'Transfer LabMate UI to board' -Completed
    Write-Host $response
    Write-Host 'UPLOAD OK. Reopen your serial terminal. Board path: /home/root/labmate_ui_test'
} catch {
    if ($receiving -and $port.IsOpen) {
        try { $port.WriteLine('__LM_ABORT__'); Start-Sleep -Milliseconds 500 } catch {}
    }
    throw
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
