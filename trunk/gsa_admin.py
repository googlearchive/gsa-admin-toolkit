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

"""Classes for administering the Google Search Appliance.

Currently, the classes available can be used to import/export/rewrite
the config file. This module is designed to be expandable so that
other functionality can be easily included.

gsaConfig: Class for handling XML from GSA export/import.
gsaWebInterface: Class for interacting with GSA Web Interface.

Example usage:

1. Export the config file:

gsa.py -n <host> --port 8000 -u admin -p <pw> -e --sign-password
hellohello -o ~/tmp/o.xml -v

2. Make a change to the config file and sign:

./gsa.py -s --sign-password hellohello -f ~/tmp/o.xml -v -o ~/tmp/o2.xml

3. Import the new config file:

./gsa.py -n <host> --port 8000 -u admin -p <pw> -i --sign-password
hellohello -f ~/tmp/o2.xml -v

Note that you must use the same password to sign a file that you used
when exporting. You will get an error when importing if you do not do
this.
"""

__author__ = "alastair@mcc-net.co.uk (Alastair McCormack)"


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
from optparse import OptionParser, OptionGroup

reload(sys)
sys.setdefaultencoding("utf-8")
del sys.setdefaultencoding

DEFAULTLOGLEVEL=logging.INFO
log = logging.getLogger(__name__)

class gsaConfig:
  "Google Search Appliance XML configuration tool"

  configXMLString = None

  def __init__(self, fileName=None):
    if fileName:
      self.configXMLString = open(fileName).read()

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
    self.configXMLString = xmlString
    #log.warning("Signature maybe invalid. Please verify before uploading or saving")

  def getXMLContents(self):
    "Returns the contents of the XML file"
    return self.configXMLString

  def sign(self, password):
    doc = xml.dom.minidom.parseString(self.configXMLString)
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
    doc = xml.dom.minidom.parseString(self.configXMLString)
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

  def __init__(self, hostName, username, password, port=8000):
    self.baseURL = 'http://%s:%s/EnterpriseController' % (hostName, port)
    self.hostName = hostName
    self.username = username
    self.password = password
    self.cookieJar = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
    urllib2.install_opener(opener)

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
      request = urllib2.Request(self.baseURL)
      result = urllib2.urlopen(request)
      request = urllib2.Request(self.baseURL,
                                urllib.urlencode(
          {'actionType' : 'authenticateUser',
           'userName' : self.username,
           'password' : self.password}))

      log.debug("Logging in as %s..."  % self.username)
      result = urllib2.urlopen(request)
      resultString = result.read()
      home = re.compile("Google Search Appliance\s*&gt;\s*Home")
      if not home.search(resultString):
        log.error("Login failed")
        sys.exit(2)

      log.debug("Successfully logged in")
      self.loggedIn = True

  def _logout(self):
    request = urllib2.Request(self.baseURL,urllib.urlencode({'actionType' : 'logout'}))
    res = urllib2.urlopen(request)
    self.loggedIn = False

  def __del__(self):
    self._logout()

  def importConfig(self, gsaConfig, configPassword):
    fields = [("actionType", "importExport"), ("passwordIn", configPassword),
        ("import", " Import Configuration ")]

    files = [("importFileName", "config.xml", gsaConfig.getXMLContents() )]
    content_type, body = self._encode_multipart_formdata(fields, files)
    headers = {'User-Agent': 'python-urllib2', 'Content-Type': content_type}

    self._login()
    request = urllib2.Request(self.baseURL, body, headers)
    log.info("Sending XML...")
    result = urllib2.urlopen(request)
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
    request = urllib2.Request(self.baseURL,
                              urllib.urlencode({'actionType': 'importExport',
                                                'export': ' Export Configuration ',
                                                'password1': configPassword,
                                                'password2': configPassword}))

    log.debug("Fetching config XML")
    result = urllib2.urlopen(request)
    content = result.read()
    if content.count("Passphrase should be at least 8 characters long"):
      log.error("Passphrase should be at least 8 characters long. You entered: '%s'" % (configPassword))
      sys.exit(2)
    gsac = gsaConfig()
    log.debug("Returning gsaConfig object")
    gsac.setXMLContents(content)
    return gsac

  def setAccessControl(self, urlCacheTimeout):
    # Tested on 5.0.0.G.14
    self._login()
    request = urllib2.Request(self.baseURL,
                              urllib.urlencode({'actionType': 'cache',
                                                'authnLoginUrl': '',
                                                'authnArtifactServiceUrl': '',
                                                'sessionCookieExpiration': '480',
                                                'authzServiceUrl': '',
                                                'requestBatchTimeout': '5.0',
                                                'singleRequestTimeout': '2.5',
                                                'maxHostload': '10',
                                                'urlCacheTimeout': urlCacheTimeout,
                                                'saveSettings': 'Save Settings'}))
    result = urllib2.urlopen(request)
    content = result.read()


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
          help="Sign password for signing/import/export", metavar="FILE")

  parser.add_option("--cache-timeout", dest="cachetimeout",
          help="Value for Authorization Cache Timeout")

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

  parser.add_option_group(actionOptionsGrp)

  # gsaHostOptions
  gsaHostOptions = OptionGroup(parser, "import/export to/from GSA")

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

  if not options.setaccesscontrol:
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
  if not action:
      log.error("No action specified")
      sys.exit(3)

  if action == "import" or action == "export":
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
    if not options.cachetimeout:
      log.error("No value for Authorization Cache Timeout")
      sys.exit(3)
    try:
      cachetimeout = int(options.cachetimeout)
      log.info("Value of cache timeout: %d" % (cachetimeout))
    except ValueError:
      log.error("Cache timeout is not an integer: %s" % (cachetimeout))
      sys.exit(3)

    gsaWI = gsaWebInterface(options.gsaHostName, options.gsaUsername, options.gsaPassword)
    gsaWI.setAccessControl(options.cachetimeout)
