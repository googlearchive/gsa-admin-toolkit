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
# Name
#   adminconsole.py
#
# Description:
#   Script for automating Admin Console tasks.
#   Currently handles syncing the DB, pausing and resuming crawl,
#   getting crawl status.
#
# This script is not supported by Google.
# Has been tested with python2.4 and appliance version 4.6.4.G.70
#
# Based on scripts at:
#  https://support.google.com/enterprise/faqs?&question=192
#  http://support.google.com/enterprise/threadview?message=8201


import sys
import string
import urllib2
import urllib
import getopt
import re

def usage():
  print """Usage: %s [OPTION]... [ARGUMENTS]...

  --username: admin user username
  --password: admin user password
  --action: db_sync|pause_crawl|resume_crawl|crawl_status
  --hostname: hostname of the Google Search Appliance
  --help: output this message

If action is db_sync, you must specify the db source on the command line
following the options

Examples:
%s --username=admin --password=1234 --hostname=search.mycompany.com --action=pause_crawl
%s --username=admin --password=1234 --hostname=search.mycompany.com --action=db_sync mydbsource""" \
% (sys.argv[0], sys.argv[0], sys.argv[0])

def get_cookie(base_url):
  request = urllib2.Request(base_url)
  res = urllib2.urlopen(request)
  cookie = res.info()['Set-Cookie'].split(';')[0]
  return cookie

def login(base_url, cookie, username, password):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'authenticateUser',
                                              'userName' : username,'password' : password}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)

def check_login_successful(base_url, cookie):
  # Cannot use the HTTP response code to determine whether login succeeded
  # because the admin console doesn't redirect on a failed login.
  # Therefore, look at the page content to determine success or failure.
  request = urllib2.Request("%s?actionType=systemStatus" % (base_url))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)
  content = res.read()
  if content.find("Welcome to the Google Search Appliance!") > 0:
    print "Login failed"
    sys.exit(2)

def logout(base_url, cookie):
  request = urllib2.Request(base_url,urllib.urlencode({'actionType' : 'logout'}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)

def db_sync(base_url, cookie, dbsource):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'syncDatabase','entryName' : dbsource}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)

def pause_crawl(base_url, cookie):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'crawlStatus','pauseCrawl' : 'Pause Crawl'}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)


def resume_crawl(base_url, cookie):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'crawlStatus','resumeCrawl' : 'Resume Crawl'}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)

def crawl_status(base_url, cookie):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'crawlStatus'}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)
  content = res.read()
  regex = re.compile("""The crawling system is currently  <font color="red">(.*)</font>""")
  match = regex.search(content)
  print "Status is: %s" % (string.strip(match.group(1)))


def main(argv):
  try:
    opts, args = getopt.getopt(argv[1:], None,["help", "action=", "hostname=","username=", "password="])
  except getopt.GetoptError:
    # print help information and exit:
    usage()
    sys.exit(1)

  url = None
  action = None
  hostname = None
  username = None
  password = None

  for opt, arg in opts:
    if opt == "--help":
      usage()
      sys.exit()
    if opt == "--action":
      action = arg
      if action == "db_sync":
        if len(args) == 1:
          dbsource = args[0]
        else:
          usage()
          sys.exit(1)
    if opt == "--hostname":
      hostname = arg
    if opt == "--username":
      username = arg
    if opt == "--password":
      password = arg

  if action not in ["db_sync", "pause_crawl", "resume_crawl", "crawl_status"]:
    usage()
    sys.exit(1)

  if (action and hostname and username and password):
    base_url = 'http://%s:8000/EnterpriseController' % hostname
    cookie = get_cookie(base_url)
    login(base_url, cookie, username, password)
    check_login_successful(base_url, cookie)
    if action == "db_sync":
      db_sync(base_url, cookie, dbsource)
    elif action == "pause_crawl":
      pause_crawl(base_url, cookie)
    elif action == "resume_crawl":
      resume_crawl(base_url, cookie)
    elif action == "crawl_status":
      crawl_status(base_url, cookie)
    logout(base_url, cookie)
  else:
    usage()
    sys.exit(1)

if __name__ == '__main__':
  main(sys.argv)
