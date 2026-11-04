param([Parameter(Mandatory=$true)][string]$File,
      [Parameter(Mandatory=$true)][string]$Destination,
      [int]$TransferBaud=460800)
$ErrorActionPreference='Stop'
if ($Destination -notmatch '^/home/root/spi_stage_20261104/[a-zA-Z0-9_.-]+$') { throw 'Unexpected destination' }
$data=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $File))
$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $File).Hash.ToLowerInvariant()
$source=[IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'uart_receive.py'))
$encoded=[Convert]::ToBase64String($source)
$command='python3 -c "import base64;exec(base64.b64decode(' + "'$encoded'" + '))" ' + $data.Length + ' ' + $hash + ' ' + $Destination + ' ' + $TransferBaud
$port=[IO.Ports.SerialPort]::new('COM6',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.DtrEnable=$false; $port.RtsEnable=$false
$port.Handshake=[IO.Ports.Handshake]::None
$port.WriteTimeout=10000
$port.Encoding=[Text.Encoding]::ASCII
function Await-Text([string]$Pattern,[int]$Seconds=15) {
    $response=[Text.StringBuilder]::new()
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $Seconds) {
        $part=$port.ReadExisting()
        if ($part) { [void]$response.Append($part) }
        if ($response.ToString() -match '__SPI_ERROR__') { throw $response.ToString() }
        if ($response.ToString() -match $Pattern) { return $response.ToString() }
        Start-Sleep -Milliseconds 2
    }
    throw ('UART timeout: ' + $response.ToString())
}
$switched=$false
try {
    $port.Open(); $port.Write("`r")
    [void](Await-Text 'root@ATK-ZYNQ:[^\r\n]*#\s*$')
    for ($i=0;$i -lt $command.Length;$i+=96) {
        $port.Write($command.Substring($i,[Math]::Min(96,$command.Length-$i)))
        Start-Sleep -Milliseconds 20
    }
    $port.Write("`r")
    [void](Await-Text '__SPI_SWITCH__')
    $switched=$true; $port.BaudRate=$TransferBaud
    [void](Await-Text '__SPI_READY__')
    Write-Output "UART_UPLOAD_START bytes=$($data.Length) baud=$TransferBaud"
    for ($offset=0;$offset -lt $data.Length;) {
        $count=[Math]::Min(1024,$data.Length-$offset)
        $port.Write($data,$offset,$count)
        $offset+=$count
        $reply=Await-Text ("__SPI_ACK_{0}__" -f $offset)
        if ($offset % 262144 -eq 0) { Write-Output "UART_UPLOAD_PROGRESS $offset/$($data.Length)" }
    }
    if ($reply -notmatch ('__SPI_SUCCESS__ ' + [regex]::Escape($hash))) { $reply+=Await-Text ([regex]::Escape($hash)) }
    Start-Sleep -Milliseconds 800
    $port.BaudRate=115200; $switched=$false
    $port.Write("`r")
    [void](Await-Text 'root@ATK-ZYNQ:[^\r\n]*#\s*$')
    Write-Output "UART_UPLOAD_VERIFIED $Destination $hash"
} catch {
    if ($switched) {
        Start-Sleep -Seconds 13
        $port.BaudRate=115200
    }
    throw
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}
