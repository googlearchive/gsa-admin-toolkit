#!/usr/bin/python
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

"""Abstract connector classes."""

__author__ = 'jonathanho@google.com (Jonathan Ho)'

import base64
import threading
import urllib2
import xml.dom.minidom


class Connector(object):
  """A connector interface to be implemented by connector classes.

  A connector implementation must provide the CONNECTOR_TYPE field, as well as
  the CONNECTOR_CONFIG field if it uses the configuration form generator. It
  must implement startConnector, stopConnector, and restartConnectorTraversal.
  If the connector does not use the configuration form generator, it must also
  implement getConfigForm and getPopulatedConfigForm.

  The ExampleConnector and TimedConnector serve as examples of direct
  implementations of this interface.
  """

  def __init__(self, manager, name, config, schedule, data):
    """Creates a connector, and then calls init().

    This should only be called by the connector manager.

    Args:
      manager: The connector manager creating the connector.
      name: The instance name as a string.
      config: The connector configuration XML string.
      schedule: The connector running schedule XML string.
      data: Stored connector data (any pickle-able object).
    """
    self._manager = manager
    self._name = name
    self._config = config
    self._schedule = schedule
    self._data = data
    self.init()

  def init(self):
    """Initialization method to be implemented, if needed (the constructor is
    only for the ConnectorManager to use). This is called right after the
    connector is initialized, as well as when a connector's schedule or
    configuration is changed. A connector can use this method to load any such
    configuration or scheduling data and use it appropriately.
    """
    pass

  @staticmethod
  def _generateConfigFormField(name, spec, value=''):
    fieldstr = ''
    if spec['type'] == 'text':
      fieldstr = '<input type="text" name="%s" value="%s" />' % (name, value)
    return fieldstr

  @classmethod
  def _generateConfigForm(cls):
    """Generates a configuration form from cls.CONNECTOR_CONFIG.

    Returns:
      A string of HTML ready to be injected into the GSA admin form.
    """
    rows = []
    # for now, this only works with text input fields
    for name, spec in cls.CONNECTOR_CONFIG.iteritems():
      field = cls._generateConfigFormField(name, spec)
      row = '<tr><td>%s</td><td>%s</td></tr>' % (spec['label'], field)
      rows.append(row)
    return '\n'.join(rows)

  def _generatePopulatedConfigForm(self):
    """Generates a configuration form from self.CONNECTOR_CONFIG. Similar to
    _generateConfigForm, except this fills in the form with values from
    getConfigParam.

    Returns:
      A string of HTML ready to be injected into the GSA admin form.
    """
    rows = []
    # for now, this only works with text input fields
    for name, spec in self.CONNECTOR_CONFIG.iteritems():
      value = self.getConfigParam(name)
      field = self._generateConfigFormField(name, spec, value)
      row = '<tr><td>%s</td><td>%s</td></tr>' % (spec['label'], field)
      rows.append(row)
    return '\n'.join(rows)

  @classmethod
  def getConfigForm(cls):
    """Returns the empty configuration form.

    The form should be encapsulated inside a
    <CmResponse><ConfigureResponse><FormSnippet> CDATA tag.

    Returns:
      A string with the empty configuration form HTML enclosed in a
      <CmResponse><ConfigureResponse><FormSnippet> CDATA tag.
    """
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConfigureResponse>'
            '<FormSnippet><![CDATA[%s]]></FormSnippet>'
            '</ConfigureResponse>'
            '</CmResponse>') % cls._generateConfigForm()

  def getPopulatedConfigForm(self):
    """Returns a populated configuration form.

    (The form should not be encapsulated in anything, unlike getConfigForm)

    Returns:
      A string with the populated config form HTML enclosed in a CDATA tag.
    """
    return '<![CDATA[%s]]>' % self._generatePopulatedConfigForm()

  def getName(self):
    """Returns the connector instance name.

    Returns:
      The connector instance name as a string.
    """
    return self._name

  def getConfig(self):
    """Returns the connector configuration XML.

    Returns:
      The connector configuration XML string.
    """
    return self._config

  def setConfig(self, config):
    """Sets the connector configuration.

    Args:
      config: The raw XML configuration string.
    """
    self._config = config

  def getSchedule(self):
    """Returns the raw XML schedule data.

    Returns:
      The scheduling data XML string.
    """
    return self._schedule

  def setSchedule(self, schedule):
    """Sets the connector schedule.

    Args:
      schedule: The raw XML schedule as a string.
    """
    self._schedule = schedule

  def getData(self):
    """Returns stored data.

    Returns:
      The stored data. The type depends on the object given by setData.
    """
    return self._data

  def setData(self, data):
    """Sets the data storage object.

    This data is stored via pickle and base64 along with the connector's other
    configuration data. The connector can use this to store information that
    persists through connector manager restarts.
    The data is only written to disk when the connector manager writes its
    configuration file to disk.

    Args:
      data: The object to be stored. This can be of any pickle-able type.
    """
    self._data = data

  def getLoad(self):
    """Returns the current load setting (docs to traverse per min).

    This parameter is initally provided inside the schedule XML.
    A connector does not have to do anything with this parameter.

    Returns:
      The load setting as an integer.
    """
    return int(self.getScheduleParam('load'))

  def getRetryDelay(self):
    """Returns the retry delay in milliseconds.

    The default value is 300000 milliseconds.

    Returns:
      The retry delay in milliseconds as an integer.
    """
    delay = self.getScheduleParam('RetryDelayMillis')
    # it seems that the delay isn't provided when a connector is first created,
    # so we have to provide a default value
    if not delay:
      return 300000
    return int(delay)

  def getTimeIntervals(self):
    """Returns the time intervals over which to traverse.

    The time intervals are formatted as a single string, with individual
    intervals delimited by colons.
    This parameter is provided by setSchedule in the connector manager. It's
    also set and explictly by the connector. A connector does not have to do
    anything with this parameter (you can ignore it if needed).

    Returns:
      The time intervals setting as a string in the format described above.
    """
    return self.getScheduleParam('TimeIntervals')

  def getStatus(self):
    """Returns the status of the connector (0 --> OK).

    Returns:
      A string describing the status of the connector.
    """
    return '0'

  def startConnector(self):
    """Starts the connector.

    It's up to connectors to provide their own scheduling schemes.
    """
    raise NotImplementedError("startConnector() not implemented")

  def stopConnector(self):
    """Stops the connector."""
    raise NotImplementedError("stopConnector() not implemented")

  def restartConnectorTraversal(self):
    """Restarts the traversal."""
    raise NotImplementedError("restartConnectorTraversal() not implemented")

  def authenticate(self, domain, username, password):
    """Authenticates a user and returns the identity.

    This should be overridden if the connector needs to implement
    authentication. The GSA will invoke this for secure feeds.
    The default behavior is to succeed on all inputs.

    Args:
      domain: The authentication domain (string).
      username: The username (string).
      password: The user's password (string).

    Returns:
      The username string on success, or None on failure.
    """
    return username

  def authorize(self, identity, domain, resource):
    """Authorizes a user.

    This should be overridden if the connector needs to implement
    authorization. The GSA will invoke this for secure feeds.
    The default behavior is to succeed on all inputs.

    Args:
      identity: The identity trying to access the resource (string).
      domain: The domain (string).
      resource: The resource URL (string).

    Returns:
      The authorization response string ('Permit', 'Deny', or 'Indeterminate').
    """
    return 'Permit'

  def getConfigParam(self, param_name):
    """Returns a specific parameter of the configuration data set by setConfig.

    Args:
      param_name: The parameter name.

    Returns:
      The value of the parameter as a string, or None if the parameter is not
      present in the configuration.
    """
    xmldoc = xml.dom.minidom.parseString(self.getConfig())
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      for node in rnode.childNodes:
        if (node.nodeName == 'Param' and
            node.attributes["name"].value == param_name):
            return node.attributes["value"].value
    return None


  def setConfigParam(self, param_name, param_value):
    """Sets a specific parameter of the configuration data set.

    Args:
      param_name:  The parameter name.
      param_value: The parameter value.

    Returns: None
    """
    xmldoc = xml.dom.minidom.parseString(self.getConfig())
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      for node in rnode.childNodes:
        if (node.nodeName == 'Param' and
            node.attributes["name"].value == param_name):
            node.attributes["value"].nodeValue = param_value
    self.setConfig(xmldoc.toxml())
    return None


  def getScheduleParam(self, param_name):
    """Returns a specific parameter of the scheduling data set by setSchedule.

    Args:
      param_name: The parameter name string.

    Returns:
      The value of the parameter as a string, or None if the parameter is not
      present in the schedule.
    """
    xmldoc = xml.dom.minidom.parseString(self.getSchedule())
    m_node = xmldoc.getElementsByTagName('ConnectorSchedules')
    for rnode in m_node:
      for node in rnode.childNodes:
        if node.nodeName == param_name:
          return node.childNodes[0].nodeValue
    return None

  def pushRaw(self, data, feed_type):
    """Pushes a feed (as raw XML) to the GSA.

    Args:
      data: The XML string to send to the GSA. This may be a hassle to
        generate; using pushFeed with a Feed object is the preferred over
        using this method by itself.
      feed_type: The feed type string. Can be 'incremental', 'full', or
        'metadata-and-xml'.

    Returns:
      The GSA response status as a string.
    """
    def encode_multipart_formdata(xmldata):
      BOUNDARY = '<<'
      CRLF = '\r\n'
      L = []
      L.append('--' + BOUNDARY)
      L.append('Content-Disposition: form-data; name="datasource"')
      L.append('Content-Type: text/plain')
      L.append('')
      L.append(self._name)

      L.append('--' + BOUNDARY)
      L.append('Content-Disposition: form-data; name="feedtype"')
      L.append('Content-Type: text/plain')
      L.append('')
      L.append(feed_type)

      L.append('--' + BOUNDARY)
      L.append('Content-Disposition: form-data; name="data"')
      L.append('Content-Type: text/xml')
      L.append('')
      L.append(xmldata)
      L.append('')
      L.append('--' + BOUNDARY + '--')
      L.append('')
      return ('multipart/form-data; boundary=%s' % BOUNDARY, CRLF.join(L))

    self.logger().debug('Posting Aggregated Feed to : %s' % self._name)
    xmldata = ('<?xml version=\'1.0\' encoding=\'UTF-8\'?>'
               '<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" '
               '"gsafeed.dtd">'
               '<gsafeed>'
               '<header>'
               '<datasource>%s</datasource>'
               '<feedtype>%s</feedtype>'
               '</header>'
               '<group>%s</group>'
               '</gsafeed>') % (self._name, feed_type, data)
    content_type, body = encode_multipart_formdata(xmldata)
    headers = {}
    headers['Content-type'] = content_type
    headers['Content-length'] = str(len(body))
    u = 'http://%s:19900/xmlfeed' % self._manager.gsa
    request_url = urllib2.Request(u, body, headers)
    if self._manager.debug_flag:
      self.logger().debug('POSTING Feed to GSA %s ' % self._manager.gsa)
      self.logger().debug(request_url.get_method())
      self.logger().debug(request_url.get_full_url())
      self.logger().debug(request_url.headers)
      self.logger().debug(request_url.get_data())
    status = urllib2.urlopen(request_url).read()
    self.logger().debug("Response status from GSA [%s]" % status)
    return status

  def pushFeed(self, feed):
    """Pushes a feed (as a Feed object) to the GSA.

    Args:
      feed: A Feed object.

    Returns:
      The GSA response string.
    """
    return self.pushRaw(feed.toXML(), feed.getType())

  def pushFeedSingleRecord(self, feed_type, **attrs):
    """Pushes a feed with a single record to the GSA.

    Args:
      feed_type: The feed type. See the constructor for Feed.
      **attrs: Other args. See Feed.addRecord.

    Returns:
      The GSA response string.
    """
    feed = Feed(feed_type)
    feed.addRecord(attrs)
    return self.pushFeed(feed)

  def logger(self):
    """Returns this connector's logger.

    Returns:
      The Logger object belonging to this connector.
    """
    return self._manager.logger(self)


class TimedConnector(Connector):
  """An abstract connector that runs continually with a specified time interval.

  A connector that implements this TimedConnector just needs to override the
  run() method. The getInterval and setInterval methods are provided to
  manipulate the timer delay (the default is 15 minutes).

  If a TimedConnector implementation's interval comes from the configuration
  form, then setInterval should be called in an init() method with the
  appropriate value from getConfigParam.
  """

  _interval = 15*60 # 15 minutes
  _timer = None

  def run(self):
    """Runs the connector logic."""
    raise NotImplementedError("run() not implemented")

  def _run(self):
    self.run()
    self._timer = threading.Timer(self._interval, self.startConnector)
    self._timer.start()

  def startConnector(self):
    """Starts the connector by calling the run() method periodically, as
    specified by setInterval."""
    self._timer = threading.Timer(self._interval, self._run)
    self._timer.start()

  def stopConnector(self):
    """Stops the connector by cancelling the timer."""
    if self._timer:
      self._timer.cancel()
      self._timer = None

  def restartConnectorTraversal(self):
    """Restarts the connector by stopping and starting it again.

    Note: this may be completely incorrect, depending on the connector
    implementation. For example, if the connector maintains some sort of
    traversal state after stopConnector(), this would fail to reset that state.
    This method should, of course, be overridden if this is the case.
    """
    self.stopConnector()
    self.startConnector()

  def getInterval(self):
    """Returns the timer interval.

    Returns:
      The timer interval, in seconds.
    """
    return self._interval

  def setInterval(self, interval):
    """Sets the timer interval.

    Args:
      interval: The timer interval in seconds, as a float or int.
    """
    self._interval = interval


class Feed(object):
  """A set of records to be placed in an XML feed.

  Note: The name of the class may be a little misleading. This class does not
  represent a feed in its entirety, just a feed's records. That is, when toXML
  is called, a series of <record>...</record><record>...</record> elements is
  produced, not a complete <gsafeed>...</gsafeed> element.
  """

  def __init__(self, feedtype):
    """Creates the feed.

    Args:
      feedtype: The feed type. Must be a string, either 'incremental', 'full',
      or 'metadata-and-url'.
    """
    self._type = feedtype
    self._records = []

  def _generateRecordElement(self, attrs, metadata, content):
    """Generates a <record> element for a record.

    Args:
      attrs: The attributes for the record tag, as a dictionary that maps
        attribute names (strings) to their values (strings). Example:
        {'url': 'http://example.com/index.html',
         'displayurl': 'http://example.com/index.html',
         'action': 'add',
         'mimetype': 'text/html'}
        Note that the 'url' and 'mimetype' attributes are required by the GSA.
      metadata: Metadata tags to add to the feed (can be None if not needed).
        Should be a dictionary that maps strings to strings.
      content: Adds a content tag for content feeds. Should be a string, or None
       if this is not to be a content feed.

    Returns:
      The constructed record XML element (string).
    """
    # generate the record attrib list string
    attrlist = []
    for key, value in attrs.iteritems():
      attrlist.append('%s="%s"' % (key, value))
    attrstr = ' '.join(attrlist)
    # generate metadata tags
    metastr = ''
    if metadata:
      metalist = []
      for key, value in metadata.iteritems():
        metalist.append('<meta name="%s" content="%s"/>' % (key, value))
      metastr = '<metadata>%s</metadata>' % ''.join(metalist)
    # generate content tag
    contentstr = ''
    if content:
      contentstr = ('<content encoding="base64binary">'
                    '%s'
                    '</content>') % base64.encodestring(content)
    return '<record %s>%s%s</record>' % (attrstr, metastr, contentstr)

  def addRecord(self, **kwargs):
    """Adds a record to the feed.

    Args:
      url, displayurl, mimetype, etc.: Attributes for the record tag, to be
        provided as needed (should be strings). The GSA requires the url and
        metadata arguments to be provided. See
        http://code.google.com/apis/searchappliance/
            documentation/64/feedsguide.html#defining_the_xml
        for a full list of record tag attributes.
      metadata: Optional. Metadata tags to add to the feed, as a dictionary
        that maps strings to strings.
      content: Optional; required if the feed is a content feed. Adds a content
        tag to the record. Should be a string.

    Example:
      addRecord(url='http://example.com/index.html', action='add',
                mimetype='text/html', content='<html>...</html>')
      This adds a record to a content feed, with the record element attributes
      'url', 'action', and 'mimetype'. A <content> element is also added.
      The following XML will be produced by toXML for this record:
      <record url='http://example.com/index.html' action='add'
              mimetype='text/html'>
        <content encoding="base64binary">
          ... the base64-encoded version of the content ...
        </content>
      </record>
    """
    content = None
    if 'content' in kwargs:
      content = kwargs['content']
      del kwargs['content']
    metadata = None
    if 'metadata' in kwargs:
      metadata = kwargs['metdata']
      del kwargs['metdata']
    self._records.append((kwargs, metadata, content))

  def toXML(self):
    """Returns the XML version of all the records added.
    Like this: <record>...</record><record>...</record>...

    Returns:
      A string of XML.
    """
    return ''.join(self._generateRecordElement(rec[0], rec[1], rec[2])
                   for rec in self._records)

  def getType(self):
    """Returns the connector type.

    Returns:
      The connector type (string).
    """
    return self._type

  def clear(self):
    """Clears the list of records."""
    self._records = []