[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CommandFile,
    [string]$PortName = 'COM11',
    [int]$BaudRate = 115200,
    [int]$TimeoutSeconds = 30,
    [string]$LogFile,
    [switch]$Interrupt,
    [switch]$KeepDtrLow,
    [string]$ExpectedPrompt = 'root@ATK-ZYNQ:[^\r\n]*#\s*$'
)

$ErrorActionPreference = 'Stop'
$command = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $CommandFile), [Text.Encoding]::UTF8).TrimEnd("`r", "`n")
$port = [IO.Ports.SerialPort]::new($PortName, $BaudRate, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$port.Encoding = [Text.UTF8Encoding]::new($false)
$port.Handshake = [IO.Ports.Handshake]::None
$port.DtrEnable = -not $KeepDtrLow
$port.RtsEnable = $false
$port.WriteTimeout = 3000
$output = [Text.StringBuilder]::new()
$complete = $false
try {
    $port.Open()
    Start-Sleep -Milliseconds 200
    $initial = $port.ReadExisting()
    if ($initial) { [void]$output.Append($initial) }
    if ($Interrupt) {
        $port.Write([string][char]3)
        Start-Sleep -Milliseconds 300
        [void]$output.Append($port.ReadExisting())
    }
    $wireText = $command.Replace("`r`n", "`n").Replace("`n", "`r") + "`r"
    $wireBytes = $port.Encoding.GetBytes($wireText)
    for ($offset = 0; $offset -lt $wireBytes.Length; $offset += 128) {
        $count = [Math]::Min(128, $wireBytes.Length - $offset)
        $port.Write($wireBytes, $offset, $count)
        Start-Sleep -Milliseconds 20
        $echoChunk = $port.ReadExisting()
        if ($echoChunk) { [void]$output.Append($echoChunk) }
    }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $quiet = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $chunk = $port.ReadExisting()
        if ($chunk) {
            [void]$output.Append($chunk)
            $quiet.Restart()
        }
        if ($quiet.ElapsedMilliseconds -gt 700 -and $output.ToString() -match $ExpectedPrompt) {
            $complete = $true
            break
        }
        Start-Sleep -Milliseconds 50
    }
}
finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
    if ($LogFile) { [IO.File]::WriteAllText($LogFile, $output.ToString(), [Text.UTF8Encoding]::new($false)) }
    [Console]::Out.Write($output.ToString())
}
if (-not $complete) { throw "Board prompt not observed within $TimeoutSeconds seconds. Read the log before sending another command." }
