#!/usr/bin/python
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
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

Sample Setup
1. Install Python, cherrypy3.
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

The connector manger does not manage individual connectors' checkpointing or
traversal rates--it's entirely up to connector implementations to handle
how often and how to manage the traversal state. However, the connector base
class does provide a data storage facility with getData/setData that keeps data
in the configuration file. See the documentation for Connector for more
information.

Configured connector instances are stored in config.xml (created on initial
startup) which includes the entire base64 encoded XML configuration and schedule
for that connector, and a base64 encoded version of pickled storage data.

NOTE:  The protocol between the GSA and ConnectorManager is subject to change
       but is verified to work on GSA 6.2
       
       
NOTE:  You may need to change the default encoding of python:
edit edit /usr/lib/pythonX.X/site.py
change
  encoding = "ascii"
to
  encoding = "UTF-8"


usage:
  ./connectormanager.py
    --debug           Show debug logs
    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected
    --port=           Set the listener port of the cherrypy webserver
                      (default 38080)
    --connectors=     The connectors to load. Must be provided in
                      <package>.<class> form

    The connector sends feeds back to the GSA using the pushToGSA method in the
    connector class. The pushToGSA method, however, requires that its 'data'
    parameter be an XML record description, which my be quite complex to
    construct. Thus the sendMultiContentFeed and sendContentFeed methods are
    supplied to simplify sending content feeds to the GSA.
    (Information about the feed XML format can be found at
    http://code.google.com/apis/searchappliance/
        documentation/62/feedsguide.html).

    When a connector is added or modified from the GSA's admin console, the
    ConnectorManager will call stopConnector() then startConnector().  The
    specific connector implementation must make sure to properly stop/start
    traversal on the content system.

    It's common for a connector to have a traversal method that runs
    periodically with a specific time interval between runs. The TimedConnector
    abstract connector is provided for this purpose. To use this, simply extend
    from this class and override the run() method. See the TimedConnector
    documentation for more details.

    Three example connector implementations are provided:
      ExampleConnector: Does absolutely nothing. This serves as boilerplate
        code, useful for writing new connectors.
      URLConnector: Extends TimedConnector. This connector fetches the contents
        of a URL and sends it to the GSA as a content feed. The URL and a delay
        are specified in its configuration form.
      SitemapConnector: Extends TimedConnector. Given a delay and a sitemap URL
        from its configuration form, this connector will fetch the sitemap XML
        file and send the URLs specified in the sitemap file to the GSA.

http://www.cherrypy.org/
"""

__author__ = "salrashid123@gmail.com for Google on 2010.1.21"

import base64
import cPickle
import getopt
import logging
import os
import platform
import sys
import xml.dom.minidom
import xml.sax.saxutils
import cherrypy
import connector


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
  and pass in a dictionary that maps connector type strings to their
  corresponding connector classes.

  ConnectorManager(connector_classes, debug_flag, use_ssl, port)
  """

  gsa = ''
  configfile = 'config.xml'
  connector_list = []
  loggers = {}

  class ConnectorPool(cherrypy.process.plugins.SimplePlugin):
    """CherryPy engine plugin for starting/stopping connectors."""

    def __init__(self, bus, connector_manager):
      cherrypy.process.plugins.SimplePlugin.__init__(self, bus)
      self.connector_manager = connector_manager

    def start(self):
      self.connector_manager.startConnectors()

    def stop(self):
      self.connector_manager.stopConnectors()

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
    connector_pool = self.ConnectorPool(cherrypy.engine, self)
    connector_pool.subscribe()
    cherrypy.quickstart(self, script_name='/')

  def startConnectors(self):
    self._loadPropFile()
    for c in self.connector_list:
      self.logger().info('Starting connector: ' + c.getName())
      c.startConnector()

  def stopConnectors(self):
    for c in self.connector_list:
      self.logger().info('Stopping connector: ' + c.getName())
      c.stopConnector()
    self._savePropFile()

  def index(self):
    conn_info = ''
    for c in self.connector_list:
      escaped_config = xml.sax.saxutils.escape(c.getConfig())
      escaped_schedule = xml.sax.saxutils.escape(c.getSchedule())
      conn_info += ('Name: %s<br />Config: %s<br />'
                    'Schedule: %s<br />') % (
          c.getName(), escaped_config, escaped_schedule)
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
    self.logger().debug('setManagerConfig  %s' % data)
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ManagerConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'FeederGate':
          self.gsa = nodes.attributes["host"].value
    self.logger().debug(('Registered GSA at %s') %(self.gsa))
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setManagerConfig.exposed = True

  def testConnectivity(self):
  #no input data
    data = cherrypy.request.body.read()
    if self.gsa == '':
      self.gsa = cherrypy.request.remote.ip
    self.logger().debug('testConnectivity  %s' %data)
    return ('<CmResponse><Info>%s</Info><StatusCode>0</StatusCode>'
            '<StatusId>0</StatusId></CmResponse>') % self._getPlatformInfo()
  testConnectivity.exposed = True

  def getConnectorList(self, ConnectorType=None):
    self.logger().debug(('getConnectorList '))
    connector_types = ''
    for connector_type in self.connector_classes:
      connector_types += '<ConnectorType version="1.0.6a ${TODAY}">%s</ConnectorType>' % connector_type

    return ('<CmResponse>'
            '<Info>%s</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorTypes>%s</ConnectorTypes>'
            '</CmResponse>') % (self._getPlatformInfo(), connector_types)
  getConnectorList.exposed = True

  def getConfigForm(self, Lang=None, ConnectorType=None):
    #Lang=en&ConnectorType=sitemap-connector
    self.logger().debug('getConfigForm ConnectorType=%s' % ConnectorType)
    return self.connector_classes[ConnectorType].getConfigForm()
  getConfigForm.exposed = True

  def getConnectorLogLevel(self):
    self.logger().debug('getConnectorLogLevel')
    return ('<CmResponse><StatusId>0</StatusId><Level>OFF</Level><Info>Connector Logging level is OFF</Info></CmResponse>')
  getConnectorLogLevel.exposed = True

  def getFeedLogLevel(self):
    return ('<CmResponse><StatusId>0</StatusId><Level>OFF</Level><Info>Feed Logging level is OFF</Info></CmResponse>')
  getFeedLogLevel.exposed = True

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
    self.logger().debug('setConnectorConfig  %s' % config)
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
    # if the connector already exists, stop it, set its config, and start it
    # otherwise, make a new one
    c = self._getConnector(ConnectorName)
    if c:
      c.stopConnector()
      c.setConfig(config)
      c.init()
      c.startConnector()
    else:
      connector_class = self.connector_classes[ConnectorType]
      c = connector_class(self, ConnectorName, config, '', None)
      self._setConnector(c)
    self._savePropFile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setConnectorConfig.exposed = True

  def setSchedule(self):
    #<ConnectorSchedules>
    #<ConnectorName>connector1</ConnectorName>
    #<load>200</load>
    #<TimeIntervals>0-0</TimeIntervals>
    #</ConnectorSchedules>
    data = cherrypy.request.body.read()
    self.logger().debug('setSchedule %s' % data)
    ConnectorName = ''
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ConnectorSchedules')
    for rnode in m_node:
      for node in rnode.childNodes:
        if node.nodeName == 'ConnectorName':
          ConnectorName = node.childNodes[0].nodeValue
          break
    c = self._getConnector(ConnectorName)
    c.stopConnector()
    c.setSchedule(data)
    c.init()
    c.startConnector()
    self._savePropFile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setSchedule.exposed = True

  #Returns a list of all the connector instances running
  def getConnectorInstanceList(self, Lang=None):
    self.logger().debug('getConnectorInstanceList')
    instance_list = ''
    if not self.connector_list:
      return ('<CmResponse>'
              '<Info>%s</Info>'
              '<StatusId>5215</StatusId>'
              '</CmResponse>') % self._getPlatformInfo()
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
                                                  c.CONNECTOR_TYPE,
                                                  c.getStatus(), c.getName(),
                                                  c.getLoad(),
                                                  c.getRetryDelay(),
                                                  c.getTimeIntervals(),
                                                  c.getName(), c.getLoad(),
                                                  c.getTimeIntervals())

    return ('<CmResponse>'
            '<Info>%s</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorInstances>%s</ConnectorInstances>'
            '</CmResponse>') % (self._getPlatformInfo(), instance_list)
  getConnectorInstanceList.exposed = True

  def getConnectorStatus(self, ConnectorName=None):
    # ConnectorName=sitemap-connector
    self.logger().debug('getConnectorStatus %s' % ConnectorName)
    c = self._getConnector(ConnectorName)
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConnectorStatus>'
            '<ConnectorName>%s</ConnectorName>'
            '<ConnectorType>%s</ConnectorType>'
            '<Status>%s</Status>'
            '<ConnectorSchedules version="3">%s:%s:%s:%s</ConnectorSchedules>'
            '</ConnectorStatus>'
            '</CmResponse>') % (
                c.getName(), c.CONNECTOR_TYPE, c.getStatus(),
                c.getName(), c.getLoad(), c.getRetryDelay(),
                c.getTimeIntervals())
  getConnectorStatus.exposed = True

  def removeConnector(self, ConnectorName=None):
    # ConnectorName=connector1
    self.logger().debug('removeConnector %s' % ConnectorName)
    c = self._getConnector(ConnectorName)
    self.connector_list.remove(c)
    c.stopConnector()
    c = None
    self._savePropFile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  removeConnector.exposed = True

  def getConnectorConfigToEdit(self, ConnectorName=None, Lang=None):
    self.logger().debug('getConnectorConfigToEdit %s' % ConnectorName)
    c = self._getConnector(ConnectorName)
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConfigureResponse>'
            '<FormSnippet>%s</FormSnippet>'
            '</ConfigureResponse>'
            '</CmResponse>') % c.getPopulatedConfigForm()
  getConnectorConfigToEdit.exposed = True

  #not implemented yet but (wtf?)
  def restartConnectorTraversal(self, ConnectorName=None, Lang=None):
    self.logger().debug('restartConnectorTraversal %s' % ConnectorName)
    c = self._getConnector(ConnectorName)
    c.restartConnectorTraversal()
    return '<CmResponse><StatusId>%s</StatusId></CmResponse>' % c.getStatus()
  restartConnectorTraversal.exposed = True

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
    self.logger().debug('authenticate ')
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
    self.logger().debug('authorize ')
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
          if 'domain' in nodes.attributes:
            domain = nodes.attributes["domain"].value
          source = nodes.attributes["source"].value
          if 'password' in nodes.attributes:
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

  def logger(self, src=None):
    """Returns a Logger object designated for the src object.

    If src is None, then the Logger for the connector manager will be returned.
    If a logger for src has never been created, one will be created and stored.
    Otherwise, the stored logger will be returned.

    Args:
      src: The object whose logger to return.

    Returns:
      The Logger object for src.
    """
    if not src:
      src = self
    if src not in self.loggers:
      if src is self:
        srcname = 'connectormanager'
      else:
        srcname = 'connector-' + src.getName()
      logger = logging.getLogger(srcname)
      ch = logging.StreamHandler()
      formatter = logging.Formatter(
          '[%(asctime)s %(name)s %(levelname)s] %(message)s',
          '%Y/%m/%d:%H:%M:%S')
      ch.setFormatter(formatter)
      logger.addHandler(ch)
      if self.debug_flag:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
      self.loggers[src] = logger
    return self.loggers[src]

  def _getConnector(self, connector_name):
    for con in self.connector_list:
      if con.getName() == connector_name:
        return con
    return None

  def _setConnector(self, cdata):
    found = False
    for index, con in enumerate(self.connector_list):
      if con.getName() == cdata.getName():
        found = True
        self.connector_list[index] = cdata
    if found == False:
      self.connector_list.append(cdata)

  def _savePropFile(self):
    self.logger().debug('Saving Prop file ')
    str_out = '<connectormanager><connectors><gsa>%s</gsa>' % self.gsa
    for c in self.connector_list:
      config = base64.encodestring(c.getConfig())
      schedule = base64.encodestring(c.getSchedule())
      data = base64.encodestring(cPickle.dumps(c.getData(), 2))
      str_out += ('<connector><name>%s</name><type>%s</type>'
                  '<config>%s</config><schedule>%s</schedule>'
                  '<data>%s</data></connector>') % (
                      c.getName(), c.CONNECTOR_TYPE, config,
                      schedule, data)
    str_out += '</connectors></connectormanager>'
    str_out = xml.dom.minidom.parseString(str_out).toprettyxml()
    try:
      out_file = open(self.configfile, 'w')
      out_file.write(str_out)
      out_file.close()
    except IOError:
      print 'Error Saving Config File'

  def _loadPropFile(self):
    self.logger().debug('Loading Prop File')
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
          cgsa = rnode.childNodes[0].nodeValue.strip()
        if self.gsa == '':
          self.gsa = cgsa
      except IndexError:
        self.logger().debug(('GSA Address not found in config file..'
                             'waiting for testConnectivity()'))
      m_node = xmldoc.getElementsByTagName('connector')
      for rnode in m_node:
        rchild = rnode.childNodes
        for nodes in rchild:
          if nodes.childNodes:
            val = nodes.childNodes[0].nodeValue.strip()
          if nodes.nodeName == 'name':
            name = val
          if nodes.nodeName == 'type':
            type = val
          if nodes.nodeName == 'config':
            config = base64.decodestring(val)
          if nodes.nodeName == 'schedule':
            schedule = base64.decodestring(val)
          if nodes.nodeName == 'data':
            data = cPickle.loads(base64.decodestring(val))
        if type not in self.connector_classes:
          print 'Connector type %s not loaded' % type
          sys.exit(1)
        connector_class = self.connector_classes[type]
        c = connector_class(self, name, config, schedule, data)
        self._setConnector(c)
    except IOError:
      print 'Error Opening Config File'

  def _getPlatformInfo(self):
    return 'Google Search Appliance Python Connector Manager 3.0.2 (%s; %s %s (%s))' % (
        platform.python_version(), platform.system(),
        platform.release(), platform.machine())

if __name__ == '__main__':
  port = 38080
  use_ssl = False
  debug_flag = False
  connectors = ''

  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["debug", "use_ssl",
                                                    "port=", "connectors="])
  except getopt.GetoptError:
    print ('Invalid arguments: valid args --debug  --use_ssl --port=<port> '
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
  for modulename, _, classname in [c.rpartition('.') for c in
                                   connectors.split(',')]:
    module = __import__(modulename)
    cls = getattr(module, classname)
    connector_classes[cls.CONNECTOR_TYPE] = cls

  ConnectorManager(connector_classes, debug_flag, use_ssl, port)
