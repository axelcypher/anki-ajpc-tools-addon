using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using System.Threading;

namespace AjpcRestartHelper
{
    internal static class Program
    {
        private sealed class Args
        {
            public int ParentPid;
            public string Target = "";
            public int DelayMs = 700;
            public int MaxWaitMs = 120000;
            public readonly List<string> TargetArgs = new List<string>();
        }

        private static int Main(string[] argv)
        {
            Args args;
            try
            {
                args = ParseArgs(argv);
            }
            catch
            {
                return 1;
            }

            if (!WaitForParentExit(args.ParentPid, args.MaxWaitMs))
            {
                return 2;
            }

            if (args.DelayMs > 0)
            {
                Thread.Sleep(args.DelayMs);
            }

            try
            {
                StartTarget(args.Target, args.TargetArgs);
                return 0;
            }
            catch
            {
                return 3;
            }
        }

        private static Args ParseArgs(string[] argv)
        {
            var a = new Args();
            for (var i = 0; i < argv.Length; i++)
            {
                var key = argv[i] ?? "";
                if (key == "--parent-pid" && i + 1 < argv.Length)
                {
                    a.ParentPid = int.Parse(argv[++i]);
                }
                else if (key == "--target" && i + 1 < argv.Length)
                {
                    a.Target = argv[++i] ?? "";
                }
                else if (key == "--delay-ms" && i + 1 < argv.Length)
                {
                    a.DelayMs = Math.Max(0, int.Parse(argv[++i]));
                }
                else if (key == "--max-wait-ms" && i + 1 < argv.Length)
                {
                    a.MaxWaitMs = Math.Max(0, int.Parse(argv[++i]));
                }
                else if (key == "--arg" && i + 1 < argv.Length)
                {
                    a.TargetArgs.Add(argv[++i] ?? "");
                }
            }

            if (a.ParentPid <= 0)
            {
                throw new ArgumentException("parent pid missing");
            }
            if (string.IsNullOrWhiteSpace(a.Target))
            {
                throw new ArgumentException("target missing");
            }
            return a;
        }

        private static bool WaitForParentExit(int pid, int maxWaitMs)
        {
            var deadline = DateTime.UtcNow.AddMilliseconds(Math.Max(0, maxWaitMs));
            while (DateTime.UtcNow < deadline)
            {
                if (!IsProcessAlive(pid))
                {
                    return true;
                }
                Thread.Sleep(100);
            }
            return !IsProcessAlive(pid);
        }

        private static bool IsProcessAlive(int pid)
        {
            try
            {
                using (var p = Process.GetProcessById(pid))
                {
                    return !p.HasExited;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void StartTarget(string target, List<string> args)
        {
            var psi = new ProcessStartInfo
            {
                FileName = target,
                Arguments = BuildArguments(args),
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = SafeWorkingDirectory(target)
            };
            Process.Start(psi);
        }

        private static string SafeWorkingDirectory(string target)
        {
            try
            {
                var dir = System.IO.Path.GetDirectoryName(target);
                return string.IsNullOrWhiteSpace(dir) ? Environment.CurrentDirectory : dir;
            }
            catch
            {
                return Environment.CurrentDirectory;
            }
        }

        private static string BuildArguments(List<string> args)
        {
            var sb = new StringBuilder();
            for (var i = 0; i < args.Count; i++)
            {
                if (i > 0)
                {
                    sb.Append(' ');
                }
                sb.Append(QuoteArgument(args[i] ?? ""));
            }
            return sb.ToString();
        }

        // Windows command-line quoting compatible with CreateProcess parsing.
        private static string QuoteArgument(string value)
        {
            if (value.Length == 0)
            {
                return "\"\"";
            }

            var hasSpace = false;
            for (var i = 0; i < value.Length; i++)
            {
                var c = value[i];
                if (char.IsWhiteSpace(c) || c == '"')
                {
                    hasSpace = true;
                    break;
                }
            }
            if (!hasSpace)
            {
                return value;
            }

            var sb = new StringBuilder();
            sb.Append('"');
            var backslashes = 0;
            for (var i = 0; i < value.Length; i++)
            {
                var c = value[i];
                if (c == '\\')
                {
                    backslashes++;
                    continue;
                }
                if (c == '"')
                {
                    sb.Append('\\', backslashes * 2 + 1);
                    sb.Append('"');
                    backslashes = 0;
                    continue;
                }
                if (backslashes > 0)
                {
                    sb.Append('\\', backslashes);
                    backslashes = 0;
                }
                sb.Append(c);
            }
            if (backslashes > 0)
            {
                sb.Append('\\', backslashes * 2);
            }
            sb.Append('"');
            return sb.ToString();
        }
    }
}
