#!/usr/bin/python2.5
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
# This code is not supported by Google
#
"""Classes for administering the Google Search Appliance.

Currently, the classes available can be used to import/export/rewrite
the config file. This module is designed to be expandable so that
other functionality can be easily included.

gsaConfig: Class for handling XML from GSA export/import.
gsaWebInterface: Class for interacting with GSA Web Interface.

Example usage:

1. Export the config file:

gsa_admin.py -n <host> --port 8000 -u admin -p <pw> -e --sign-password
hellohello -o ~/tmp/o.xml -v

2. Make a change to the config file and sign:

./gsa_admin.py -s --sign-password hellohello -f ~/tmp/o.xml -v -o ~/tmp/o2.xml

3. Import the new config file:

./gsa_admin.py -n <host> --port 8000 -u admin -p <pw> -i --sign-password
hellohello -f ~/tmp/o2.xml -v

4. Export all the URLs to a file:

./gsa_admin.py --hostname=<host> --username=admin
--password=<pw> --all_urls --output=/tmp/all_urls

5. Retrieve GSA^n (mirroring) status from the admin console
./gsa_admin.py -z -n <host> -u admin -p <pw>

Note that you must use the same password to sign a file that you used
when exporting. You will get an error when importing if you do not do
this.

TODO(jlowry): add in functionality from adminconsole.py: sync DB,
pause/resume crawl, get crawl status, shutdown.
"""

__author__ = "alastair@mcc-net.co.uk (Alastair McCormack)"


import cgi
import os.path
import logging
import sys
import xml.dom.minidom
import hashlib
import hmac
import codecs
import urllib2
import urllib
import cookielib
import re
import time
import urlparse
from optparse import OptionParser, OptionGroup

# Required for utf-8 file compatibility
reload(sys)
sys.setdefaultencoding("utf-8")
del sys.setdefaultencoding

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

DEFAULTLOGLEVEL=logging.INFO
log = logging.getLogger(__name__)
log.addHandler(NullHandler())

class gsaConfig:
  "Google Search Appliance XML configuration tool"

  configXMLString = None

  def __init__(self, fileName=None):
    if fileName:
      self.openFile(fileName)

  def __str__(self):
    return self.configXMLString

  def openFile(self, fileName):
    "Read in file as string"
    if not os.path.exists(fileName):
      log.error("Input file does not exist")
      sys.exit(1)
    configXMLdoc = open(fileName)
    self.configXMLString = configXMLdoc.read()
    configXMLdoc.close()

  def setXMLContents(self, xmlString):
    "Sets the runtime XML contents"
    self.configXMLString = xmlString.encode("utf-8")
    #log.warning("Signature maybe invalid. Please verify before uploading or saving")

  def getXMLContents(self):
    "Returns the contents of the XML file"
    return self.configXMLString.encode("utf-8")

  def sign(self, password):
    configXMLString = self.configXMLString
    # ugly removal of spaces because minidom cannot remove them automatically when removing a node
    configXMLString = re.sub('          <uam_dir>', '<uam_dir>', configXMLString)
    configXMLString = re.sub('</uam_dir>\n', '</uam_dir>', configXMLString)

    doc = xml.dom.minidom.parseString(configXMLString)
    # Remove <uam_dir> node because new GSAs expect so
    uamdirNode = doc.getElementsByTagName("uam_dir").item(0)
    globalConfigNode = uamdirNode.parentNode
    globalConfigNode.removeChild(uamdirNode)
    # Get <config> node
    configNode = doc.getElementsByTagName("config").item(0)
    # get string of Node and children (as utf-8)
    configNodeXML = configNode.toxml()
    # Create new HMAC using user password and configXML as sum contents
    myhmac = hmac.new(password, configNodeXML, hashlib.sha1)

    # Get <signature> node
    signatureNode = doc.getElementsByTagName("signature").item(0)
    signatureCDATANode = signatureNode.firstChild
    # Set CDATA/Text area to new HMAC
    signatureCDATANode.nodeValue = myhmac.hexdigest()
    # Put <uam_dir> back
    globalConfigNode.appendChild(uamdirNode)
    self.configXMLString = doc.toxml()

  def writeFile(self, filename):
    if os.path.exists(filename):
      log.error("Output file exists")
      sys.exit(1)
    doc = xml.dom.minidom.parseString(self.configXMLString)
    outputXMLFile = codecs.open(filename, 'w', "utf-8")
    log.debug("Writing XML to %s" % filename)
    doc.writexml(outputXMLFile)

  def verifySignature(self, password):
    configXMLString = self.getXMLContents()
    # ugly removal of spaces because minidom cannot remove them automatically when removing a node
    configXMLString = re.sub('          <uam_dir>', '<uam_dir>', configXMLString)
    configXMLString = re.sub('</uam_dir>\n', '</uam_dir>', configXMLString)

    doc = xml.dom.minidom.parseString(configXMLString)
    # Remove <uam_dir> node because new GSAs expect so
    uamdirNode = doc.getElementsByTagName("uam_dir").item(0)
    uamdirNode.parentNode.removeChild(uamdirNode)
    # Get <config> node
    configNode = doc.getElementsByTagName("config").item(0)
    # get string of Node and children (as utf-8)
    configNodeXML = configNode.toxml()
    # Create new HMAC using user password and configXML as sum contents
    myhmac = hmac.new(password, configNodeXML, hashlib.sha1)

    # Get <signature> node
    signatureNode = doc.getElementsByTagName("signature").item(0)
    signatureCDATANode = signatureNode.firstChild
    signatureValue = signatureNode.firstChild.nodeValue
    # signatureValue may contain whitespace and linefeeds so we'll just ensure that
    # our HMAC is found within

    if signatureValue.count(myhmac.hexdigest()) :
      log.debug("Signature matches")
      return 1
    else:
      log.debug("Signature does not match")
      return None


class gsaWebInterface:
  "Google Search Appliance Web Interface Wrapper)"

  baseURL = None
  username = None
  password = None
  hostName = None
  loggedIn = None
  _url_opener = None

  def __init__(self, hostName, username, password, port=8000):
    self.baseURL = 'http://%s:%s/EnterpriseController' % (hostName, port)
    self.hostName = hostName
    self.username = username
    self.password = password
    # build cookie jar for this web instance only. Should allow for GSAs port mapped behind a reverse proxy.
    cookieJar = cookielib.CookieJar()
    self._url_opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookieJar))

  def _openurl(self, request):
    """Args:
      request: urllib2 request object or URL string.
    """
    return self._url_opener.open(request)

  def _encode_multipart_formdata(self, fields, files):
    """
    fields: a sequence of (name, value) elements for regular form fields.
    files: a sequence of (name, filename, value) elements for data to be uploaded as files
    """
    BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
    CRLF = '\r\n'
    lines = []
    for (key, value) in fields:
      lines.append('--' + BOUNDARY)
      lines.append('Content-Disposition: form-data; name="%s"' % key)
      lines.append('')
      lines.append(value)
    for (key, filename, value) in files:
      lines.append('--' + BOUNDARY)
      lines.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
      lines.append('Content-Type: text/xml')
      lines.append('')
      lines.append(value)
    lines.append('--' + BOUNDARY + '--')
    lines.append('')
    body = CRLF.join(lines)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body

  def _login(self):
    if not self.loggedIn:
      log.debug("Fetching initial page for new cookie")
      self._openurl(self.baseURL)
      request = urllib2.Request(self.baseURL,
                                urllib.urlencode(
          {'actionType' : 'authenticateUser',
           'userName' : self.username,
           'password' : self.password}))

      log.debug("Logging in as %s..."  % self.username)
      result = self._openurl(request)
      resultString = result.read()
      home = re.compile("Google Search Appliance\s*&gt;\s*Home")
      if not home.search(resultString):
        log.error("Login failed")
        sys.exit(2)

      log.debug("Successfully logged in")
      self.loggedIn = True

  def _logout(self):
    request = urllib2.Request(self.baseURL + "?" + urllib.urlencode({'actionType' : 'logout'}))
    self._openurl(request)
    self.loggedIn = False

  def __del__(self):
    self._logout()

  def importConfig(self, gsaConfig, configPassword):
    fields = [("actionType", "importExport"), ("passwordIn", configPassword),
        ("import", " Import Configuration ")]

    files = [("importFileName", "config.xml", gsaConfig.getXMLContents() )]
    content_type, body = self._encode_multipart_formdata(fields,files)
    headers = {'User-Agent': 'python-urllib2', 'Content-Type': content_type}

    self._login()
    security_token = self.getSecurityToken('cache')
    request = urllib2.Request(self.baseURL + "?" +
                              urllib.urlencode({'actionType': 'importExport',
                                                'export': ' Import Configuration ',
                                                'security_token': security_token,
                                                'passwordIn': configPassword}),
                              body, headers)
    log.info("Sending XML...")
    result = self._openurl(request)
    content = result.read()
    if content.count("Invalid file"):
      log.error("Invalid configuration file")
      sys.exit(2)
    elif content.count("Wrong passphrase or the file is corrupt"):
      log.error("Wrong passphrase or the file is corrupt. Try ")
      sys.exit(2)
    elif content.count("Passphrase should be at least 8 characters long"):
      log.error("Passphrase should be at least 8 characters long")
      sys.exit(2)
    elif content.count("File does not exist"):
      log.error("Configuration file does not exist")
      sys.exit(2)
    elif not content.count("Configuration imported successfully"):
      log.error("Import failed")
      sys.exit(2)
    else:
      log.info("Import successful")

  def exportConfig(self, configPassword):
    self._login()
    security_token = self.getSecurityToken('cache')
    request = urllib2.Request(self.baseURL + "?" +
                              urllib.urlencode({'actionType': 'importExport',
                                                'export': ' Export Configuration ',
                                                'security_token': security_token,
                                                'password1': configPassword,
                                                'password2': configPassword}))

    log.debug("Fetching config XML")
    result = self._openurl(request)
    content = result.read()
    if content.count("Passphrase should be at least 8 characters long"):
      log.error("Passphrase should be at least 8 characters long. You entered: '%s'" % (configPassword))
      sys.exit(2)
    gsac = gsaConfig()
    log.debug("Returning gsaConfig object")
    gsac.setXMLContents(content)
    return gsac

  def getSecurityToken(self, actionType):
    """Gets the value of the security_token hidden form parameter.

    Args:
      actionType: a string, used to fetch the Admin Console form.

    Returns:
      A long string, required as a parameter when submitting the form.
      Returns an empty string if security_token does not exist.
    """
    self._login()
    # request needs to be a GET not POST
    url = '%s?actionType=%s' % (self.baseURL, actionType)
    log.debug('Fetching url: %s' % (url))
    result = self._openurl(url)
    content = result.read()
    token_re = re.compile('name="security_token"[^>]*value="([^"]*)"', re.I)
    match = token_re.search(content)
    if match:
      security_token = match.group(1)
      log.debug('Security token is: %s' % (security_token))
      return security_token
    else:
      return ""

  def setAccessControl(self, maxhostload=10, urlCacheTimeout=3600):
    # Tested on 6.8. Will not work on previous versions unless the form
    # parameters are modified.
    self._login()
    security_token = self.getSecurityToken('cache')
    # Sample body of a POST from a 6.8 machine:
    #  security_token=Vaup237Rd5jXE6ZC0Iy6BeVo4h0%3A1290533850660&
    #  actionType=cache&
    #  basicAuthChallengeType=auto&
    #  authzServiceUrl=&
    #  overallAuthzTimeout=20.0&
    #  requestBatchTimeout=5.0&
    #  singleRequestTimeout=2.5&
    #  maxHostload=10&
    #  urlCacheTimeout=3600&
    #  saveSettings=Save+Settings
    request = urllib2.Request(self.baseURL,
                              urllib.urlencode({'security_token': security_token,
                                                'actionType': 'cache',
                                                'basicAuthChallengeType': 'auto',
                                                'authzServiceUrl': '',
                                                'overallAuthzTimeout': '20.0',
                                                'requestBatchTimeout': '5.0',
                                                'singleRequestTimeout': '2.5',
                                                'maxHostload': maxhostload,
                                                'urlCacheTimeout': urlCacheTimeout,
                                                'saveSettings': 'Save Settings'}))
    result = self._openurl(request)
    # Form submit did not work if content contains this string: "Forgot Your Password" or
    # <font color="red"> unless multiple users are logged in.
    # content = result.read()
    # log.info(content)

  def _unescape(self, s):
    s = s.replace('&amp;', '&')
    return s

  def syncDatabases(self, database_list):
    """Sync databases in the GSA.

    Args:
      database_list: a List of String, a list of database name to sync
    """
    self._login()
    for database in database_list:
      log.info("Syncing %s ..." % database)
      param = urllib.urlencode({"actionType": "syncDatabase",
                                "entryName": database})
      request = urllib2.Request(self.baseURL + "?" + param)
      try:
        result = self._openurl(request)
      except:
        log.error("Unable to sync %s properly" % database)

  def exportKeymatches(self, frontend, out):
    """Export all keymatches for a frontend.

    Args:
      frontend: a String, the frontend name.
      out: a File, the file to write to.
    """
    self._login()
    log.info("Retrieving the keymatch file for %s" % frontend)
    param = urllib.urlencode({'actionType' : 'frontKeymatchImport',
                              'frontend' : frontend,
                              'frontKeymatchExportNow': 'Export KeyMatches Now',
                              'startRow' : '1', 'search' : ''})
    request = urllib2.Request(self.baseURL + "?" + param)
    try:
      result = self._openurl(request)
      output = result.read()
      out.write(output)
    except Exception, e:
      log.error("Unable to retrieve Keymatches for %s" % frontend)
      log.error(e)

  def exportSynonyms(self, frontend, out):
    """Export all Related Queries for a frontend.

    Args:
      frontend: a String, the frontend name.
      out: a File, the file to write to.
    """
    self._login()
    log.info("Retrieving the Related Queries file for %s" % frontend)
    param = urllib.urlencode({'actionType' : 'frontSynonymsImport',
                              'frontend' : frontend,
                              'frontSynonymsExportNow': 'Export Related Queries Now',
                              'startRow' : '1', 'search' : ''})
    request = urllib2.Request(self.baseURL + "?" + param)
    try:
      result = self._openurl(request)
      output = result.read()
      out.write(output)
    except:
      log.error("Unable to retrieve Related Queries for %s" % frontend)

  def getAllUrls(self, out):
    """Retrieve all the URLs in the Crawl Diagnostics.

       The URLs can be extracted from the crawl diagnostics URL with
       actionType=contentStatus.  For example, the URL in link

       /EnterpriseController?actionType=contentStatus&...&uriAt=http%3A%2F%2Fwww.google.com%2F

       is http://www.google.com/

       We only follow crawl diagnostic URLs that contain actionType=contentStatus
    """
    self._login()
    log.debug("Retrieving URLs from Crawl Diagostics")
    tocrawl = set([self.baseURL + '?actionType=contentDiagnostics&sort=crawled'])
    crawled = set([])
    doc_urls = set([])
    href_regex = re.compile(r'<a href="(.*?)"')
    while 1:
      try:
        log.debug('have %i links to crawl' % len(tocrawl))
        crawling = tocrawl.pop()
        log.debug('crawling %s' % crawling)
      except KeyError:
        raise StopIteration
      url = urlparse.urlparse(crawling)
      request = urllib2.Request(crawling)
      try:
        result = self._openurl(request)
      except:
        print 'unable to open url'
        continue
      content = result.read()
      crawled.add(crawling)

      links = href_regex.findall(content)
      log.debug('found %i links' % len(links))
      for link in (links.pop(0) for _ in xrange(len(links))):
        log.debug('found a link: %s' % link)
        if link.startswith('/'):
          link = url[0] + '://' + url[1] + link
          link = self._unescape(link)
          if link not in crawled:
            log.debug('this links has not been crawled')
            if (link.find('actionType=contentDiagnostics') != -1 and
                 link.find('sort=excluded') == -1 and
                 link.find('sort=errors') == -1 and
                 link.find('view=excluded') == -1 and
                 link.find('view=successful') == -1 and
                 link.find('view=errors') == -1):
              tocrawl.add(link)
              #print 'add this link to my tocrawl list'
            elif link.find('actionType=contentStatus') != -1:
              # extract the document URL
              doc_url = ''.join(cgi.parse_qs(urlparse.urlsplit(link)[3])['uriAt'])
              if doc_url not in doc_urls:
                out.write(doc_url + '\n')
                doc_urls.add(doc_url)
                if len(doc_urls) % 100 == 0:
                  print len(doc_urls)
            else:
              log.debug('we are not going to crawl this link %s' % link)
              pass
          else:
            log.debug('already crawled %s' % link)
            pass
        else:
          log.debug('we are not going to crawl this link %s' % link)
          pass

  def getStatus(self):
    """Get System Status and mirroring if enabled

      The GSA sends out daily email but it doesn't inlcude mirroing status
      Temporary solution -- only tested with 6.2.0.G.44
    """

    self._login()
    log.info("Retrieving GSA^n network diagnostics status from: %s", self.hostName)
    request = urllib2.Request(self.baseURL + "?" +
                              urllib.urlencode({'actionType': 'gsanDiagnostics'}))

    result = self._openurl(request)
    content = result.read()

    nodes = re.findall("row.*(<b>.*</b>)", content)
    if not nodes:
      log.error("Could not find any replicas...")
      exit(3)

    log.debug(nodes)
    connStatus = re.findall("(green|red) button", content)
    log.debug(connStatus)

    numErrs = 0
    for index, val in enumerate(connStatus):
      if val == "green":
        connStatus[index] = "OK"
      else:
        connStatus[index] = "ERROR - Test FAILED"
        numErrs += 1

    pos = 0
    print "========================================="
    for node in nodes:
      print "Node: " +  re.sub(r'<[^<]*?/?>', '', node)
      print "Ping Status: " + connStatus[0+pos]
      print "Stunnel Listener up: ", connStatus[1+pos]
      print "Stunnel Connection: ", connStatus[2+pos]
      print "PPP Connection Status: ", connStatus[3+pos]
      print "Application Connection Status: ", connStatus[4+pos]
      pos += 5
      if pos < len(connStatus):
        print "----------------------------------------"
    print "========================================="
    if numErrs:
      print numErrs,  "ERROR(s) detected. Please review mirroing status"
    else:
      print "All Tests passes successfully"
    print "=========================================\n"

    detailStats = re.search("Detailed Status(.*)\"Balls\">", content, re.DOTALL)
    if detailStats:
    #Check if this is primary node and display sync info
      detailStats = re.sub(r'</td>\n<td ', ': <', detailStats.group(), re.DOTALL)
      detailStats = re.sub(r'</td> <td ',' | <', detailStats, re.DOTALL)
      detailStats = re.sub(r'<[^<]*?/?>', '', detailStats)

      prettyStats = detailStats.split("\n")
      for row in prettyStats:
        cols = row.split(": ")
        if len(cols) > 1:
          cols[0] = cols[0] + ":" + " " * (40 - len(cols[0]))
        print ''.join(cols)
      print "==========================================================="


###############################################################################
# MAIN
###############################################################################

if __name__ == "__main__":
  log.setLevel(DEFAULTLOGLEVEL)
  logStreamHandler = logging.StreamHandler(sys.stdout)
  logStreamHandler.setFormatter(logging.Formatter("%(asctime)s %(levelname)5s %(name)s %(lineno)d: %(message)s"))
  log.addHandler(logStreamHandler)

  # Get command options
  parser = OptionParser()

  parser.add_option("-f", "--input-file", dest="inputFile",
                      help="Input XML file", metavar="FILE")

  parser.add_option("-o", "--output", dest="outputFile",
          help="Output file name", metavar="FILE")

  parser.add_option("-g", "--sign-password", dest="signpassword",
          help="Sign password for signing/import/export")

  parser.add_option("--cache-timeout", dest="cachetimeout",
          help="Value for Authorization Cache Timeout")

  parser.add_option("--max-hostload", dest="maxhostload",
          help="Value for max number of concurrent authz requests per server")

  parser.add_option("--sources", dest="sources",
                    help="List of databases to sync (database1,database2,database3)")

  parser.add_option("--frontend", dest="frontend",
                    help="Frontend used to export keymatches or related queries")

  # actionsOptions
  actionOptionsGrp = OptionGroup(parser, "Actions:")

  actionOptionsGrp.add_option("-i", "--import", dest="actimport",
          help="Import config file to GSA", action="store_true")

  actionOptionsGrp.add_option("-e", "--export", dest="export",
          help="Export GSA config file from GSA", action="store_true")

  actionOptionsGrp.add_option("-s", "--sign", dest="sign", action="store_true",
           help="Sign input XML file")

  actionOptionsGrp.add_option("-r", "--verify", dest="verify", action="store_true",
           help="Verify signature/HMAC in XML Config")

  actionOptionsGrp.add_option("-a", "--set", dest="setaccesscontrol", action="store_true",
           help="Set Access Control settings")

  actionOptionsGrp.add_option("-l", "--all_urls", dest="all_urls",
          help="Export all URLs from GSA", action="store_true")

  actionOptionsGrp.add_option("-d" ,"--database_sync", dest="database_sync",
                              help="Sync databases", action="store_true")

  actionOptionsGrp.add_option("-k" ,"--keymatches_export", dest="keymatches_export",
                              help="Export All Keymatches", action="store_true")

  actionOptionsGrp.add_option("-y" ,"--synonyms_export", dest="synonyms_export",
                              help="Export All Related Queries", action="store_true")

  actionOptionsGrp.add_option("-z", "--get-status", dest="getstatus",
                              action="store_true", help="Get GSA Status")

  parser.add_option_group(actionOptionsGrp)

  # gsaHostOptions
  gsaHostOptions = OptionGroup(parser, "GSA info")

  gsaHostOptions.add_option("-n", "--hostname", dest="gsaHostName",
          help="GSA hostname")

  gsaHostOptions.add_option("--port", dest="port",
          help="Upload port. Defaults to 8000", default="8000")

  gsaHostOptions.add_option("-u", "--username", dest="gsaUsername",
            help="Username to login GSA")

  gsaHostOptions.add_option("-p", "--password", dest="gsaPassword",
            help="Password for GSA user")

  parser.add_option_group(gsaHostOptions)

  parser.add_option("-v", "--verbose", action="count", dest="verbosity", help="Specify multiple times to increase verbosity")

  (options, args) = parser.parse_args()

  if options.verbosity:
    # The -v option is counted so more -v the more verbose we should be.
    # As the log level are actually ints of multiples of 10
    # we count how many -v were specified x 10 and subtract the result from the minimum level of logging
    startingLevel = DEFAULTLOGLEVEL
    logOffset = 10 * options.verbosity
    logLevel = startingLevel - logOffset
    log.setLevel(logLevel)

  # Actions actimport, export, sign, & verify need signpassword
  # if not options.setaccesscontrol:
  if options.actimport or options.export or options.sign or options.verify:
    # Verify opts
    if not options.signpassword:
      log.error("Signing password not given")
      sys.exit(3)

    if len(options.signpassword) < 8:
      log.error("Signing password must be 8 characters or longer")
      sys.exit(3)

  action = None

  # Ensure only one action is specified
  if options.actimport:
    action = "import"
  if options.setaccesscontrol:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "setaccesscontrol"
  if options.export:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "export"
  if options.sign:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "sign"
  if options.verify:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "verify"
  if options.all_urls:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "all_urls"
  if options.database_sync:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "database_sync"
  if options.keymatches_export:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "keymatches_export"
  if options.synonyms_export:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "synonyms_export"
  if options.getstatus:
    if action:
      log.error("Specify only one action")
      sys.exit(3)
    else:
      action = "status"
  if not action:
      log.error("No action specified")
      sys.exit(3)


  if action != "sign" or action != "verify":
    #Check user, password, host
    if not options.gsaHostName:
      log.error("hostname not given")
      sys.exit(3)
    if not options.gsaUsername:
      log.error("username not given")
      sys.exit(3)
    if not options.gsaPassword:
      log.error("password not given")
      sys.exit(3)

  # Actions
  if action == "sign":
    if not options.inputFile:
      log.error("Input file not given")
      sys.exit(3)

    if not options.outputFile:
      log.error("Output file not given")
      sys.exit(3)

    log.info("Signing %s" % options.inputFile)
    gsac = gsaConfig(options.inputFile)
    gsac.sign(options.signpassword)
    log.info("Writing signed file to %s" % options.outputFile)
    gsac.writeFile(options.outputFile)

  elif action == "import":
    if not options.inputFile:
      log.error("Input file not given")
      sys.exit(3)
    log.info("Importing %s to %s" % (options.inputFile, options.gsaHostName) )
    gsac = gsaConfig(options.inputFile)
    if not gsac.verifySignature(options.signpassword):
      log.warn("Pre-import validation failed. Signature does not match. Expect the GSA to fail on import")
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsaWI.importConfig(gsac, options.signpassword)
    log.info("Import completed")

  elif action == "export":
    if not options.outputFile:
      log.error("Output file not given")
      sys.exit(3)
    log.info("Exporting config from %s to %s" % (options.gsaHostName, options.outputFile) )
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsac = gsaWI.exportConfig(options.signpassword)
    gsac.writeFile(options.outputFile)
    log.info("Export completed")

  elif action == "verify":
    if not options.inputFile:
      log.error("Input file not given")
      sys.exit(3)
    gsac = gsaConfig(options.inputFile)
    if gsac.verifySignature(options.signpassword):
      log.info("XML Signature/HMAC matches supplied password" )
    else:
      log.warn("XML Signature/HMAC does NOT matches supplied password" )
      sys.exit(1)

  elif action == "setaccesscontrol":
    log.info("Setting access control")
    if options.cachetimeout:
      try:
        cachetimeout = int(options.cachetimeout)
        log.info("Value of cache timeout: %d" % (cachetimeout))
      except ValueError:
        log.error("Cache timeout is not an integer: %s" % (cachetimeout))
        sys.exit(3)
    if options.maxhostload:
      try:
        maxhostload = int(options.maxhostload)
        log.info("Value of cache timeout: %d" % (maxhostload))
      except ValueError:
        log.error("Cache timeout is not an integer: %s" % (maxhostload))
        sys.exit(3)

    if options.maxhostload and options.cachetimeout:
      gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
      gsaWI.setAccessControl(options.maxhostload, options.cachetimeout)
    elif options.maxhostload:
      gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
      gsaWI.setAccessControl(options.maxhostload)
    else:
      log.error("No value for Authorization Cache Timeout or Max Host Load")
      sys.exit(3)

  elif action == "all_urls":
    if not options.outputFile:
      log.error("Output file not given")
      sys.exit(3)
    try:
      f = open(options.outputFile, 'w')
    except IOError:
      log.error("unable to open %s to write" % options.outputFile)
      sys.exit(3)
    else:
      log.info("Retrieving URLs in crawl diagnostics to %s" % options.outputFile)
      gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
      gsaWI.getAllUrls(f)
      f.close()
      log.info("All URLs exported.")

  elif action == "database_sync":
    if not options.sources:
      log.error("No sources to sync")
      sys.exit(3)
    databases = options.sources.split(",")
    log.info("Sync'ing databases %s" % options.sources)
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsac = gsaWI.syncDatabases(databases)
    log.info("Sync completed")

  elif action == "keymatches_export":
    if not options.outputFile:
      log.error("Output file not given")
      sys.exit(3)
    if not options.frontend:
      log.error("No frontend defined")
      sys.exit(3)
    try:
      f = open(options.outputFile, 'w')
    except IOError:
      log.error("unable to open %s to write" % options.outputFile)
      sys.exit(3)

    log.info("Exporting keymatches for %s to %s" % (options.frontend, options.outputFile) )
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsaWI.exportKeymatches(options.frontend, f)
    f.close()

  elif action == "synonyms_export":
    if not options.outputFile:
      log.error("Output file not given")
      sys.exit(3)
    if not options.frontend:
      log.error("No frontend defined")
      sys.exit(3)
    try:
      f = open(options.outputFile, 'w')
    except IOError:
      log.error("unable to open %s to write" % options.outputFile)
      sys.exit(3)

    log.info("Exporting synonyms for %s to %s" % (options.frontend, options.outputFile) )
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsaWI.exportSynonyms(options.frontend, f)
    f.close()
  elif action == "status":
    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsaWI.getStatus()
