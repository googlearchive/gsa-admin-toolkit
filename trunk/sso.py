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


""" Simple web server for testing Cookie Crawl.



"""

__author__ = 'jlowry@google.com (John Lowry)'

import cherrypy
import urllib
import sys
import getopt

class Sso(object):

  def __init__(self, argv):
    self.FORM_COOKIE = "ObFormLoginCookie"
    self.SSO_COOKIE = "ObSSOCookie"
    self.test_cookie_path = False
    try:
      opts, args = getopt.getopt(argv[1:], None,["test_cookie_path"])
    except getopt.GetoptError:
      print "Invalid arguments"
      sys.exit(1)
    for opt, arg in opts:
      if opt == "--test_cookie_path":
        self.test_cookie_path = True

  def index(self):
    return ("<a href=\"public\">public</a><br>"
            "<a href=\"secure\">secure</a><br>"
            "<a href=\"authorized\">authorized</a><br>"
            "<a href=\"logout\">logout</a>")

  def form(self, path="/"):
    if self.test_cookie_path:
      try:
        form_cookie = cherrypy.request.cookie[self.FORM_COOKIE].value
        return "%s incorrectly sent" % (self.FORM_COOKIE)
      except:
        # this is expected
        pass
    return ("<h2>Login form</h2>"
            "<form action=login>"
            "<input type=hidden name=path value=\"%s\">"
            "Username: <input type=text name=login><br>"
            "Password: <input type=psssword name=password><br>"
            "<input type=submit>"
            "</form") % (path)

  def get_host(self):
    return cherrypy.request.headers["host"]

  def login(self, login, password, path):
    if self.test_cookie_path:
      try:
        form_cookie = cherrypy.request.cookie[self.FORM_COOKIE].value
        # this is expected
      except:
        return "You did not send %s" % (self.FORM_COOKIE)
    if login != None and login.strip() != "":
      cherrypy.response.cookie[self.SSO_COOKIE] = urllib.quote(login.strip())
      self.redirect(path)
    else:
      self.redirect("form?path=%s" % (path))

  def redirect(self, path):
    cherrypy.response.status = 302
    location = "http://%s/%s" % (self.get_host(), path)
    cherrypy.response.headers["location"] = location

  def authenticate(self, path):
    print cherrypy.request.headers
    try:
      login = cherrypy.request.cookie[self.SSO_COOKIE].value
      return login
    except:
      if self.test_cookie_path:
        cherrypy.response.cookie[self.FORM_COOKIE] = "1"
        cherrypy.response.cookie[self.FORM_COOKIE]["path"] = "/login"
        self.redirect("obrareq?path=%s" % (path))
      else:
        self.redirect("form?path=%s" % (path))

  def obrareq(self, path):
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
    cherrypy.response.cookie[self.SSO_COOKIE] = ""
    cherrypy.response.cookie[self.SSO_COOKIE]['expires'] = 0
    if self.test_cookie_path:
      cherrypy.response.cookie[self.FORM_COOKIE] = ""
      cherrypy.response.cookie[self.FORM_COOKIE]['expires'] = 0
    return "You are logged out. Return to the <a href=/>index</a>."


  login.exposed = True
  form.exposed = True
  public.exposed = True
  secure.exposed = True
  index.exposed = True
  authorized.exposed = True
  logout.exposed = True
  obrareq.exposed = True

def main(argv):
  pass

if __name__ == '__main__':
  cherrypy.quickstart(Sso(sys.argv))
