' 隐藏命令行窗口启动程序
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c """ & WshShell.CurrentDirectory & "\.venv\Scripts\python.exe"" """ & WshShell.CurrentDirectory & "\My-Video Generator.py""", 0, False
Set WshShell = Nothing
