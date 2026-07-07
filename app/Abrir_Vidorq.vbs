' Vidorq - lanzador facil de abrir, sin ventana de consola.
' Arranca el motor local (si no esta ya corriendo) y la app en modo dev,
' que compila siempre desde el codigo actual: se actualiza sola cada vez
' que Munir/Claude editen el proyecto, sin tener que reinstalar nada.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)

' 1) Motor local (puerto 9877) - lo arranca oculto si no responde ya
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP")
http.Open "GET", "http://127.0.0.1:9877/health", False
http.Send()
engineUp = (Err.Number = 0) And (http.Status = 200)
On Error Goto 0

If Not engineUp Then
  shell.Run "cmd /c """ & root & "\..\engine\start_engine.bat""", 0, False
End If

' 2) La app en modo dev (compila Rust la primera vez; luego arranca rapido)
shell.CurrentDirectory = root
shell.Run "cmd /c pnpm tauri dev", 0, False
