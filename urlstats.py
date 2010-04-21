#!/usr/bin/python2.4
# 
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""urlstats.py analyzes a data file and generates a set of reports.

The file should be exported from the "Status and Reports > Export All URLs"
page on a Google Search Appliance (version 6.0 & 6.2).  The exported URL file
contains the following fields separated by tab:

url
crawl_frequency
state
currently_inflight
error_count
contentfeed_datasource_fingerprint
in_index
locked
crawled_securely
last_crawled
content_type
contentsize_in_bytes
content_checksum
fetchtime_in_ms
"""

import getopt
import sys

# command line options
OPTIONS = 'h:'
LONG_OPTIONS = ['help',
                'listurlslargerthan=',
                'all',
                'state',
                'server',
                'size',
                'debug']
# add a key value pair for each type of report
REPORT_CFG = {'reportAll': True,
              'reportState': False,
              'reportServer': False,
              'reportSize': False,
              'listurlslargerthan': -1
             }
DEBUG_MODE = False


def main():
  global DEBUG_MODE
  try:
    opts, args = getopt.getopt(sys.argv[1:], OPTIONS, LONG_OPTIONS)
  except getopt.GetoptError, err:
    # print help information and exit:
    print str(err)
    Usage()
    sys.exit(2)

  for o, a in opts:
    if o == '--listurlslargerthan':
      REPORT_CFG['reportAll'] = False
      REPORT_CFG['listurlslargerthan'] = int(a)  # output the large files
    elif o == '--state':
      REPORT_CFG['reportAll'] = False
      REPORT_CFG['reportState'] = True  # generate a report based on URL state
    elif o == '--server':
      REPORT_CFG['reportAll'] = False
      REPORT_CFG['reportServer'] = True  # generate a report of URL grouped by server
    elif o == '--size':
      REPORT_CFG['reportAll'] = False
      REPORT_CFG['reportSize'] = True  # generate a report based on URL size
    elif o == '--debug':
      DEBUG_MODE = True
    elif o in ('-h', '--help'):
      Usage()
      sys.exit()
    else:
      assert False, 'unhandled option'
      sys.exit()

  try:
    log_file = args[0]  # The log file to be analyzed
  except IndexError:
    log_file = 'all_urls'

  GenReport(log_file)


def GenReport(log_file):
  """Read each line of the log file and generate reports."""
  total_url = 0
  states = dict()
  servers = dict()
  # The content sizes in KB that we want to report on
  # The for loop below assumes that this list is in ascending order
  sizes_kb = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2*1024, 4*1024, 32*1024]
  # initialize the content size map.  it is a dictionary with
  # key: content size threshold (up to) # value: number of documents
  content_size_map = dict([(x*1024, 0) for x in sizes_kb])
  # files that are larger than all the value in sizes_kb are considered
  # very large
  very_large_files = 0

  try:
    f = open(log_file, 'r')
  except IOError:
    print 'unable to open file %s' % file
    Usage()
    sys.exit()

  # The url file can be large (>1GB), so we don't want to read
  # the entire file into memory. We do more I/O and keep memory
  # footprint small.
  for line in f:
    fields = line.split('\t')

    # collect url state information
    try:
      state = fields[2].strip()
    except IndexError, e:
      print 'IndexError:', e
    else:
      total_url += 1
      if state in states:
        states[state] += 1
      else:
        states.update({state: 1})

    # collect information to group urls by server, prot://host:[port]/
    try:
      # assume url format protocol://host/path
      url_elems = fields[0].split('/', 3)
      server = (url_elems[0], url_elems[2])
    except IndexError, e:
      print 'IndexError:', e
    else:
      if server in servers:
        servers[server] += 1
      else:
        servers.update({server: 1})

    # collect content size in byte
    try:
      size = int(fields[11] )
    except ValueError, e:
      # We encountered some value that can not be converted to a number.
      # Most likely it is the header line, but could be something else.
      # We will just skip it unless we are in debug mode.
      MyDebug('Unable to convert the string to a number.  ValueError:')
      MyDebug(e)
    except IndexError, e:
      # We encountered a line that contains less than 12 fields
      # We will just skip it unless we are in debug mode.
      MyDebug('Encountered a bad line:')
      MyDebug(line)
      MyDebug('IndexError:')
      MyDebug(e)
    else:
      for size_kb in sizes_kb:
        if size < size_kb*1024:
          content_size_map[size_kb*1024] += 1
          break
      else:
        # The for loop fell through, the content size is
        # greater than all the size thresholds in the list
        # The file is considered very large
        very_large_files += 1
      if (REPORT_CFG['listurlslargerthan'] != -1 and
          size > REPORT_CFG['listurlslargerthan']):
        print '%16s\t%s' % (line.split('\t')[11], line.split('\t')[0])

    # TODO(Jason): collect extension info
    # TODO(Jason): collect content_type info
    # TODO(Jason): collect URL length info, such as longer than a threshold
    #              or way longer than average, and print the extra long urls
  f.close()

  # remove the header
  try:
    del states['state']
  except KeyError, e:
    MyDebug('Did not find a header line.')
  else:
    total_url -= 1          # removed the header, so decrement by one

  # build a list, reversely sorted by number of URLs
  states_sorted = states.items()
  states_sorted.sort(key=lambda x: (x[1], x[0]), reverse=True)

  # build a list, reversely sorted by number of URLs
  servers_sorted = servers.items()
  servers_sorted.sort(key=lambda x: (x[1], x[0]), reverse=True)

  # build a list, reversely sorted by content size threshold
  content_size_map_sorted = content_size_map.items()
  content_size_map_sorted.sort(key=lambda x: (x[0], x[1]), reverse=True)

  # print report
  if (REPORT_CFG['reportState'] or
      REPORT_CFG['reportServer'] or
      REPORT_CFG['reportSize'] or
      REPORT_CFG['reportAll']):
    PrintSeparatorLine()
    PrintTwoCol('Total URLs the GSA discovered', total_url)
    PrintSeparatorLine()

  # generate a summary of URL state
  if REPORT_CFG['reportState'] or REPORT_CFG['reportAll']:
    PrintTwoCol('NUMBER OF URLS', 'URL STATE')
    PrintTwoCol ('--------------------', '------------------------')
    for (state, count) in states_sorted:
      PrintTwoCol(str(count).rjust(16), state)
    PrintSeparatorLine()

  # generate a summary of number of URLs per server
  if REPORT_CFG['reportServer'] or REPORT_CFG['reportAll']:
    PrintTwoCol('NUMBER OF URLS', 'SERVERS (total: %i)' % len(servers_sorted))
    PrintTwoCol ('--------------------', '------------------------')
    for (server, count) in servers_sorted:
      PrintTwoCol(str(count).rjust(16), '%s//%s' % server)
    PrintSeparatorLine()

  # generate a summary of URL size
  if REPORT_CFG['reportSize'] or REPORT_CFG['reportAll']:
    PrintTwoCol('CONTENT SIZE (UP TO)', 'NUMBER OF URLS')
    PrintTwoCol ('--------------------', '------------------------')
    PrintTwoCol('32MB+', str(very_large_files).rjust(8))
    for (size, count) in content_size_map_sorted:
      PrintTwoCol(str(size).rjust(16), str(count).rjust(8))

  # TODO(Jason): generate a summary of various extensions
  # TODO(Jaosn): generate a summary of content_type
# END of GenReport


def MyDebug(s):
  if DEBUG_MODE:
    print s


def PrintSeparatorLine():
  print '*********************************************'


def PrintTwoCol(col1, col2):
  #print '%-30s\t%10s' % (col1, col2)
  print '%16s\t%s' % (col1, col2)


def Usage():
  """Print the help message."""
  print """
Usage: urlstats.py [--state|size|listurlslargerthan|debug][FILE]

  Generate a report from FILE, which is the file exported from the
"Status and Reports > Export All URLs" page in the Admin Console
on a Google Search Appliance.

Examples:

1. To read the input file named all_urls from working directory and generate
   all the reports, but not list the large URLs.

   urlstats.py

2. To do the same things as example one but read from a different file

   urlstats.py my_url_file.txt

3. To list URLs larger than 1000 bytes

   urlstats.py --listurlslargerthan=1000

4. Only print a report about URL state

   urlstats.py --state
  """


if __name__ == '__main__':  # If we're being launched as a standalone app...
  main()
