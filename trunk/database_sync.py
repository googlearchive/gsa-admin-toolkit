#!/usr/bin/python2.4
#
# Copyright 2009 Google Inc. All Rights Reserved.
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
# limitations under the License

"""Script for automating the sync of database using the GSA Admin console.

 Tested with GSA 6.0 and GSA 6.2.
"""

import optparse
import sys
import urllib
import urllib2


def main(unused_argv):
  parser = optparse.OptionParser()
  parser.add_option("-x", "--hostname", action="store",
                    help="Hostname or IP of the GSA")
  parser.add_option("-u", "--username", action="store",
                    help="Username to be used in the admin console")
  parser.add_option("-p", "--password", action="store",
                    help="Password to be used to log into the admin console")
  parser.add_option("-s", "--source", action="store",
                    help="Database's name to sync")
  (options, unused_args) = parser.parse_args()

  for option in eval(str(options)).itervalues():
    if option is None:
      print "Run %s -h." % sys.argv[0]
      sys.exit(1)

  base_url = "http://%s:8000/EnterpriseController?" % options.hostname

  print "Starting sync for", options.source, "using username", options.username
  print "Logging In ..."
  res = urllib2.urlopen(base_url)
  cookie = res.info()["Set-Cookie"].split(";")[0]

  param = urllib.urlencode({"actionType": "authenticateUser",
                            "userName": options.username,
                            "password": options.password})
  request = urllib2.Request(base_url)
  request.add_header("Cookie", cookie)
  res = urllib2.urlopen(request, param)

  print "Syncing ..."
  param = urllib.urlencode({"actionType": "syncDatabase",
                            "entryName": options.source})
  request = urllib2.Request(base_url + param)
  request.add_header("Cookie", cookie)
  res = urllib2.urlopen(request)

  print "Finished !"

if __name__ == "__main__":
  main(sys.argv)
