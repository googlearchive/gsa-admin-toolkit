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
#
# This code is not supported by Google
#

""" Simple web server for testing Cookie Sites.

This is a simple web server for testing Forms Authentication and
Cookie Sites in a Google Search Appliance. Configure the Admin Console
as follows:

Crawl and Index
  Crawl URLs:
    Start crawling from: http://www.mycompany.com:8080/
    Follow patterns: http://www.mycompany.com:8080/
  Cookie Sites/Forms Authentication:
    URL of the login page: http://www.mycompany.com:8080/secure
    URL pattern for this rule: http://www.mycompany.com:8080/
    Click "Create a New Cookie/Forms Authentication Rule"
    Enter username "crawler" and password "crawler". Submit form.
    Click "Save Cookie Rule and Close Window".

For Legacy Authn:

Serving > Forms Authentication
    URL: http://www.mycompany.com:8080/secure
    Cookie name: sso

    If you want to use External Login you can check the
    "Always redirect to external login server"  option and point
    the appliance to http://myhost.mydomain.com:8080/externalLogin
    Note that the external login script will not work when
    calling sso.py with the test_cookie_path option.
    You must also set the --cookied_domain  and --gsa_host options
    to something like
          --cookie_domain=".mydomain.com"
          --gsa_host="search.mydomain.com"

For Security Manager (if using the Universal Login Form, not silent authentication):
    Use the Default credential group.
    Set up an Auth Mechanism as follows:
      Credential Group: Default
      Redirect to a form when sample URL check fails: checked
      Mechanism name: test
      Sample URL: http://www.mycompany.com:8080/secure

Options:

  --cookie_cracking         Return X-Username: and X-Groups for "/secure"
  --cookie_domain=          Specifies Cookie Domain.
                            Required if you access sso.py's login form directly.
  -- gsa_host=                   The Fully Qualified Domain Name of the GSA.
                            Required if you use Legacy AuthN and no Referrer presents.
  --test_cookie_path        Mimics an Oblix server's cookie handling
  --test_bug_950572         Tests whether bug has been fixed that
                            prevents more than one cookie being handled
  --test_meta_refresh       Tests whether appliance handles meta refresh
  --use_ssl                 Run server as HTTP

This script requires the cherrypy v3 to be installed (v2 gives an error
since quickstart is not available).
"""

__author__ = 'jlowry@gmail.com (John Lowry)'

import cherrypy
import urllib
import sys
import time
import getopt
from socket import gethostname

FORM_COOKIE = "form"
SSO_COOKIE = "sso"

class Sso(object):

  def __init__(self, cookie_cracking, cookie_domain, gsa_host, test_cookie_path, protocol, test_bug_950572, test_meta_refresh, delay):
    self.cookie_cracking = cookie_cracking
    self.test_cookie_path = test_cookie_path
    self.protocol = protocol
    self.test_bug_950572 = test_bug_950572
    self.test_meta_refresh = test_meta_refresh
    self.delay = delay
    self.cookie_domain = ""
    if cookie_domain:
      self.cookie_domain = cookie_domain
    self.search_host = ""
    if gsa_host:
      self.search_host = gsa_host;

  def index(self):
    secure_links = "Additional secure links: "
    for i in range(1000):
      secure_links += "<a href=\"secure?param=%s\">.</a>" % (i)
    return ("<a href=\"public\">public</a><br>"
            "<a href=\"secure\">secure</a><br>"
            "<a href=\"authorized\">authorized</a><br>"
            "<a href=\"logout\">logout</a><br>"
            "%s" % (secure_links))

  def form(self, path="/"):
    if self.test_cookie_path and cherrypy.request.cookie.has_key(FORM_COOKIE):
      form_cookie = cherrypy.request.cookie[FORM_COOKIE].value
      self.redirect("login", "bad_cookie")
    else:
      return ("<h2>Login form</h2>"
              "<form action=/login method=POST>"
              "<input type=hidden name=path value=\"%s\">"
              "Username: <input type=text name=login><br>"
              "Password: <input type=password name=password><br>"
              "<input type=submit>"
              "</form>") % (path)

  def get_host(self):
    return cherrypy.request.headers["host"]

  def login(self, login=None, password=None, path="", msg=None):
    # print cherrypy.request.headers
    if self.test_cookie_path:
      if msg != None:
        return "You got message: %s" % (msg)
      if cherrypy.request.cookie.has_key(FORM_COOKIE):
        form_cookie = cherrypy.request.cookie[FORM_COOKIE].value
        # Firefox sends sso_cookie but Admin Console in 4.6.4.G.70
        # and 5.0 does not due to bug #950572.
        if self.test_bug_950572:
          sso_cookie = cherrypy.request.cookie[SSO_COOKIE].value
          if sso_cookie != "1":
            return "Wrong value for %s cookie." % (SSO_COOKIE)
      else:
        return "You did not send a required cookie."
    if login != None and login.strip() != "":
      cherrypy.response.cookie[SSO_COOKIE] = urllib.quote(login.strip())
      if self.cookie_domain:
        cherrypy.response.cookie[SSO_COOKIE]['domain'] = self.cookie_domain
      self.redirect(path)
    else:
      self.redirect("form?path=%s" % (path))

  def redirect(self, path, msg=None):
    cherrypy.response.status = 302
    if path.startswith("http://") or path.startswith("https://"):
     location = path
    elif msg == None:
      location = "%s://%s/%s" % (self.protocol, self.get_host(), path)
    else:
      location = "%s://%s/%s?msg=%s" % (self.protocol, self.get_host(), path, msg)
    cherrypy.response.headers["location"] = location

  def authenticate(self, path):
    if cherrypy.request.cookie.has_key(SSO_COOKIE):
      return cherrypy.request.cookie[SSO_COOKIE].value
    else:
      if self.test_cookie_path:
        uri = "obrareq?path=%s" % (path)
      else:
        uri = "form?path=%s" % (path)
      location = "%s://%s/%s" % (self.protocol, self.get_host(), uri)
      raise cherrypy.HTTPRedirect(location)

  def externalLogin (self, returnPath=None):
    if not returnPath:
      return "Need to specify returnPath"
    if returnPath.startswith ("http://") or returnPath.startswith("https://"):
    # Security Manager sets returnPath with the host part
      path = returnPath
    else:
    # Legacy AuthN sets returnPath without the host part
    #
      if cherrypy.request.headers.has_key("Referer"):
        returnHost = cherrypy.request.headers["Referer"].split('/')[2]
      else:
        returnHost = self.search_host
      path = "http://" + returnHost + returnPath
    self.authenticate(urllib.quote(path))
    self.redirect(path)

  def obrareq(self, path):
    cherrypy.response.cookie[FORM_COOKIE] = "1"
    cherrypy.response.cookie[FORM_COOKIE]["path"] = "/login"
    self.redirect("form?path=%s" % (path))

  def public(self):
    return "Anyone can view this page. No authentication is required"

  def secure(self, redirected=None, param=None):
    # print cherrypy.request.headers
    login = self.authenticate("secure")
    if self.cookie_cracking:
      cherrypy.response.headers["X-Username"] = login
      cherrypy.response.headers["X-Groups"] = "ssopygroup"
    refresh = ""
    if self.test_meta_refresh:
      this_url = "%s://%s/secure?redirected=1" % (self.protocol, self.get_host())
      if not redirected:
        refresh = """<meta http-equiv="Refresh" content ="0;URL=%s">""" % this_url
    if self.delay:
      time.sleep(self.delay)
    return ("<html><head>%s</head><body>"
            "You must be authenticated to view this page."
            "You are authenticated as &quot;%s&quot;. "
            "The value of param is '%s'."
            "</body></html>") % (refresh, login, param)

  def authorized(self):
    login = self.authenticate("authorized")
    if login == "crawler":
      return ("You must be authorized to view this page."
              "You are authenticated as &quot;%s&quot;.") % (login)
    elif login == None or login == "":
      self.redirect("form?path=authorized")
    else:
      raise cherrypy.HTTPError(401, "Unauthorized")

  def logout(self):
    cherrypy.response.cookie[SSO_COOKIE] = ""
    if self.cookie_domain:
      cherrypy.response.cookie[SSO_COOKIE]['domain'] = self.cookie_domain
    cherrypy.response.cookie[SSO_COOKIE]['expires'] = 0
    if self.test_cookie_path:
      cherrypy.response.cookie[FORM_COOKIE] = ""
      cherrypy.response.cookie[FORM_COOKIE]['expires'] = 0
    return "You are logged out. Return to the <a href=/>index</a>."

  def testcookiepath(self, value=None):
    if value != None and value == "1":
      self.test_cookie_path = True
    elif value != None and value == "0":
      self.test_cookie_path = False
    return str(self.test_cookie_path)

  def set_cookie_domain(self, value=None):
    if value != None:
      self.cookie_domain = value
    return str(self.cookie_domain)

  def set_search_host(self, value=None):
    if value != None:
      self.search_host = value
    return str(self.search_host)

  login.exposed = True
  form.exposed = True
  public.exposed = True
  secure.exposed = True
  index.exposed = True
  authorized.exposed = True
  logout.exposed = True
  obrareq.exposed = True
  testcookiepath.exposed = True
  externalLogin.exposed = True
  set_cookie_domain.exposed = True
  set_search_host.exposed = True

def main(argv):
  pass

if __name__ == '__main__':
  cookie_cracking = False
  cookie_domain = None
  gsa_host = None
  test_cookie_path = False
  protocol = "http"
  test_bug_950572 = False
  test_meta_refresh = False
  delay = 0
  # By default cherrypy runs on localhost
  # But we would normally want to run on the external interface
  hostname = gethostname()
  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["cookie_cracking", "cookie_domain=", "gsa_host=",
                                                "test_cookie_path", "use_ssl",
                                                "test_bug_950572", "test_meta_refresh",
                                                "port=", "delay=", "host="])
  except getopt.GetoptError:
    print "Invalid arguments"
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--cookie_cracking":
      cookie_cracking = True
    if opt=="--cookie_domain":
      cookie_domain = arg
    if opt == "--gsa_host":
      gsa_host = arg
    if opt == "--test_cookie_path":
      test_cookie_path = True
    if opt == "--use_ssl":
      cherrypy.config.update({"global": {
          "server.ssl_certificate": "ssl.crt",
          "server.ssl_private_key": "ssl.key", }})
      protocol = "https"
    if opt == "--test_bug_950572":
      test_bug_950572 = True
    if opt == "--test_meta_refresh":
      test_meta_refresh = True
    if opt == "--port":
      # By default, runs on port 8080
      port = int(arg)
      cherrypy.config.update({"global": { "server.socket_port": port }})
    if opt == "--delay":
      delay = int(arg)
    if opt == "--host":
      hostname = arg

  cherrypy.config.update({"global": { "server.socket_host": hostname }})
  cherrypy.quickstart(Sso(cookie_cracking, cookie_domain, gsa_host, test_cookie_path, protocol, test_bug_950572, test_meta_refresh, delay))
