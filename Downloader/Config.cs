using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Xml;

namespace Conductor {
    internal class Config {
        private XmlDocument _config;

        internal Config(string file) {
            _config = new XmlDocument();
            _config.Load(file);
        }

        internal string this[string path] {
            get {
                XmlNode node = _config.SelectSingleNode(path);
                return (node == null ? null : node.InnerText);
            }
        }
    }
}
