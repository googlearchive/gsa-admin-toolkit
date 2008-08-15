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
#
# Name
#   load.py
#
# Description:
#   Simple script for load testing the appliance.
#
# Usage:
#   First extract some sample queries from the search logs on your appliance
#     cat <logs> | awk '{ print $7 }' | sed -e 's/^\(.*\)&ip=.*$/\1/' > q.txt
#   You can specify queries as a full URI (e.g. /search?q=foo&...) or
#   as a URL-encoded query term (script will use default_collection
#   and default_frontend).
#   Then run the load testing script with the following parameters:
#     load.py --host <appliance-hostname> --queries <queries-file>
#   Additional options are:
#     --port            Port on the webserver (default is port 80)
#     --threads         Number of concurrent queries (default is 3)
#
# Sample output from a successful query:
#   Fri Aug 15 13:19:43 2008: Thread-3: success: 0.3 secs query: foo
#


# TODO(jlowry):
#  * Would be good to send a fixed qps to a GSA.

import getopt
import httplib
import logging
import Queue
import socket
import string
import sys
import thread
import threading
import time


class Results(object):
  """Class for holding results of load tests."""

  def __init__(self):
    self.good_result_times = []
    self.error_result_count = 0
    self.start = time.time()

  def Summary(self):
    """Summarizes the results.

    Returns:
      A string, summarizing the results
    """
    end = time.time()
    self.good_result_times.sort()
    total_200 = len(self.good_result_times)
    total_all = total_200 + self.error_result_count
    total_time = end - self.start
    av_qps = total_200 / total_time
    median = self.good_result_times[int(total_200 / 2.0) - 1]
    std_dev = self.good_result_times[int(total_200 * 0.9) - 1]
    max_time = self.good_result_times[-1]
    return (("Number of responses:\n"
             "  200:              %s\n"
             "  errors:           %s\n"
             "  total:            %s\n"
             "\nThroughput:\n"
             "  average:      %.2f qps\n"
             "\nLatency:\n"
             "  median:           %.2f secs\n"
             "  maximum:          %.2f secs\n"
             "  90th percentile:  %.2f secs"
             "\n") % (total_200, self.error_result_count, total_all, av_qps,
                      median, max_time, std_dev))


class Client(threading.Thread):

  def __init__(self, host, port, queries, res):
    threading.Thread.__init__(self)
    self.host = host
    self.port = port
    self.res = res
    self.queries = queries

  def run(self):
    while not self.queries.empty():
      try:
        q = self.queries.get()
      except Queue.Empty:
        return
      else:
        self.FetchContent(self.host, self.port, q.strip())

  def FetchContent(self, host, port, q):
    start_time = time.ctime(time.time())
    if q.find("/search?") == 0:
      query = q
    else:
      query = ("/search?q=%s&output=xml_no_dtd&client=default_frontend&"
               "proxystylesheet=default_frontend&site=default_collection" % (q))
    try:
      timer_start = time.time()
      conn = httplib.HTTPConnection(host, port)
      conn.request("GET", query)
      res = conn.getresponse()
      content = res.read()
      conn.close()
      if res.status != 200:
        content_lines = content.splitlines()
        exc_value = str(res.status)
        exc_value += " "
        exc_value += content_lines[-1]
        raise httplib.HTTPException(exc_value)
      timer_end = time.time()
      exec_time = timer_end - timer_start
      logging.info(("%s: %s: success: %.1f secs query: "
                    "%s") % (start_time, self.getName(), exec_time, q))
      self.res.good_result_times.append(exec_time)
    except httplib.HTTPException, value:
      logging.info(("%s: %s: error: %s query: "
                    "%s") % (start_time, self.getName(), value, q))
      self.res.error_result_count += 1
    except socket.error, msg:
      logging.info("%s: %s: %s query: %s" % (start_time, self.getName(), msg, q))
      self.res.error_result_count += 1
    except:
      the_type, value, tb = sys.exc_info()
      logging.info("%s: %s: exception: %s %s query: %s" % (start_time, self.getName(),
                                                           the_type, value, q))
      self.res.error_result_count += 1


if __name__ == "__main__":

  num_threads = 3
  port = 80
  host = ""
  queries_filename = ""
  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["host=", "port=", "threads=", "queries="])
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
      port = arg

  if not host or not queries_filename:
    print "Must provide a hostname and queries filename"
    sys.exit(1)

  queries = Queue.Queue()
  queries_file = open(queries_filename)
  for q in queries_file.readlines():
    queries.put(q)
  queries_file.close()

  logging.basicConfig(level=logging.INFO,
                      format="%(message)s")

  res = Results()
  thread_list = []
  while num_threads > 0:
    c = Client(host, port, queries, res)
    thread_list.append(c)
    c.start()
    num_threads -= 1

  # Wait for all the threads to finish before printing the summary
  for t in thread_list:
    t.join()
  logging.info(res.Summary())
