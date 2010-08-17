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
#
# This code is not supported by Google
#

"""A connector that crawls a public SMB share."""

__author__ = 'jonathanho@google.com (Jonathan Ho)'

import mimetypes
import os
import subprocess
import tempfile
import smbcrawler
import connector

class SMBConnector(connector.TimedConnector):
  """A connector that crawls an SMB share.

  Pseudocode:
    - Get a list of documents in the SMB share using smbcrawler
    - For each document:
      - Download it with smbclient to a temporary file
      - Read the file's contents to memory
      - Send the file's contents to the GSA as a content feed.

  The mimetypes of a file in the SMB share is inferred from its name.
  """

  CONNECTOR_TYPE = 'smb-connector'
  CONNECTOR_CONFIG = {
      'share': { 'type': 'text', 'label': 'SMB share' },
      'delay': { 'type': 'text', 'label': 'Fetch delay' }
  }

  def init(self):
    self.setInterval(int(self.getConfigParam('delay')))
    self.share = self.getConfigParam('share')
    # smbcrawler doesn't work unless the share ends in a slash
    if self.share[-1] != '/':
      self.share += '/'
    self.smbconfig = smbcrawler.Config(['', self.share])

  def run(self):
    # fetch all the document URLs with smbcrawler
    output = smbcrawler.Crawl(self.smbconfig)

    # now download each file individually with smbclient into a temporary file,
    # then send the file content as a content feed to the GSA
    feed = connector.Feed('incremental')
    devnull = open(os.devnull, 'w')
    for url, doc in output.urls_map.iteritems():
      if not doc.IsFile():
        continue
      filename = doc.filename[1:] # strip out initial slash
      mimetype = mimetypes.guess_type(url)[0] or 'application/octet-stream'
      # download the file to a temporary place, and read out its contents
      tmp = tempfile.NamedTemporaryFile()
      subprocess.call(['smbclient', self.share, '-N', '-c',
                       'get %s %s' % (filename, tmp.name)],
                      stdout=devnull, stderr=devnull)
      tmp.seek(0)
      filedata = tmp.read()
      tmp.close()
      feed.addRecord(url=url, action='add', mimetype=mimetype, content=filedata)
    devnull.close()
    self.pushFeed(feed)
