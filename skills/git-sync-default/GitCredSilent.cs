using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace ArenaDeskSilentCred
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            try
            {
                if (args == null || args.Length == 0 || args[0] != "get")
                {
                    return 0;
                }

                Dictionary<string, string> input = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                using (Stream stdin = Console.OpenStandardInput())
                {
                    if (stdin != null && stdin != Stream.Null)
                    {
                        using (StreamReader sr = new StreamReader(stdin, Encoding.UTF8))
                        {
                            string line;
                            while ((line = sr.ReadLine()) != null)
                            {
                                if (line.Length == 0) break;
                                int eq = line.IndexOf('=');
                                if (eq > 0)
                                {
                                    input[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
                                }
                            }
                        }
                    }
                }

                string host = input.ContainsKey("host") ? input["host"] : "";
                if (!string.Equals(host, "github.com", StringComparison.OrdinalIgnoreCase))
                {
                    return 0;
                }

                string account = ResolveDesiredAccount(input);
                string token = GetCachedOrFreshToken(account);
                if (string.IsNullOrEmpty(token) && !string.Equals(account, "mqgg5630-cyber", StringComparison.OrdinalIgnoreCase))
                {
                    account = "mqgg5630-cyber";
                    token = GetCachedOrFreshToken(account);
                }
                if (string.IsNullOrEmpty(token))
                {
                    return 0;
                }

                string payload = "protocol=https\nhost=github.com\nusername=" + account + "\npassword=" + token + "\n\n";
                byte[] outBytes = Encoding.ASCII.GetBytes(payload);
                using (Stream stdout = Console.OpenStandardOutput())
                {
                    if (stdout != null && stdout != Stream.Null)
                    {
                        stdout.Write(outBytes, 0, outBytes.Length);
                        stdout.Flush();
                    }
                }
                return 0;
            }
            catch
            {
                return 0;
            }
        }

        private static string ResolveDesiredAccount(Dictionary<string, string> input)
        {
            string user = input.ContainsKey("username") ? input["username"] : "";
            if (!string.IsNullOrEmpty(user) && !string.Equals(user, "x-access-token", StringComparison.OrdinalIgnoreCase))
            {
                return user;
            }
            string path = input.ContainsKey("path") ? input["path"] : "";
            if (!string.IsNullOrEmpty(path))
            {
                int slash = path.IndexOf('/');
                string owner = slash > 0 ? path.Substring(0, slash) : path;
                if (string.Equals(owner, "shaohuawen03-cyber", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(owner, "hukeying85-ux", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(owner, "mqgg5630-cyber", StringComparison.OrdinalIgnoreCase))
                {
                    return owner;
                }
            }
            return "mqgg5630-cyber";
        }

        private static string GetCacheFile(string account)
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                @"ArenaDesk\cred-cache"
            );
            Directory.CreateDirectory(dir);
            string safe = account.Replace("/", "_").Replace("\\", "_").Replace(":", "_");
            return Path.Combine(dir, "gh_" + safe + ".dpapi");
        }

        private static string GetCachedOrFreshToken(string account)
        {
            string cacheFile = GetCacheFile(account);
            try
            {
                if (File.Exists(cacheFile))
                {
                    TimeSpan age = DateTime.UtcNow - File.GetLastWriteTimeUtc(cacheFile);
                    if (age.TotalMinutes < 30)
                    {
                        byte[] enc = File.ReadAllBytes(cacheFile);
                        byte[] dec = ProtectedData.Unprotect(enc, null, DataProtectionScope.CurrentUser);
                        string cached = Encoding.UTF8.GetString(dec).Trim();
                        if (!string.IsNullOrEmpty(cached))
                        {
                            return cached;
                        }
                    }
                }
            }
            catch { }

            string fresh = QueryGhTokenSilent(account);
            if (!string.IsNullOrEmpty(fresh))
            {
                try
                {
                    byte[] raw = Encoding.UTF8.GetBytes(fresh);
                    byte[] enc = ProtectedData.Protect(raw, null, DataProtectionScope.CurrentUser);
                    File.WriteAllBytes(cacheFile, enc);
                }
                catch { }
            }
            return fresh;
        }

        private static string QueryGhTokenSilent(string account)
        {
            string ghExe = @"C:\Program Files\GitHub CLI\gh.exe";
            if (!File.Exists(ghExe))
            {
                ghExe = "gh.exe";
            }
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(ghExe, "auth token -h github.com -u " + account)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                psi.EnvironmentVariables["GH_PROMPT_DISABLED"] = "1";
                using (Process p = Process.Start(psi))
                {
                    if (p == null) return "";
                    string stdout = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(6000);
                    if (p.ExitCode == 0 && !string.IsNullOrEmpty(stdout))
                    {
                        return stdout.Trim();
                    }
                }
            }
            catch { }
            return "";
        }
    }
}
