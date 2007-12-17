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
Serving > Forms Authentication
    URL: http://www.mycompany.com:8080/secure
    Cookie name: ObSSOCookie

You can use this program to mimic an Oblix server by running with the
--test_cookie_path option.

You can test whether bug #950572 has been fixed by running with the
test_bug_950572 option. This bug causes only one cookie to be sent by
the browser to the Admin Console.

For SSL, call this script with the --use_ssl option.

This script requires the cherrypy v3 to be installed (v2 gives an error
since quickstart is not available).
"""

__author__ = 'jlowry@google.com (John Lowry)'

import cherrypy
import urllib
import sys
import getopt

FORM_COOKIE = "ObFormLoginCookie"
SSO_COOKIE = "ObSSOCookie"

class Sso(object):

  def __init__(self, argv):
    self.test_cookie_path = False
    self.protocol = "http"
    self.test_bug_950572 = False
    try:
      opts, args = getopt.getopt(argv[1:], None, ["test_cookie_path", "use_ssl",
                                                  "test_bug_950572"])
    except getopt.GetoptError:
      print "Invalid arguments"
      sys.exit(1)
    for opt, arg in opts:
      if opt == "--test_cookie_path":
        self.test_cookie_path = True
      if opt == "--use_ssl":
        cherrypy.config.update({'global': {
            'server.ssl_certificate': 'ssl.crt',
            'server.ssl_private_key': 'ssl.key', }})
        self.protocol = "https"
      if opt == "--test_bug_950572":
        self.test_bug_950572 = True

  def index(self):
    return ("<a href=\"public\">public</a><br>"
            "<a href=\"secure\">secure</a><br>"
            "<a href=\"authorized\">authorized</a><br>"
            "<a href=\"logout\">logout</a>")

  def form(self, path="/"):
    if self.test_cookie_path and cherrypy.request.cookie.has_key(FORM_COOKIE):
        form_cookie = cherrypy.request.cookie[FORM_COOKIE].value
        self.redirect("login", "bad_cookie")
    else:
      cherrypy.response.cookie[SSO_COOKIE] = "1"
      return ("<h2>Login form</h2>"
              "<form action=login method=POST>"
              "<input type=hidden name=path value=\"%s\">"
              "Username: <input type=text name=login><br>"
              "Password: <input type=password name=password><br>"
              "<input type=submit>"
              "</form>") % (path)

  def get_host(self):
    return cherrypy.request.headers["host"]

  def login(self, login=None, password=None, path=None, msg=None):
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
      self.redirect(path)
    else:
      self.redirect("form?path=%s" % (path))

  def redirect(self, path, msg=None):
    cherrypy.response.status = 302
    if msg == None:
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

  def obrareq(self, path):
    cherrypy.response.cookie[FORM_COOKIE] = "1"
    cherrypy.response.cookie[FORM_COOKIE]["path"] = "/login"
    self.redirect("form?path=%s" % (path))

  def public(self):
    return "Anyone can view this page. No authentication is required"

  def secure(self):
    login = self.authenticate("secure")
    return ("You must be authenticated to view this page."
            "You are authenticated as &quot;%s&quot;.") % (login)

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

  login.exposed = True
  form.exposed = True
  public.exposed = True
  secure.exposed = True
  index.exposed = True
  authorized.exposed = True
  logout.exposed = True
  obrareq.exposed = True
  testcookiepath.exposed = True

def main(argv):
  pass

if __name__ == '__main__':
  cherrypy.quickstart(Sso(sys.argv))
