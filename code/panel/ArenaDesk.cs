using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace ArenaDeskApp
{
    static class Program
    {
        private const string BaseUrl = "http://127.0.0.1:18765/";
        private static NotifyIcon tray;

        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool IsIconic(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool BringWindowToTop(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);

        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

        private static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        private static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
        private const uint SWP_NOSIZE = 0x0001;
        private const uint SWP_NOMOVE = 0x0002;
        private const uint SWP_SHOWWINDOW = 0x0040;
        private const int SW_RESTORE = 9;
        private const int SW_SHOW = 5;

        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string appDir = ResolveAppDir();
            bool bootDefault = IsBootEnabledByDefault(appDir);
            string initialHash = bootDefault ? "#boot" : "";

            if (args != null && args.Length > 0 && !string.IsNullOrEmpty(args[0]))
            {
                string a0 = args[0].Trim();
                if (a0 == "--noboot") initialHash = "#overview";
                else if (a0.StartsWith("#")) initialHash = a0;
                else if (a0 == "--boot" || a0 == "boot") initialHash = "#boot";
                else if (a0.StartsWith("--")) initialHash = "#" + a0.Substring(2);
            }

            bool createdNew;
            using (Mutex mutex = new Mutex(true, @"Local\ArenaDeskDesktopShellV2", out createdNew))
            {
                EnsureBackendReady(appDir);
                OpenAppWindow(appDir, initialHash);

                if (!createdNew)
                {
                    return;
                }

                Icon appIcon = SystemIcons.Application;
                string icoPath = Path.Combine(appDir, @"assets\ArenaDesk.ico");
                try
                {
                    if (File.Exists(icoPath))
                    {
                        appIcon = new Icon(icoPath);
                    }
                    else
                    {
                        appIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                    }
                }
                catch { }

                ContextMenuStrip menu = new ContextMenuStrip();
                menu.Items.Add("\u6253\u5f00 Arena Desk v2.8 \u4e3b\u7a97\u53e3 (\u542b\u5f00\u673a\u52a8\u753b)", null, (s, e) => OpenAppWindow(appDir, IsBootEnabledByDefault(appDir) ? "#boot" : ""));
                menu.Items.Add("\u76f4\u63a5\u8fdb\u5165\u4e3b\u9762\u677f (\u8df3\u8fc7\u52a8\u753b)", null, (s, e) => OpenAppWindow(appDir, "#overview"));
                menu.Items.Add("\ud83d\udcf1 \u5b89\u5353\u624b\u673a App \u626b\u7801\u5b89\u88c5\u4e0e\u597d\u4e86\u5417 (#beacon)", null, (s, e) => OpenAppWindow(appDir, "#beacon"));
                menu.Items.Add("\ud83d\udc96 \u7231\u60c5\u4e0e\u7eaa\u5ff5\u7a7a\u95f4 (#love)", null, (s, e) => OpenAppWindow(appDir, "#love"));
                menu.Items.Add("\ud83d\udc19 \u4e09\u8d26\u53f7\u72ec\u7acb\u5206\u8231\u76d1\u63a7 (#gh)", null, (s, e) => OpenAppWindow(appDir, "#gh"));
                menu.Items.Add("\ud83e\ude9f \u4e00\u952e\u4e09\u8054\u6253\u5f00\u4e09\u8d26\u53f7 Arena \u4e13\u7a97", null, (s, e) => OpenArenaSlotWindow(appDir, "ALL"));
                menu.Items.Add("   \ud83d\udcbb S1 \u4e3b\u63a7 Arena (mqgg5630)", null, (s, e) => OpenArenaSlotWindow(appDir, "S1"));
                menu.Items.Add("   \ud83e\uddec S2 \u8d85\u7b97 Arena (shaohuawen03)", null, (s, e) => OpenArenaSlotWindow(appDir, "S2"));
                menu.Items.Add("   \ud83d\udda5\ufe0f S3 \u7c97\u7c92\u5316 Arena (hukeying85)", null, (s, e) => OpenArenaSlotWindow(appDir, "S3"));
                menu.Items.Add("\ud83c\udf93 \u6bd5\u4e1a\u8bba\u6587\u4e00\u952e\u6539\u683c\u5f0f (Lark-Formatter)", null, (s, e) => OpenAppWindow(appDir, "#thesis"));
                menu.Items.Add("\ud83c\udfac \u6f14\u793a dsh-video-skin \u5f00\u673a\u52a8\u753b (#boot)", null, (s, e) => OpenAppWindow(appDir, "#boot"));
                menu.Items.Add(new ToolStripSeparator());
                menu.Items.Add("\u663e\u793a / \u9690\u85cf \u684c\u9762\u5ba0\u7269 (Ctrl+Alt+H)", null, (s, e) => RunPsSilent(Path.Combine(appDir, "pet_toggle.ps1")));
                menu.Items.Add(new ToolStripSeparator());
                menu.Items.Add("\u9000\u51fa\u6258\u76d8\u56fe\u6807 (\u57fa\u5ea7\u7ee7\u7eed\u503c\u5b88)", null, (s, e) =>
                {
                    tray.Visible = false;
                    Application.Exit();
                });

                tray = new NotifyIcon
                {
                    Icon = appIcon,
                    Text = "Arena Desk v2.8 \u00b7 \u4e09\u8d26\u53f7\u534f\u540c\u00b7\u53cc\u673a\u81ea\u6108\u4e0e\u7c97\u7c92\u5316\u63a7\u5236\u4e2d\u5fc3",
                    ContextMenuStrip = menu,
                    Visible = true
                };
                tray.DoubleClick += (s, e) => OpenAppWindow(appDir, IsBootEnabledByDefault(appDir) ? "#boot" : "");

                Application.Run();
            }
        }

        private static string ResolveAppDir()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            if (File.Exists(Path.Combine(baseDir, "server.py"))) return baseDir;
            string[] roots = new string[]
            {
                @"E:\0apps\ArenaDesk",
                @"D:\0apps\ArenaDesk",
                @"C:\0apps\ArenaDesk",
                @"C:\cgmd\0fuye\code\panel"
            };
            foreach (string r in roots)
            {
                if (File.Exists(Path.Combine(r, "server.py"))) return r;
            }
            return baseDir;
        }

        private static bool IsBootEnabledByDefault(string appDir)
        {
            try
            {
                string p = Path.Combine(appDir, @"data\appearance.json");
                if (File.Exists(p))
                {
                    string txt = File.ReadAllText(p, Encoding.UTF8);
                    if (txt.IndexOf("\"boot_enabled\": false", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        txt.IndexOf("\"boot_enabled\":false", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return false;
                    }
                }
            }
            catch { }
            return true;
        }

        private static void PromoteWindowToForeground(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return;
            try
            {
                if (IsIconic(hWnd))
                {
                    ShowWindow(hWnd, SW_RESTORE);
                }
                else
                {
                    ShowWindow(hWnd, SW_SHOW);
                }

                IntPtr fg = GetForegroundWindow();
                uint fgThread = 0;
                uint dummyPid;
                if (fg != IntPtr.Zero)
                {
                    fgThread = GetWindowThreadProcessId(fg, out dummyPid);
                }
                uint targetThread = GetWindowThreadProcessId(hWnd, out dummyPid);

                // Z-order topmost pulse guarantees window lifts above background browser even under Windows 11 ForegroundLockTimeout
                SetWindowPos(hWnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
                if (fgThread != 0 && targetThread != 0 && fgThread != targetThread)
                {
                    AttachThreadInput(fgThread, targetThread, true);
                    BringWindowToTop(hWnd);
                    SetForegroundWindow(hWnd);
                    AttachThreadInput(fgThread, targetThread, false);
                }
                else
                {
                    BringWindowToTop(hWnd);
                    SetForegroundWindow(hWnd);
                }
                Thread.Sleep(120);
                SetWindowPos(hWnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
                SetForegroundWindow(hWnd);
            }
            catch { }
        }

        private static IntPtr FindArenaWindow()
        {
            IntPtr found = IntPtr.Zero;
            EnumWindows((hWnd, lParam) =>
            {
                if (!IsWindowVisible(hWnd)) return true;
                StringBuilder sb = new StringBuilder(256);
                if (GetWindowText(hWnd, sb, sb.Capacity) > 0)
                {
                    string title = sb.ToString();
                    if (title.IndexOf("Arena Desk", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        found = hWnd;
                        return false;
                    }
                }
                return true;
            }, IntPtr.Zero);
            return found;
        }

        private static void BringArenaWindowToFrontWithRetry(int maxWaitMs)
        {
            int elapsed = 0;
            while (elapsed < maxWaitMs)
            {
                IntPtr hWnd = FindArenaWindow();
                if (hWnd != IntPtr.Zero)
                {
                    PromoteWindowToForeground(hWnd);
                    Thread.Sleep(350);
                    PromoteWindowToForeground(hWnd);
                    return;
                }
                Thread.Sleep(180);
                elapsed += 180;
            }
        }

        private static bool IsBackendAlive()
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(BaseUrl + "api/bootstrap");
                req.Timeout = 1500;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    return resp.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void EnsureBackendReady(string appDir)
        {
            if (IsBackendAlive()) return;

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("schtasks.exe", "/Run /TN \"arena-desk-panel\"")
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process p = Process.Start(psi);
                if (p != null) p.WaitForExit(3000);
            }
            catch { }

            for (int i = 0; i < 12; i++)
            {
                if (IsBackendAlive()) return;
                Thread.Sleep(500);
            }

            string savedPy = "";
            try
            {
                string pyHintFile = Path.Combine(appDir, @"data\pythonw-path.txt");
                if (File.Exists(pyHintFile))
                {
                    savedPy = File.ReadAllText(pyHintFile, Encoding.UTF8).Trim();
                }
            }
            catch { }

            string userHome = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] pyCandidates = new string[]
            {
                savedPy,
                Path.Combine(appDir, @"python\pythonw.exe"),
                Path.Combine(appDir, @"python\python.exe"),
                @"E:\spider\pythonw.exe",
                @"E:\spider\python.exe",
                @"E:\Miniforge3\pythonw.exe",
                @"E:\miniconda3\pythonw.exe",
                @"C:\ProgramData\Miniforge3\pythonw.exe",
                @"C:\ProgramData\Miniforge3\python.exe",
                @"C:\ProgramData\anaconda3\pythonw.exe",
                @"C:\ProgramData\miniconda3\pythonw.exe",
                Path.Combine(userHome, @"Miniforge3\pythonw.exe"),
                Path.Combine(userHome, @"miniconda3\pythonw.exe"),
                Path.Combine(userHome, @"anaconda3\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python312\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python311\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python310\pythonw.exe"),
                @"D:\Miniforge3\pythonw.exe",
                @"D:\miniconda3\pythonw.exe",
                @"C:\Python312\pythonw.exe",
                @"C:\Python311\pythonw.exe"
            };
            string serverPy = Path.Combine(appDir, "server.py");
            foreach (string py in pyCandidates)
            {
                if (string.IsNullOrEmpty(py) || py.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0)
                    continue;
                if (!File.Exists(py))
                    continue;
                try
                {
                    Process.Start(new ProcessStartInfo(py, "\"" + serverPy + "\"")
                    {
                        WorkingDirectory = appDir,
                        CreateNoWindow = true,
                        UseShellExecute = false,
                        WindowStyle = ProcessWindowStyle.Hidden
                    });
                    for (int k = 0; k < 10; k++)
                    {
                        Thread.Sleep(400);
                        if (IsBackendAlive()) return;
                    }
                }
                catch { }
            }
        }

        private static string FindAppBrowser()
        {
            string[] candidates = new string[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\Edge\Application\msedge.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Google\Chrome\Application\chrome.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Google\Chrome\Application\chrome.exe")
            };
            foreach (string c in candidates)
            {
                if (File.Exists(c)) return c;
            }
            return "";
        }

        private static void OpenAppWindow(string appDir, string hash)
        {
            string url = BaseUrl + (hash ?? "");
            string browser = FindAppBrowser();
            if (!string.IsNullOrEmpty(browser))
            {
                string profileDir = Path.Combine(appDir, @"data\desktop-window-profile");
                Directory.CreateDirectory(profileDir);
                string args = string.Format(
                    "--new-window --app=\"{0}\" --user-data-dir=\"{1}\" --window-size=1520,940 --autoplay-policy=no-user-gesture-required --no-first-run --no-default-browser-check",
                    url, profileDir
                );
                try
                {
                    Process.Start(new ProcessStartInfo(browser, args) { UseShellExecute = false });
                    BringArenaWindowToFrontWithRetry(4800);
                    return;
                }
                catch { }
            }
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                BringArenaWindowToFrontWithRetry(4800);
            }
            catch { }
        }

        private static void OpenArenaSlotWindow(string appDir, string slot)
        {
            string browser = FindAppBrowser();
            if (string.IsNullOrEmpty(browser)) return;
            string[][] defs = new string[][]
            {
                new string[] { "S1", "S1-mqgg5630", "https://arena.ai/" },
                new string[] { "S2", "S2-shaohuawen03", "https://arena.ai/" },
                new string[] { "S3", "S3-hukeying85", "https://arena.ai/" }
            };
            int idx = 0;
            foreach (string[] d in defs)
            {
                if (slot == "ALL" || slot == d[0])
                {
                    string prof = Path.Combine(appDir, Path.Combine("arena-profiles", d[1]));
                    Directory.CreateDirectory(prof);
                    string posArg = slot == "ALL"
                        ? string.Format("--window-position={0},0 --window-size=640,1030", idx * 640)
                        : "--window-size=1280,920";
                    string args = string.Format(
                        "--new-window --app=\"{0}\" --user-data-dir=\"{1}\" {2} --no-first-run --no-default-browser-check",
                        d[2], prof, posArg
                    );
                    try { Process.Start(new ProcessStartInfo(browser, args) { UseShellExecute = false }); } catch { }
                    idx++;
                }
            }
        }

        private static void RunPsSilent(string scriptPath)
        {
            if (!File.Exists(scriptPath)) return;
            try
            {
                Process.Start(new ProcessStartInfo("powershell.exe",
                    "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"" + scriptPath + "\"")
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                });
            }
            catch { }
        }
    }
}
