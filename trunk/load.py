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
#     --suggest         Enable query suggestions
#     --cluster         Enable result clustering
#
# Sample output from a successful query:
#   Fri Aug 15 13:19:43 2008: Thread-3: success: 0.3 secs query: foo
#
# This code is not supported by Google
#


# TODO(jlowry):
#  * Would be good to send a fixed qps to a GSA using Python's
#    built-in scheduler module.
#  * Implement functionality of Mohit's query repeater script that takes search logs
#    from the GSA and replays the queries
# TODO(lchabardes):
#  *Implement a benchmark feature to automaticly establish max qps for an appliance
#  *Simplify query input: directly from search report, and/or generate query 
#   set from clustering
#  *Investigate feasibility of secure search load testing
#  *Make the repartition of suggest/clustering configurable
#  *Make the number of suggest random
#  *Enable Chart output using Google Chart Tools

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
import urlparse

class Results(object):
  """Class for holding results of load tests."""

  def __init__(self):
    #self.good_result_times = []
    self.error_search_result_count = 0
    self.error_cluster_result_count = 0
    self.error_suggest_result_count = 0
    self.good_search_result_times = []
    self.good_cluster_result_times = []
    self.good_suggest_result_times = []
    self.start = time.time()

  def Summary(self):
    """Summarizes the results.

    Returns:
      A string, summarizing the results
    """
    end = time.time()
    self.good_search_result_times.sort()
    self.good_cluster_result_times.sort()
    self.good_suggest_result_times.sort()
    total_search_200 = len(self.good_search_result_times)
    total_cluster_200 = len(self.good_cluster_result_times)
    total_suggest_200 = len(self.good_suggest_result_times)
    total_200 = total_search_200 + total_cluster_200 + total_suggest_200
    error_result_count =  self.error_search_result_count + self.error_cluster_result_count + self.error_suggest_result_count
    total_all = total_200 + error_result_count
    total_time = end - self.start
    av_qps = total_200 / total_time
    #Stats for total requests:
    #median = self.good_result_times[int(total_200 / 2.0) - 1]
    #std_dev = self.good_result_times[int(total_200 * 0.9) - 1]
    #max_time = self.good_result_times[-1]
    #Stats for pure search queries:
    median_search = self.good_search_result_times[int(total_search_200 / 2.0) - 1]
    std_dev_search = self.good_search_result_times[int(total_search_200 * 0.9) - 1]
    max_time_search = self.good_search_result_times[-1]
    print("Load test report:\n")
    #Stats for clustering request:
    if total_cluster_200 != 0:
      median_cluster = self.good_cluster_result_times[int(total_cluster_200 / 2.0) - 1]
      std_dev_cluster = self.good_cluster_result_times[int(total_cluster_200 * 0.9) - 1]
      max_time_cluster = self.good_cluster_result_times[-1]
      print("  \nResults Clustering Stats")
      print("  Number of responses:")
      print("    200:              %s" %total_cluster_200)
      print("    errors:           %s" %self.error_cluster_result_count)
      print("\n  Latency:")
      print("    median:           %.2f secs" %median_cluster)
      print("    maximum:          %.2f secs" %max_time_cluster)
      print("    90th percentile:  %.2f secs\n" %std_dev_cluster)
    #Stats for query suggestion:
    if total_suggest_200 != 0:
      median_suggest = self.good_suggest_result_times[int(total_suggest_200 / 2.0) - 1]
      std_dev_suggest = self.good_suggest_result_times[int(total_suggest_200 * 0.9) - 1]
      max_time_suggest = self.good_suggest_result_times[-1]
      print("\nQuery Suggestions Stats")
      print("  Number of responses:")
      print("    200:              %s" %total_suggest_200)
      print("    errors:           %s" %self.error_suggest_result_count)
      print("\n  Latency:")
      print("    median:           %.2f secs" %median_suggest)
      print("    maximum:          %.2f secs" %max_time_suggest)
      print("    90th percentile:  %.2f secs\n" %std_dev_suggest)
    print("\nSearch Query Stats")
    print("  Number of responses:")
    print("   200:              %s" %total_search_200)
    print("    errors:           %s" %self.error_search_result_count)
    print("\n  Latency:")
    print("    median:           %.2f secs" %median_search)
    print("    maximum:          %.2f secs" %max_time_search)
    print("    90th percentile:  %.2f secs\n" %std_dev_search)
    print("Overall results")
    print("Number of responses:")
    print("  200:              %s" %total_200)
    print("  errors:           %s" %error_result_count)
    print(" total:            %s" %total_all)
    print("\nThroughput:")
    print("  average:      %.2f qps" %av_qps)
    

class Client(threading.Thread):

  def __init__(self, host, port, queries, res, enable_cluster, enable_suggest):
    threading.Thread.__init__(self)
    self.host = host
    self.port = port
    self.res = res
    self.queries = queries
    self.enable_cluster = enable_cluster
    self.enable_suggest = enable_suggest

  def run(self):
    while True:
      try:
        q = self.queries.get(block=False)
      except Queue.Empty:
        break
      else:
        query_parsed = urlparse.urlparse(q.strip())
        query_parsed_clean = query_parsed[4]
        #Cleaning up query input to prevent invalid requests.
        if query_parsed_clean[0] == "&":
          query_parsed_clean = query_parsed_clean[1:-1]
        query_terms = []
        for qterm in query_parsed_clean.split('&'):
          if qterm.find("=") != -1:
            query_terms.append(qterm)
        try:
          parameters = dict([param.split('=') for param in query_terms])
        except Exception, e:
          print e
          print query_parsed
          print parameters
          raise
        if 'q' in parameters:
          self.FetchContent(self.host, self.port, q.strip(), parameters)

  def FetchContent(self, host, port, q, parameters):
    start_time = time.ctime(time.time())
    test_requests = []
    #For each queries we get from the queue, making one suggest query and one clustering req:
    if q.find("/search?") == 0 and q.find("coutput=json") != 0:
      test_requests.append(q)
    else:
      test_requests.append("/search?q=%s&output=xml_no_dtd&client=default_frontend&roxystylesheet=default_frontend&site=default_collection" % (q))
    if enable_cluster == True: 
      token = parameters.get('q')
      frontend = parameters.get('client', "default_frontend")
      collection = parameters.get('site', "default_collection")
      test_requests.append("/cluster?coutput=json&q=%s&site=%s&client=%s" %(token, collection, frontend))
    if enable_suggest == True:
      token = parameters.get('q')
      frontend = parameters.get('client', "default_frontend")
      collection = parameters.get('site', "default_collection")
      test_requests.append("/suggest?q=%s&max_matches=10&use_similar&access=p&format=rich" %(token[0:2]))
    for req in test_requests:
      try:
        timer_start = time.time()
        conn = httplib.HTTPConnection(host, port)
        if req.find("/suggest?") == 0 or req.find("/cluster?") == 0:
          conn.request("POST", req)
        else:
          conn.request("GET", req)
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
                      "%s") % (start_time, self.getName(), exec_time, req))
        if req.find("/suggest?") != -1:
          self.res.good_suggest_result_times.append(exec_time)
        if req.find("/cluster?") != -1:
          self.res.good_cluster_result_times.append(exec_time)
        else:
          self.res.good_search_result_times.append(exec_time)
      except httplib.HTTPException, value:
        logging.info(("%s: %s: error: %s query: "
                      "%s") % (start_time, self.getName(), value, req))
        if req.find("/suggest?") != -1:
          self.res.error_suggest_result_count += 1
        if req.find("/cluster?") != -1:
          self.res.error_cluster_result_count += 1
        else:
          self.res.error_search_result_count += 1
      except socket.error, msg:
        logging.info("%s: %s: %s query: %s" % (start_time, self.getName(), msg, req))
        if req.find("/suggest?") != -1:
          self.res.error_suggest_result_count += 1
        if req.find("/cluster?") != -1:
          self.res.error_cluster_result_count += 1
        else:
          self.res.error_search_result_count += 1
      except:
        the_type, value, tb = sys.exc_info()
        logging.info("%s: %s: exception: %s %s query: %s" % (start_time, self.getName(),
                                                             the_type, value, req))
        if req.find("/suggest?") != -1:
          self.res.error_suggest_result_count += 1
        if req.find("/cluster?") != -1:
          self.res.error_cluster_result_count += 1
        else:
          self.res.error_search_result_count += 1


def usage():
  return ("load.py --queries=<queries-filename> --host=<gsa-hostname> "
          "[--threads=<num-threads>] [--port=<gsa-port>] [--suggest] [--cluster]")


if __name__ == "__main__":

  num_threads = 3
  port = 80
  enable_suggest = False
  enable_cluster = False
  host = ""
  queries_filename = ""
  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["host=", "port=", "threads=", "queries=", "cluster", "suggest"])
  except getopt.GetoptError:
    print usage()
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
    if opt == "--cluster":
      enable_cluster = True
    if opt == "--suggest":
      enable_suggest = True

  if not host or not queries_filename:
    print usage()
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
    c = Client(host, port, queries, res, enable_cluster, enable_suggest)
    thread_list.append(c)
    c.start()
    num_threads -= 1

  # Wait for all the threads to finish before printing the summary
  for t in thread_list:
    t.join()
  logging.info(res.Summary())