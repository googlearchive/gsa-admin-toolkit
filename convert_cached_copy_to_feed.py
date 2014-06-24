#!/usr/bin/python2
#
# Copyright 2007 Google Inc. All Rights Reserved.
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

"""This script helps to migrate data from one appliance to another.

You need to compile a list of source urls (e.g. via export urls from crawl
diagnostics or export all urls).

IMPORTANT NOTES:
- the script will only export the content, not any meta tags associated
- the script will only contain what the cached version contains
  i.e. the truncated file if the original source was longer than 2.5 MB
- since the script uses the cached version, it assumes to have the default
  stylsheet. In case you modified the chached version header in the
  default stylesheet, you need to adjust the header scrapper
- the script will use one connection to the appliance at a time to
  download the cached versions. This means that you will have less
  serving bandwidth during the runtime of the script
- 1GB limit is not honored. You might have to manually split the output file.

TODO(mblume)
- add meta data via get the search results first with getfields
- parse xml and add these as metadata to the feed.

"""

import base64
import codecs
import getopt
import sys
import urllib
import urllib2
import zlib

import HTMLParser
import xml.etree.cElementTree as ElementTree
from xml.sax.saxutils import quoteattr

#
# constants for the script
# NOTE: you should modify the <datasource>-tag content
#
# the xml header for the content feed
feed_header_text = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<gsafeed>
  <header>\
  <datasource>convert_cached_copy_to_feed</datasource>
  <feedtype>full</feedtype>
  </header>
  <group>\n"""
# the xml footer for the content feed
feed_footer_text = '	</group>\n</gsafeed>'


def DeflateAndBase64Encode(string_val):
  """zlib compress and base64 encode a string."""
  zlibbed_str = zlib.compress(string_val)
  return base64.b64encode(zlibbed_str)


def Usage():
  """Print script usage instructions on stdout."""
  print """A python script to download the cached version from a GSA
and generate a feed that can be submitted to another GSA.

Usage: %s ARGS
  --gsaname:  hostname or ip of the source gsa,
              e.g. search.company.com or 129.13.54.2
  --urlfile:  path and filename of the file containing all urls to download.
              The format should be one url per line
  --output:   path and filename of the generated XML feed file
  --help:     output this message""" % sys.argv[0]


def main(argv):
  #
  # Parameters we are going to initialize via command line args
  #
  # URL that is being indexed by the appliance.
  cached_url_file_name = None
  # Hostname of the GSA/Mini.
  appliance_hostname = None
  # output file:
  output_feed_file_name = None

  try:
    opts, args = getopt.getopt(argv[1:], None,
                         ['help', 'gsaname=', 'urlfile=', 'output='])
  except getopt.GetoptError:
    # print help information and exit:
    Usage()
    sys.exit(2)

  for opt, arg in opts:
    if opt == '--help':
      Usage()
      sys.exit()
    if opt == '--gsaname':
      appliance_hostname = arg
    if opt == '--urlfile':
      cached_url_file_name = arg
    if opt == '--output':
      output_feed_file_name = arg

  if appliance_hostname and cached_url_file_name and output_feed_file_name:
    #
    # Real work begins here.
    #
    try:
      parser = HTMLParser.HTMLParser()
      output_file = open(output_feed_file_name, 'w')
      output_file.write(feed_header_text)
      # get all cached urls:
      cached_url_file = open(cached_url_file_name, 'r')
      for url in cached_url_file:
        cached_url = 'http://' + appliance_hostname + '/search?q=cache:'
        cached_url +=  urllib.quote_plus(url.rstrip())
        print 'Accessing URL - %s ' %cached_url

        # since 7.0 (and possibly earlier), content is an XML document
        # containing the cached content
        content = urllib2.urlopen(cached_url).read()
        gsp = ElementTree.fromstring(content)
        content_type = gsp.findall('.//CACHE_CONTENT_TYPE')[0].text
        blob = gsp.findall('.//BLOB')[0]
        encoding = blob.get('encoding')

        cache_response = codecs.decode(
            base64.b64decode(blob.text), encoding)

        if content_type == 'text/plain':
          # the blob that comes back is wrapped in HTML; unwrap it
          pre_body = cache_response[cache_response.find('<pre>') + len('<pre>'):
                                    cache_response.rfind('</pre>')]
          cached_content = parser.unescape(pre_body)
        else:
          cached_content = cache_response

        compressed_cached_content = DeflateAndBase64Encode(
            codecs.encode(cached_content, 'utf-8'))

        # debug output------------------------------------
        #print 'complete content from GSA is:\n%s' % cached_content
        #print 'cached content is:\n%s' % compressed_cached_content
        # end debug output --------------------------------
        output_file.write("""    <record url=%s mimetype=%s>
      <content encoding="base64compressed">%s</content>
    </record>\n""" % (quoteattr(url.rstrip()), quoteattr(content_type),
                      compressed_cached_content))
    except Exception, exception:
      print 'Got exception: %s' %exception
      sys.exit(1)
    finally:
      output_file.write(feed_footer_text)
  else:
    Usage()
    sys.exit(1)

if __name__ == '__main__':
  main(sys.argv)
