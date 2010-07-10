#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.
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
# This code is not supported by Google
#

"""ConnectorManager+connector Lite for the Google Search Appliance (GSA)

This script runs a lightweight GSA ConnectorManager on port 38080.

The ConnectorManager will handle the protocol communication with the GSA and
provide an interface for connnector implementations.

Two connectors are provided separately: an example connector that consists of
just boilerplate code (suitable for use as a base for new connector
implementations), and a sitemap connector which just downloads a plain (not
compressed) sitemap in xml format and proceeds to send the URLs in it as
metadata+url feed to the GSA.  It takes the URL for the sitemap and a delay
(in seconds) after which it should download and process the xml file.  The
sitemap connector is provided to understand how to potentially trigger the
'traversal' of a content system and how to feed data to the GSA.

Sample Setup
1. Install Python, cherrypy.
2. Start the connector, listing the connector classes to be loaded, separated by
commas: python ConnectorManager.py --debug
--connectors=sitemap_connector.SitemapConnector,
             example_connector.ExampleConnector
    (assuming you're running this on host: myconnector.mydomain.com)
3. On the GSA Admin console, create a new connector-manager and set the host
   to http://myconnector.mydomain.com:38080   (note, no '/' at the end)
4. Create a connector instance
5. Assuming a sitemap connector was created, configure the connector instance
   to use sample URL:  http://www.domain.com/sitemap.xml
   Delay: 60  (for example)
6. On the GSA Admin Console, under Crawl+Follow, enter
   http://www.domain.com/*
6. Every 60 seconds the connector will download the sitemap and feed it into the
   GSA

This script can be used as a template to write arbitrary simple connectors.

The connector manger does not manage individual connectors' checkpointing or
traversal rates--it's entirely up to connector implementations to handle
how often and how to manage the traversal state. However, the connector base
class does provide a data storage facility with getData/setData that keeps data
in the configuration file. See the documentation for Connector for more
information.

Configured connector instances are stored in config.xml (created on initial
startup) which includes the entire base64 encoded XML configuration form for
that connector, a base64 encoded version of pickled storage data, and other
connector settings.

NOTE:  The protocol between the GSA and ConnectorManager is subject to change
       but is verified to work on GSA 6.2

usage:
  ./ConnectorManager.py
    --debug           Show debug logs
    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected
    --port=           Set the listener port of the cherrypy webserver
                      (default 38080)
    --connectors=     The connectors to load. Must be provided in
                      <package>.<class> form

    The connector will send a feed back to the GSA by creating a postfeeder
      #feed_type = 'incremental'
      feeder = connectormanager.Postfeed(feed_type, debug_flag)
      #then add some metadata or incremental data XML records
      feeder.addrecord(strrecord)
      #finally feed in the data with the GSA's IP address and feed name was
      #sent in with the  __init__ constructor of the connector
      feeder.post_multipart(gsa, name)

    When a connector is added or modified from the GSAs admin console, the
    ConnectorManager will call stopConnector() then startConnector().  The
    specific connector implementation must make sure to properly stop/start
    traversal on the content system.

  --postfeed:
       Code taken from our push_feeder.py class
       code.google.com/apis/searchappliance/documentation/62/feedsguide.html
       Which sends the feed to the GSA

http://www.cherrypy.org/
"""

__author__ = "salrashid123@gmail.com for Google on 2010.1.21"

import base64
import cPickle
import datetime
import getopt
import os
import sys
import urllib2
import xml.dom.minidom
import xml.sax.saxutils
import cherrypy


class ConnectorManager(object):
  """The main class which is mounted as the root context of cherrypy
  (i.e, the '/' context when you hit http://ConnectorManager:38080/)
  this class accepts all the input methods the GSA sends to it and
  responds back with the correct protocol:
  some sample methods:   /setManagerConfig  or /getConnectorList ,etc)
  the input XML thats passed to the method is shown in the comment line
  in the method declaration
  The ConnectorManager creates instances of the actual connector (class
  connectorimpl) and keeps a list of the instances it hosts

  To start the connector, simply instantiate a connector manager class
  and pass in a dictionary mapping connector type strings to their
  corresponding connector classes.

  ConnectorManager(connector_classes, debug_flag, use_ssl, port)
  """

  gsa = ''
  configfile = 'config.xml'
  connector_list = []

  def __init__(self, connector_classes, debug_flag, use_ssl, port):
    self.debug_flag = debug_flag
    cherrypy.config.update({'global': {'server.socket_host': '0.0.0.0'}})
    self.connector_classes = connector_classes
    if use_ssl:
      cherrypy.config.update({'global': {
          'server.ssl_certificate': 'ssl.crt',
          'server.ssl_private_key': 'ssl.key'}})
    if debug_flag:
      cherrypy.config.update({'global': {'log.screen': True}})
    else:
      cherrypy.config.update({'global': {'log.screen': False}})
    cherrypy.config.update({'global': {'server.socket_port': port}})
    self.loadPropFile()
    for c in self.connector_list:
      c.startConnector()
    cherrypy.quickstart(self, script_name='/')
    self.savePropFile()

  def index(self):
    conn_info = ''
    for c in self.connector_list:
      escaped_config = xml.sax.saxutils.escape(c.getConfig())
      conn_info += ('Name: %s<br />Config: %s<br />'
                    'Load: %s<br />Retry Delay: %s<br />'
                    'Intervals: %s<br />') % (
          c.getName(), escaped_config, c.getLoad(), c.getRetryDelay(),
          c.getTimeIntervals())
    return ('<html><head><title>ConnectorManager</title></head>'
            '<body><p>Index page for python ConnectorManager:<br/>'
            'Registered ConnectorTypes: %s</p><p>GSA: %s</p>'
            '<p>Connectors: <br/>%s</p>'
            '</body></html>') % (self.connector_classes.keys(),
                                 self.gsa, conn_info)
  index.exposed = True

  def setManagerConfig(self):
    #<ManagerConfig>
    #<FeederGate host="172.25.17.23" port="19900"/>
    #</ManagerConfig>
    data = cherrypy.request.body.read()
    self.log('setManagerConfig  %s' % data)
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ManagerConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'FeederGate':
          self.gsa = nodes.attributes["host"].value
    self.log(('Registered GSA at %s') %(self.gsa))
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setManagerConfig.exposed = True

  def testConnectivity(self):
  #no input data
    data = cherrypy.request.body.read()
    if self.gsa == '':
      self.gsa = cherrypy.request.remote.ip
    self.log('testConnectivity  %s' %data)
    return ('<CmResponse>'
            '<Info>Google Enterprise Connector Manager 2.0.0 (build 2123  '
            'June 12 2009); Sun Microsystems Inc. '
            'OpenJDK 64-Bit Server VM 1.6.0_0; Linux '
            '2.6.24-gg804003-generic (amd64)</Info>'
            '<StatusId>0</StatusId>'
            '</CmResponse>')
  testConnectivity.exposed = True

  def getConnectorList(self, ConnectorType=None):
    self.log(('getConnectorList '))
    connector_types = ''
    for connector_type in self.connector_classes:
      connector_types += '<ConnectorType>%s</ConnectorType>' % connector_type

    return ('<CmResponse>'
            '<Info>Google Enterprise Connector Manager 2.0.0 '
            '(build 2123  June 12 2009); Sun Microsystems Inc. '
            'OpenJDK 64-Bit Server VM 1.6.0_0; '
            'Linux 2.6.24-gg804003-generic (amd64)</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorTypes>%s</ConnectorTypes>'
            '</CmResponse>') % connector_types
  getConnectorList.exposed = True

  def getConfigForm(self, Lang=None, ConnectorType=None):
    #Lang=en&ConnectorType=sitemap-connector
    self.log('getConfigForm ConnectorType=%s' % ConnectorType)
    return self.connector_classes[ConnectorType].getConfigForm()
  getConfigForm.exposed = True

  def setConnectorConfig(self):
    #<ConnectorConfig>
    #<ConnectorName>connector1</ConnectorName>
    #<ConnectorType>sitemap-connector</ConnectorType>
    #<Lang>en</Lang>
    #<Update>false</Update>
    #<Param  name="surl" value="surlvalue"/>
    #<Param  name="interval" value="interval value"/>
    #</ConnectorConfig>
    config = cherrypy.request.body.read()
    self.log('setConnectorConfig  %s' % config)
    ConnectorName = ''
    ConnectorType = ''
    xmldoc = xml.dom.minidom.parseString(config)
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'ConnectorType':
          ConnectorType = nodes.childNodes[0].nodeValue
    #first check to see if a connector with this name exists
    #if it does, keep its old state (except the config)
    exists = False
    c = self.getConnector(ConnectorName)
    if c is not None:
      exists = True
      data = c.getData()
      load = c.getLoad()
      retry_delay = c.getRetryDelay()
      intervals = c.getTimeIntervals()
      c.stopConnector()
      self.removeConnector(ConnectorName)
    #create the connector given the string form of the connectorname
    connector_class = self.connector_classes[ConnectorType]
    c = connector_class(ConnectorName, self.gsa, self.debug_flag)
    c.setConfig(config)
    if exists:
      c.setData(data)
      c.setLoad(load)
      c.setRetryDelay(retry_delay)
      c.setTimeIntervals(intervals)
    self.setConnector(c)
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setConnectorConfig.exposed = True

  def setSchedule(self):
    #<ConnectorSchedules>
    #<ConnectorName>connector1</ConnectorName>
    #<load>200</load>
    #<TimeIntervals>0-0</TimeIntervals>
    #</ConnectorSchedules>
    data = cherrypy.request.body.read()
    self.log('setSchedule %s' % data)
    ConnectorName = ''
    load = '200'
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ConnectorSchedules')
    RetryDelayMillis = '' # doesn't seem to appear when a connector is created
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'load':
          load = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'RetryDelayMillis':
          RetryDelayMillis = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'TimeIntervals':
          TimeIntervals = nodes.childNodes[0].nodeValue
    c = self.getConnector(ConnectorName)
    c.stopConnector()
    c.setLoad(load)
    c.setRetryDelay(RetryDelayMillis)
    c.setTimeIntervals(TimeIntervals)
    self.setConnector(c)
    c.startConnector()
    self.savePropFile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setSchedule.exposed = True

  #Returns a list of all the connector instances running
  def getConnectorInstanceList(self, Lang=None):
    self.log('getConnectorInstanceList')
    instance_list = ''
    if not self.connector_list:
      return ('<CmResponse>'
              '<Info>Google Enterprise Connector Manager 2.0.0 (build 2123  '
              'June 12 2009); Sun Microsystems Inc. OpenJDK 64-Bit '
              'Server VM 1.6.0_0; Linux 2.6.24-gg804003-generic (amd64)</Info>'
              '<StatusId>5215</StatusId>'
              '</CmResponse>')
    for c in self.connector_list:
      instance_list += ('<ConnectorInstance>'
                        '<ConnectorName>%s</ConnectorName>'
                        '<ConnectorType>%s</ConnectorType>'
                        '<Status>%s</Status>'
                        '<ConnectorSchedules version="3">%s:%s:%s:%s'
                        '</ConnectorSchedules>'
                        '<ConnectorSchedule version="1">%s:%s:%s'
                        '</ConnectorSchedule>'
                        '</ConnectorInstance>') %(c.getName(),
                                                  c.getConnectorType(),
                                                  c.getStatus(), c.getName(),
                                                  c.getLoad(),
                                                  c.getRetryDelay(),
                                                  c.getTimeIntervals(),
                                                  c.getName(), c.getLoad(),
                                                  c.getTimeIntervals())

    return ('<CmResponse>'
            '<Info>Google Enterprise Connector Manager 2.0.0 '
            '(build 2123  June 12 2009); Sun Microsystems Inc. '
            'OpenJDK 64-Bit Server VM 1.6.0_0; Linux 2.6.24-gg804003-generic'
            ' (amd64)</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorInstances>%s</ConnectorInstances>'
            '</CmResponse>') % instance_list
  getConnectorInstanceList.exposed = True

  def getConnectorStatus(self, ConnectorName=None):
    # ConnectorName=sitemap-connector
    self.log('getConnectorStatus %s' % ConnectorName)
    c = self.getConnector(ConnectorName)
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConnectorStatus>'
            '<ConnectorName>%s</ConnectorName>'
            '<ConnectorType>%s</ConnectorType>'
            '<Status>%s</Status>'
            '<ConnectorSchedules version="3">%s:%s:%s:%s</ConnectorSchedules>'
            '</ConnectorStatus>'
            '</CmResponse>') % (
                c.getName(), c.getConnectorType(), c.getStatus(),
                c.getName(), c.getLoad(), c.getRetryDelay(),
                c.getTimeIntervals())
  getConnectorStatus.exposed = True

  def removeConnector(self, ConnectorName=None):
    # ConnectorName=connector1
    self.log('removeConnector %s' % ConnectorName)
    c = self.getConnector(ConnectorName)
    self.connector_list.remove(c)
    c.stopConnector()
    c = None
    self.savePropFile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  removeConnector.exposed = True

  def getConnectorConfigToEdit(self, ConnectorName=None, Lang=None):
    self.log('getConnectorConfigToEdit %s' % ConnectorName)
    c = self.getConnector(ConnectorName)
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConfigureResponse>'
            '<FormSnippet>%s</FormSnippet>'
            '</ConfigureResponse>'
            '</CmResponse>') % c.getForm()
  getConnectorConfigToEdit.exposed = True

  #not implemented yet but (wtf?)
  def restartConnectorTraversal(self, ConnectorName=None, Lang=None):
    self.log('restartConnectorTraversal %s' % ConnectorName)
    c = self.getConnector(ConnectorName)
    c.restartConnectorTraversal()
    return '<CmResponse><StatusId>%s</StatusId></CmResponse>' % c.getStatus()
  restartConnectorTraversal.exposed = True

  def getConnector(self, connector_name):
    for con in self.connector_list:
      if con.name == connector_name:
        return con
    return None

  def setConnector(self, cdata):
    found = False
    for index, con in enumerate(self.connector_list):
      if con.name == cdata.name:
        found = True
        self.connector_list[index] = cdata
    if found == False:
      self.connector_list.append(cdata)

  def savePropFile(self):
    self.log('Saving Prop file ')
    str_out = '<connectormanager><connectors><gsa>%s</gsa>\n' % self.gsa
    for c in self.connector_list:
      config = base64.encodestring(c.getConfig())
      data = base64.encodestring(cPickle.dumps(c.getData(), 2))
      str_out += ('<connector><name>%s</name><type>%s</type><load>%s</load>'
                  '<retry_delay>%s</retry_delay><intervals>%s</intervals>'
                  '<config>%s</config><data>%s</data></connector>\n') % (
                      c.getName(), c.getConnectorType(), c.getLoad(),
                      c.getRetryDelay(), c.getTimeIntervals(),
                      config, data)
    str_out += '</connectors></connectormanager>\n'
    try:
      out_file = open(self.configfile, 'w')
      out_file.write(str_out)
      out_file.close()
    except IOError:
      print 'Error Saving Config File'

  def loadPropFile(self):
    self.log('Loading Prop File')
    try:
      if not os.path.exists(self.configfile):
        in_file = open(self.configfile, 'w')
        in_file.close()
        return
      in_file = open(self.configfile, 'r')
      text = in_file.read()
      in_file.close()
      xmldoc = xml.dom.minidom.parseString(text)
      m_node = xmldoc.getElementsByTagName('gsa')
      try:
        for rnode in m_node:
          cgsa = rnode.childNodes[0].nodeValue
        if self.gsa == '':
          self.gsa = cgsa
      except IndexError:
        self.log(('GSA Address not found in config file..'
                 'waiting for testConnectivity()'))
      m_node = xmldoc.getElementsByTagName('connector')
      for rnode in m_node:
        rchild = rnode.childNodes
        for nodes in rchild:
          if nodes.nodeName == 'name':
            name = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'type':
            type = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'config':
            config = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'data':
            data = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'load':
            load = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'retry_delay':
            retry_delay = nodes.childNodes[0].nodeValue
          if nodes.nodeName == 'intervals':
            intervals = nodes.childNodes[0].nodeValue
        if type not in self.connector_classes:
          print 'Connector type %s not loaded' % type
          sys.exit(1)
        config = base64.decodestring(config)
        data = cPickle.loads(base64.decodestring(data))
        connector_class = self.connector_classes[type]
        c = connector_class(name, self.gsa, self.debug_flag)
        c.setConfig(config)
        c.setData(data)
        c.setLoad(load)
        c.setRetryDelay(retry_delay)
        c.setTimeIntervals(intervals)
        self.setConnector(c)
    except IOError:
      print 'Error Opening Config File'

  def authenticate(self):
    #<AuthnRequest>
    #<Credentials>
    #<Domain>esodomain</Domain>
    #<Username>user1</Username>
    #<Password>xxxx</Password>
    #</Credentials>
    #</AuthnRequest>
    #
    #do something to authenticate the user here
    #extract the username and return success for all connectors
    # I know this form works as a response but since no connector name
    # was sent in with the authnrequest context, we should check all connectors
    # and aggregate the responses (i'm guessing)
    #
    # I verified the following works for a single connector
    # <CmResponse>
    # <AuthnResponse>
    # <Success ConnectorName="connector1">
    #  <Identity>user1</Identity>
    # </Success>
    # </AuthnResponse>
    # </CmResponse>
    #
    # and for failure
    # <CmResponse>
    # <AuthnResponse>
    # <Failure ConnectorName="connector1"/>
    # </AuthnResponse>
    # </CmResponse>

    data = cherrypy.request.body.read()
    self.log(('authenticate '))
    domain = ''
    username = ''
    password = ''
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('Credentials')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'Domain':
          if len(nodes.childNodes) > 0:
            domain = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'Username':
          username = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'Password':
          password = nodes.childNodes[0].nodeValue
    str_response = ('<CmResponse><AuthnResponse>')
    for con in self.connector_list:
      identity = con.authenticate(domain, username, password)
      if identity is not None:
        str_response += ('<Success ConnectorName="%s">'
                         '<Identity>%s</Identity>'
                         '</Success>') %(con.name, identity)
      else:
        str_response += ('<Failure ConnectorName="%s"/>') %(con.name)
      str_response += '</AuthnResponse></CmResponse>'
    return str_response
  authenticate.exposed = True

  def authorization(self):
    #<AuthorizationQuery>
    #<ConnectorQuery>
    #<Identity domain="esodomain" password="dsjflaskf" source="connector">user1
    #</Identity>
    #<Resource>googleconnector://connector1.localhost/doc?docid=123</Resource>
    #<Resource>googleconnector://connector1.localhost/doc?docid=456</Resource>
    #<Resource>googleconnector://connector1.localhost/doc?docid=789</Resource>
    #</ConnectorQuery>
    #</AuthorizationQuery>

    #I don't know if Indeterminate is a valid response or not....
    #<CmResponse>
    #<AuthorizationResponse>
    #<Answer>
    #<Resource>googleconnector://connector1.localhost/doc?docid=123</Resource>
    #<Decision>Permit</Decision>
    #</Answer>
    #<Answer>
    #<Resource>googleconnector://connector1.localhost/doc?docid=456</Resource>
    #<Decision>Deny</Decision>
    #</Answer>
    #<Answer>
    #<Resource>googleconnector://connector1.localhost/doc?docid=789</Resource>
    #<Decision>Indeterminate</Decision>
    #</Answer>
    #</AuthorizationResponse>
    #<StatusId>0</StatusId>
    #</CmResponse>

    data = cherrypy.request.body.read()
    self.log(('authorize '))
    str_response = ('<CmResponse><AuthorizationResponse>')
    domain = ''
    identity = ''
    password = ''
    source = ''
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ConnectorQuery')
    resource_list = []
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'Identity':
          identity = nodes.childNodes[0].nodeValue
          try:
            domain = nodes.attributes["domain"].value
          except KeyError:
            domain = ''
          source = nodes.attributes["source"].value
          password = nodes.attributes["password"].value
        if nodes.nodeName == 'Resource':
          resource = nodes.childNodes[0].nodeValue
          resource_list.append(resource)
    for res in resource_list:
      for con in self.connector_list:
        az_decision = con.authorize(identity, domain, res)
        str_response += ('<Answer><Resource>%s</Resource>'
                         '<Decision>%s</Decision></Answer>') % (
                             res, az_decision)
    str_response += ('</AuthorizationResponse>'
                     '<StatusId>0</StatusId></CmResponse>')
    return str_response
  authorization.exposed = True

  def log(self, deb_string):
    if self.debug_flag:
      now = datetime.datetime.now()
      print "%s  %s" % (now, deb_string)


class Postfeed(object):
  def __init__(self, feed_type, debug_flag):
    self.debug_flag = debug_flag
    self.feed_type = feed_type
    self.records = ''

  def log(self, deb_string):
    if self.debug_flag:
      now = datetime.datetime.now()
      print "%s  %s" % (now, deb_string)

  def addrecord(self, srecord):
    self.log('Adding %s record: %s ' %(self.feed_type, srecord))
    self.records += srecord

  def post_multipart(self, gsa, datasource):
    self.log('Posting Aggregated Feed to : %s' %datasource)
    xmldata = ('<?xml version=\'1.0\' encoding=\'UTF-8\'?>'
               '<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" '
               '"gsafeed.dtd">'
               '<gsafeed>'
               '<header>'
               '<datasource>%s</datasource>'
               '<feedtype>%s</feedtype>'
               '</header>'
               '<group>%s</group>'
               '</gsafeed>') % (datasource, self.feed_type, self.records)

    content_type, body = self.encode_multipart_formdata(datasource, xmldata)
    headers = {}
    headers['Content-type'] = content_type
    headers['Content-length'] = str(len(body))
    u = 'http://%s:19900/xmlfeed' % gsa
    request_url = urllib2.Request(u, body, headers)
    if self.debug_flag:
      self.log('POSTING Feed to GSA %s ' %gsa)
      self.log(request_url.get_method())
      self.log(request_url.get_full_url())
      self.log(request_url.headers)
      self.log(request_url.get_data())
    status = urllib2.urlopen(request_url).read()
    self.records = ''
    self.log("Response status from GSA [%s]" %status)
    return status

  def encode_multipart_formdata(self, datasource, xmldata):
    BOUNDARY = '<<'
    CRLF = '\r\n'
    L = []
    L.append('--' + BOUNDARY)
    L.append('Content-Disposition: form-data; name="datasource"')
    L.append('Content-Type: text/plain')
    L.append('')
    L.append(datasource)

    L.append('--' + BOUNDARY)
    L.append('Content-Disposition: form-data; name="feedtype"')
    L.append('Content-Type: text/plain')
    L.append('')
    L.append(self.feed_type)

    L.append('--' + BOUNDARY)
    L.append('Content-Disposition: form-data; name="data"')
    L.append('Content-Type: text/xml')
    L.append('')
    L.append(xmldata)
    L.append('')
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body


class Connector(object):
  """A connector interface to be implemented by connector classes"""

  def __init__(self, name, gsa, debug_flag=True):
    """Creates a connector.

    Args:
      name: The instance name.
      gsa: The GSA's IP address.
      debug_flag: A debug flag for logging.
    """
    self.name = name
    self.config = ''
    self.data = None
    self.gsa = gsa
    self.load = '200'
    self.retry_delay = '300000'
    self.time_intervals = '0-0'
    self.debug_flag = debug_flag

  @staticmethod
  def getConfigForm():
    """Returns the empty configuration form.

    The form should be encapsulated inside a
    <CmResponse><ConfigureResponse><FormSnippet> CDATA tag.
    """
    raise NotImplementedError("getConfigForm() not implemented")

  def getForm(self):
    """Returns a filled configuration form.

    (The form should not be encapsulated in anything, unlike getConfigForm)
    """
    raise NotImplementedError("getForm() not implemented")

  def getName(self):
    """Returns the instance name."""
    return self.name

  @staticmethod
  def getConnectorType():
    """Returns the connector type string.

    This is required. This is used by the connector manager to identify
    individual connector types."""
    raise NotImplementedError("getConnectorType() not implemented")

  def getConfig(self):
    """Returns the raw XML configuration data."""
    return self.config

  def setConfig(self, config):
    """Sets the connector configuration.

    Args:
      config: The raw XML configuration.
    """
    self.config = config

  def getData(self):
    """Returns stored data."""
    return self.data

  def setData(self, data):
    """Sets the data storage object.

    This data is stored via pickle and base64 along with the connector's other
    configuration data. The connector can use this to store information that
    persists through connector manager restarts.
    (The data is only written to disk when the connector manager writes its
    configuration file to disk.)

    Args:
      data: The object to be stored.
    """
    self.data = data

  def getLoad(self):
    """Returns the current load setting (docs to traverse per min).

    This parameter is initally provided inside config raw XML the connector
    A connector does not have to do anything with this parameter.
    """
    return self.load

  def setLoad(self, load):
    """Sets the load setting.

    Args:
      load: The load setting (docs per minute).
    """
    self.load = load

  def getRetryDelay(self):
    """Returns the retry delay."""
    return self.retry_delay

  def setRetryDelay(self, retry_delay):
    """Sets the retry delay.

    Args:
      retry_delay: The retry delay.
    """
    self.retry_delay = retry_delay

  def getTimeIntervals(self):
    """Returns the time intervals over which to traverse.

    The time intervals are formatted as a single string, with individual
    intervals delimited by colons.
    This parameter is initally provided by setSchedule in the connector
    manager. It's also set and explictly by the connector. A connector does
    not have to do anything with this parameter (you can ignore it if needed).
    """
    return self.time_intervals

  def setTimeIntervals(self, intervals):
    """Sets the time intervals.

    Args:
      intervals: The time intervals, delimited by colons.
    """
    self.time_intervals = intervals

  def getStatus(self):
    """Returns the status of the connector (0 --> OK)."""
    raise NotImplementedError("getStatus() not implemented")

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
    """
    return username

  def authorize(self, identity, domain, resource):
    """Authorizes a user.

    See comment for authenticate()
    """
    return 'Permit'

  def getConfigParam(self, param_name):
    """Returns a specific parameter of the configuration data set by setConfig.

    Args:
      param_name: The parameter whose value to return.

    Returns:
      The value of the parameter, or None if the parameter is not present in
      the configuration.
    """
    xmldoc = xml.dom.minidom.parseString(self.getConfig())
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'Param':
          nodename = nodes.attributes["name"].value
          if nodename == param_name:
            return nodes.attributes["value"].value
    return None

  def log(self, deb_string):
    if self.debug_flag:
      now = datetime.datetime.now()
      print "%s  %s" % (now, deb_string)

if __name__ == '__main__':
  port = 38080
  use_ssl = False
  debug_flag = False
  connectors = ''

  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["debug", "use_ssl",
                                                    "port=", "connectors="])
  except getopt.GetoptError:
    print ('Invalid arguments: valid args --debug  --use_ssl --port=<port>'
           '--connectors=<connectors>')
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--debug":
      debug_flag = True
    if opt == "--use_ssl":
      use_ssl = True
    if opt == "--port":
      port = int(arg)
    if opt == "--connectors":
      connectors = arg

  if not connectors:
    print 'No connectors to load'
    sys.exit(1)

  connector_classes = {}
  for modulename, _, classname in (c.rpartition('.') for c in
                                   connectors.split(',')):
    module = __import__(modulename)
    cls = getattr(module, classname)
    connector_classes[cls.getConnectorType()] = cls

  ConnectorManager(connector_classes, debug_flag, use_ssl, port)
