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
#   The run the load testing script with the following parameters:
#     load.py <appliance-hostname> <appliance-port> <queries-file> <number-of-threads>
#   For example:
#     load.py search.mycompany.com 80 queries.txt 5
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
""" % (host, port, q)
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

  host = sys.argv[1]
  port = sys.argv[2]
  queries_filename = sys.argv[3]
  num_threads = int(sys.argv[4])

  lock = thread.allocate_lock()
  while num_threads > 0:
    c = Client(host, port, queries_filename, timeit_loaded)
    c.setLock(lock)
    c.start()
    num_threads = num_threads - 1
