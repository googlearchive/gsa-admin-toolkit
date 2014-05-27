using System;
using System.Text.RegularExpressions;
using System.Xml;
using System.Security.Cryptography;

class sign
{
	static string Hash(string password, string texttohash)
	{
		byte[] pass = System.Text.Encoding.ASCII.GetBytes(password);
		byte[] text = System.Text.Encoding.ASCII.GetBytes(texttohash);

		String hash = "";
		foreach (byte b in (new HMACSHA1(pass).ComputeHash(text))) {
			hash += String.Format("{0:x2}", b);
		}
		return hash;
	}

	public static int Main(string[] args)
	{
		if (args.Length != 2)
		{
			Console.WriteLine("gsasign.exe - signs configuration XML file for import on the GSA");
			Console.WriteLine();
			Console.WriteLine("Usage:");
			Console.WriteLine("\tgsasign config.xml PASSWORD > resigned.xml");
			Console.WriteLine();
			Console.WriteLine();
			return 1;
		}

		string password = args[1];

		XmlDocument x = new XmlDocument();
		x.PreserveWhitespace = true;
		x.Load(args[0]);

		// <uam_dir> is not considered for hash computation
		XmlNode uam_dir = x.SelectSingleNode("eef/config/globalparams/uam_dir");
		uam_dir.RemoveAll();

		// we can't remove <uam_dir> using standard XML manipulation only to make sure, we remove surrounding whitespace as well
		uam_dir.ParentNode.InnerXml = Regex.Replace(uam_dir.ParentNode.InnerXml, @"^ *<uam_dir></uam_dir>\n", "", RegexOptions.Multiline);

		// <uar_data> is replaced with HMAC of itself
		XmlNode uar_tag = x.SelectSingleNode("eef/config/globalparams/uar_data").ChildNodes[0];
		String uar_data = uar_tag.Value.TrimStart('\n').TrimEnd(' ');
		uar_tag.Value = "\n/tmp/tmp_uar_data_dir," + Hash(password, uar_data) + "\n          ";

		XmlNode n = x.SelectSingleNode("eef/config");
		String signature = Hash(password, n.OuterXml);

		// we reload the document - the edits we've done above are only for signature computation
		x.Load(args[0]);
		n = x.SelectSingleNode("eef/config");

		Console.Write("<?xml version=\"1.0\" encoding=\"UTF-8\" ?>\n<eef>\n  ");
		Console.Write(n.OuterXml);
		Console.WriteLine("\n  <signature><![CDATA[\n" + signature + "\n  " + "]]></signature>\n</eef>");
		return 0;
	}
}
