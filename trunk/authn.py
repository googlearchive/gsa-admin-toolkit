#!/usr/bin/python
#
# Copyright (C) 2007 Google Inc.
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


""" Simple web server for testing the Authn/Authz SPI

This script runs a web server on port 8080 that allows you
to test the Authn/Authz SPI on the Google Search Appliance.
If you run the script on a host called "www.foo.com",
then configure the appliance "search.foo.com" as
follows:

Start crawling from: http://www.foo.com:8080/
Follow pattern: www.foo.com:8080/
Crawler access:
  Pattern: www.foo.com:8080/
  Username: crawler
  Password: crawler
  Make Public: unchecked
Serving > Access Control
  User login URL: http://www.foo.com:8080/login?host=search.foo.com
  Artifact service URL: http://www.foo.com:8080/artifact_service
  Authz service URL: http://www.foo.com:8080/authz
  Disable prompt for Basic authentication: checked

Be sure to always use FQDNs so that cookie domains are consistent.

After the crawl has completed, you can test serving with the
following command:

curl --insecure --location-trusted -v --basic --user user1:userpw \
-b /tmp/cookies "http://search.foo.com/search?q=secure&site=default_collection\
&client=default_frontend&output=xml&access=a"

This script requires the cherrypy module to be installed:

http://www.cherrypy.org/
"""

__author__ = 'jlowry@google.com (John Lowry)'

import cherrypy
import time
import md5
import urllib
import re
import urllib2
import sys
import base64


class AuthN(object):

  def __init__(self):
    self.realm = "authn"
    self.user_db = {'user1':'userpw', 'crawler':'crawler'}
    self.passwd_db = {}
    for user in self.user_db:
      self.passwd_db[user] = md5.new(self.user_db[user]).hexdigest()

  def index(self):
    return ("<a href=\"public\">public</a><br>"
            "<a href=\"secure\">secure</a><br>"
            "<a href=\"sleep\">sleep</a><br>"
            "<a href=\"authorized\">authorized</a>")

  def authenticate(self):
    print cherrypy.request.headers
    cherrypy.tools.basic_auth.callable(self.realm, self.passwd_db)
    return cherrypy.request.login

  def public(self):
    return "Anyone can view this page. No authentication is required"

  def secure(self):
    login = self.authenticate()
    return ("You must be authenticated to view this page."
            "You are authenticated as &quot;%s&quot;.") % (login)

  def sleep(self):
    login = self.authenticate()
    time.sleep(75)
    return "I'm awake!"

  def authorized(self):
    login = self.authenticate()
    if login == "crawler":
      return ("You must be authorized to view this page."
              "You are authenticated as &quot;%s&quot;.") % (login)
    else:
      raise cherrypy.HTTPError(401, "Unauthorized")

  def login(self, RelayState=None, SAMLRequest=None, host=None):
    if host == None:
      raise cherrypy.HTTPError(500, "no host parameter specified")
    login = self.authenticate()
    cherrypy.response.status = 302
    location = "http://%s/SamlArtifactConsumer?SAMLart=%s&RelayState=%s" % \
               (host, login, urllib.quote(RelayState))
    cherrypy.response.headers["location"] = location
    return

  def artifact_service(self, SAMLart=None, RelayState=None):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pattern = re.compile(".*<samlp:Artifact>(.*)</samlp:Artifact>.*")
    body = cherrypy.request.body.read()
    print "Body is: %s" % (body)
    match = pattern.match(body)
    login = match.group(1)
    if cherrypy.request.headers["host"].find(":") > -1:
      host = cherrypy.request.headers["host"].split(":")[0]
    else:
      host = cherrypy.request.headers["host"]
    response = ("<SOAP-ENV:Envelope "
                "xmlns:SOAP-ENV=\"http://schemas.xmlsoap.org/soap/envelope/\">"
                "<SOAP-ENV:Body><samlp:ArtifactResponse "
                "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\" "
                "xmlns=\"urn:oasis:names:tc:SAML:2.0:assertion\" "
                "ID=\"alsorandomlooking\" Version=\"2.0\" "
                "InResponseTo=\"randomlooking\" IssueInstant=\"%s\">"
                "<Issuer>%s</Issuer><samlp:Status><samlp:StatusCode "
                "Value=\"urn:oasis:names:tc:SAML:2.0:status:Success\"/>"
                "</samlp:Status><samlp:Response ID=\"blahblah\" "
                "Version=\"2.0\" IssueInstant=\"%s\">"
                "<samlp:Status><samlp:StatusCode "
                "Value=\"urn:oasis:names:tc:SAML:2.0:status:Success\"/>"
                "</samlp:Status><Assertion Version=\"2.0\" ID=\"blahblah2\" "
                "IssueInstant=\"%s\"><Issuer>%s</Issuer><Subject>"
                "<NameID>CN=%s</NameID></Subject><AuthnStatement "
                "AuthnInstant=\"%s\"><AuthnContext><AuthnContextClassRef> "
                "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport "
                "</AuthnContextClassRef></AuthnContext></AuthnStatement>"
                "</Assertion></samlp:Response></samlp:ArtifactResponse>"
                "</SOAP-ENV:Body>"
                "</SOAP-ENV:Envelope>") % (now, host, now, now, host, login, now)
    print response
    return response

  def authz(self):
    body = cherrypy.request.body.read()
    pattern = re.compile(""".*Resource="([^"]*)".*""")
    match = pattern.match(body)
    resource = match.group(1)
    pattern = re.compile(""".*<saml:NameID>CN=(.*)</saml:NameID>.*""")
    match = pattern.match(body)
    login = match.group(1)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if cherrypy.request.headers["host"].find(":") > -1:
      host = cherrypy.request.headers["host"].split(":")[0]
    else:
      host = cherrypy.request.headers["host"]
    base64string = base64.encodestring('%s:%s' % (login, self.user_db[login]))[:-1]
    req = urllib2.Request(resource)
    req.add_header("Authorization", "Basic %s" % base64string)
    try:
      urllib2.urlopen(req)
      decision = "Permit"
    except:
      type, value, tb = sys.exc_info()
      # l = traceback.format_tb(tb, None)
      # print "%-20s%s: %s" % (string.join(l[:], ""), type, value)
      print "Exception: %s %s" % (type, value)
      decision = "Deny"
    response = ("<soapenv:Envelope "
                "xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\">"
                "<soapenv:Body><samlp:Response "
                "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\" "
                "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\" "
                "ID=\"blahblah\" Version=\"2.0\" IssueInstant=\"%s\">"
                "<samlp:Status><samlp:StatusCode "
                "Value=\"urn:oasis:names:tc:SAML:2.0:status:Success\"/>"
                "</samlp:Status><saml:Assertion Version=\"2.0\" "
                "ID=\"blahblah2\" IssueInstant=\"%s\">"
                "<saml:Issuer>%s</saml:Issuer><saml:Subject>"
                "<saml:NameID>CN=%s</saml:NameID></saml:Subject>"
                "<saml:AuthzDecisionStatement Resource=\"%s\" "
                "Decision=\"%s\"><saml:Action "
                "Namespace=\"urn:oasis:names:tc:SAML:1.0:action:ghpp\">"
                "GET</saml:Action></saml:AuthzDecisionStatement>"
                "</saml:Assertion></samlp:Response></soapenv:Body>"
                "</soapenv:Envelope>") % (now, now, host, login, resource, decision)
    print response
    return response

  authz.exposed = True
  artifact_service.exposed = True
  login.exposed = True
  public.exposed = True
  secure.exposed = True
  index.exposed = True
  authorized.exposed = True
  sleep.exposed = True


def main(argv):
  pass

if __name__ == '__main__':
  cherrypy.quickstart(AuthN())
