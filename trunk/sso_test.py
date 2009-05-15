#!/usr/bin/python2.4
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


"""Unit tests for SSO server.

The SSO server must be running on localhost port 8080.

We test the following conditions:

         with right cookies without auth cookie bad cookie
          test_cookie_path   test_cookie_path
          enabled disabled   enabled disabled
  /public       x        x
  /secure       x        x         x        x
  /login        x        x                               x
  /form         x        x                               x
  /obrareq      x

"""

__author__ = 'jlowry@google.com (John Lowry)'

import getopt
import urllib
import urllib2
import cookielib
import sys
import unittest
import sso


class CustomRedirectHandler(urllib2.HTTPRedirectHandler):

  def http_error_302(self, req, fp, code, msg, headers):
    return None

  def http_error_303(self, req, fp, code, msg, headers):
    return None

class Error(Exception):
  """Base exception class for this module."""
  pass


class SsoUnitTestException(Error):
  """Exception thrown when running the unit tests.."""
  pass


class SsoUnitTest(unittest.TestCase):

  url_prefix = "http://localhost:8080"
  login = "test1"
  cookie_domain = ".foo.com"
  search_host = "search.foo.com"

  def setUp(self):
    url = "%s/testcookiepath" % (SsoUnitTest.url_prefix)
    f = urllib2.urlopen(url)
    val = f.read()
    if val.find("True") > -1:
      self.test_cookie_path = 1
    else:
      self.test_cookie_path = 0
    url = "%s/set_cookie_domain" % (SsoUnitTest.url_prefix)
    f = urllib2.urlopen(url)
    self.cookie_domain = f.read()
    url = "%s/set_search_host" % (SsoUnitTest.url_prefix)
    f = urllib2.urlopen(url)
    self.search_host = f.read()

  def tearDown(self):
    url = "%s/testcookiepath?value=%s" % (SsoUnitTest.url_prefix, self.test_cookie_path)
    f = urllib2.urlopen(url)
    url = "%s/set_cookie_domain?value=%s" % (SsoUnitTest.url_prefix, self.cookie_domain)
    f = urllib2.urlopen(url)
    url = "%s/set_search_host?value=%s" % (SsoUnitTest.url_prefix, self.search_host)
    f = urllib2.urlopen(url)

  def setCookieTest(self, value):
    """Method for switching test_cookie_path on and off."""
    url = "%s/testcookiepath?value=%s" % (SsoUnitTest.url_prefix, value)
    f = urllib2.urlopen(url)
    val = f.read()
    if value:
      self.assert_("""val.find("True") > -1""")
    else:
      self.assert_("""val.find("True") == -1""")

  def setCookieDomain(self, value):
    url = "%s/set_cookie_domain?value=%s" % (SsoUnitTest.url_prefix, value)
    f = urllib2.urlopen(url)
    val = f.read()
    self.assertEqual(val, value)

  def setSearchHost(self, value):
    url = "%s/set_search_host?value=%s" % (SsoUnitTest.url_prefix, value)
    f = urllib2.urlopen(url)
    self.cookie_domain = f.read()
    self.assertEqual(self.cookie_domain, value)

  def getPublic(self):
    """Method for getting a public URL."""
    url = "%s/public" % (SsoUnitTest.url_prefix)
    f = urllib2.urlopen(url)
    self.assert_("f.code() == 200")
    self.assertEqual(f.geturl(), url)

  def testGetPublicCookiePathEnabled(self):
    """Get a public URL with test_cookie_path enabled."""
    self.setCookieTest(0)
    self.getPublic()

  def testGetPublicCookiePathDisabled(self):
    """Get a public URL with test_cookie_path disabled."""
    self.setCookieTest(1)
    self.getPublic()

  def getSecureWithAuth(self):
    """Method for getting a secure URL with the authentication cookies."""
    url = "%s/secure" % (SsoUnitTest.url_prefix)
    req = urllib2.Request(url)
    req.add_header("Cookie", "%s=%s;" % (sso.SSO_COOKIE, SsoUnitTest.login))
    f = urllib2.urlopen(req)
    self.assert_("f.code() == 200")
    self.assertEqual(f.geturl(), url)

  def testGetSecureWithAuthCookiePathEnabled(self):
    """Get a secure URL with a cookie and with test_cookie_path enabled."""
    self.setCookieTest(0)
    self.getSecureWithAuth()

  def testGetSecureWithAuthCookiePathDisabled(self):
    """Get a secure URL with a cookie and with test_cookie_path disabled."""
    self.setCookieTest(1)
    self.getSecureWithAuth()

  def getSecureWithoutAuth(self, script):
    """Method for getting a secure URL without the authentication cookies."""
    url = "%s/secure" % (SsoUnitTest.url_prefix)
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(url)
      raise SsoUnitTestException("secure page did not redirect to login form")
    except urllib2.HTTPError, e:
      self.assert_(e.code == 302 or e.code == 303)
      self.assertEqual(e.headers["location"],
                       "%s/%s?path=secure" % (SsoUnitTest.url_prefix, script))
      self.assert_(e.headers.has_key("set-cookie") == False)

  def testGetSecureWithoutAuthCookiePathDisabled(self):
    """Get a secure URL without a cookie and with test_cookie_path disabled.
    Should redirect to /secure without setting any cookies."""
    self.setCookieTest(0)
    self.getSecureWithoutAuth("form")

  def testGetSecureWithoutAuthCookiePathEnabled(self):
    """Get a secure URL without a cookie and with test_cookie_path enabled.
    Should redirect to /obrareq without setting any cookies."""
    self.setCookieTest(1)
    self.getSecureWithoutAuth("obrareq")

  def testGetObrareq(self):
    """Method for getting a secure URL without the authentication cookies.
    Should redirect to the login form and set FORM_COOKIE with a path of /login."""
    self.setCookieTest(0)
    url = "%s/obrareq?path=%s" % (SsoUnitTest.url_prefix, "secure")
    cj = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj), CustomRedirectHandler())
    try:
      f = opener.open(url)
      raise SsoUnitTestException("obrareq did not redirect to login form")
    except urllib2.HTTPError, e:
      self.assertEqual(e.code, 302)
      self.assertEqual(e.headers["location"],
                       "%s/form?path=%s" % (SsoUnitTest.url_prefix, "secure"))
      self.assertEqual(e.headers["set-cookie"],
                       "%s=%s; Path=/login;" % (sso.FORM_COOKIE, "1"))

  def getForm(self, test_cookie_path):
    """Method for getting the login form."""
    url = "%s/form?path=secure" % (SsoUnitTest.url_prefix)
    f = urllib2.urlopen(url)
    self.assert_("f.code() == 200")
    self.assertEqual(f.geturl(), url)
    if test_cookie_path:
      self.assertEqual(f.headers["set-cookie"],
                       "%s=%s;" % (sso.SSO_COOKIE, "1"))

  def testGetFormWithBadcookie(self):
    """Method for getting the login form with a bad cookie."""
    self.setCookieTest(1)
    url = "%s/form?path=secure" % (SsoUnitTest.url_prefix)
    req = urllib2.Request(url)
    req.add_header("Cookie", "%s=%s;" % (sso.FORM_COOKIE, "1"))
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(req)
      raise SsoUnitTestException("form did not redirect when getting bad cookie")
    except urllib2.HTTPError, e:
      self.assertEqual(e.code, 302)
      self.assertEqual(e.headers["location"],
                       "%s/login?msg=%s" % (SsoUnitTest.url_prefix, "bad_cookie"))

  def testGetLoginPageWithError(self):
    """Method for posting the login form with an error message.
    Expect to get back a 200 status code with an error in the HTML body
    and no SSO_COOKIE."""
    self.setCookieTest(1)
    url = "%s/login?msg=%s" % (SsoUnitTest.url_prefix, "bad_cookie")
    params = urllib.urlencode({ "login":SsoUnitTest.login,
                                "password":"test1",
                                "path":"secure" })
    req = urllib2.Request(url)
    req.add_header("Cookie", "%s=%s;" % (sso.FORM_COOKIE, "1"))
    req.add_data(params)
    opener = urllib2.build_opener(CustomRedirectHandler())
    f = opener.open(req)
    self.assert_("f.code() == 200")
    self.assertEqual(f.geturl(), url)
    self.assert_(f.headers.has_key("set-cookie") == False)

  def testGetFormCookiePathEnabled(self):
    self.setCookieTest(1)
    self.getForm(True)

  def testGetFormCookiePathDisabled(self):
    self.setCookieTest(0)
    self.getForm(False)

  def testPostFormCookiePathDisabled(self):
    self.setCookieTest(0)
    self.setCookieDomain(SsoUnitTest.cookie_domain)
    url = "%s/login" % (SsoUnitTest.url_prefix)
    params = urllib.urlencode({ "login":SsoUnitTest.login,
                                "password":"test1",
                                "path":"secure" })
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(url, params)
      raise SsoUnitTestException("login form did not redirect after submit")
    except urllib2.HTTPError, e:
      self.assertEqual(e.code, 302)
      self.assertEqual(e.headers["location"],
                       "%s/secure" % (SsoUnitTest.url_prefix))
      if self.cookie_domain:
        self.assertEqual(e.headers["set-cookie"], "%s=%s; Domain=%s;" %
                         (sso.SSO_COOKIE, SsoUnitTest.login, SsoUnitTest.cookie_domain))
      else:
        self.assertEqual(e.headers["set-cookie"], "%s=%s" %
                         (sso.SSO_COOKIE, SsoUnitTest.login))

  def testPostFormCookiePathEnabled(self):
    self.setCookieTest(1)
    self.setCookieDomain(SsoUnitTest.cookie_domain)
    url = "%s/login" % (SsoUnitTest.url_prefix)
    params = urllib.urlencode({ "login":SsoUnitTest.login,
                                "password":"test1",
                                "path":"secure" })
    req = urllib2.Request(url)
    req.add_header("Cookie", "%s=%s; %s=%s;" % (sso.SSO_COOKIE, "1", sso.FORM_COOKIE, "1"))
    req.add_data(params)
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(req)
      raise SsoUnitTestException("login form did not redirect after submit")
    except urllib2.HTTPError, e:
      self.assertEqual(e.code, 302)
      self.assertEqual(e.headers["location"],
                       "%s/secure" % (SsoUnitTest.url_prefix))
      if self.cookie_domain:
        self.assertEqual(e.headers["set-cookie"], "%s=%s; Domain=%s;" %
                         (sso.SSO_COOKIE, SsoUnitTest.login, SsoUnitTest.cookie_domain))
      else:
        self.assertEqual(e.headers["set-cookie"], "%s=%s" %
                         (sso.SSO_COOKIE, SsoUnitTest.login))

  def testExternalLoginWithAuth(self):
    """Method for getting the External Login URL with the authentication cookies."""
    self.setCookieTest(0)
    self.setCookieDomain(SsoUnitTest.cookie_domain)
    self.setSearchHost(SsoUnitTest.search_host)
    url = "%s/externalLogin?returnPath=/secure" % (SsoUnitTest.url_prefix)
    req = urllib2.Request(url)
    req.add_header("Cookie", "%s=%s;" % (sso.SSO_COOKIE, SsoUnitTest.login))
    # req.add_header("Referer", "%s/" % (SsoUnitTest.url_prefix))
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(req)
      raise SsoUnitTestException("External Login did not redirect when presented with valid cookie")
    except urllib2.HTTPError, e:
      self.assertEqual(e.code, 302)
      self.assertEqual(e.headers["location"], "http://%s/secure" % (SsoUnitTest.search_host))

  def testExternalLoginWithoutAuth(self):
    """Method for getting External Login URL without the authentication cookies."""
    self.setCookieTest(0)
    self.setCookieDomain(SsoUnitTest.cookie_domain)
    self.setSearchHost(SsoUnitTest.search_host)
    url = "%s/externalLogin?returnPath=/secure" % (SsoUnitTest.url_prefix)
    req = urllib2.Request(url)
    # req.add_header("Referer", "%s/" % (SsoUnitTest.url_prefix))
    opener = urllib2.build_opener(CustomRedirectHandler())
    try:
      f = opener.open(req)
      raise SsoUnitTestException("External Login did not redirect to login form")
    except urllib2.HTTPError, e:
      self.assert_(e.code, 302)
      self.assertEqual(e.headers["location"], "%s/form?path=http%%3A//%s/secure" %
                       (SsoUnitTest.url_prefix, urllib.quote(SsoUnitTest.search_host)))
      self.assert_(e.headers.has_key("set-cookie") == False)


def main(argv):
  pass

if __name__ == '__main__':
  unittest.main()
