# Installs the two Vidorq scripts into DaVinci Resolve's Scripts menu.
#
# The bridge itself comes from the davinci-resolve-mcp project; we only rename its
# user-facing tag so the menu entry reads VidorqBridge instead of CursorBridge.
# The folder is shared across Resolve versions, so this works for 20.x and 21.

$ErrorActionPreference = "Stop"

$scripts = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
$bridgeSource = "C:\proyectos\davinci-resolve-mcp\src\CursorBridge.py"
$panelSource = Join-Path $PSScriptRoot "VidorqPanel.py"

if (-not (Test-Path $scripts)) {
    throw "No encuentro la carpeta de scripts de Resolve: $scripts"
}

# Panel
Copy-Item $panelSource (Join-Path $scripts "VidorqPanel.py") -Force
Write-Host "VidorqPanel.py instalado"

# Bridge, renombrado de cara al usuario
if (Test-Path $bridgeSource) {
    (Get-Content $bridgeSource -Raw).Replace("[CursorBridge]", "[VidorqBridge]") |
        Set-Content (Join-Path $scripts "VidorqBridge.py") -Encoding utf8
    Write-Host "VidorqBridge.py instalado"

    # La entrada vieja se aparta, no se borra: dos entradas en el menu confunden.
    $old = Join-Path $scripts "CursorBridge.py"
    if (Test-Path $old) {
        Move-Item $old "$old.bak" -Force
        Write-Host "CursorBridge.py apartado como .bak"
    }
} else {
    Write-Warning "No encuentro el puente en $bridgeSource; solo se instalo el panel."
}

Write-Host ""
Write-Host "Listo. En Resolve: Workspace > Scripts > VidorqBridge (una vez por sesion)"
Write-Host "                   Workspace > Scripts > VidorqPanel  (para editar sin salir)"
