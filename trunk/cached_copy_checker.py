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


'''
NOTE: This script will not work out of the box. Some parameters need
to be set below and the appliance needs to be configured to crawl a
URL.

PURPOSE: This script will tell you whether crawl, indexing and serving
are working on the appliance.  You create a URL on you web server that
always shows the current date and then configure the appliance to
crawl it. Then you can periodically run this script, which will check
the cached copy of the URL and compare the date in it with the current
date. If there is a big difference, then the issue is worth investigating
and the script will email you, otherwise everything is okay.

HIGH LEVEL STEPS:

1. Configure a URL on your web server that returns the current
   timestamp (seconds since the epoch).

2. Configure the appliance to crawl it and wait for it to be indexed.

3. Configure this script and perform a test run. Afterwards, run it
   periodically (once a day)

DETAILED STEPS:

1. Create a URL that returns nothing but seconds since the epoch. Here
is an example in python using CherryPy as a web server
(http://www.cherrypy.org/)

---
import cherrypy,time

class Timestamp(object):
    def index(self):
        return str(int(time.time()))

    index.exposed = True

cherrypy.server.socket_port = 8082
cherrypy.quickstart(Timestamp())
---

Let's say you run the web server on host a.b.com, then the URL you are
interested in is accessible at http://a.b.com:8082/ (this is the URL
we are going to use from now on).

2. Configure the appliance (GSA/Mini) to crawl this URL. For more
information on how to configure the appliance, please see appliance
documentation. Make sure to also add the URL to 'Freshness Tuning >
Crawl Frequently' as well.

3. Enter appropriate values in all the parameters below and perform a
test run by running this script by hand.  (You need to have python
installed. To run the script, run: python cached_copy_checker.py). 
You may want to change send_alert message to just print the error 
instead of emailing it during the first test run.
'''

import re
import smtplib
import sys
import time
import urllib
import urllib2

ONE_DAY = 60 * 60 * 24

# URL that is being indexed by the appliance.
url = 'REPLACE_WITH_URL'
# Hostname of the GSA/Mini.
appliance_hostname = 'REPLACE_WITH_HOSTNAME/IP ADDRESS' 
# How many days old can the cached copy be?
ACCEPTABLE_LAG = ONE_DAY * 4  # 4 days
# SMTP server
smtp_server = 'REPLACE_WITH_THE_ADDRESS_OF_THE_SMTP_SERVER'
# Sender of the alert email.
sender = 'REPLACE_WITH_THE_ADDRESS_OF_THE_SENDER"S_EMAIL_ADDRESS'
# Recipient of the alert email.
recipient = 'REPLACE_WITH_THE_ADDRESS_OF_THE_RECIPIENT"S_EMAIL_ADDRESS'
# Subject of the email.
subject = 'Email from Google Appliance (%s) - Cache copy checker' \
	%appliance_hostname


# Sends an email.
def send_alert(url,message):
  headers = 'From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n' \
  %(sender, recipient, subject)
  final_message = headers + url + '\n' + message
  connection = smtplib.SMTP(smtp_server)
  connection.sendmail(sender, recipient, '%s\n%s' %(url, final_message))
  connection.quit()


# Real work begins here.
try:
  cached_url = 'http://' + appliance_hostname + '/search?q=cache:' + \
    urllib.quote_plus(url)
  print 'Accessing URL - %s ' %cached_url
  content = urllib2.urlopen(cached_url).read()
  #print 'cached content is:\n %s' %content
  try:
    cached_time = int(re.search('[\d]*$',content).group())
  except:
    raise ValueError('Did not find time in the cached copy. It is possible ' 
      'that document has not yet been indexed. Please try accessing the URL '
      'directly. Here is the content I got :\n%s ' %content)
  current_time = int(time.time())
  lag = int(current_time - cached_time)
  print 'Current time: %s' %current_time
  print 'Cached  time: %s' %cached_time
  print 'Time difference is: %s seconds' %lag
  if lag > ACCEPTABLE_LAG:
    message = 'Cached copy is older than %s days! - %s days old.' \
      %(ACCEPTABLE_LAG / ONE_DAY, float(lag) / float(ONE_DAY))
    print message
    print 'Sending an alert.'
    send_alert(cached_url,message)
  else:
    print 'Cached copy is less than %s days old. Everything is good.' \
    %(ACCEPTABLE_LAG / ONE_DAY)
except Exception, exception:
  print 'Got an exception. Sending an alert.'
  send_alert(cached_url, 'Got exception: %s' %exception)
  sys.exit(1)
