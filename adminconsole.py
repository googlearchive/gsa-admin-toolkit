#!/usr/bin/python2.4
#
# http://gsa-admin-toolkit.googlecode.com/svn/trunk/adminconsole.py
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
#   getting crawl status, shutting down the appliance, importing
#   and exporting configs.
#
# This script is not supported by Google.
# Has been tested with python2.4 and appliance version 5.0.0.G.14
#
# Based on scripts at:
#  https://support.google.com/enterprise/faqs?&question=192
#  http://support.google.com/enterprise/threadview?message=8201
#
# encode_multipart_form_data function is taken from:
#  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/146306
#  License at http://community.activestate.com/faq/what-is-the-license-for-t
#

import sys
import string
import urllib2
import urllib
import getopt
import re
import os

def usage():
  return ("Usage: %s [OPTION]... [ARGUMENTS]...\n\n"
          "  --username: admin user username\n"
          "  --password: admin user password\n"
          "  --action: db_sync|pause_crawl|resume_crawl|crawl_status"
          "|shutdown|import_config|export_config\n"
          "  --hostname: hostname of the Google Search Appliance\n"
          "  --help: output this message\n\n"
          "If action is db_sync, you must specify the db source on "
          "the command line following the options. "
          "If the action is export_config, you must specify the export "
          "password on the command line following the options. If the "
          "action is import_config, you must specify the import password "
          "and import filename on the command line.\n\n"
          "Examples:\n"
          "%s --username=admin --password=1234 --hostname=search.mycompany.com "
          "--action=pause_crawl\n"
          "%s --username=admin --password=1234 --hostname=search.mycompany.com "
          "--action=export_config my_export_password\n"
          "%s --username=admin --password=1234 --hostname=search.mycompany.com "
          "--action=import_config import_password import_filename\n"
          "%s --username=admin --password=1234 --hostname=search.mycompany.com "
          "--action=db_sync mydbsource") % (sys.argv[0], sys.argv[0], sys.argv[0],
                                            sys.argv[0], sys.argv[0])


def encode_multipart_formdata(fields, files):
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

def import_config(base_url, cookie, import_password, import_filename):
  fields = [("actionType", "importExport"), ("passwordIn", import_password),
            ("import", "Import Configuration")]
  f = open(import_filename)
  filename_parts = os.path.split(import_filename)
  files = [("importFilename", filename_parts[1], f.read())]
  content_type, body = encode_multipart_formdata(fields, files)
  headers = {'User-Agent': 'python-urllib2',
             'Content-Type': content_type}
  request = urllib2.Request(base_url, body, headers)
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)
  content = res.read()
  if content.find("Invalid file") > -1:
    print "Invalid configuration file"
    sys.exit(2)
  elif content.find("Wrong passphrase or the file is corrupt") > -1:
    print "Wrong passphrase or the file is corrupt"
    sys.exit(2)
  elif content.find("Passphrase should be at least 8 characters long") > -1:
    print "Passphrase should be at least 8 characters long"
    sys.exit(2)
  elif content.find("File does not exist") > -1:
    print "Configuration file does not exist"
    sys.exit(2)
  elif content.find("Configuration imported successfully") == -1:
    print "Import failed"
    sys.exit(2)
  # else: print "Import successful"

def export_config(base_url, cookie, export_password):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType': 'importExport',
                                              'export': 'Export Configuration',
                                              'password1': export_password,
                                              'password2': export_password}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)
  content = res.read()
  if content.find("Passphrase should be at least 8 characters long") > -1:
    print "Passphrase should be at least 8 characters long"
    sys.exit(2)
  return content

def crawl_status(base_url, cookie):
  request = urllib2.Request(base_url,
                            urllib.urlencode({'actionType' : 'crawlStatus'}))
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request)
  content = res.read()
  regex = re.compile("""The crawling system is currently  <font color="red">(.*)</font>""")
  match = regex.search(content)
  print "Status is: %s" % (string.strip(match.group(1)))

def shutdown(base_url, cookie):
  request = urllib2.Request(base_url)
  request.add_header('Cookie', cookie)
  res = urllib2.urlopen(request,"powerOffYes=+Yes+&actionType=shutdown")

def main(argv):
  try:
    opts, args = getopt.getopt(argv[1:], None,["help", "action=", "hostname=",
                                               "username=", "password="])
  except getopt.GetoptError:
    # print help information and exit:
    print "Error processing options"
    print usage()
    sys.exit(1)

  url = None
  action = None
  hostname = None
  username = None
  password = None

  for opt, arg in opts:
    if opt == "--help":
      print "Printing usage information"
      print usage()
      sys.exit()
    if opt == "--action":
      action = arg
      if action == "db_sync":
        if len(args) == 1:
          dbsource = args[0]
        else:
          print "Error processing dbsource arg"
          print usage()
          sys.exit(1)
      if action == "export_config":
        if len(args) == 1:
          export_password = args[0]
        else:
          print "Error processing export_password arg"
          print usage()
          sys.exit(1)
      if action == "import_config":
        if len(args) == 2:
          import_password = args[0]
          import_filename = args[1]
        else:
          print "Error processing import_password or import_filename args"
          print usage()
          sys.exit(1)
    if opt == "--hostname":
      hostname = arg
    if opt == "--username":
      username = arg
    if opt == "--password":
      password = arg

  if action not in ["db_sync", "pause_crawl", "resume_crawl", "crawl_status",
                    "shutdown", "export_config", "import_config"]:
    print "Action not in list"
    print usage()
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
    elif action == "shutdown":
      shutdown(base_url, cookie)
    elif action == "import_config":
      import_config(base_url, cookie, import_password, import_filename)
    elif action == "export_config":
      print export_config(base_url, cookie, export_password)
    logout(base_url, cookie)
  else:
    print usage()
    sys.exit(1)

if __name__ == '__main__':
  main(sys.argv)
