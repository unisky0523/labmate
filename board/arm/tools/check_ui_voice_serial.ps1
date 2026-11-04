[CmdletBinding()]
param([string]$PortName = 'COM6', [switch]$PrepareOnly)

# The user runs this read-only check. It does not upload or replace program files.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$fixture = Join-Path $taskRoot 'work\labmate_ui\tests\fixtures\original_voice_hashes.json'
$original = Get-Content -LiteralPath $fixture -Raw -Encoding UTF8 | ConvertFrom-Json
$verifiedFixture = Join-Path $taskRoot 'work\labmate_ui\tests\fixtures\verified_voice_hashes_20261101.json'
$verified = Get-Content -LiteralPath $verifiedFixture -Raw -Encoding UTF8 | ConvertFrom-Json
$voiceHashes = [ordered]@{}
foreach ($item in $verified.PSObject.Properties | Sort-Object Name) {
    if ($item.Name.EndsWith('.py')) { $voiceHashes[$item.Name] = $item.Value }
}
$originalHashes = [ordered]@{}
foreach ($item in $original.PSObject.Properties | Sort-Object Name) {
    if ($item.Name.EndsWith('.py')) { $originalHashes[$item.Name] = $item.Value }
}
$recordsHashes = [ordered]@{}
foreach ($name in @('backend.py', 'record_store.py', 'run_ui_voice.sh')) {
    if ($name.EndsWith('.sh')) { $path = Join-Path $PSScriptRoot $name }
    else { $path = Join-Path $taskRoot ('work\labmate_ui\' + $name) }
    $data = [IO.File]::ReadAllBytes($path)
    if ($name.EndsWith('.sh')) {
        $data = [Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($path).Replace("`r`n", "`n"))
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $recordsHashes[$name] = ([BitConverter]::ToString($sha.ComputeHash($data))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
$expected = [ordered]@{
    voice = $voiceHashes
    original_voice = $originalHashes
    records = $recordsHashes
    gui = (Get-FileHash -LiteralPath (Join-Path $taskRoot 'dist\armhf\labassistant') -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json -Depth 4 -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($expected))
$source = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'audit_ui_voice.py')).Replace("`r`n", "`n")
$command = "python3 - <<'LM_VOICE_AUDIT'`nimport base64,json`n" + $source +
    "`naudit(Path('/home/root/labmate_ui_test'), json.loads(base64.b64decode('$encoded')))`nLM_VOICE_AUDIT`n"
foreach ($line in $command.Split("`n")) {
    if ($line.Length -gt 3900) { throw 'Audit command line exceeds terminal limit.' }
}
$commandFile = Join-Path $taskRoot 'tmp\ui_voice_audit_command.txt'
$logFile = Join-Path $taskRoot 'work\ui_voice_version_check_latest.log'
[IO.Directory]::CreateDirectory((Split-Path -Parent $commandFile)) | Out-Null
[IO.File]::WriteAllText($commandFile, $command, [Text.UTF8Encoding]::new($false))
if ($PrepareOnly) {
    Write-Output ('Read-only audit prepared: {0} verified voice files, {1} record files. No serial port opened.' -f $voiceHashes.Count, $recordsHashes.Count)
    return
}
$serialHelper = Join-Path $PSScriptRoot 'board_serial_command.ps1'
$response = & powershell -NoProfile -ExecutionPolicy Bypass -File $serialHelper -CommandFile $commandFile -PortName $PortName -KeepDtrLow -TimeoutSeconds 30 -LogFile $logFile 2>&1
if ($LASTEXITCODE -ne 0) { throw (($response -join "`n") + "`nAudit log: " + $logFile) }
$responseText = [IO.File]::ReadAllText($logFile, [Text.Encoding]::UTF8)
$match = [regex]::Match($responseText, '(?ms)^__LM_VOICE_AUDIT_START__\r?$.*?^__LM_VOICE_AUDIT_END__\r?$')
if (-not $match.Success) { throw ('Audit did not complete. Output saved at: ' + $logFile) }
Write-Output $match.Value
Write-Output ('Audit log: ' + $logFile)
