#!/usr/bin/python2.2
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
# searchstats.py
#
# By Gregg Bloom for Google on 2007.03.08
#
# searchstats.py will provide useful statistics by culling data from an
# appliance's search logs.
#
# Revised on 2008.03.20 to utilize either a partnerlog or an extracted search
#   log.
# Revised on 2008.03.20 to provide an average response time.
# Revised on 2007.06.11 to use second-buckets rather than minute-buckets.

import sys    # Used for processing command line arguments

def main():
  log_file = sys.argv[1]    # The log file to be analyzed
  try:
    interval = sys.argv[2]    # The interval over which to summarize
  except IndexError:
    interval = "30m"    # If no interval is specified, use a default

  spb = 1800    # The number of seconds per bin in each day.

  period_type = interval[-1:]    # Grabbing the last character of the interval
                                 # to check for a specified period type

  get_period = 0    # Assume no period type
  period_multiplier = 60    # Assume the period is in minutes

  if period_type == 'd':    # Days
    get_period = 1
    period_multiplier = 86400
  elif period_type == 'h':    # Hours
    get_period = 1
    period_multiplier = 3600
  elif period_type == 'm':    # Minutes
    get_period = 1
  elif period_type == 's':    # Seconds
    get_period = 1
    period_multiplier = 1

  if get_period:    # If there was a period type provided, we need to get the
                    # period
    try:
      period = int(interval[:-1])
    except ValueError:    # If up to the last character of interval is not an
                          # integer, it'll throw a ValueError
      print "ERROR: Please specify an interval in the proper format."
      sys.exit(1)

    spb = period * period_multiplier    # Calculate the seconds per bin
  else:    # No period type was provided in the interval.  Assume it's all an
           # interval
    try:
      spb = int(interval) * period_multiplier
    except ValueError:    # If interval isn't an integer, it'll throw a
                          # ValueError
      print "ERROR: Please specify an interval in the proper format."
      sys.exit(1)

  if spb > 86400:    # Bins can't be longer than a day.
    print "ERROR: Maximum time per bin is one day (1d)"
    sys.exit(4)

  num_bins = int(86400 / spb)    # Each day of output will have the same number
                                 # of bins

  days = []    # Initialize our data container
   
  try:
    search_log = open(log_file, 'r')
  except:    # If we can't open the provided log file, throw an error.
    print "ERROR: Log file %s cannot be opened." % log_file
    sys.exit(2)

  first_line = 1    # On the first pass through the file, we'll always
                       # start with the first line.

  split_on = " "    # The input file could be a partnerlog file or a search log.
                    # We'll need to split each line differently based on the
                    # type of file.  split_on will contain the split character.
  date_field = 0    # date_field will be the field which contains the date.
                    # The date is in a different position depending on the
                    # type of file we've received.
  response_field = 0    # Just like the date_field, the response_filed changes
                        # depending on the type of file we've received.  The
                        # response_field houes the HTTP response.
  check_timing = 0    # If we're parsing a partnerlog file, we can also
                          # calculate the average response time for requests.

  line_count = 0    # line_count will contain the number of entries processed
                    # from the log file we received.

  previous_date = ""    # previous_date contains the date of the previously-
                        # processed entry.
  for line in search_log:    # Iterate through lines of the log file.
    if first_line:    # If this is the first line, we need to figure out what
                      # kind of file we've received (search log or partnerlog).
      if len(((line.split())[0]).split('.')) == 4:
        # The log file entries start with an IP address, so we assume that it's
        # a search log.  Set our correct field and split variables.
        split_on = " "
        date_field = 3
        response_field = 8
        check_timing = 0
      elif len(((line.split())[0]).split('/')) == 3:
        # The log file entries start with a date, so we assume that it's a
        # partnerlog.  Set our correct field and split variables.
        date_field = 0
        response_field = 3
        check_timing = 1
        split_on = "\t"
      else:    # Dude!  What kind of file _is_ this?!?!
        print "ERROR: %s is not a search log or partnerlog" % log_file
        sys.exit(3)

      first_line = 0    # We're no longer at the first line of the file.

    items = line.split(split_on)    # Split the entries of this line into an
                                    # array.
    # Extract the date and time.
    date_parts = items[date_field].split('[')[1].split(']')[0].split(':')
    date = date_parts[0]    # Separate the date.

    if date != previous_date:    # If this date is different than the last-
                                 # processed date, prepare this date's data
                                 # structure.
      days.append({'date': date, 'total':0, 'bins': []})

      # Iterate through the number of bins per day to prepare their data
      # structures.
      for bin_ix in range(num_bins):
        days[-1]['bins'].append({'total': 0,
                                 '200': 0,
                                 'non200': 0,
                                 'response_time': 0})
      previous_date = date    # Set the previous date to this date for the next
                              # iteration.

    # Grab the second of the day for this log entry.
    sod = ((int(date_parts[1]) * 3600) + (int(date_parts[2]) * 60)
        + int(date_parts[3]))
    bin = int(sod) / spb    # Figure out which bin this entry belongs in.

    days[-1]['bins'][bin]['total'] += 1    # Increment the total for the bin.

    if items[response_field] == "200":
      # If the response was 200, increment the 200 bin.
      days[-1]['bins'][bin]['200'] += 1
    else:    # If the response wasn't 200, increment the non200 bin.
      days[-1]['bins'][bin]['non200'] += 1

    if check_timing:    # If we're supposed to check timing, increment the
                        # response time for later averaging.
      days[-1]['bins'][bin]['response_time'] += float((items[10].split())[0])

    days[-1]['total'] += 1    # Increment the number of searches processed on
                              # this date.
    line_count = line_count + 1    # Increment the number searches processed.

  search_log.close()    # We're done with the log file.  Close it!

  for days_ix in range(len(days)):    # Iterate through the days for which we
                                      # have data.
    # Display a header for the day.
    print "Summary for %s:   total searches: %d" % (days[days_ix]['date'],
        days[days_ix]['total'])

    timing_text = ""    # If we didn't check timing, there won't be any timing
                        # column.
    if check_timing:    # If we did check timing, add a header.
      timing_text = "av. response"

    # Display a header for this day's output.
    print ("             time     200 non-200    %err   total     %tot" +
           "    qps " + timing_text)

    # Iterate through the bins for this date.
    for bin_ix in range(num_bins):
      err = 0.0    # The bin's error rate for the date.
      tot = 0.0    # The bin's percent of total for the date.
      av_response = 0.0    # The average response time for the bin.

      # Let's avoid those divide by zero errors by only calculating percentages
      # if there were queries in the bin.
      if days[days_ix]['bins'][bin_ix]['total'] != 0:
        err = (float(days[days_ix]['bins'][bin_ix]['non200']) * 100.0 /
               float(days[days_ix]['bins'][bin_ix]['total']))
        tot = (days[days_ix]['bins'][bin_ix]['total'] * 100.0 / 
               float(days[days_ix]['total']))
        av_response = (days[days_ix]['bins'][bin_ix]['response_time'] /
                       float(days[days_ix]['bins'][bin_ix]['total']))

      # Calculate the queries per second for this bin.
      qps = days[days_ix]['bins'][bin_ix]['total'] / (spb * 1.0)

      start = bin_ix * spb    # The start time of this bin.
      end = bin_ix * spb + spb - 1    # The end time of this bin.

      if check_timing:    # If we checked timing, we'll need to output that
                          # extra average response time column.
        print ('%2.2d:%2.2d:%2.2d-%2.2d:%2.2d:%2.2d %7d %7d  %6.2f %7d' +
               '   %6.2f %6.2f %10.3f') % (
               start / 3600, (start % 3600) / 60, start % 60,
               end / 3600, (end % 3600) / 60, end % 60, 
               days[days_ix]['bins'][bin_ix]['200'],
               days[days_ix]['bins'][bin_ix]['non200'], err,
               days[days_ix]['bins'][bin_ix]['total'], tot,
               qps, av_response)
      else:    # If we didn't check timing, don't print average response times.
        print '%2.2d:%2.2d:%2.2d-%2.2d:%2.2d:%2.2d %7d %7d  %6.2f %7d   %6.2f %6.2f' % (
        start / 3600, (start % 3600) / 60, start % 60,
        end / 3600, (end % 3600) / 60, end % 60, 
        days[days_ix]['bins'][bin_ix]['200'],
        days[days_ix]['bins'][bin_ix]['non200'], err,
        days[days_ix]['bins'][bin_ix]['total'], tot,
        qps)
    print ("-------------------------------------------------------" +
           "-------------------------")
  # We're done.  How many entries did we process?
  print 'Total entries: %d' % line_count


if __name__ == '__main__':    # If we're being launched as a standalone app...
  # Check the number of command line arguments.  There should be 2 or 3.
  if len(sys.argv) < 2 or len(sys.argv) > 3:
    # If we received the wrong number or arguments, print usage information.
    print "USAGE: searchstats.py [search log file] [interval]"
    print "   [search log file] - an exported search log or an internal partner log"
    print "                     - this argument is mandatory"
    print "   [interval] - [period][period type]"
    print "       [period] - the duration over which to summarize search information"
    print "       [period type] - can be:"
    print "            s - seconds"
    print "            m - minutes"
    print "            h - hours"
    print "                     - if no period type is specified, minutes are assumed"
    print "                     - default is 30m"
    print "EXAMPLE:"
    print "   searchstats.py jan_2008_all.log 5m"
    print "       will display information from a file called jan_2008_all.log,"
    print "       summarized in five-minute intervals."
    print "   searchstats.py mysearches.log 1h"
    print "       will display information from a file called mysearches.log, summarized"
    print "       in one-hour intervals."
  else:    # The number of command line arguments looks good.  Let's go!
    main()
