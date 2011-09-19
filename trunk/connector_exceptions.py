#!/usr/bin/env python
# coding: utf-8
#
# http://gsa-admin-toolkit.googlecode.com/svn/trunk/connector_exceptions.py
#
# Copyright 2008 Google Inc. All Rights Reserved.
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
# This script is not supported by Google.

"""Summarizes the exceptions found in the connector logs."""


from collections import defaultdict
from datetime import datetime
from itertools import takewhile
from optparse import OptionParser
import re
import sys


usage = """Reads google connector log files provided as argument and
summarizes the counts and nature of the exceptions in the logs. Use
'-' to read stdin.

The script looks for pattern such as 'SEVERE:', or
'java.lang.IllegalStateException' then acccumulates lines until a line
start with the log4j date format.
"""

p = OptionParser(usage=usage)
p.add_option('-p', '--pattern', default='',
             help=('Only exceptions matching this regex are listed. '
                   'Ex: "-p ldap: or "--pattern sharepoint"'))

p.add_option('-v', '--verbose', action='count', default=None,
             help=('The actual stack trace are actually shown'))

exception_starts = ['AxisFault',
                    'java.lang.IllegalStateException',
                    'SEVERE:',
                    'WARNING: Exception']


def doesnt_starts_with_date(line):
  """Returns True when 'line' does not starts with a date pattern"""
  if len(line) <= 24:
    return True
  try:
    m=re.search('(.*\d{1,2}:\d{1,2} (A|P)M)',line)
    datetime.strptime(m.groups()[0], '%b %d, %Y %I:%M:%S %p')
    return False
  except (ValueError, AttributeError):
    return True


def starts_with(line, starts_list):
  """Returns True when the line starts with any of the string in
  starts_list"""
  return any([line.startswith(s) for s in starts_list])

counter = defaultdict(int)
when = defaultdict(list)


o, a = p.parse_args()
assert len(a) > 0, 'Error: arguments should be connector log files'
files = [(open(i) if i != '-' else sys.stdin) for i in a]


for lines in files:
  old_line, antepenultieme = '', ''
  for l in lines:

    if starts_with(l, exception_starts):

      exception = l + ''.join(takewhile(doesnt_starts_with_date, lines))
      counter[exception] += 1
      when[exception].append(antepenultieme + old_line)
    old_line, antepenultieme = l, old_line

items = sorted(counter.items())

if o.pattern:
  items = [(e, c) for (e, c) in items if re.search(o.pattern, e.lower())]

for e, c in items:
  print '%s\t%s%s\n' % (c, ''.join(when[e][0]), e.split('\n')[0])

if o.verbose:
  for e, c in items:
    print '_____________________________________'
    print 'The following exception was found %s in the logs' % (
        '%s times' % c if c > 1 else 'once')
    print '%s\n%s' % (''.join(when[e][:3]), e)


