' ===========================================================================
' CgmdPoll.vbs - zero-window entry point of the CGMD desktop hub poller.
'
' wscript.exe is a GUI-subsystem host: it NEVER opens a console window, so
' the 60 s scheduled task produces no black frame at all, not even a flicker.
' It prefers the compiled CGMDHub.exe (/target:winexe) and falls back to a
' hidden powershell.exe when the wrapper has not been built yet.
'
' Registered by Register-CgmdHubTask.ps1 as:
'     wscript.exe "<...>\CgmdPoll.vbs"
' ===========================================================================
Option Explicit

Dim fso, shell, here, wrapper, ps1, cmd, logDir, logFile
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
wrapper = here & "\CGMDHub.exe"
ps1 = here & "\Invoke-CgmdPoll.ps1"

If Not fso.FileExists(ps1) Then
    WScript.Quit 2
End If

If fso.FileExists(wrapper) Then
    cmd = """" & wrapper & """ --script """ & ps1 & """"
Else
    cmd = "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass" & _
          " -WindowStyle Hidden -File """ & ps1 & """"
End If

' 0 = hidden window, False = do not wait (wscript exits immediately)
shell.Run cmd, 0, False
WScript.Quit 0
