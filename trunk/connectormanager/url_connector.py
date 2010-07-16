#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""A connector that fetches the contents of a URL and sends it to the GSA as a
content feed.
"""

__author__ = 'jonathanho@google.com (Jonathan Ho)'

import timed_connector
import urllib2

class URLConnector(timed_connector.TimedConnector):
  CONNECTOR_TYPE = 'url-connector'
  CONNECTOR_CONFIG = {
      'url': { 'type': 'text', 'label': 'URL to fetch' },
      'delay': { 'type': 'text', 'label': 'Fetch delay' }
  }

  def init(self):
    self.setInterval(int(self.getConfigParam('delay')))

  def run(self):
    url = self.getConfigParam('url')
    req = urllib2.Request(url)
    response = urllib2.urlopen(req)
    content = response.read()
    self.sendContentFeed(url=url, action='add', mimetype='text/html',
                         content=content)
