#!/usr/bin/python
#
# Copyright (C) 2012 Google Inc.
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

# This simple python script follows GSA's redirects to retrieve
# secure search results. The script expects ULF-based authentication
# such as LDAP.
#
# Useful for prototyping retrieval of secure search results on behalf of
# the user.
#
# Could be further extended:
#  - maintain session cookies to avoid doing
#  authentication on every request
#  - support other mechanisms such as Kerberos
#
# Before you use the script set the constants.
#
# Tested on 6.14, it works!

import httplib
import re
import urllib


GSA_HOST = 'search.example.com'
SEARCH_URI = '/search?q=a&site=default_collection&client=default_frontend&output=xml_no_dtd&access=a'
FORM_URI = '/security-manager/samlauthn'
USERNAME = ''
PASSWORD = ''

_COOKIE_PATTERN = re.compile(r'^(.*);.*$') # extracts cookie from headers


def _GetCookie(response):
  raw = response.getheader('Set-Cookie')
  return _COOKIE_PATTERN.match(raw).group(1)


def _GetLocation(response):
  return response.getheader('Location')


def main():
  conn = httplib.HTTPSConnection(GSA_HOST)

  # perform first fetch, expect a cookie and redirect to ULF login form
  conn.request('GET', SEARCH_URI)
  resp = conn.getresponse()
  location = _GetLocation(resp) # location of next redirect
  cookie = _GetCookie(resp) # GSA_SESSION_ID must be kept for all future requests
  headers = { 'Cookie': cookie }

  # perform second fetch, get the ULF form
  conn.request('GET', location, None, headers)
  resp = conn.getresponse()

  # submit credentials to the ULF form
  params = urllib.urlencode({'uDefault': USERNAME, 'pwDefault': PASSWORD})
  conn.request('POST', FORM_URI, params, headers)
  resp = conn.getresponse()
  location = _GetLocation(resp)

  # follow another redirect to complete authentication
  conn.request('GET', location, None, headers)
  resp = conn.getresponse()
  location = _GetLocation(resp)

  # finally, get the results
  conn.request('GET', location, None, headers)
  resp = conn.getresponse()

  print resp.read()


if __name__ == "__main__":
  main()
