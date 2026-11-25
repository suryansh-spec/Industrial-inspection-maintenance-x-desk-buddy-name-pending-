Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
RootDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BackendDir = RootDir & "\deskbuddy_backend"
PythonExe = "C:\Users\Suryansh3584\.conda\envs\inspection\python.exe"
If Not FSO.FileExists(PythonExe) Then PythonExe = "python"

WshShell.CurrentDirectory = BackendDir
WshShell.Run """" & PythonExe & """ -m app.main", 0, False
