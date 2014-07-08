#!/usr/bin/env python2
#
# Copyright 2014 Google, Inc.
# All Rights Reserved.

"""gsa_feed.py pushes an xml feed file to the GSA.

1. pushes an XML file to the GSA
2. show examples feed for each feedtype
3. validates GSA XML feed with a DTD


=== 1/3 Push a feed file
  ~$ gsa_feed.py feed.xml entzo34.hot

  The XML file and GSA hostname are given as file arguments , the
  order is not important, the feed file must end with .xml.

  No need to specify the feedtype and datasource, they are extracted
  from the XML feed.

  The script shows the minimal required set of "follows URLs".

  Make sure, in the case of a web feed, that the content server owner
  granted you permission to crawl its content server.


=== 2/3 Show examples feeds
  ~$ gsa_feed.py --example full
  ~$ gsa_feed.py --example incremental
  ~$ gsa_feed.py --example metadata-and-url
  ~$ gsa_feed.py --example metadata-and-url-base64
  ~$ gsa_feed.py --example groupsdb


=== 3/3 Validate the feeds against the GSA feed DTD

  The DTD can be retrieved from a GSA
  ~$ gsa_feed.py --dtd gsa_hostname feed.xml

  The DTD can be a local file
  ~$ gsa_feed.py --dtd gsafeed.dtd feed.xml

  The DTD filename must end with '.dtd'. It is always available at
  http://<gsa hostname>/gsafeed.dtd.

Backward compatible with pushfeed_client.py: the same options are supported.
"""

import optparse
import sys
import urllib2
import urlparse
from xml.etree.ElementTree import iterparse

try:
  from lxml import etree
except ImportError:
  etree = None
  print ('DTD validation is not available as the lxml library is missing.\n'
         'To enable this feature, you can install the library, on Linux:\n'
         '~$ sudo aptitude install python-lxml')

VERSION = (1, 0)


EXAMPLES = {
    'full': """<?xml version="1.0" encoding="UTF8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<gsafeed>
  <header>
    <datasource>sample</datasource>
    <feedtype>full</feedtype>
  </header>
  <group>
    <record url="http://example.com/hello01" mimetype="text/plain"
      last-modified="Tue, 6 Nov 2007 12:45:26 GMT">
      <content>This is hello01</content>
    </record>
    <record url="http://example.com/hello02" mimetype="text/plain"
      lock="true">
      <content>This is hello02</content>
    </record>
    <record url="http://example.com/hello03" mimetype="text/html">
    <content><![CDATA[
      <html>
        <title>namaste</title>
        <body>
          This is hello03
        </body>
      </html>
    ]]></content>
    </record>
    <record url="http://example.com/hello04" mimetype="text/html">
      <content encoding="base64binary">Zm9vIGJhcgo</content>
    </record>
  </group>
</gsafeed>""",
    'metadata-and-url-base64': """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" ">"
<gsafeed>
  <header>
    <datasource>example3</datasource>
    <feedtype>metadata-and-url</feedtype>
  </header>
  <group>
    <record url="http://example.com/myfeed.html" action="add" mimetype="text/html">
      <metadata>
        <meta encoding="base64binary" name="cHJvamVjdF9uYW1l" content="Y2lyY2xlZ19yb2Nrcw==">
      </metadata>
    </record>
  </group>
</gsafeed>""",
    'incremental': """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<gsafeed>
  <header>
    <datasource>web</datasource>
    <feedtype>incremental</feedtype>
  </header>
  <group>
    <record url="http://example.com/hello02" mimetype="text/plain"></record>
  </group>
</gsafeed>""",
    'metadata-and-url': """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<gsafeed>
  <header>
    <datasource>example3</datasource>
    <feedtype>metadata-and-url</feedtype>
  </header>
  <group>
    <record url="http://example.com/search/employeesearch.php?q=jwong"
      action="add" mimetype="text/html" lock="true">
      <metadata>
        <meta name="Name" content="Jenny Wong"/>
        <meta name="Title" content="Metadata Developer"/>
        <meta name="Phone" content="x12345"/>
        <meta name="Floor" content="3"/>
        <meta name="PhotoURL"
          content="http://www/employeedir/engineering/jwong.jpg"/>
        <meta name="URL"
          content="http://example.com/search/employeesearch.php?q=jwong"/>
      </metadata>
    </record>
  </group>
</gsafeed>""",
    'groupsdb': """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<xmlgroups>
  <membership>
    <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="GROUP">
      abc.com/group1
    </principal>
    <members>
      <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="GROUP">
        subgroup1
      </principal>
      <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="USER">
        user1
      </principal>
    </members>
  </membership>
  <membership>
    <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="GROUP">
        subgroup1
    </principal>
    <members>
      <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="USER">
        example.com/user2
      </principal>
    </members>
  </membership>
</xmlgroups>"""}


p = optparse.OptionParser(usage=__doc__.strip())

p.add_option(
    '--dtd',
    help=('A string: either the filename of the dtd in the local directory, or '
          'the hostname of a GSA on which the script will fetch the latest '
          ' dtd. Use this option to validate the feed with the GSA DTD. The '
          'DTD is on the GSA, at the '
          'address http://<gsa hostname>/gsafeed.dtd.'),
    action='store_true',
    default=False)
p.add_option(
    '--example',
    help='can be: %s' % ', '.join(EXAMPLES.keys()),
    default=None)
p.add_option(
    '-s', '--datasource',
    help=('Name of the datasource. Deprecated option, the datasource is now '
          'extracted from the XML feed.'),
    default=None)
p.add_option(
    '--feedtype',
    help=('Can be "full", "incremental", or "metadata-and-url". Deprecated '
          'option, the feedtype is now extracted from the XML feed. '),
    default=None)
p.add_option(
    '-u', '--url',
    help=('URL of the feed component e.g. '
          'http://<gsa address>:19900/xmlfeed. '
          'Deprecated option: the GSA host is the positional arg that does not '
          'end in ".xml"'),
    default=None)
p.add_option(
    '--xmlfilename',
    help=('The feed xml file you want to feed. '
          'Deprecated option: the filename is the positional arg ending '
          'in ".xml"'),
    default=None)


def ShowExamples(example):
  """Prints the example to the console."""
  assert example in EXAMPLES.keys(), (
      'The "--example" value must be one of %s' % EXAMPLES.keys())
  print EXAMPLES[example]


def SendFeed(xmlfilename=None, url=None, feedtype=None, datasource=None):
  """Sends an HTTP post from the command line flags.

  Args:
    xmlfilename: the filename of a XML GSA feed
    url: the URL of the feed service on the GSA
    feedtype: incremental, full, etc (more details in the reference)
    datasource: a string label of the user choice

  Returns:
    None. All side effect.
  """

  def EncodeMultipart(fields):
    """Returns input  data in multipart/form-data encoding.

    Args:
      fields: list of 2-strings tuples.
        Example: [('feedtype', 'incremental'),
                  ('datasource', 'mydatasource')
                  ('data', '<xml feed string ...')]

    Returns:
       a 2-tuple of strings:
        - the content_type (with the part 'boundary=')
        - a multipart/form-data encoding string
    """
    boundary = '----------boundary_of_feed_data$'

    lines = []
    for key, value in fields:
      lines.extend(('--' + boundary,
                    'Content-Disposition: form-data; name="%s"' % key,
                    '',
                    value))
    lines.extend(('--' + boundary + '--', ''))

    return 'multipart/form-data; boundary=%s' % boundary, '\r\n'.join(lines)

  parts = [('feedtype', feedtype),
           ('datasource', datasource),
           ('data', open(xmlfilename, 'r').read())]

  content_type, body = EncodeMultipart(parts)
  headers = {'Content-type': content_type,
             'Content-length': str(len(body))}

  try:
    print 'Sending the feed to:', url
    return urllib2.urlopen(urllib2.Request(
        url, body, headers)).read()
  except urllib2.URLError:

    url = url.replace(
        'http', 'https').replace('19900', '19902')
    print 'Trying sending the feed to:', url
    return urllib2.urlopen(urllib2.Request(
        url, body, headers)).read()


def Validate(dtd_filename_or_url, xmlfilename):
  """Validate the input file against a GSA feed DTD.

  Args:
    dtd_filename_or_url: string either a .dtd file in the current directory,
      or the hostname of a GSA on which to fetch the DTD.

  Returns:
    True if validation passed, otherwise an exception is raised.

  Raises:
    ImportError: A DTD validation exception or an error when the hostname
      set is not reachable on the port 80, on the URL
      http://<ip address>/gsafeed.dtd.
  """

  if not etree:
    raise ImportError(
        'As the lxml module not available, feed validation is not '
        'available, please check http://lxml.de/installation.html\n'
        'On Linux, "sudo aptitude install python-lxml"')

  if dtd_filename_or_url.endswith('.dtd'):
    f = open(dtd_filename_or_url)
  else:
    try:
      dtd_url = 'http://%s/gsafeed.dtd' % dtd_filename_or_url
      print 'Trying to fetch the dtd from:', dtd_url
      f = urllib2.urlopen(dtd_url)
    except urllib2.URLError:
      try:
        dtd_url = dtd_url.replace('http', 'https').replace('19900', '19902')
        print 'Trying to fetch the dtd from:', dtd_url
      except:
        raise Exception(
            'Could not download the dtd from %s. '
            'Is this GSA reachable, is the port 80 or 443 open and reachable?'
            % dtd_url)

  etree.DTD(f).validate(etree.parse(xmlfilename))
  return True


def ExtractFeedtypeAndDatasource(filename):
  """Extracts the feed type and the datasource.

  Args:
    filename: string filename of a XML GSA feed document.

  Returns:
    A tuple of string: (feedtype, datasource)

  Raises:
    ValueError: when the datasource and feedtype are missing from the XML file.
  """

  feedtype, datasource = None, None
  for event, elem in iterparse(filename):
    if event == 'end':
      if elem.tag == 'feedtype':
        feedtype = elem.text
      elif elem.tag == 'datasource':
        datasource = elem.text
    if feedtype and datasource:
      return feedtype, datasource
  raise ValueError(
      'Could not find the feed type and datasource in the XML file')


def ExtractFollowUrls(filename):
  """Returns a minimal set of hostnames matching the URLs in the feed."""
  follow_urls = set()
  for event, elem in iterparse(filename):
    if event == 'end':
      if elem.tag == 'record':
        if 'url' in elem.attrib:
          url = urlparse.urlparse(elem.attrib['url'])
          follow_urls.add('/'.join([url.scheme, url.netloc]) + '/')
  return follow_urls


def main(options):
  if options.example:
    ShowExamples(options.example)

  elif options.dtd:
    if not options.xmlfilename:
      print 'Provide a document to validate'

    if Validate(options.host, options.xmlfilename):
      print 'Valid XML document, valid GSA feed.'

  else:
    if not options.url or not options.xmlfilename:
      print ('No hostname or no feed file:'
             '\n  gsa_feed.py feed.xml gsa.company.com')
      sys.exit(1)

    # If the datasource or the feedtype is empty extract it from the feed file.
    if options.feedtype is None or options.datasource is None:
      feedtype, datasource = ExtractFeedtypeAndDatasource(options.xmlfilename)

      if options.feedtype is None:
        options.feedtype = feedtype

      if options.datasource is None:
        o.datasource = datasource

    response = SendFeed(
        options.xmlfilename, options.url, options.feedtype, options.datasource)
    print 'Feed service responded:', response
    if response == 'Success':
      print ('\nMake sure the GSA is configured in "Content Sources > Feeds" '
             'for receiving feeds from this workstation IP address. ')
      print ('Make sure the URLs you push are matching a "follow URL". '
             'See below for minimal set of matching follow URLs:')

      for l in ExtractFollowUrls(options.xmlfilename):
        print l


if __name__ == '__main__':

  if len(sys.argv) == 1:
    p.print_help()
    sys.exit(1)

  o, a = p.parse_args()
  o.host = None

  # sets the positional args to the 'xmlfilename' and 'host' depending on the
  # term suffix: it is an XML filename iff ends with .xml
  for option in a:
    setattr(o, 'xmlfilename' if option.endswith('.xml') else 'host', option)

  # Sets the full URL from the host shortcut
  if o.host:
    o.url = 'http://%s:19900/xmlfeed' % o.host

  main(o)
