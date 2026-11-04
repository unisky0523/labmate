$ErrorActionPreference='Stop'
$port=[IO.Ports.SerialPort]::new('COM6',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.DtrEnable=$false; $port.RtsEnable=$false
$log=[Text.StringBuilder]::new()
$sent=$false; $success=$false
try {
    $port.Open(); $port.Write("`r")
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 100) {
        $chunk=$port.ReadExisting()
        if ($chunk) {
            [void]$log.Append($chunk); [Console]::Write($chunk)
            if (-not $sent -and $log.ToString() -match 'root@ATK-ZYNQ:[^\r\n]*#\s*$') {
                $port.Write("sync; reboot`r")
                $sent=$true; [void]$log.Clear()
            } elseif ($sent -and $log.ToString() -match 'SPI_PERMANENT_BOOT_20261104' -and $log.ToString() -match 'root@ATK-ZYNQ:[^\r\n]*#\s*$') {
                $success=$true; break
            }
        }
        Start-Sleep -Milliseconds 10
    }
} finally {
    if ($port.IsOpen) {$port.Close()}; $port.Dispose()
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'autoboot.log'),$log.ToString())
}
if (-not $success) {throw 'Automatic SPI boot did not reach Linux; inspect autoboot.log'}
Write-Output 'AUTOMATIC_QSPI_TO_EMMC_SPI_BOOT_CONFIRMED'
