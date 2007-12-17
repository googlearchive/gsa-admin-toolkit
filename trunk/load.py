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
#   load.py
#
# Description:
#   Simple script for load testing the appliance.
#
# Usage:
#   First extract some sample queries from the search logs on your appliance
#     cat <exported-logs> | awk '{ print $7 }' | sed -e 's/^\(.*\)&ip=.*$/\1/' > queries.txt
#   You can specify queries as a full URI (e.g. /search?q=foo&...) or as a URL-encoded
#   query term (script will use default_collection and default_frontend).
#   The run the load testing script with the following parameters:
#     load.py --host <appliance-hostname> --queries <queries-file>
#   Additional options are:
#     --port            Port on the webserver (default is port 80)
#     --threads         Number of concurrent queries (default is 3)
#
# Sample output from a successful query:
#   Tue Aug 14 08:48:26 2007: success: 0.1
#

import httplib
import mimetools
import threading
import sys
import thread
import string
import time
import socket
import traceback
import getopt

class Client(threading.Thread):

  queries = []

  def __init__(self, host, port, queries_filename, timeit_loaded):
    self.host = host
    self.port = port
    queries_file = open(queries_filename)
    Client.queries = queries_file.readlines()
    queries_file.close()
    self.timeit_loaded = timeit_loaded
    threading.Thread.__init__(self)

  def run(self):
    while len(Client.queries) > 0:
      self.lock.acquire()
      if len(Client.queries) == 0: return
      q = Client.queries[0]
      Client.queries = Client.queries [1:]
      self.lock.release()
      q = string.strip(q)
      self.getContent(self.host, self.port, q)

  def setLock(self, l):
    self.lock = l

  def getContent(self, host, port, q):
    start_time = time.ctime(time.time())
    if q.find("/search?") == 0:
      query = q
    else:
      query = ("""/search?q=%s&output=xml_no_dtd&client=default_frontend&"""
               """proxystylesheet=default_frontend&site=default_collection""" % (q))
    try:
      s = """
conn = httplib.HTTPConnection("%s", %s)
conn.request("GET", "%s")
res = conn.getresponse()
headers = res.msg
content = res.read()
conn.close()
if res.status != 200:
  content_lines = content.splitlines()
  exc_value = str(res.status)
  exc_value += " "
  exc_value += content_lines[-1]
  raise httplib.HTTPException, exc_value
""" % (host, port, query)
      if self.timeit_loaded:
        t = timeit.Timer(setup="import httplib", stmt=s)
        exec_time = t.timeit(1)
      else:
        timer_start = time.time()
        exec s
        timer_end = time.time()
        exec_time = timer_end - timer_start
      print "%s: success: %.1f" % (start_time, exec_time)
    except httplib.HTTPException, value:
      print "%s: error: %s" % (start_time, value)
    except socket.error, msg:
      print "%s: %s" % (start_time, msg)
    except:
      type, value, tb = sys.exc_info()
      # l = traceback.format_tb(tb, None)
      # print "%-20s%s: %s" % (string.join(l[:], ""), type, value)
      print "%s: exception: %s %s" % (start_time, type, value)


if __name__=='__main__':
  # timeit requires python 2.3
  try:
    import timeit
    timeit_loaded = 1
  except ImportError:
    timeit_loaded = 0

  num_threads = 3
  port = 80
  host = ""
  queries_filename = ""
  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["host=", "port=", "threads=", "queries="])
  except getopt.GetoptError:
    print "Invalid arguments"
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--host":
      host = arg
    if opt == "--queries":
      queries_filename = arg
    if opt == "--threads":
      num_threads = int(arg)
    if opt == "--port":
      port == arg

  if not host or not queries_filename:
    print "Must provide a hostname and queries filename"
    sys.exit(1)

  lock = thread.allocate_lock()
  while num_threads > 0:
    c = Client(host, port, queries_filename, timeit_loaded)
    c.setLock(lock)
    c.start()
    num_threads = num_threads - 1
