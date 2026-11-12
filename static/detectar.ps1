# PC Doctor Expert - lector de componentes (solo lectura, Windows)
# Lee: procesador, tarjeta grafica, memoria RAM, discos y sistema operativo.
# No instala nada ni envia datos por Internet: el resultado se copia a tu portapapeles.
$ErrorActionPreference = 'SilentlyContinue'
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpus = @(Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notmatch 'Basic|Remote|Virtual|Parsec|Meta' })
$gpu = $gpus | Where-Object { $_.Name -match 'NVIDIA|GeForce|Radeon RX|Radeon Pro|Arc A' } | Select-Object -First 1
$dedicada = [bool]$gpu
if (-not $gpu) { $gpu = $gpus | Select-Object -First 1 }
$tipos = @{ 24 = 'DDR3'; 26 = 'DDR4'; 30 = 'LPDDR4'; 34 = 'DDR5'; 35 = 'LPDDR5' }
$ram = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
  $t = $tipos[[int]$_.SMBIOSMemoryType]
  if (-not $t) { if ([int]$_.Speed -ge 4800) { $t = 'DDR5' } elseif ([int]$_.Speed -ge 2133) { $t = 'DDR4' } else { $t = 'DDR3' } }
  $f = $_.ConfiguredClockSpeed; if (-not $f) { $f = $_.Speed }
  [pscustomobject]@{ capacidad_gb = [int]($_.Capacity / 1GB); tipo = $t; frecuencia_mhz = [int]$f; marca = ([string]$_.Manufacturer).Trim() }
})
$sistema = (Get-Partition -DriveLetter $env:SystemDrive[0] | Get-Disk).Number
$discos = @(Get-PhysicalDisk | Where-Object { $_.BusType -ne 'USB' } | ForEach-Object {
  if ($_.BusType -eq 'NVMe') { $tipo = 'SSD NVMe' } elseif ($_.MediaType -eq 'HDD') { $tipo = 'HDD' } else { $tipo = 'SSD SATA' }
  [pscustomobject]@{ tipo = $tipo; capacidad_gb = [int]($_.Size / 1GB); modelo = $_.FriendlyName; es_sistema = ([int]$_.DeviceId -eq [int]$sistema) }
})
$so = ((Get-CimInstance Win32_OperatingSystem).Caption -replace '^Microsoft\s+', '').Trim()
$resultado = [pscustomobject]@{ so = $so; procesador = ($cpu.Name -replace '\s+', ' ').Trim(); nucleos = [int]$cpu.NumberOfCores; gpu = $gpu.Name; gpu_dedicada = $dedicada; ram = $ram; discos = $discos }
$json = $resultado | ConvertTo-Json -Depth 4 -Compress
Set-Clipboard -Value $json
$json
Write-Host ''
Write-Host 'Listo: el resultado se copio al portapapeles. Vuelve a PC Doctor Expert y pegalo.' -ForegroundColor Green
