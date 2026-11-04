[CmdletBinding()]
param(
    [string]$Source = 'D:\labmate_b',
    [string]$Destination = 'D:\fpga amd xinlx\dist\labmate_b_board'
)

$ErrorActionPreference = 'Stop'

$sourceFull = [System.IO.Path]::GetFullPath($Source)
$destinationFull = [System.IO.Path]::GetFullPath($Destination)
$distRoot = [System.IO.Path]::GetFullPath('D:\fpga amd xinlx\dist')
if (-not $sourceFull.StartsWith([System.IO.Path]::GetFullPath('D:\labmate_b'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Source must stay inside D:\labmate_b: $sourceFull"
}
if (-not $destinationFull.StartsWith($distRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must stay inside ${distRoot}: $destinationFull"
}
if (-not (Test-Path -LiteralPath $sourceFull)) {
    throw "Source directory does not exist: $sourceFull"
}

if (Test-Path -LiteralPath $destinationFull) {
    Remove-Item -LiteralPath $destinationFull -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $destinationFull | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $destinationFull 'models') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $destinationFull 'data\audio\prompts') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $destinationFull 'data\state') | Out-Null

$files = @(
    'main.py',
    'text_cli.py',
    'asr_cli.py',
    'board_audio.py',
    'board_mic.py',
    'board_speaker.py',
    'board_ui.py',
    'board_sources.py',
    'board_app.py',
    'asr_backend.py',
    'vosk_lite.py',
    'readback.py',
    'run_board.sh',
    'libvosk.so',
    'requirements_board.txt',
    'README_board.md'
)

foreach ($name in $files) {
    $sourcePath = Join-Path $sourceFull $name
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Missing required file: $sourcePath"
    }
    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $destinationFull $name) -Force
}

$modelSource = Join-Path $sourceFull 'models\vosk-model-small-cn-0.22'
if (Test-Path -LiteralPath $modelSource) {
    Copy-Item -LiteralPath $modelSource -Destination (Join-Path $destinationFull 'models') -Recurse -Force
}

$promptSource = Join-Path $sourceFull 'data\audio\prompts'
if (Test-Path -LiteralPath $promptSource) {
    Copy-Item -LiteralPath $promptSource -Destination (Join-Path $destinationFull 'data\audio') -Recurse -Force
}

$librarySource = Join-Path $sourceFull 'lib'
if (Test-Path -LiteralPath $librarySource) {
    Copy-Item -LiteralPath $librarySource -Destination $destinationFull -Recurse -Force
}

Write-Host "Clean board package created:"
Write-Host "  $destinationFull"
Write-Host "Excluded: .venv, __pycache__, logs, test records, generated WAV files."
