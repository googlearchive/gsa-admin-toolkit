#!/usr/bin/python2.4
#
# http://gsa-admin-toolkit.googlecode.com/svn/trunk/smbcrawler.py
#
# Copyright 2008 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This script is not supported by Google.
# Tested with Python 2.4 on Ubuntu Linux 6.04 and Mac OS X 10.5

"""
Name
   smbcrawler.py

Description:
   Script for crawling Windows File Shares and extract URLs.
   This script uses local smbclient commands.
   The aim is to help Google Search Appliance and Google Mini users
   get their file shares crawled, with several approaches.

Features:
 + crawls as anonymous (guest) or authenticated user.
 + accepts following URL formats: \\\\filer\\share\\ [smb:|unc:]//filer/share/
 + accepts URLs from XML Sitemaps, CSV, plain text files (and partial content)
 + reports mismatch between file size on directory listing and readable size (*)
 + writes in plain text, CSV and XML Sitemap (**)
 + allows to limit directory depth

 (*) In the event of authentication being fine but getting permission denied for
     a file or folder, this script should get NT_STATUS_ACCESS_DENIED from the
     server, but it is suspected some servers might return an empty file.

 (**) See http://www.google.com/webmasters/tools/docs/en/protocol.html

Examples:

 - Crawl everything as guest/anonymous user under smb://filer/share/
   (and on \\host\share\ only \folder\ or only \another\file.txt)

   $ smbcrawler smb://filer/share/ smb://host/share/folder/
   $ smbcrawler smb://host/share/another/file.txt:

   NOTE: trailing slashes are mandatory for directories

 - Crawl with user credentials

   $ smbcrawler --workgroup MyDomain --username bob --password secret \
   > smb://filer/share/private/

 - Take URLs to crawl from a CSV file, specifying field, separator and lines:

   $ smbcrawler --input urls.csv -f1 -s, -L 2,5-14

   For XML Sitemap, -L counts URLs instead of lines.
   This flag is also available for input plain text files.

 - Export report of unreachable URLs to XML Sitemap
   $ smbcrawler -O unreachable.xml -G unreachable smb://filer/share/

 - Export full report to CSV file (will include status and size for each file)
   $ smbcrawler -O denied.csv -G accessdenied,reachable smb://mort.dub/gsa/smb/

 - Read only the first 5 URLs and the nineth:
   $ smbcrawler -I input.xml -L 1-5,9

 - Take all URLs from XML sitemap and save unreachable ones:
   $ smbcrawler -I sitemap.xml -O unreachable.txt -G unreachable
"""

__pychecker__ = 'no-argsused no-classattr'


import commands
import datetime
import getopt
import getpass
import os
import sys
import urllib
from xml.parsers import expat
from xml.sax import saxutils


# Global constants
COMMAND_OPTIONS_SHORTCUTS = "W:U:P:I:L:f:s:q:F:O:G:M:D:h"
COMMAND_OPTIONS_WITH_SHORTCUTS = [
    "help", "noprompt", "debug=", "workgroup=", "username=", "input=",
    "output=", "password=", "groups=", "maxdepth="]
COMMAND_OPTIONS_WITHOUT_SHORTCUT = [
    "iformat=", "ilines=", "ifield=", "isep=", "iquot=", "oformat=", "olines=",
    "ofield=", "osep=", "oquot="]
COMMAND_OPTIONS = (COMMAND_OPTIONS_WITH_SHORTCUTS +
                   COMMAND_OPTIONS_WITHOUT_SHORTCUT)
DEFAULT_CSV_FIELD = 1
DEFAULT_CSV_SEPARATOR = ','
DEFAULT_CSV_QUOTATION = ''
DEFAULT_OPTIONS = {
    "debug": 0,
    "maxdepth": -1,
    "ifield": DEFAULT_CSV_FIELD,
    "isep": DEFAULT_CSV_SEPARATOR,
    "iquot": DEFAULT_CSV_QUOTATION,
    "ofield": DEFAULT_CSV_FIELD,
    "osep": DEFAULT_CSV_SEPARATOR,
    "oquot": DEFAULT_CSV_QUOTATION,
}
SHORT_MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
USAGE_TEXT = """Usage %s [OPTIONS] [[smb:|unc:]//server/share/path/to/file]

  -W,--workgroup: crawler workgroup
  -U,--username: crawler username
  -P,--password: crawler password (leave blank for prompt)
  -I,--input: take URLs from XML, CSV or plain text file
     --ilines: read only certains lines (e.g. 2,5-14 - counts URLs in XML)
     --ifield: specify field for CSV files (default is %d)
     --isep: specify separator for CSV files (default is %s)
     --iqout: specify quotation for CSV files (default is %s)
     --iformat: force it to xml, csv or txt (plain text)
     (specifying any of -if -is -iq implies file is in CSV format)
  -O,--output: save URLs from XML, CSV or plain text file
               (only CSV includes status and size)
    Use --ifield --osep --oquot --oformat similarly to --i* for input.
    Use -L -f -s -q -F to override both -i* for input and -o* for output.
    -G,--groups: specify comma-separated groups of URLs (by status) to output:
      reachable - all downloadable documents, including
        zerosize - reachable documents with no content, including
          sizemismatch - empty documents listed as non-empty (very rare)
      unreachable - all non-downloadable documents, including
        logonfailure - returned NT_STATUS_LOGON_FAILURE
        accessdenied - returned NT_STATUS_ACCESS_DENIED
        notfound - returned NT_STATUS_OBJECT_NAME_NOT_FOUND
        others - returned any other NT_STATUS message
  -M,--maxdepth: limit directory depth, relative to share root
  -D,--debug: verbosity level (0-5, default to 0)
  -h,--help: print this message\n
  -N,--noprompt: do not prompt for password\n
You can crawl a whole share, a directory or a single file,
( *** note that the trailing slash is mandatory *** ).
If password is left blank, you will be prompted for one.
Leave username blank to crawl as anonymous.
"""
NT_TO_HTTPS_STATUS_MAP = {
    "NT_STATUS_ACCESS_DENIED": 401,
    "NT_STATUS_BAD_NETWORK_NAME": 400,
    "NT_STATUS_BAD_NETWORK_PATH": 400,
    "NT_STATUS_CONNECTION_DISCONNECTED": 503,
    "NT_STATUS_CONNECTION_REFUSED": 503,
    "NT_STATUS_DEVICE_OFF_LINE": 503,
    "NT_STATUS_DFS_UNAVAILABLE": 503,
    "NT_STATUS_DISK_OPERATION_FAILED": 500,
    "NT_STATUS_DUPLICATE_NAME": 400,
    "NT_STATUS_HOST_UNREACHABLE": 503,
    "NT_STATUS_INSUFFICIENT_RESOURCES": 503,
    "NT_STATUS_INVALID_NETWORK_RESPONSE": 503,
    "NT_STATUS_INVALID_PARAMETER": 400,
    "NT_STATUS_IO_TIMEOUT": 408,
    "NT_STATUS_LOGON_FAILURE": 401,
    "NT_STATUS_NETLOGON_NOT_STARTED": 401,
    "NT_STATUS_NETWORK_BUSY": 503,
    "NT_STATUS_NETWORK_NAME_DELETED": 410,
    "NT_STATUS_NETWORK_UNREACHABLE": 503,
    "NT_STATUS_NO_SUCH_DEVICE": 404,
    "NT_STATUS_NO_SUCH_FILE": 404,
    "NT_STATUS_NO_SUCH_LOGON_SESSION": 401,
    "NT_STATUS_OBJECT_NAME_NOT_FOUND": 404,
    "NT_STATUS_OBJECT_PATH_NOT_FOUND": 404,
    "NT_STATUS_REMOTE_NOT_LISTENING": 503,
    "NT_STATUS_REQUEST_NOT_ACCEPTED": 503,
    "NT_STATUS_SHARING_PAUSED": 503,
    "NT_STATUS_UNEXPECTED_NETWORK_ERROR": 500,
    "NT_STATUS_UNMAPPABLE_CHARACTER": 400,
    "NT_STATUS_USER_SESSION_DELETED": 401,
    "NT_STATUS_VIRTUAL_CIRCUIT_CLOSED": 500,
}


# Gets rid of any bad PYTHONPATH if necessary
BAD_PATHS = ['/usr/local/buildtools/current/sitecustomize']
if 'PYTHONPATH' in os.environ:
  paths = os.environ['PYTHONPATH'].split(':')
  for badpath in BAD_PATHS:
    if badpath in paths:
      paths.remove(badpath)
  os.environ['PYTHONPATH'] = ':'.join(paths)


def Usage():
  """Returns help text.
  
  Args:
    none
  Returns:
    help text."""

  return USAGE_TEXT % (sys.argv[0], DEFAULT_CSV_FIELD,
                       DEFAULT_CSV_SEPARATOR, DEFAULT_CSV_QUOTATION)


def UrlEncode(url):
  """Applies URL encoding to dangerous characters.
  
  Only for character that may let filenames inject shell commands.
  
  Args:
    url: potentially with dangerous characters.
  
  Returns:
    same URL after URL-encoding: ' ; " ."""

  return url.replace("'", "%27").replace(";", "%3B").replace('"', "%22")


def UrlEscape(url):
  """Scapes XML entities.
  
  Args:
    url: potentially with XML invalid characters.
  
  Returns:
    same URL after replacing those with XML entities."""

  return url.replace("'", "&apos;").replace("'", '&quot;')


def UrlUnscape(url):
  """Unscapes XML entities.
  
  Args:
    url: potentially with XML entities.
  
  Returns:
    same URL after unscaping XML entities."""

  return url.replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')


class SitemapParser(object):
  """Parses XML Sitemaps but takes only URLs and ignores the rest."""

  def __init__(self, input):
    """Parses an input file."""
    self.url = None
    self.opentag = None
    
    def StartElement(name, attrs):
      self.url = ''
      self.opentag = name

    def CharData(data):
      if self.opentag == 'loc':
        self.url += data

    def EndElement(name):
      if self.opentag == 'loc':
        self.urls.append(self.url)
      self.opentag = None
    self.urls = []
    self.p = expat.ParserCreate()
    self.p.StartElementHandler = StartElement
    self.p.CharacterDataHandler = CharData
    self.p.EndElementHandler = EndElement
    fd = open(input, 'r')
    data = fd.read()
    self.p.Parse(data, 1)
    fd.close()


class Config(object):
  """Parses and keeps flags-driven configuration."""

  def __init__(self, argv=None):
    """Create a new config instance and parses input if any."""

    for option in COMMAND_OPTIONS:
      if option[-1] == '=':
        self.__setattr__(option[:-1], None)
      else:
        self.__setattr__(option, False)
    for option, value in DEFAULT_OPTIONS.iteritems():
      self.__setattr__(option, value)
    if argv:
      self.Parse(argv)

  def Parse(self, argv):
    """Parses input from command line flags."""

    try:
      opts, args = getopt.getopt(
          argv[1:], COMMAND_OPTIONS_SHORTCUTS, COMMAND_OPTIONS)
    except getopt.GetoptError:
      print "\nError processing options\n."
      print Usage()
      sys.exit(1)
    for opt, arg in opts:
      if opt in ('-h', '--help'):
        print Usage()
        sys.exit(0)
      if opt == '-L':
        self.ilines = self.olines = arg
      if opt == '-f':
        self.ifield = self.ofield = arg
      if opt == '-s':
        self.isep = self.osep = arg
      if opt == '-q':
        self.iquot = self.oquot = arg
      if opt == '-F':
        self.iformat = self.oformat = arg
      for option in COMMAND_OPTIONS:
        option = option.split('=')[0]
        flags = ['--%s' % option]
        if option + '=' in COMMAND_OPTIONS_WITH_SHORTCUTS:
          flags.append('-%s' % option[0].upper())
        if opt in flags:
          if arg:
            self.__setattr__(option, arg)
          else:
            self.__setattr__(option, True)
    # Check there is something to crawl
    if self.input is None and len(args) < 1:
      print "\nMissing URLs to crawl, printing Usage information\n." % args
      print Usage()
      sys.exit()
    # Check for input file and format if any, defaults output format to TXT
    if self.input and self.iformat is None:
      if len(self.input) < 4:
        self.iformat = 'txt'
      else:
        ext = self.input[-3:].lower()
        if self.input[-4] == '.' and ext in ('txt', 'csv', 'xml'):
          self.iformat = ext
        else:
          self.iformat = 'txt'
    # Check for output file and format if any, defaults output format to CSV
    if self.output and self.oformat is None:
      if len(self.output) < 4:
        self.oformat = 'csv'
      else:
        ext = self.output[-3:].lower()
        if self.output[-4] == '.' and ext in ('txt', 'csv', 'xml'):
          self.oformat = ext
        else:
          self.oformat = 'csv'
    # Convert lines ranges to sequence
    for attr in ('ilines', 'olines'):
      if self.__getattribute__(attr) is not None:
        lines = []
        for token in self.__getattribute__(attr).split(','):
          numbers = map(int, token.split('-'))
          if len(numbers) == 1:
            lines.append(numbers[0])
          elif len(numbers) == 2:
            lines.extend(range(numbers[0], 1 + numbers[1]))
          else:
            print ("\nBad range for --lines option: %s\n" %
                   self.__getattribute__(attr))
            print Usage()
            sys.exit(1)
        self.__setattr__(attr, lines)
    # Convert groups to sequence and make sure no one is repeated or redundant
    if self.groups is not None:
      self.groups = dict.fromkeys(self.groups.split(',')).keys()
      if self.groups.count('reachable'):
        if self.groups.count('zerosize'):
          self.groups.remove('zerosize')
        if self.groups.count('sizemismatch'):
          self.groups.remove('sizemismatch')
      if self.groups.count('zerosize'):
        if self.groups.count('sizemismatch'):
          self.groups.remove('sizemismatch')
      if self.groups.count('unreachable'):
        if self.groups.count('logonfailure'):
          self.groups.remove('logonfailure')
        if self.groups.count('accessdenied'):
          self.groups.remove('accessdenied')
        if self.groups.count('notfound'):
          self.groups.remove('notfound')
        if self.groups.count('others'):
          self.groups.remove('others')
    # Show debug info
    self.debug = int(self.debug)
    self.maxdepth = int(self.maxdepth)
    if self.debug > 3:
      for option in COMMAND_OPTIONS:
        option = option.split('=')[0]
        value = self.__getattribute__(option)
        if value:
          print "%s set to %s" % (option, value)
    # Prompt for password if necessary
    if self.username is not None and (
        self.password is None and self.noprompt is False):
      self.password = getpass.getpass('Password: ')
    # Save the remainder as arguments
    self.args = map(UrlEncode, map (urllib.unquote, args))

  def Shares(self):
    """Extracts the list of shares to crawl.
    
  Returns:
    shares: List of Share objects."""

    shares = []
    urls = self.args

    # Extract URLs from input file
    if self.input:
      if self.iformat == 'xml':
        urls_from_xml = SitemapParser(self.input).urls
        if self.ilines:
          for i in range(len(urls_from_xml)):
            if i + 1 in self.ilines:
              urls.append(urls_from_xml[i])
        else:
          urls.extend(urls_from_xml)
      elif self.iformat in ('csv', 'txt'):
        fd = open(self.input, 'r')
        line_counter = 1
        for line in fd:
          if not self.ilines or line_counter in self.ilines:
            url = line.strip().split(self.isep)[self.ifield - 1]
            if self.iquot:
              url = url[len(self.iquot):-len(self.iquot)]
            urls.append(UrlUnscape(url))
          line_counter += 1
        fd.close()
      else:
        print "\nBad format (%s) for input file '%s'\n" % (
            self.iformat, self.input)
        print Usage()
        sys.exit(1)

    # Extract URLs from command line arguments and input files
    for url in urls:
      hostname = None
      share = None
      filename = None
      # Detect URL format
      if url[:4] in ('smb:', 'unc:'):
        url = url[4:]
      if url[:2] == '//':
        slash = '/'   # Processing forward slashes
      elif url[:2] == '\\\\':
        slash = '\\'  # Processing backslashes
      else:
        print ("\nInvalid URL for file share: \"%s\"\n"
               "Please use one of the following formats:\n\n"
               "smb://fileserver/share/path/to/file\n"
               "unc://fileserver/share/path/to/file\n"
               "//fileserver/share/path/to/file\n"
               "\\\\fileserver\\share\\path\\to\\file\n" % url)
        print Usage()
        sys.exit(1)
      slash_1 = url.find(slash, 2)
      slash_2 = url.find(slash, slash_1 + 1)
      hostname = url[2:slash_1]
      share = url[slash_1 + 1: slash_2]
      filename = '/' + url[slash_2 + 1:]
      shares.append(Share(hostname=hostname, share=share, filename=filename,
                          domain=self.workgroup, username=self.username,
                          password=self.password))
    return shares


class Share(object):

  def __init__(self, **kwargs):
    self.hostname = kwargs['hostname']
    self.share = kwargs['share']
    self.filename = kwargs.get('filename', '/')
    # These defautl to None:
    self.domain = kwargs.get('domain')
    self.username = kwargs.get('username')
    self.password = kwargs.get('password')
    # Compute initial directory depth
    self.depth = self.filename.count('/') - 1

  def IsDirectory(self):
    return self.filename[-1] == '/'

  def IsFile(self):
    return self.filename[-1] != '/'

  def __str__(self):
    str = "smb://%s/%s%s" % (self.hostname, self.share, self.filename)
    if self.domain:
      str += " on workgroup '%s'" % self.domain
    if self.username:
      str += " as user '%s'" % self.username
    if self.password:
      str += " with password '%s'" % ('*' * len(self.password),)
    return str

  def __repr__(self):
    return "smb://%s/%s%s" % (self.hostname, self.share, self.filename)

  def Url(self, filename=None):
    if filename is None: filename = self.filename
    return "smb://%s/%s%s" % (self.hostname, self.share, filename)

  def Root(self):
    return "smb://%s/%s/" % (self.hostname, self.share)


class Document(object):

  def __init__(self, share, filename=None, lastmod=None):
    self.share = share
    self.filename = filename
    if self.filename is None:
      self.filename = self.share.filename
    self.lastmod = lastmod
    self.status = None
    self.real_size = None
    self.list_size = 0

  def __str__(self):
    return "smb://%s/%s%s" % (
        self.share.hostname, self.share.share, self.filename)

  def Url(self):
    return "smb://%s/%s%s" % (
        self.share.hostname, self.share.share, self.filename)

  def HttpStatus(self):
    """Map NT_STATUS_* to HTTP response codes.

       Statuses from http://msdn.microsoft.com/en-us/library/cc202275.aspx"""
    if self.status is None:
      if self.real_size != 0:
        return 200
      elif self.list_size == 0:
        return 204
      else:
        return 401
    return NT_TO_HTTPS_STATUS_MAP[self.status]

  def IsDirectory(self):
    return self.filename[-1] == '/'

  def IsFile(self):
    return self.filename[-1] != '/'

  def Size(self):
    if self.IsDirectory():
      return 0
    if self.real_size is not None:
      return self.real_size
    else:
      return self.list_size

  def GroupsByStatus(self):
    """Retuns the status groups matching the NT_STATUS message.

    Groups are reachable, zerosize, sizemismatch, unreachable, logonfailure,
    accessdenied, notfound, others.
    """
    if self.status is None:
      if self.real_size == 0:
        return ['reachable', 'zerosize']
      elif self.real_size != self.list_size:
        return ['reachable', 'zerosize', 'sizemismatch']
      return ['reachable']
    else:
      if self.status in [
          "NT_STATUS_LOGON_FAILURE", "NT_STATUS_NO_SUCH_LOGON_SESSION"]:
        return ['unreachable', 'logonfailure']
      elif self.status in ["NT_STATUS_ACCESS_DENIED"]:
        return ['unreachable', 'accessdenied']
      elif self.status in [
          "NT_STATUS_NO_SUCH_DEVICE", "NT_STATUS_NO_SUCH_FILE",
          "NT_STATUS_OBJECT_NAME_NOT_FOUND", "NT_STATUS_OBJECT_PATH_NOT_FOUND"]:
        return ['unreachable', 'notfound']
      elif self.status in [
          "NT_STATUS_BAD_NETWORK_NAME", "NT_STATUS_BAD_NETWORK_PATH",
          "NT_STATUS_CONNECTION_DISCONNECTED", "NT_STATUS_CONNECTION_REFUSED",
          "NT_STATUS_DEVICE_OFF_LINE", "NT_STATUS_DFS_UNAVAILABLE",
          "NT_STATUS_DISK_OPERATION_FAILED", "NT_STATUS_DUPLICATE_NAME",
          "NT_STATUS_HOST_UNREACHABLE", "NT_STATUS_INSUFFICIENT_RESOURCES",
          "NT_STATUS_INVALID_NETWORK_RESPONSE", "NT_STATUS_INVALID_PARAMETER",
          "NT_STATUS_IO_TIMEOUT", "NT_STATUS_NETLOGON_NOT_STARTED",
          "NT_STATUS_NETWORK_BUSY", "NT_STATUS_NETWORK_NAME_DELETED",
          "NT_STATUS_NETWORK_UNREACHABLE", "NT_STATUS_REMOTE_NOT_LISTENING",
          "NT_STATUS_REQUEST_NOT_ACCEPTED", "NT_STATUS_SHARING_PAUSED",
          "NT_STATUS_UNEXPECTED_NETWORK_ERROR",
          "NT_STATUS_UNMAPPABLE_CHARACTER",
          "NT_STATUS_USER_SESSION_DELETED", "NT_STATUS_VIRTUAL_CIRCUIT_CLOSED"]:
        return ['unreachable', 'others']
      return ['unreachable']


class Report(object):
  """Stores the result of crawling URLs."""

  def __init__(self):
    """Creates and empty report."""

    self.groups_map = dict()
    self.status_map = dict()
    self.urls_map = dict()
    self.zero_sized = []
    self.size_mismatch = []

  def __str__(self):
    """Prints the report in human-friendly format."""

    output = "Successfully crawled documents:\n"
    for url, doc in self.urls_map.iteritems():
      if doc.status is None and doc.real_size not in (0, None):
        if doc.IsFile():
          output += " - %s  --  size %d\n" % (doc.Url(), doc.list_size)
        elif doc.IsDirectory():
          output += " - %s\n" % (doc.Url())
    if self.zero_sized:
      output += "Empty documents:\n - %s\n" % "\n - ".join(self.zero_sized)
    if self.size_mismatch:
      output += "Empty documents listed as non-empty:\n - %s\n" % "\n - ".join(
          self.size_mismatch)
    for status, urls in self.status_map.iteritems():
      if urls:
        output += "%s was returned for these URLs:\n - %s\n" % (
            status, "\n - ".join(urls))
    return output

  def Add(self, doc):
    """Adds a document to the report."""

    self.urls_map[doc.Url()] = doc

  def Update(self, url, **kwargs):
    """Updates a document already present in the report."""

    for key, value in kwargs.iteritems():
      self.urls_map[url].__setattr__(key, value)
    size = kwargs.get('real_size')
    if size == 0:
      self.zero_sized.append(url)
      if size != self.urls_map[url].list_size:
        self.size_mismatch.append(url)
    status = kwargs.get('status')
    if status is not None:
      if status in self.status_map:
        self.status_map[status].append(url)
      else:
        self.status_map[status] = [url]
    for group in self.urls_map[url].GroupsByStatus():
      if group in self.groups_map:
        self.groups_map[group].append(url)
      else:
        self.groups_map[group] = [url]

  def Save(self, config):
    """Saves the report to a XML, CSV or plain text file, accordingly to the
       flags-driven configuration.
       
       Only CSV includes status and size, XML and text include only URLs.
       
       Args:
         config, flag-drive configuration.
       
       Raise:
         Exception, a generice exception."""

    if config.output is None:
      config.output = '/dev/stdout'
      if config.oformat is None:
        return
    fd = open(config.output, 'w')
    if config.oformat == 'xml':
      fd.write(
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.google.com/schemas/sitemap/0.84"\n'
          '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
          '  xsi:schemaLocation="http://www.google.com/schemas/sitemap/0.84\n'
          '  http://www.google.com/schemas/sitemap/0.84/sitemap.xsd">\n')
    # Check for groups
    if config.groups is None:
      urls = self.urls_map.keys()
    else:
      urls = []
      for group in config.groups:
        if group in self.groups_map:
          urls.extend(self.groups_map[group])
    for url in urls:
      doc = self.urls_map[url]
      if config.oformat == 'xml':
        fd.write('  <url>\n    <loc>%s</loc>\n  </url>\n' % url)
      elif config.oformat == 'csv':
        fd.write(config.osep.join(["%s%s%s" % (config.oquot, data, config.oquot)
                                   for data in (saxutils.escape(url),
                                                doc.HttpStatus(), doc.list_size)]) + '\n')
      elif config.oformat == 'txt':
        fd.write('%s\n' % url)
      else:
        raise Exception("This should never happen!")
    if config.oformat == 'xml':
      fd.write('</urlset>\n')
    fd.close()


def Crawl(config):
  """Crawls a list of SMB file shares.
  
  Args:
    config: Config object holding global configuration from commands flags
    
  Returns:
    report: Report object holding the results from the crawling the shares"""

  shares = config.Shares()
  if not shares:
    print "No shares found!"
    sys.exit(1)
  if config.debug > 0:
    print "Shares to crawl: \n - %s" % '\\\n - '.join([str(s) for s in shares])
  report = Report()
  for share in shares:
    opts = ['-N']
    if share.domain is not None:
      opts.append('-W%s' % share.domain)
    if share.username is not None:
      if share.password is not None:
        opts.append("-U'%s%%%%%s'" % (share.username, share.password))
      else:
        opts.append("-U'%s'" % share.username)
    else:
      opts.append('-Uguest')
    smbclient = "smbclient %s //%s/%s -c'%%s'" % (
        ' '.join(opts), share.hostname, share.share)
    crawl_queue = [share.filename]
    crawled = []
    report.Add(Document(share))
    while crawl_queue:
      filename = crawl_queue.pop()
      while filename in crawled:
        filename = crawl_queue.pop()
      crawled.append(filename)
      file_url = share.Root() + filename[1:]
      if config.debug > 1:
        print "Trying %s" % share.Url(filename)
      if filename[-1] == '/':
        cmd = 'ls "%s*"' % filename.replace('/', '\\')
      else:
        cmd = 'get "%s" /dev/null' % filename.replace('/', '\\')
      if config.debug > 3:
        print "Running command: %s" % (smbclient % cmd,)
      status, output = commands.getstatusoutput(smbclient % cmd)
      if filename[-1] == '/':
        # Get filenames out of directory listing
        for line in output.split('\n'):
          if line[:2] == '  ' and line[2:4] != '..':
            parts = line.split()
            timestamp = ':'.join((parts[-1], str(
                SHORT_MONTH_NAMES.index(parts[-4])+1), parts[-3], parts[-2]))
            timestamp = datetime.datetime(*map(int, timestamp.split(':')))
            size = int(parts[-6])
            child = ' '.join(parts[:-6])
            if child[-1] == 'D': child = child[:-2] + '/'   # Dirs
            if child[-1] == 'A': child = child[:-2]         # Apps
            if child[-1] == 'H': child = child[:-2]         # Hidden
            if child[0] == '.':
              doc = Document(share, filename, lastmod=timestamp)
              doc.list_size = doc.real_size = 4096   # Just to avoid zero-sized
              report.Add(doc)
              continue
            path = UrlEncode(os.path.join(filename, child))
            if config.maxdepth != -1 and (
                path[:-1].count('/') - share.depth) > config.maxdepth:
              continue
            doc = Document(share, path, lastmod=timestamp)
            crawl_queue.append(path)
            if doc.IsFile:
              doc.list_size = size
            report.Add(doc)
            if config.debug > 3:
              print "Found '%s' last modified %s" % (doc.Url(), doc.lastmod)
          elif line[:3] == 'NT_':
            status = line.split()[0]
            if config.debug > 2:
              print "%s for %s" % (status, filename)
            report.Update(file_url, status=status)
          else:
            words = line.split()
            for error in words:
              if error[:3] == 'NT_':
                report.Update(file_url, status=error)
      else:
        # Get result of downloading the file
        for line in output.split('\n'):
          if line[:7] == 'getting':
            parts = line.split()
            size = int(parts[parts.index('size') + 1])
            if config.debug > 2:
              print "%s has size %s" % (filename, size)
            report.Update(file_url, real_size=size)
          elif line[:3] == 'NT_':
            error = line.split()[0]
            if config.debug > 2:
              print "%s for %s" % (error, filename)
            report.Update(file_url, status=error)
          else:
            words = line.split()
            for error in words:
              if error[:3] == 'NT_':
                report.Update(file_url, status=error)
  return report


def main(argv):
  """Runs the crawls."""

  config = Config(argv)
  report = Crawl(config)
  if config.output is None:
    print report
  else:
    report.Save(config)
    print "Report written to '%s'." % config.output

if __name__ == '__main__':
  main(sys.argv)
