#!/usr/bin/python2.6
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
#   There are two ways to specify the queries to use:
#   1. Extract some sample queries from the search logs on your appliance
#        cat <logs> | awk '{ print $7 }' | sed -e 's/^\(.*\)&ip=.*$/\1/' > q.txt
#      You can specify queries as a full URI (e.g. /search?q=foo&...) or
#      as a URL-encoded query term (script will use default_collection
#      and default_frontend).
#      Then run the load testing script with the following parameters:
#        load.py --host <appliance-hostname> --queries <queries-file>
#   2. Specify the name of a GSA search log, as well as the username and
#      password for the admin interface. Then, run the load testing script
#      as follows:
#        load.py --host <appliance-hostname> --query_log=<query-log-name> \
#                --admin_username=<username> --admin_password=<password>
#   Additional options are:
#     --port          Port on the webserver (default is port 80)
#     --threads       Number of concurrent queries (default is 3)
#     --suggest       Enable query suggestions
#     --rand_suggest  If --suggest is given, this flag will make a random
#                     number of suggestion queries between 1 and the length
#                     of the query string. If this flag is not given, then
#                     only one suggestion query will be made.
#     --cluster       Enable result clustering
#     --format        Determines the report format. Can be 'text' or 'html'.
#     --output        The report output location. If unspecified, the report
#                     will be printed to stdout.
#     --charts        Generate Google Charts URLs in reports for visualizing
#                     reponse times
#     --auth_cfg      If any of the queries are secure, then this is required.
#                     This specifies the authentication configuration file to
#                     read, in YAML format.
#                     (A query is assumed to be secure if the script is
#                     redirected to a page starting with something other than
#                     /search, /cluster, or /suggest.
#     --mode          Can be "once" or "benchmark".
#                     once: The default (assumed if --mode is unspecified).
#                       Runs the load testing once with the specified thread
#                       count.
#                     benchmark: Loops the test, starting with 10 threads and
#                       increasing by 10 every iteration (this number can be
#                       customized with --thread_step). Exits when the
#                       failure rate exceeds the value specified by
#                       --max_err_rate, or when the number of iterations
#                       hits the maximum specified by --max_trials.
#     --thread_step   For --mode=benchmark. Specifies the number of threads
#                     to increase by for each iteration. Default is 10.
#     --max_err_rate  Only for --mode=benchmark. This is the error
#                     rate at which the testing stops. Should be specified
#                     as a floating point value between 0.0 and 1.0. The default
#                     value is 0.5.
#     --max_trials    Also for the benchmark mode. Specifies the maximum
#                     number of test iterations to run. The default value
#                     is 15 trials.
#
#
# Sample output from a successful query:
#   Fri Aug 15 13:19:43 2008: Thread-3: success: 0.3 secs query: foo
#
# Example auth_cfg file:
#   universal-login:
#     Default:
#       username: user1
#       password: password1
#     secondary:
#       username: user2
#       password: password2
#   forms:
#     http://sso.mydomain.com/login.jsp:
#       post: http://sso.mydomain.com/verifylogin.jsp
#       fields:
#         username: user3
#         password: password3
# In this example, whenever the load script encounters a universal login
# form, it will fill in and post the form with user1/password1 for the
# Default credential group and user2/password2 for the secondary
# credential group. If the script is ever redirected to an external form
# for authentication called 'http://sso.mydomain.com/login.jsp', the script
# will fill in the fields username/password with the values user3/password3
# and will post to http://sso.mydomain.com/verifylogin.jsp.
# For forms authentication, each request thread will keep its authentication
# cookies (as long as they don't expire) throughout its lifetime.
#
#
# This code is not supported by Google
#


# TODO(jlowry):
#  * Would be good to send a fixed qps to a GSA using Python's
#    built-in scheduler module.
# TODO(lchabardes):
#  * Simplify query input: generate query set from clustering
#  * Make the repartition of suggest/clustering configurable
# TODO(jonathanho):
#  * Separate secure searches from regular ones in the report output

import cookielib
import getopt
import logging
import math
import Queue
import random
import re
import sys
import threading
import time
import urllib
import urllib2
import urlparse
import xml.dom.minidom
import yaml


class TimeSet(object):
  """Holds a set of times for requests, and generates pretty visualizations."""

  def __init__(self, name):
    self.good_times = []
    self.error_count = 0
    self.name = name

  def Extend(self, ts):
    self.good_times.extend(ts.good_times)
    self.error_count += ts.error_count

  def AddGood(self, t):
    self.good_times.append(t)

  def AddError(self):
    self.error_count += 1

  def NumGood(self):
    return len(self.good_times)

  def NumError(self):
    return self.error_count

  def NumTotal(self):
    return len(self.good_times) + self.error_count

  def ErrorRate(self):
    return float(self.NumError()) / float(self.NumTotal())

  def MinGood(self):
    return min(self.good_times)

  def MeanGood(self):
    return sum(self.good_times) / float(self.NumGood())

  def MedianGood(self):
    l = self.NumGood()
    if l % 2 == 1:
      return self.good_times[(l - 1)/2]
    return (self.good_times[l/2 - 1] + self.good_times[l/2]) / 2.0

  def MaxGood(self):
    return max(self.good_times)

  def StdDevGood(self):
    mean = self.MeanGood()
    s = 0.0
    for t in self.good_times:
      s += (t - mean)**2
    return math.sqrt(s / float(self.NumGood()))

  def ChartURLGood(self):
    """Generates a histogram with Google Charts for the good response data.

    Returns:
      The URL (a string).
    """
    self.good_times.sort()
    total_min, total_max = self.good_times[0], self.good_times[-1]
    total_range = total_max - total_min
    # calculate the height of each bin
    nbins = int(math.ceil(math.sqrt(len(self.good_times))))
    nbins = min(nbins, 13)  # the Charts API seems to have a bar cap
    width = total_range / float(nbins)
    # fill in the bins
    bins = [0] * nbins
    curr_bin = 0
    bin_min, bin_max = total_min, total_min + width
    for t in self.good_times:
      # move along till we get to the correct bin
      while (t < bin_min or t >= bin_max) and curr_bin < nbins:
        curr_bin += 1
        bin_min, bin_max = bin_max, bin_max + width
      # if we get the last item by itself at the end, put it in the last bucket
      if curr_bin >= nbins:
        bins[-1] += 1
        break
      bins[curr_bin] += 1
    # generate the google charts url and return it
    chart_data = ",".join(str(b) for b in bins)
    return ("http://chart.apis.google.com/chart?"
            "cht=bvs&"
            "chs=450x400&"
            "chxt=x,y,x,y&"
            "chxr=0,%.2f,%.2f,%.2f|1,%d,%d&"
            "chxl=2:|Time+(s)|3:|Queries&"
            "chxp=2,50|3,50&"
            "chtt=Distribution+of+Query+Times+for+%s&"
            "chd=t:%s&"
            "chds=0,%d") % (
                total_min, total_max, width,
                min(bins), max(bins),
                self.name,
                chart_data,
                max(bins))

  def Report(self, chart, format):
    """Generates a report of the data.

    Args:
      chart: A boolean that determines if this will output a Google Charts URL.
      format; A string, 'text' or 'html'.

    Returns:
      The report string.
    """
    chartstr = ""
    if chart:
      url = self.ChartURLGood()
      if format == 'html':
        url = '<img src="%s" />' % url
      chartstr = "  Histogram of 200s:\n    %s\n" % url
    rep = "Stats for %s:\n" % self.name
    if format == 'html':
      rep = '<h2>%s</h2>' % rep
    rep += ("  Number of responses:\n"
            "    200:              %s\n"
            "    errors:           %s\n"
            "  Latency:\n"
            "    median:           %.2f secs\n"
            "    maximum:          %.2f secs\n"
            "    std dev:          %.2f secs\n"
            "%s") % (
               self.NumGood(), self.NumError(), self.MedianGood(),
               self.MaxGood(), self.StdDevGood(), chartstr)
    if format == 'html':
      rep = rep.replace('\n', '<br/>')
    return rep


class Results(object):
  """Class for holding results of load tests."""

  def __init__(self, gen_charts, format):
    self.search_times = TimeSet("Search")
    self.cluster_times = TimeSet("Cluster")
    self.suggest_times = TimeSet("Suggest")
    self.start = time.time()
    self.gen_charts = gen_charts
    self.format = format

  def Summary(self):
    """Summarizes the results.

    Returns:
      A string, summarizing the results
    """
    end = time.time()
    total_200 = (self.search_times.NumGood() + self.cluster_times.NumGood() +
                 self.suggest_times.NumGood())
    total_time = end - self.start
    av_qps = total_200 / total_time

    summary = "Load test report:\n"
    if self.format == 'html':
      summary = '<h1>%s</h1>' % summary

    if self.cluster_times.NumTotal():
      summary += self.cluster_times.Report(self.gen_charts, self.format)
    if self.suggest_times.NumTotal():
      summary += self.suggest_times.Report(self.gen_charts, self.format)
    summary += self.search_times.Report(self.gen_charts, self.format)

    overall = self.OverallTimes()
    summary += overall.Report(self.gen_charts, self.format)
    summary += "  Average QPS: %f\n" % av_qps
    return summary

  def OverallTimes(self):
    """Generates a TimeSet containing all search types.

    Returns:
      A TimeSet.
    """
    overall = TimeSet("Overall")
    overall.Extend(self.cluster_times)
    overall.Extend(self.suggest_times)
    overall.Extend(self.search_times)
    return overall


class Client(threading.Thread):

  def __init__(self, host, port, queries, res, enable_cluster, enable_suggest,
               rand_suggest, auth_cfg):
    threading.Thread.__init__(self)
    self.host = host
    self.port = port
    self.res = res
    self.queries = queries
    self.enable_cluster = enable_cluster
    self.enable_suggest = enable_suggest
    self.rand_suggest = rand_suggest
    self.auth_cfg = auth_cfg
    self.cookies = cookielib.LWPCookieJar()
    cookie_processor = urllib2.HTTPCookieProcessor(self.cookies)
    self.opener = urllib2.build_opener(cookie_processor)
    # when scanning for the credential groups in the universal login page,
    # match the CSS, which will have something like
    #           #<group name>Active
    self.credgrp_re = re.compile(r"#(.*)Active")

  def run(self):
    while True:
      try:
        q = self.queries.get(block=False)
      except Queue.Empty:
        break
      else:
        parameters = dict()
        if q.find("/search?") >= 0:
          query_parsed = urlparse.urlparse(q.strip())
          query_parsed_clean = query_parsed[4]
        #Cleaning up query input to prevent invalid requests.
          if query_parsed_clean[0] == "&":
            query_parsed_clean = query_parsed_clean[1:-1]
          query_terms = []
          for qterm in query_parsed_clean.split("&"):
            if qterm.find("=") != -1:
              query_terms.append(qterm)
          try:
            parameters = dict([param.split("=") for param in query_terms])
          except Exception, e:
            print e
            print query_parsed
            print parameters
            raise
          if 'q' in parameters:
            self.FetchContent(self.host, self.port, q.strip(), parameters)
        else:
          self.FetchContent(self.host, self.port, q.strip(), parameters)

  def Request(self, host, port, method, req):
    def TimedRequest(url, data):
      start = time.time()
      resp = self.opener.open(url, data)
      end = time.time()
      return (resp, end - start)

    # make urllib2 use the method we want
    data = None
    if method == "POST":
      data = ""

    result = TimedRequest("http://%s:%s%s" % (host, port, req), data)
    resp = result[0]

    # check if we've ended up at the actual search results page
    # if not, then assume we've landed at some sort of auth page
    respurl = urlparse.urlparse(resp.geturl())
    if (respurl[2] != "/search" and respurl[2] != "/suggest" and
        respurl[2] != "/cluster"):
      if not self.auth_cfg:
        raise urllib2.URLError("No auth cfg found, needed for %s" % req)

      # the URL we're now at, minus all the GET parameters
      path = "%s://%s%s" % (respurl[0], respurl[1], respurl[2])

      # now find out what kind of auth page we're at
      # case 1: universal login
      if respurl[2] == "/security-manager/samlauthn":
        # scan through the form to see the credential groups wanted
        credgrps = []
        for match in self.credgrp_re.finditer(resp.read()):
          credgrps.append(match.group(1))
        # construct the POST fields
        formdata = {}
        for credgrp in credgrps:
          ufield = "u" + credgrp
          pwfield = "pw" + credgrp
          grpdata = self.auth_cfg["universal-login"][credgrp]
          formdata[ufield] = grpdata["username"]
          formdata[pwfield] = grpdata["password"]
        # post it
        result = TimedRequest(path, urllib.urlencode(formdata))

      # case 2: forms-based login
      elif path in self.auth_cfg["forms"]:
        form = self.auth_cfg["forms"][path]
        result = TimedRequest(form["post"], urllib.urlencode(form["fields"]))

      # unsupported/unknown auth mech
      else:
        raise urllib2.URLError("Login unrecognized: %s" % respurl.geturl())

      # if we're still not at the results page, the auth probably failed
      if urlparse.urlparse(result[0].geturl())[2] != "/search":
        raise urllib2.URLError("Auth failed: %s" % req)

    return result

  def FetchContent(self, host, port, q, parameters):
    start_time = time.ctime(time.time())
    test_requests = []
    #For each queries we get from the queue, making one suggest query and one clustering req:
    if self.enable_cluster == True:
      token = parameters.get('q')
      frontend = parameters.get('client', "default_frontend")
      collection = parameters.get('site', "default_collection")
      test_requests.append("/cluster?coutput=json&q=%s&site=%s&client=%s" %(token, collection, frontend))
    if self.enable_suggest == True:
      token = parameters.get('q')
      frontend = parameters.get('client', "default_frontend")
      collection = parameters.get('site', "default_collection")
      sugtokens = []
      if self.rand_suggest:
        # generate a random number of suggestion queries
        # between 1 and the token length
        nsug = random.randint(1, len(token))
        sugsize = (len(token) + nsug - 1) / nsug
        for i in range(0, len(token), sugsize):
          sugtokens.append(token[i:i+sugsize])
      else:
        sugtokens.append(token[0:2])
      for s in sugtokens:
        test_requests.append("/suggest?q=%s&max_matches=10&use_similar&"
                             "access=p&format=rich" % s)
    if q.find("/search?") == 0 and q.find("coutput=json") != 0:
      test_requests.append(q)
    else:
      test_requests.append("/search?q=%s&output=xml_no_dtd&client=default_frontend&roxystylesheet=default_frontend&site=default_collection" % (q))
    for req in test_requests:
      try:
        if req.find("/suggest?") == 0 or req.find("/cluster?") == 0:
          res, exec_time = self.Request(host, port, "POST", req)
        else:
          res, exec_time = self.Request(host, port, "GET", req)
        logging.info("%s: %s: success: %.1f secs query: %s", start_time,
                     self.name, exec_time, req)
        if req.find("/suggest?") != -1:
          self.res.suggest_times.AddGood(exec_time)
        if req.find("/cluster?") != -1:
          self.res.cluster_times.AddGood(exec_time)
        else:
          self.res.search_times.AddGood(exec_time)
      except urllib2.URLError, value:
        logging.info("%s: %s: error: %s query: %s", start_time,
                     self.name, value, req)
        if req.find("/suggest?") != -1:
          self.res.suggest_times.AddError()
        if req.find("/cluster?") != -1:
          self.res.cluster_times.AddError()
        else:
          self.res.search_times.AddError()
      except:
        the_type, value, tb = sys.exc_info()
        logging.info("%s: %s: exception: %s %s query: %s", start_time, self.name,
                     the_type, value, req)
        if req.find("/suggest?") != -1:
          self.res.suggest_times.AddError()
        if req.find("/cluster?") != -1:
          self.res.cluster_times.AddError()
        else:
          self.res.search_times.AddError()


class LoadTester(object):
  """The load tester class."""

  def Init(self):
    # read the queries, from either source
    self.queries_list = []
    if self.queries_filename and self.query_log_name:
      logging.warning("Both query file and query log were provided. "
                      "Using query file.")
    if self.queries_filename:
      queries_file = open(self.queries_filename, 'r')
      logging.info("Reading queries from: %s", self.queries_filename) 
      for line in queries_file:
        self.queries_list.append(line)
      queries_file.close()
    else:
      if not self.admin_username or not self.admin_password:
        logging.critical("GSA admin interface login info required for fetching "
                         "search logs")
        sys.exit(1)
      self.queries_list = self.FetchSearchLogs()
    # load authentication config
    self.auth_cfg = None
    if self.auth_cfg_file:
      f = open(self.auth_cfg_file, 'r')
      self.auth_cfg = yaml.load(f)
      f.close()

  def FetchSearchLogs(self):
    """Fetches search logs using the appliance's admin API.

    Returns:
      A list of query strings, e.g. ['/search?....', '/search?.....']
    """
    opener = urllib2.build_opener()
    # log in first
    post = urllib.urlencode({'Email': self.admin_username,
                             'Passwd': self.admin_password})
    req = None
    try:
      req = opener.open('https://%s:8443/accounts/ClientLogin' % self.host,
                        post)
    except urllib2.HTTPError, e:
      logging.critical("Couldn't log in to admin API: %s", str(e))
      sys.exit(1)
    token = re.search(r"Auth=(\S+)", req.read())
    if not token:
      logging.critical("Couldn't parse auth token for GSA admin API")
      sys.exit(1)
    # request the log
    headers = {'Content-type': 'application/atom+xml',
               'Authorization': 'GoogleLogin auth=%s' % token.group(1)}
    req = urllib2.Request('http://%s:8000/feeds/searchLog/%s' % (
        self.host, self.query_log_name), headers=headers)
    resp = opener.open(req).read()
    # extract the contents of the log
    doc = xml.dom.minidom.parseString(resp)
    content = None
    for node in doc.getElementsByTagName('gsa:content'):
      if node.getAttribute('name') == 'logContent':
        content = node.childNodes[0].nodeValue
        break
    if not content:
      logging.critical("Couldn't parse log content from %s on %s",
                       self.query_log_name, host)
      sys.exit(1)
    queries = []
    for line in content.split('\n'):
      res = re.search(r"GET (\S+)", line)
      if not res:
        continue
      queries.append(res.group(1))
    return queries

  def RunOnce(self):
    queries = Queue.Queue()
    for q in self.queries_list:
      queries.put(q)
    logging.info("Queries loaded")

    # initiate results object
    res = Results(self.charts, self.format)
    thread_list = []
    for i in range(self.num_threads):
      c = Client(self.host, self.port, queries, res,
                 self.enable_cluster, self.enable_suggest, self.rand_suggest,
                 self.auth_cfg)
      c.name = "Thread-%d" % i
      thread_list.append(c)
      c.start()
    # Wait for all the threads to finish before printing the summary
    for t in thread_list:
      t.join()
    return res

  def Benchmark(self):
    # Loops the load testing, increasing the thread count on each iteration,
    # until a certain error rate is reached
    rates = []
    for n in range(1, self.max_trials + 1):
      self.num_threads = n * self.thread_step
      logging.info("Running with %d threads", self.num_threads)
      timeset = self.RunOnce().OverallTimes()
      rates.append((self.num_threads, timeset))
      if timeset.ErrorRate() > self.max_err_rate:
        break
    # generate report
    ret = "Benchmark results:\n"

    if self.format == 'html':
      ret = '<h1>%s</h1>' % ret

    for nthreads, timeset in rates:
      ret += "  Thread count: %d\tMean latency: %.2f s\tError rate: %.2f\n" % (
          nthreads, timeset.MeanGood(), timeset.ErrorRate())
    if self.format == 'html':
      ret = ret.replace('\n', '<br/>')

    if self.charts:
      latency_data = ",".join("%.2f" % r[1].MeanGood() for r in rates)
      max_latency = max(r[1].MeanGood() for r in rates)
      header = "Graph of mean latency vs. thread count:\n  "
      if self.format == 'html':
        header = '<h2>%s</h2>' % header
      url = ("http://chart.apis.google.com/chart?"
             "cht=lc&"
             "chs=550x400&"
             "chxt=x,y,x,y&"
             "chxr=0,%d,%d,%d|1,0,%.2f&"
             "chxl=2:|Thread+count|3:|Mean+latency+(s)&"
             "chxp=2,50|3,50&"
             "chtt=Latency+vs+Thread+count&"
             "chd=t:%s&"
             "chds=0,%.2f") % (
                 rates[0][0], rates[-1][0], self.thread_step,
                 max_latency,
                 latency_data,
                 max_latency)
      if self.format == 'html':
        url = '<img src="%s" />' % url
      ret += header + url

      err_rate_data = ",".join("%.4f" % r[1].ErrorRate() for r in rates)
      max_err_rate = max(r[1].ErrorRate() for r in rates)
      header = "\nGraph of error rate vs. thread count:\n  "
      if self.format == 'html':
        header = '<h2>%s</h2>' % header
      url = ("http://chart.apis.google.com/chart?"
             "cht=lc&"
             "chs=550x400&"
             "chxt=x,y,x,y&"
             "chxr=0,%d,%d,%d|1,0,%.2f&"
             "chxl=2:|Thread+count|3:|Error+rate&"
             "chxp=2,50|3,50&"
             "chtt=Error+rate+vs+Thread+count&"
             "chd=t:%s&"
             "chds=0,%.2f") % (
                 rates[0][0], rates[-1][0], self.thread_step,
                 max_err_rate,
                 err_rate_data,
                 max_err_rate)
      if self.format == 'html':
        url = '<img src="%s" />' % url
      ret += header + url
    return ret

  def Run(self):
    if self.mode == "benchmark":
      logging.info("Mode selected: Benchmark")
      return self.Benchmark()
    else:
      logging.info("Mode selected: Standard")
      return self.RunOnce().Summary()


def usage():
  return ("load.py --queries=<queries-filename> --host=<gsa-hostname> "
          "[--threads=<num-threads>] [--port=<gsa-port>] [--suggest] "
          "[--rand_suggest] [--cluster] [--auth_cfg=<auth-cfg>] "
          "[--query_log=] [--admin_username=] [--admin_password=] [--charts] "
          "[--mode=once|benchmark] [--thread_step=<thread-step>] "
          "[--max_err_rate=<max-err-rate>] [--max_trials=<max-trials> "
          "[--format=text|html] [--output=<output_file>]")


def main():
  lt = LoadTester()
  lt.num_threads = 3
  lt.port = 80
  lt.enable_suggest = False
  lt.enable_cluster = False
  lt.rand_suggest = False
  lt.host = ""
  lt.queries_filename = ""
  lt.query_log_name = ""
  lt.charts = False
  lt.auth_cfg_file = ""
  lt.admin_username = ""
  lt.admin_password = ""
  lt.max_err_rate = 0.5
  lt.max_trials = 15
  lt.thread_step = 10
  lt.mode = "once"
  lt.format = "text"
  output = None

  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["host=", "port=", "threads=", "queries=",
                                "query_log=", "cluster", "suggest",
                                "rand_suggest", "charts", "auth_cfg=",
                                "admin_username=", "admin_password=",
                                "mode=", "thread_step=", "max_err_rate=",
                                "max_trials=", "format=", "output="])
  except getopt.GetoptError:
    print usage()
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--host":
      lt.host = arg
    if opt == "--queries":
      lt.queries_filename = arg
    if opt == "--query_log":
      lt.query_log_name = arg
    if opt == "--threads":
      lt.num_threads = int(arg)
    if opt == "--port":
      lt.port = arg
    if opt == "--cluster":
      lt.enable_cluster = True
    if opt == "--suggest":
      lt.enable_suggest = True
    if opt == "--rand_suggest":
      lt.rand_suggest = True
    if opt == "--charts":
      lt.charts = True
    if opt == "--auth_cfg":
      lt.auth_cfg_file = arg
    if opt == "--admin_username":
      lt.admin_username = arg
    if opt == "--admin_password":
      lt.admin_password = arg
    if opt == "--thread_step":
      lt.thread_step = int(arg)
    if opt == "--max_err_rate":
      lt.max_err_rate = float(arg)
    if opt == "--max_trials":
      lt.max_trials = int(arg)
    if opt == "--mode":
      lt.mode = arg
    if opt == "--format":
      lt.format = arg
    if opt == "--output":
      output = arg

  if not lt.host or not (lt.queries_filename or lt.query_log_name):
    print usage()
    sys.exit(1)

  logging.basicConfig(level=logging.INFO,
                      format="%(message)s")

  logging.info("Initializing...")
  lt.Init()
  logging.info("Initializing complete...")
  report = lt.Run()

  if not output:
    print report
  else:
    out_file = open(output, 'w')
    out_file.write(report + '\n')
    out_file.close()

if __name__ == "__main__":
  main()
