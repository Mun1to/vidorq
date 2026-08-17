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
$bridge = "C:\proyectos\davinci-resolve-mcp\src\CursorBridge.py"
# pythonw y no python: el de interfaz grafica no puede abrir una consola ni un parpadeo.
$python = "C:\proyectos\davinci-resolve-mcp\venv\Scripts\pythonw.exe"

if (-not (Test-Path $bridge)) {
    Write-Warning "No encuentro el puente en $bridge; Vidorq no podra hablar con Resolve."
}

# 1. El puntero. Es lo unico que sabe donde vive Vidorq.
$confDir = Join-Path $env:APPDATA "Vidorq"
if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Path $confDir | Out-Null }
# Sin la ruta de la app a proposito: se busca al hacer clic, porque normalmente
# se compila despues de que la extension ya este en el menu.
$conf = [ordered]@{ home = $home_; bridge = $bridge; python = $python }
# Sin BOM a proposito: Set-Content -Encoding utf8 lo mete y json.load de Python lo rechaza.
$sinBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $confDir "resolve.json"), ($conf | ConvertTo-Json), $sinBom)
Write-Host "Configuracion escrita en $confDir\resolve.json"

# 2. La unica entrada del menu.
Copy-Item (Join-Path $PSScriptRoot "Vidorq.py") (Join-Path $scripts "Vidorq.py") -Force
Write-Host "Instalado: Workspace > Scripts > Vidorq"

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
