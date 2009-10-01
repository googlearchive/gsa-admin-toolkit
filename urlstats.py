#!/usr/bin/python
#
# Copyright (C) 2009 Google Inc.
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
# urlstats.py
#
# By Jason Liu for Google on 2009.09.30
#
# urlstats.py analyzes the file exported from the "Status and Reports > 
# Export All URLs" page on a Google Search Appliance (version 6.0).  The
# exported URL file contains the following fields:
#
# url	
# crawl_frequency
# state
# currently_inflight
# error_count
# contentfeed_datasource_fingerprint
# in_index
# locked
# crawled_securely
# last_crawled
# content_type
# contentsize_in_bytes
# content_checksum
# fetchtime_in_ms

import sys    # Used for processing command line arguments

def main():
  try:
    log_file = sys.argv[1]    # The log file to be analyzed
  except IndexError:
    usage()
    exit()

  reportOnState(log_file)

def reportOnState(file):
  """
  Go through each line of the log file and count the number
of URLs in each state.
  The url file can be large (>1GB), so we don't want to read
the entire file into memory. We do more I/O and keep memory 
footprint small.
  """
  totalUrl = 0
  states = dict()
  f = open(file, 'r') 
  for line in f:
    try:
      state = line.split()[2]
      totalUrl += 1
      if state in states:
        states[state] += 1
      else:
        states.update({state: 1})
    except:
      pass
  f.close()

  # remove the header
  del states['state'] 
  totalUrl -= 1
    
  # build a list, reversely sorted by number of URLs
  states_sorted = states.items()
  states_sorted.sort(key=lambda x:(x[1], x[0]), reverse=True)

  # print report
  printSeparatorLine()
  myPrint2("Total URLs the GSA discovered", totalUrl)
  printSeparatorLine()
  myPrint2("    URL STATE", "NUMBER OF URLS")
  myPrint2 ("--------------------------", "--------------")
  for (state, count) in states_sorted:
    myPrint2(state, count)
# END of reportOnState

def printSeparatorLine():
  print "*********************************************"

def myPrint2(field, value):
  print "%-30s %10s" % (field, value)

def usage():
  print """
USAGE: urlstats.py FILE

Generate a report from FILE, which is the file exported from the
"Status and Reports > Export All URLs" page in the Admin Console
on a Google Search Appliance.
  """

if __name__ == '__main__':    # If we're being launched as a standalone app...
    main()
