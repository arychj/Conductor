using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Conductor {
    internal static class Extensions {
        public static string Build(this string s, Dictionary<string, string> p) {
            foreach (KeyValuePair<string, string> kvp in p)
                s = s.Replace("{" + kvp.Key + "}", kvp.Value);

            return s;
        }
    }
}
