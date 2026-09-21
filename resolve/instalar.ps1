# Installs Vidorq into DaVinci Resolve. One entry in the Scripts menu, once.
#
# What lands in Resolve is a loader that holds no logic and never changes. The
# code it runs lives in this repo and is pointed at from a config file, so any
# update to Vidorq reaches Resolve without anyone reinstalling anything.
#
# Run it again only if you move the Vidorq folder.

$ErrorActionPreference = "Stop"

$scripts = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
if (-not (Test-Path $scripts)) {
    throw "No encuentro la carpeta de scripts de Resolve: $scripts"
}

$home_ = Split-Path $PSScriptRoot -Parent
$vecinos = Split-Path $home_ -Parent

# El puente (CursorBridge.py) vive en otro repositorio, davinci-resolve-mcp. Se
# busca en vez de darlo por hecho: escribir aqui la ruta de una maquina concreta
# hace que el instalador solo funcione en esa maquina.
$candidatosPuente = @()
if ($env:VIDORQ_BRIDGE) { $candidatosPuente += $env:VIDORQ_BRIDGE }
$candidatosPuente += @(
    (Join-Path $vecinos "davinci-resolve-mcp\src\CursorBridge.py"),
    "C:\proyectos\davinci-resolve-mcp\src\CursorBridge.py"
)
$bridge = $candidatosPuente | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($bridge) {
    $bridge = (Resolve-Path $bridge).Path
    Write-Host "Puente encontrado: $bridge"
} else {
    $bridge = $candidatosPuente[-1]
    Write-Warning "No encuentro CursorBridge.py. Clona davinci-resolve-mcp al lado de Vidorq,"
    Write-Warning "o pon su ruta en la variable VIDORQ_BRIDGE y vuelve a lanzar esto."
}

# pythonw y no python: el de interfaz grafica no puede abrir una consola ni un parpadeo.
# Primero el entorno de Vidorq, luego el del puente, y por ultimo el del sistema.
$candidatosPython = @(
    (Join-Path $home_ ".venv\Scripts\pythonw.exe"),
    (Join-Path $vecinos "davinci-resolve-mcp\venv\Scripts\pythonw.exe"),
    "C:\proyectos\davinci-resolve-mcp\venv\Scripts\pythonw.exe"
)
$python = $candidatosPython | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    $delSistema = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($delSistema) { $python = $delSistema.Source }
}
if ($python) {
    Write-Host "Python: $python"
} else {
    Write-Warning "No encuentro ningun pythonw.exe. Crea el entorno de Vidorq primero:"
    Write-Warning "  python -m venv .venv"
    Write-Warning "  .venv\Scripts\pip install -r requirements.txt"
}

# 1. El puntero. Es lo unico que sabe donde vive Vidorq.
$confDir = Join-Path $env:APPDATA "Vidorq"
if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Path $confDir | Out-Null }
# Sin la ruta de la app a proposito: se busca al hacer clic, porque normalmente
# se compila despues de que la extension ya este en el menu.
# Cadena vacia y no $null: ConvertTo-Json escribe `null`, y del otro lado
# `.get(clave, "")` devuelve None con eso, no "". Un null aqui salia como
# TypeError al pulsar el menu, dentro de Resolve, sin mensaje.
$conf = [ordered]@{
    home   = "$home_"
    bridge = if ($bridge) { "$bridge" } else { "" }
    python = if ($python) { "$python" } else { "" }
}
# Sin BOM a proposito: Set-Content -Encoding utf8 lo mete y json.load de Python lo rechaza.
$sinBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $confDir "resolve.json"), ($conf | ConvertTo-Json), $sinBom)
Write-Host "Configuracion escrita en $confDir\resolve.json"

# 2. La unica entrada del menu.
Copy-Item (Join-Path $PSScriptRoot "Vidorq.py") (Join-Path $scripts "Vidorq.py") -Force
Write-Host "Instalado: Workspace > Scripts > Vidorq"

# 2b. DaVinci gratis 21.1 o posterior ya no ejecuta Python, y el menu no ensena
# Vidorq.py. Ahi va Vidorq.lua, que trae al timeline el ultimo video editado (el
# motor le escribe la ruta al terminar cada edicion). Solo en esas versiones: donde
# Python si corre, dos entradas "Vidorq" en el menu no se sabria cual es cual.
# Y solo si no esta ya, para no pisar la ruta que haya dejado el motor.
$lua = Join-Path $scripts "Vidorq.lua"
$resolveExe = $null
$lnk = Join-Path $env:USERPROFILE "Desktop\DaVinci Resolve.lnk"
if (Test-Path $lnk) { $resolveExe = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).TargetPath }
if (-not ($resolveExe -and (Test-Path $resolveExe))) { $resolveExe = "C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe" }
if (Test-Path $resolveExe) {
    $info = (Get-Item $resolveExe).VersionInfo
    $partes = "$($info.ProductVersion)".Split(".")
    $sinPython = ($info.ProductName -notmatch "Studio") -and ([int]$partes[0] -gt 21 -or ([int]$partes[0] -eq 21 -and [int]$partes[1] -ge 1))
    if ($sinPython -and -not (Test-Path $lua)) {
        Copy-Item (Join-Path $PSScriptRoot "Vidorq.lua") $lua
        Write-Host "DaVinci $($info.ProductVersion) gratis no ejecuta Python: instalado tambien Vidorq.lua"
    }
}

# 3. Las entradas viejas se apartan, no se borran. Tres Vidorq en el menu confunden.
foreach ($viejo in "VidorqBridge.py", "VidorqPanel.py", "VidorqProbe.py", "CursorBridge.py") {
    $ruta = Join-Path $scripts $viejo
    if (Test-Path $ruta) {
        Move-Item $ruta "$ruta.bak" -Force
        Write-Host "Apartado: $viejo"
    }
}

Write-Host ""
Write-Host "Listo. En Resolve, una sola vez por sesion:  Workspace > Scripts > Vidorq"
Write-Host "Eso enciende el motor, abre la ventana y deja el puente escuchando."
