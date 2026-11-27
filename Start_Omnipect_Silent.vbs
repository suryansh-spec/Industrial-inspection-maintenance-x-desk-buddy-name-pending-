Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
RootDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BackendDir = RootDir & "\deskbuddy_backend"
UserProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")

If Not FSO.FileExists(BackendDir & "\.env") Then
    If FSO.FileExists(BackendDir & "\.env.example") Then
        FSO.CopyFile BackendDir & "\.env.example", BackendDir & "\.env"
    End If
End If

Candidates = Array( _
    RootDir & "\.venv\Scripts\python.exe", _
    BackendDir & "\.venv\Scripts\python.exe", _
    UserProfile & "\.conda\envs\inspection\python.exe", _
    UserProfile & "\miniconda3\envs\inspection\python.exe", _
    UserProfile & "\anaconda3\envs\inspection\python.exe", _
    "C:\ProgramData\miniconda3\envs\inspection\python.exe", _
    "C:\ProgramData\anaconda3\envs\inspection\python.exe" _
)

PythonExe = "python"
For Each Candidate In Candidates
    If FSO.FileExists(Candidate) Then
        PythonExe = Candidate
        Exit For
    End If
Next

WshShell.CurrentDirectory = BackendDir
WshShell.Run """" & PythonExe & """ -m app.main", 0, False
