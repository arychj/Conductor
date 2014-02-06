using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

using ActiveUp.Net.Mail;

namespace Conductor {
    class Program {
        private static Config _config;

        private const int BN_CLICKED = 245;

        [DllImport("User32.dll")]
        public static extern Int32 FindWindow(String lpClassName, String lpWindowName);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        public static extern int SendMessage(int hWnd, int msg, int wParam, IntPtr lParam);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern IntPtr FindWindowEx(IntPtr parentHandle, IntPtr childAfter, string className, string windowTitle);

        public static void Main(string[] args) {
            if(args.Length > 0)
                _config = new Config(args[0]);
            else
                _config = new Config(string.Format("{0}/config.xml", Path.GetDirectoryName(Assembly.GetExecutingAssembly().GetName().CodeBase)));

            if(bool.Parse(_config["//actions/download"]))
                DownloadEpisodes();

            if (bool.Parse(_config["//actions/discover"]))
                DiscoverEpisodes();

            if (bool.Parse(_config["//actions/move"]))
                MoveProcessedEpisodes();

            if (bool.Parse(_config["//actions/cleanup"]))
                Cleanup();

            if (bool.Parse(_config["//settings/debug"]))
                Console.ReadLine();
        }

        private static void DownloadEpisodes() {
            Regex rEpisodeLink = new Regex(_config["//regex/episodedownloadlink"]);
            FlagCollection seenflag = new FlagCollection() { "Seen" };
            Message message;
            string body;

            Console.WriteLine("Looking for new episodes...");

            Console.Write("  Connecting to email... ");
            Imap4Client imap = new Imap4Client();
            imap.ConnectSsl(_config["//email/host"], int.Parse(_config["//email/port"]));
            imap.Login(_config["//email/username"], _config["//email/password"]);
            Console.WriteLine("done.");

            Console.WriteLine("  Searching for new Season Pass notifications... ");
            Mailbox inbox = imap.SelectMailbox(_config["//itunes/seasonpass/inbox"]);
            int[] messageids = inbox.Search("UNSEEN");
            foreach (int messageid in messageids) {
                message = inbox.Fetch.MessageObject(messageid);
                inbox.RemoveFlags(messageid, seenflag);

                if (message.From.Email == _config["//itunes/seasonpass/from"]) {
                    body = message.BodyText.Text.Replace("=\r\n", string.Empty).Replace("=3D", "=");

                    if (body.Contains(_config["//itunes/seasonpass/ident"])) {
                        Match match = rEpisodeLink.Match(body);

                        if (match.Success) {
                            Console.WriteLine("    Found new episode of '{0}' Season {1}... ", match.Groups["seriesname"].Value, match.Groups["seasonnumber"].Value);

                            Console.Write("      Launching downloader... ");
                            Process process = System.Diagnostics.Process.Start(_config["//settings/browser"], match.Groups["downloadlink"].Value);
                            System.Threading.Thread.Sleep(int.Parse(_config["//delays/browserdownload"]) * 1000);
                            if (!process.HasExited)
                                process.Kill();
                            Console.WriteLine("done.");

                            Console.Write("      Starting download... ");
                            int hwnd = FindWindow(null, _config["//itunes/windowname"]);
                            if (hwnd != 0) {
                                IntPtr hwndChild = FindWindowEx((IntPtr)hwnd, IntPtr.Zero, "Button", _config["//itunes/downloadhandle"]);
                                SendMessage((int)hwndChild, BN_CLICKED, 0, IntPtr.Zero);
                                Console.WriteLine("done.");
                            }
                            else {
                                Console.WriteLine("unable to locate iTunes handle.");
                            }

                            inbox.AddFlags(messageid, seenflag);

                            System.Threading.Thread.Sleep(int.Parse(_config["//delays/downloadlaunch"]) * 1000);
                        }
                    }
                }
            }

            Console.WriteLine("  done.");
            Console.WriteLine("done.");
        }

        private static void DiscoverEpisodes() {
            string tempName;

            Console.WriteLine("\nDiscovering...");
            DirectoryInfo source = new DirectoryInfo(_config["//paths/source"]);
            foreach (DirectoryInfo series in source.GetDirectories()) {
                foreach (DirectoryInfo season in series.GetDirectories()) {
                    foreach (FileInfo episode in season.GetFiles("*.m4v")) {
                        Console.WriteLine("  Found '{0}/{1}'...", series.Name, episode.Name);
                        tempName = _config["//settings/destinationformat"].Build(new Dictionary<string, string>(){
                            {"DestinationPath", _config["//paths/processing"]},
                            {"SeriesName", series.Name},
                            {"SeasonName", season.Name},
                            {"EpisodeName", episode.Name}
                        });

                        Console.Write("    Moving to processing directory... ");
                        File.Create(string.Format(_config["//settings/timelockformat"], tempName, DateTime.Now));
                        episode.MoveTo(tempName);
                        Console.WriteLine("done.");

                        ProcessEpisode(tempName);
                    }
                }
            }

            Console.WriteLine("done.");
        }

        private static void ProcessEpisode(string sFile) {
            if (_config["//paths/processor"].Length > 0) {
                FileInfo file = new FileInfo(sFile);

                Console.Write("    Processing '{0}'...", file.Name);
                Process process = System.Diagnostics.Process.Start(_config["//paths/processor"], string.Format(_config["//processor/arguments"], file.FullName));
                Thread.Sleep(int.Parse(_config["//delays/processingstartup"]) * 1000);
                Console.WriteLine("done.");
            }
        }

        private static void MoveProcessedEpisodes() {
            Regex rexTimelock = new Regex(_config["//regex/timelock"]);
            FileInfo timelockFile;
            DateTime timelock;
            Match match;

            Console.WriteLine("\nMoving processed episodes...");
            DirectoryInfo processing = new DirectoryInfo(_config["//paths/processing"]);
            foreach (FileInfo file in processing.GetFiles(_config["//settings/filefilter"])) {
                Console.WriteLine("  Found '{0}'... ", file.Name);
                if (processing.GetFiles(string.Format("{0}.tmp", file.Name)).Length == 0) {
                    timelockFile = processing.GetFiles(string.Format("{0}*", file.Name)).Where(f => rexTimelock.Match(f.Name).Success).FirstOrDefault();

                    if (timelockFile != default(FileInfo)) {
                        match = rexTimelock.Match(timelockFile.Name);
                        if (match.Success) {
                            timelock = new DateTime(
                                            int.Parse(match.Groups[1].Value),
                                            int.Parse(match.Groups[2].Value),
                                            int.Parse(match.Groups[3].Value),
                                            int.Parse(match.Groups[4].Value),
                                            int.Parse(match.Groups[5].Value),
                                            int.Parse(match.Groups[6].Value));

                            if (DateTime.Now - timelock > (new TimeSpan(0, 0, int.Parse(_config["//delays/postprocess"])))) {
                                Console.Write("    Moving to destination... ");
                                file.MoveTo(string.Format(@"{0}\{1}", _config["//paths/destination"], file.Name));
                                timelockFile.Delete();
                                Console.WriteLine("done.");
                            }
                            else
                                Console.WriteLine("timelock has not expired.");
                        }
                        else
                            Console.WriteLine("no timelock match.");
                    }
                    else
                        Console.WriteLine("no timelock.");
                }
                else
                    Console.WriteLine("not finished processing.");
            }

            Console.WriteLine("done.");
        }

        private static void Cleanup() {
            Console.WriteLine("\nCleaning up... ");
            Process[] processes = System.Diagnostics.Process.GetProcessesByName(_config["//processor/processname"]);
            foreach (Process process in processes) {
                Console.Write("  Found {0}:{1:yyyy-MM-dd HH:mm:ss} ({2})... ", _config["//processor/processname"], process.StartTime, process.WorkingSet64);
                if (process.StartTime < DateTime.Now.Subtract(new TimeSpan(0, 0, int.Parse(_config["//processor/killtimethreshold"]))) && process.WorkingSet64 < int.Parse(_config["//processor/killmemorythreshold"]) * 1024 * 1024) {
                    Console.Write("killing... ");
                    if (!process.HasExited)
                        process.Kill();
                    Console.WriteLine("done.");
                }
                else
                    Console.WriteLine("skipping.");

            }
            Console.WriteLine("done.");
        }
    }
}