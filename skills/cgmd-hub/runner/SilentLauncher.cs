// ===========================================================================
// CGMDHub - silent (window-less) launcher for the desktop hub.
//
// Compiled to a Windows GUI executable (/target:winexe) so that NOTHING is
// ever drawn on screen:
//
//     csc.exe /nologo /target:winexe /out:CGMDHub.exe SilentLauncher.cs
//
// Usage:
//     CGMDHub.exe --script C:\cgmd\0fuye\skills\cgmd-hub\runner\Invoke-CgmdPoll.ps1
//                 [--args "-ConfigPath ..."] [--log C:\...\hub-runner.log]
//                 [--wait]
//
//     CGMDHub.exe --exe C:\Program Files\Git\cmd\git.exe --args "status" --cwd C:\repo
//
// Everything is launched with UseShellExecute = false and CreateNoWindow = true,
// so the child process inherits no console and cannot flash a black window.
// ===========================================================================
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class CgmdHubSilent
{
    private static string _logPath;
    private static readonly object _sync = new object();

    private static void WriteLog(string message)
    {
        string line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message;
        lock (_sync)
        {
            try
            {
                if (!string.IsNullOrEmpty(_logPath))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(_logPath));
                    File.AppendAllText(_logPath, line + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch
            {
                // never fail because of logging
            }
        }
        Console.Error.WriteLine(line);
    }

    private static void Print(string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        WriteLog(text.TrimEnd());
    }

    private static ProcessStartInfo BuildPowerShell(string script, string extraArgs)
    {
        string exe = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(exe))
        {
            exe = "powershell.exe";
        }
        var psi = new ProcessStartInfo();
        psi.FileName = exe;
        psi.Arguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File \""
            + script + "\" " + (extraArgs ?? string.Empty);
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.RedirectStandardInput = false;
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;
        if (!string.IsNullOrEmpty(Path.GetDirectoryName(script)))
        {
            psi.WorkingDirectory = Path.GetDirectoryName(script);
        }
        return psi;
    }

    private static ProcessStartInfo BuildGeneric(string exe, string extraArgs, string cwd)
    {
        var psi = new ProcessStartInfo();
        psi.FileName = exe;
        psi.Arguments = extraArgs ?? string.Empty;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;
        if (!string.IsNullOrEmpty(cwd)) psi.WorkingDirectory = cwd;
        return psi;
    }

    public static int Main(string[] args)
    {
        string script = null;
        string exe = null;
        string extraArgs = null;
        string cwd = null;
        bool wait = false;

        try
        {
            for (int i = 0; i < args.Length; i++)
            {
                switch (args[i].ToLowerInvariant())
                {
                    case "--script": script = args[++i]; break;
                    case "--exe": exe = args[++i]; break;
                    case "--args": extraArgs = args[++i]; break;
                    case "--log": _logPath = args[++i]; break;
                    case "--cwd": cwd = args[++i]; break;
                    case "--wait": wait = true; break;
                    case "-h":
                    case "--help":
                        Console.Error.WriteLine("CGMDHub.exe --script <ps1> | --exe <path> [--args \"...\"] [--log <file>] [--cwd <dir>] [--wait]");
                        return 0;
                }
            }
        }
        catch (IndexOutOfRangeException)
        {
            // a flag was given without its value: fail quietly instead of crashing
            return 2;
        }

        if (string.IsNullOrEmpty(script) && string.IsNullOrEmpty(exe))
        {
            Console.Error.WriteLine("nothing to run: give --script or --exe");
            return 2;
        }

        try
        {
            ProcessStartInfo psi = string.IsNullOrEmpty(script)
                ? BuildGeneric(exe, extraArgs, cwd)
                : BuildPowerShell(script, extraArgs);

            using (var process = new Process())
            {
                process.StartInfo = psi;
                process.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { Print(e.Data); };
                process.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { Print(e.Data); };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (wait)
                {
                    process.WaitForExit();
                    WriteLog("child exited with " + process.ExitCode);
                    return process.ExitCode;
                }
                process.WaitForExit(2000);
                return 0;
            }
        }
        catch (Exception ex)
        {
            WriteLog("fatal: " + ex.GetType().Name + ": " + ex.Message);
            return 1;
        }
    }
}
