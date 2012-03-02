#!/usr/bin/python
#
# Copyright 2010 Google Inc. All Rights Reserved.
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


"""Simple web server for testing the Authz

usage:
  ./authz.py
    --debug           Show debug logs

    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected

    --port=           Set the listener port of the cherrypy webserver
                      (default 28081)

    --saml_issuer=    set the SAML_issuer ID parameter
                      Default is set to authz.py

    --backend=        *Required* Set the authz database backend to use. Should be 
                      specified in the form <module>.<class>. If only the class is
                      provided, then the script will look for the class in the
                      list of globals.

This script runs a web server on port 28081 that allows you to test the
Authz SPI on the Google Search Appliance.

The authz.py script is basically a SAML Policy server which authorizes users and
then complies the result with SAML2.0 specifications.

It is not designed to handle full production load but rather just as a
proof-of-concept.

This script comes with two authz backends: DictAuthzBackend and
FileAuthzBackend.
  DictAuthzBackend: Simply determines a user's access to a resource as defined
    in a hardcoded dictionary.  See self.authz_db variable in DictAuthzBackend
  FileAuthzBackend: Reads access rules from the file 'acl.txt' in the current
    directory. The acl.txt file is a text file in the following format:
      resource1|user1,user2
      resource2|user2
      (etc.)

It's very simple to write custom authorization backends: simply implement the
AuthzBackend interface and provide the authorize(username, resource) method (see
the documentation for AuthzBackend for more details). To use the custom
backend, run authz.py with the --backend option specifiying the module and class
name of the backend.

SETUP and RUN configuration.
   After startup, you can view the configured authz backend by visiting
   http://idp.yourdomain.com:28081/  (if idp.yourdomain.com is where authz.py
   is running)

   In the GSA admin interface, go to:
            Serving-->Access Control
                          Authorization service URL:
                            http://idp.yourdomain.com:28081/authz

This script requires the cherrypy v3 to be installed (v2 gives an error since
quickstart is not available).

http://www.cherrypy.org/

Also see:
code.google.com/apis/searchappliance/documentation/64/authn_authz_spi.html
"""


import datetime
import getopt
import random
import sys
import time
import xml.dom.minidom
import cherrypy
from xml.sax.saxutils import escape
from socket import gethostname


class AuthZ(object):

  def __init__(self, authz_backend, protocol, debug_flag, saml_issuer):
    self.authz_backend = authz_backend
    self.protocol = protocol
    self.debug_flag = debug_flag
    self.saml_issuer = saml_issuer

    log ('--------------------------------')
    log ('-----> Starting authz.py <------')
    log ('--------------------------------')


  # Main landing page
  def index(self):
    return ('<html><head><title>Authz Landing Page</title></head>'
            '<body><center>'
            '<h3>Landing page for SPI authz.py</h3>'
            '<p>Authz backend: %s</p>'
            '</center></body></html>') % self.authz_backend.__class__.__name__
  index.exposed = True

  # Public page
  def public(self):
    return 'Anyone can view this page. No authentication is required"'
  public.exposed = True

  # Generates SAML 2.0 IDs randomly.
  def getrandom_samlID(self):
    # Generate a randomID starting with an character
    return random.choice('abcdefghijklmnopqrstuvwxyz') + hex(random.getrandbits(160))[2:-1]

  # 
  def get_saml_namespace(self, xmldoc, tagname):
    a = xmldoc.getElementsByTagName('samlp:%s' % tagname)
    if a != []:
      return ("samlp", "saml", a)
    a = xmldoc.getElementsByTagName('saml2p:%s' % tagname)
    if a != []:
      return ("saml2p", "saml2", a)

    log("exotic namespace")
    #  TODO get the name space and return it
    return ("", "", [])

  # The SAML Authorization service (/authz) called by the GSA to query to see
  # if individual URLs are authorized for a given user. Both the username
  # and the URL to check for is passed in
  def authz(self):
    authz_request = cherrypy.request.body.read()
    xmldoc = xml.dom.minidom.parseString(authz_request)

    if self.debug_flag:
      log('-----------  AUTHZ BEGIN  -----------')
      log('AUTHZ Request: %s' % xmldoc.toprettyxml())

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    # The request should look something like
    #    request = ("<soapenv:Envelope xmlns:soapenv=\
    #        "http://schemas.xmlsoap.org/soap/envelope/\"
    #               "xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\"
    #               "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
    #               "<soapenv:Body>"
    #               "<samlp:AuthzDecisionQuery ID=
    #                    \"dbppegngllhegcobmfponljblmfhjjiglbkbmmco\"
    #               "IssueInstant=\"2008-07-09T15:22:55Z\""
    #               "Resource=\"secure.yourdomain.com/protected/page2.html\"
    #                        Version=\"2.0\"
    #               "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\""
    #               "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\">"
    #               "<saml:Issuer>google.com</saml:Issuer>"
    #               "<saml:Subject>"
    #               "<saml:NameID>user1</saml:NameID>"
    #               "</saml:Subject>"
    #               "<saml:Action Namespace=\"urn:oasis:names:tc:SAML:1.0:
    #                        action:ghpp\">GET</saml:Action>"
    #               "</samlp:AuthzDecisionQuery>"
    #               "<samlp:AuthzDecisionQuery ID=
    #                    \"eeppegngllhegcobmfabcnljblmfhrrniglbkbeed\"
    #               "IssueInstant=\"2008-07-09T15:22:55Z\""
    #               "Resource=\"secure.yourdomain.com/protected/page3.html\"
    #                        Version=\"2.0\"
    #               "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\""
    #               "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\">"
    #               "<saml:Issuer>google.com</saml:Issuer>"
    #               "<saml:Subject>"
    #               "<saml:NameID>user1</saml:NameID>"
    #               "</saml:Subject>"
    #               "<saml:Action Namespace=\"urn:oasis:names:tc:SAML:1.0:
    #                        action:ghpp\">GET</saml:Action>"
    #               "</samlp:AuthzDecisionQuery>"
    #               "</soapenv:Body>"
    #               "</soapenv:Envelope>")

    saml_id = None
    resource = None
    username = None

    # parse out the SAML AuthzRequest
    # If we don't know *for sure* if a user is allowed or not, send back an
    # indeterminate.  if the URL does *not* exist in the built in self.authz_db,
    # then we don't know if the user is allowed
    # or not for sure, then send back an Indeterminate.

    # GSA 6.0+ can request batch authorization where there can be multiple
    # samlp:AuthzDecisionQuery  in one request for several URLs
    # which means we have to responde back in one response for each request.

    # If we're using the internal authz system, parse out the inbound
    # request for the URI and use that to check against the local authz db

    (spprefix, sprefix, samlp) = self.get_saml_namespace(xmldoc, 'AuthzDecisionQuery')
    log('using prefix: %s and %s' % (spprefix, sprefix))

    response = ('<soapenv:Envelope '
                'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
                '<soapenv:Body>')

    for node in samlp:
      if (node.nodeName == "%s:AuthzDecisionQuery" % spprefix):
        saml_id = node.attributes["ID"].value
        resource = node.attributes["Resource"].value
        samlName = node.getElementsByTagName("%s:NameID" % sprefix)
        for n_issuer in samlName:
          cnode= n_issuer.childNodes[0]
          if cnode.nodeType == node.TEXT_NODE:
            username = cnode.nodeValue
        # the SAML response and assertion are unique random ID numbers
        # back in the sring with the decision.
        rand_id_saml_resp = self.getrandom_samlID()
        rand_id_saml_assert = self.getrandom_samlID()

        decision = self.authz_backend.authorize(username, resource)

        if self.debug_flag:
          log ('authz ID: %s' %(saml_id))
          log ('authz Resource: %s' %(resource))
          log ('authz samlName %s' %(username))
          log ('authz decision for resource %s [%s]' % (resource, decision))

        response = response + ('<samlp:Response '
             'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
             'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
             'ID="%s" Version="2.0" IssueInstant="%s">'
             '<samlp:Status><samlp:StatusCode '
             'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
             '</samlp:Status><saml:Assertion Version="2.0" '
             'ID="%s" IssueInstant="%s">'
             '<saml:Issuer>%s</saml:Issuer><saml:Subject>'
             '<saml:NameID>%s</saml:NameID></saml:Subject>'
             '<saml:AuthzDecisionStatement Resource="%s" '
             'Decision="%s"><saml:Action '
             'Namespace="urn:oasis:names:tc:SAML:1.0:action:ghpp">'
             'GET</saml:Action></saml:AuthzDecisionStatement>'
             '</saml:Assertion></samlp:Response>') % (rand_id_saml_resp,now,
                                                      rand_id_saml_assert,
                                                      now, self.saml_issuer, username,
                                                      escape(resource), decision)

    response += '</soapenv:Body></soapenv:Envelope>'

    if self.debug_flag:
      xmldoc = xml.dom.minidom.parseString(response)
      log('authz response %s' %(xmldoc.toprettyxml()))
      log('-----------  AUTHZ END  -----------')

    return response
  authz.exposed = True


class AuthzBackend(object):
  def authorize(username, resource):
    """Checks if a user is authorized to view a resource.

    Args:
      username: The username (string).
      resource: The resource URL (string).

    Returns:
      A string indicating the result. 'Permit' if the user is permitted to
      access the resource, 'Deny' if not, or 'Indeterminate' if unknown
      (authorization will be passed on to a fallback mechanism).
    """
    raise NotImplementedError('authorize() not implemented')


class DictAuthzBackend(AuthzBackend):
  def __init__(self):
    self.authz_db = {'http://secure.yourdomain.com/protected/page1':
                     'user1,user2,gsa1',
                     'http://secure.yourdomain.com/protected/page2':
                     'user1,gsa1',
                     'http://secure.yourdomain.com/protected/page3':
                     'user2,gsa1',
                     'http://secure.yourdomain.com/protected/page4':
                     'user1,user2,gsa1',
                     'http://meow2.mtv.corp.google.com:8000/blah-allowed.html':'user2'}

  def authorize(self, username, resource):
    decision = 'Indeterminate'
    allowed_users = None
    try:
      allowed_users = self.authz_db[resource]
    except KeyError:
      log('Resource not found in database: %s ' %(resource))
    else:
      arr_users = allowed_users.split(",")
      log('Allowed users for Resource: %s %s ' %(resource, arr_users))
      if username in arr_users:
        decision = 'Permit'
      else:
        decision = 'Deny'
    return decision


class FileAuthzBackend(AuthzBackend):
  def __init__(self):
    self.db = {}
    input = open('acl.txt', 'r')
    for line in input:
      arr = line.strip().split('|')
      resource, users = arr[0], arr[1]
      if resource in self.db:
        log('Warning: resource %s duplicated in file authz backend input' %
            resource)
      self.db[resource] = users.split(',')
    input.close()

  def authorize(self, username, resource):
    if resource not in self.db:
      return 'Indeterminate'
    if username in self.db[resource]:
      return 'Permit'
    return 'Deny'


def log(msg):
  print ('[%s] %s') % (datetime.datetime.now(), msg)


# -------
# Main
# -------------
def main():
  # Default listen port
  cherrypy.server.socket_port = 28081
  cherrypy.server.socket_host = '0.0.0.0'
  protocol = "http"
  debug_flag = False
  saml_issuer = "authn.py"
  backend = None

  def usage():
    print ('\nUsage: authz.py --debug --use_ssl '
           '--port=<port> --saml_issuer=<issuer> --backend=<backend>\n')

  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["debug", "use_ssl", "port=", "saml_issuer=",
                                "backend="])
  except getopt.GetoptError:
    usage()
    sys.exit(1)

  cherrypy.config.update({'global':{'log.screen': False}})
  for opt, arg in opts:
    if opt == "--debug":
      debug_flag = True
      cherrypy.config.update({'global':{'log.screen': True}})
    if opt == "--saml_issuer":
      saml_issuer = arg
    if opt == "--use_ssl":
      protocol = "https"
      cherrypy.config.update({"global": {
          "server.ssl_certificate": "ssl.crt",
          "server.ssl_private_key": "ssl.key",}})
    if opt == "--port":
      port = int(arg)
      cherrypy.config.update({"global": {"server.socket_port": port}})
    if opt == "--backend":
      backend = arg

  # try to import the backend class
  if not backend:
    print '\n--backend= required. Please see documentation.\n'
    usage()
    sys.exit(1)
  modulename, _, classname = backend.rpartition('.')
  if not modulename:
    # if no module name, then try to get it from globals
    backend_class = globals()[classname]
  else:
    # otherwise, import that module and get it from there
    module = __import__(modulename)
    backend_class = getattr(module, classname)

  cherrypy.quickstart(AuthZ(backend_class(), protocol, debug_flag,
                            saml_issuer))

if __name__ == '__main__':
  main()
