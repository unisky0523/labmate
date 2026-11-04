$ErrorActionPreference = 'Stop'
$port = [IO.Ports.SerialPort]::new('COM6',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.Encoding = [Text.Encoding]::UTF8
$log = [Text.StringBuilder]::new()
$rebootSent = $false
$interrupted = $false
$success = $false
try {
    $port.Open()
    $port.Write("`r")
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 45) {
        $chunk = $port.ReadExisting()
        if ($chunk) {
            [void]$log.Append($chunk)
            [Console]::Write($chunk)
            if (-not $interrupted -and $log.ToString() -match 'Hit any key to stop autoboot') {
                $port.Write("`r")
                $interrupted = $true
            }
            if ($log.ToString() -match '(?m)(?:Zynq|zynq|U-Boot)[^\r\n]*>\s*$') {
                $success = $true
                break
            }
            if (-not $rebootSent -and $log.ToString() -match 'root@ATK-ZYNQ:[^\r\n]*#\s*$') {
                $port.Write("sync; reboot`r")
                $rebootSent = $true
                $log.Clear() | Out-Null
            }
        }
        Start-Sleep -Milliseconds 10
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
    [IO.File]::WriteAllText('D:\fpga amd xinlx\work\spi_permanent_20261104\enter_uboot.log',$log.ToString())
}
if (-not $success) { throw 'U-Boot prompt not confirmed. Inspect the capture before sending further commands.' }
