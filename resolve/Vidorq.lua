--[[
Vidorq, desde el menu de DaVinci Resolve GRATIS 21.1 o posterior.

Trae a tu proyecto abierto el ultimo video que Vidorq ha editado, y lo pone al
final del timeline. Se lanza con Workspace > Scripts > Vidorq.

Por que existe, y por que en Lua y no en Python:
DaVinci Resolve 21.1 gratis dejo de ejecutar scripts de Python (verificado el
2026-09-21 en la guia de scripting que trae la instalacion). Vidorq.py sigue en
su sitio, pero el menu ya no lo ensena. Lua SI se ejecuta, pero capado: no puede
leer archivos, lanzar programas, ni abrir conexiones. Lo que si puede es lo que
hace falta aqui: importar un video al Media Pool y ponerlo en el timeline.

Como sabe cual es tu ultimo video, si no puede leer archivos: no lo busca. El
motor de Vidorq REESCRIBE este archivo al terminar cada edicion, con la ruta de
ese video metida abajo, en RUTA. DaVinci lee el contenido del script cada vez que
lo pulsas, asi que siempre trae el ultimo.

No borra nada, no cambia nada de lo que ya tienes en el timeline: solo AÑADE el
video al final. Si todavia no has editado nada, no hace nada.
--]]

-- La escribe el motor de Vidorq. Vacia = todavia no hay ningun video editado.
local RUTA = "__VIDEO__"

if RUTA == "" or RUTA == "__VIDEO__" then
    return
end

local ok, err = pcall(function()
    local r = resolve or Resolve()
    local pm = r:GetProjectManager()
    local project = pm:GetCurrentProject()
    if not project then
        return
    end
    local pool = project:GetMediaPool()
    local clips = r:GetMediaStorage():AddItemsToMediaPool(RUTA)
    if not clips or #clips == 0 then
        return
    end
    -- Si no hay ningun timeline abierto, se crea uno, en vez de dejar el video
    -- suelto en el Media Pool donde no se ve que ha llegado.
    if not project:GetCurrentTimeline() then
        pool:CreateEmptyTimeline("Vidorq")
    end
    pool:AppendToTimeline(clips)
    pm:SaveProject()
end)
