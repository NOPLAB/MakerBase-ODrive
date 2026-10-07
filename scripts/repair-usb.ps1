$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$root/logs", "$root/backups" | Out-Null
Start-Transcript -Path "$root/logs/repair-usb.log" -Force
try {
    $instance = 'USB\VID_1209&PID_0D32&MI_02\8&28D99BA3&0&0002'
    $device = Get-PnpDevice -InstanceId $instance
    if ($device.FriendlyName -ne 'ODrive 3.6 Native Interface') { throw 'Unexpected USB device' }
    $service = (Get-PnpDeviceProperty -InstanceId $instance -KeyName DEVPKEY_Device_Service).Data
    if ($service -ne 'WINUSB') { throw 'Expected existing WinUSB driver' }
    $key = "HKLM:/SYSTEM/CurrentControlSet/Enum/$instance/Device Parameters"
    $properties = Get-ItemProperty -LiteralPath $key
    if (-not $properties.DeviceInterfaceGUIDs -and -not $properties.DeviceInterfaceGUID) {
        & reg.exe export "HKLM\SYSTEM\CurrentControlSet\Enum\$instance\Device Parameters" "$root/backups/usb-parameters-before.reg" /y
        if ($LASTEXITCODE -ne 0) { throw 'Registry backup failed' }
        $guid = [guid]::NewGuid().ToString('B')
        New-ItemProperty -LiteralPath $key -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value @($guid) | Out-Null
        if ((Get-ItemProperty -LiteralPath $key).DeviceInterfaceGUIDs -notcontains $guid) { throw 'GUID verification failed' }
        Write-Output "Registered ODrive interface: $guid"
    }
    & pnputil.exe /restart-device $instance
    if ($LASTEXITCODE -ne 0) { throw 'Restart failed; reconnect USB to the same port' }
    Write-Output 'ODrive USB interface repair completed'
} finally {
    Stop-Transcript
}
