[CmdletBinding()]
param(
    [string]$PortName = "COM11",
    [int]$BaudRate = 115200
)

$ErrorActionPreference = "Stop"
$port = $null

try {
    $availablePorts = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($availablePorts -notcontains $PortName) {
        throw "Serial port '$PortName' was not found. Available ports: $($availablePorts -join ', ')"
    }

    $port = [System.IO.Ports.SerialPort]::new(
        $PortName,
        $BaudRate,
        [System.IO.Ports.Parity]::None,
        8,
        [System.IO.Ports.StopBits]::One
    )
    $port.Handshake = [System.IO.Ports.Handshake]::None
    $port.Encoding = [System.Text.UTF8Encoding]::new($false)
    $port.ReadTimeout = 50
    $port.WriteTimeout = 500
    $port.Open()

    Write-Host ""
    Write-Host "Connected to $PortName at $BaudRate baud (8-N-1, no flow control)." -ForegroundColor Green
    Write-Host "Type directly in this window. Press F10 to exit." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        $incoming = $port.ReadExisting()
        if ($incoming.Length -gt 0) {
            [Console]::Out.Write($incoming)
        }

        while ([Console]::KeyAvailable) {
            $keyInfo = [Console]::ReadKey($true)

            if ($keyInfo.Key -eq [ConsoleKey]::F10) {
                return
            }

            switch ($keyInfo.Key) {
                ([ConsoleKey]::Enter)     { $port.Write("`r") }
                ([ConsoleKey]::Backspace) { $port.Write([char]127) }
                ([ConsoleKey]::Tab)       { $port.Write("`t") }
                ([ConsoleKey]::Escape)    { $port.Write([char]27) }
                default {
                    if (-not [char]::IsControl($keyInfo.KeyChar)) {
                        $port.Write([string]$keyInfo.KeyChar)
                    }
                }
            }
        }

        Start-Sleep -Milliseconds 20
    }
}
finally {
    if ($null -ne $port -and $port.IsOpen) {
        $port.Close()
    }
    $port = $null
    [Console]::ResetColor()
}
