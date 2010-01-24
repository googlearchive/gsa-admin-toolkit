#!/usr/bin/python
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

"""ConnectorManager+connector Lite for the Google Search Appliance (GSA)

This script runs a lightweight GSA connectormanager and sitemap connector
on port 38080.

The connectormanager will handle the protocol communication with the GSA and
provide an interface for connnector implementations.

The built-in connector implemented in this script is a 'sitemap' connector which
just downloads a plain (not compressed) sitemap in xml format and proceeds
to send the URLs in it as metadata+url feed to the GSA.  It takes the URL
for the sitemap and a delay (in seconds) after which it should download and
process the xml file.  The sitemap connector is provided to understand how
to potentially trigger the 'traversal' of a content system and how to feed
data to the GSA.
sample xml sitemap:  http://www.domain.com/sitemap.xml

This script can be used as a template to write arbitrary simple connectors.

The connectormanger does not manage an individual connectors checkpointing or
traversal rates- its entirely upto the connector implementation to handle
how often and how to manage the traversal state.

Configured connector instances are stored in config.xml (created on initial
startup) and includes the entire base64 encoded XML configuration form for
that connector.

NOTE:  The protocol between the GSA and connectormanager is subject to change 
       but is verified to work on GSA 6.2

usage:
  ./connectormanager.py
    --debug           Show debug logs
    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected
    --port=           Set the listener port of the cherrypy webserver
                      (default 38080)

class structure
  --connectormanager:
        the main class which is mounted as the root context of cherrypy
        (i.e, the '/' context when you hit http://connectormanager:38080/)
        this class accepts all the input methods the GSA sends to it and
        responds back with the correct protocol:
        some sample methods:   /setManagerConfig  or /getConnectorList ,etc)
        the input XML thats passed to the method is shown in the comment line
        in the method declaration
        The connectormanager creates instances of the actual connector (class
        connectorimpl) and keeps a list of the instances it hosts

        To start the connector, simply instantiate a connector manager class
        and pass in the actual connector implementation class (not a
        connector instance but just the static class):

        connectormanager(connectorimpl, debug_flag, use_ssl, port)

  --connectorimpl:
       The actual connector instance class. This holds all the info for the
       connector (eg, config form, timer schedule) and traverses the content
       system and sends the feed to the GSA
       The connector class implements the interface iconnector with the
       following methods:

        class iconnector:

        # constructor with parameters:
        # name: connector instance name
        # config: the raw XML configuration data sent by the GSA
        # gsa:  the IP address of the GSA
        # debug_flag:  True|False flag to show debug messages
        def __init__(self, name, config, gsa, debug_flag):

        #Return the current raw XML configuration form
        def getForm(self):

        #Return the name of the connector instance 
        def getName(self):

        #Updates the raw XML configuration
        def setConfig(self, config):

        #Get/Set the 'load' setting of the instance.  Used to throttle/limit
        #number of queries to the content server
        def getLoad(self):
        def setLoad(self,load):

        #Get/Set the "TimeInterval" (when to traverse) setting of the instance
        def getTimeInterval(self):
        def setTimeInterval(self,interval):

        #Return the current connector status
        def getStatus(self):

        #Start/Stop the connector: do what you have to do when these methods
        #are called to traverse the content system given the load and
        #intervals (if applicable)
        def startConnector(self):
        def stopConnector(self):
        def restartConnectorTraversal(self):

        #If implementing secure feeds, the GSA will invoke the
        #authenticate/authorize methods.
        def authenticate(self, domain, username, password):
        def authorize(self, identity, domain, resource):

    The connector will send a feed back to the GSA by creating a postfeeder
    class and specifying the XML and GSA's IP address:
      feed_type = 'metadata-and-url' 
      #feed_type = 'incremental'
      feeder = postfeed(feed_type, debug_flag)
      #then add some metadata or incremental data XML records
      feeder.addrecord(strrecord)
      #finally feed in the data with the GSA's IP address and feed name was 
      #sent in with the  __init__ constructor of the connector
      feeder.post_multipart(gsa, name)
      
    When a connector is added or modified from the GSAs admin console, the
    connectormanager will call stopConnector() then startConnector().  The
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
import datetime
import getopt
import os
import sys
import threading
import time
import urllib2
from urllib2 import Request, urlopen
import xml.dom.minidom
import cherrypy
from xml.sax.saxutils import escape


#list of all the connector instances hosted by this manager
connector_list = []

class connectormanager(object):
  #main connector manager webcontext class i.e, the cherrypy mounted
  #root contenxt (i.e, the '/' URI when you hit http://connectormanager:38080/  
  #gsa's IP address to send feeds back to
  gsa = ''
  configfile = 'config.xml'
  
  def __init__(self, connectorref, debug_flag, use_ssl, port):
    self.debug_flag = debug_flag
    cherrypy.server.socket_host = '0.0.0.0'
    self.connectorref = connectorref
    if use_ssl == True:
      cherrypy.config.update({'global': {
          'server.ssl_certificate': 'ssl.crt',
          'server.ssl_private_key': 'ssl.key', }})
    if debug_flag == True:
      cherrypy.config.update({'global': {'log.screen': True}})
    else:
      cherrypy.config.update({'global': {'log.screen': False}})
    if port is None:
      port = 38080
    cherrypy.config.update({'global': {'server.socket_port': port}})
    cherrypy.tree.mount(self, script_name='/')
    cherrypy.engine.start()
    self.loadpropfile()
    for c in connector_list:
      c.startConnector()
    self.savepropfile()

  def index(self):
    conn_info=''
    for c in connector_list:
      conn_info += ('Name: ' + c.getName() + ' <br/> '  + escape(c.getConfig()) 
                    + '<br> Load: ' + c.getLoad() + '<br/>')
    str_cofig = ('<html><head><title>ConnectorManager</title></head>'
                 '<body><p>Index page for python ConnectorManager:<br/>'
                 'Registered ConnectorType: [%s]</p><p>GSA: [%s]</p>'
                 '<p>Connectors: <br/>%s</p>'
                 '</body></html>') %(self.connectorref.connector_type,
                                     self.gsa,conn_info)
    return str_cofig
  index.exposed = True

  def setManagerConfig(self):
    #<ManagerConfig>
    #<FeederGate host="172.25.17.23" port="19900"/>
    #</ManagerConfig>
    data = cherrypy.request.body.read()
    self.log(('setManagerConfig  %s') %data)
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
    return ('<CmResponse>'
            '<Info>Google Enterprise Connector Manager 2.0.0 '
            '(build 2123  June 12 2009); Sun Microsystems Inc. '
            'OpenJDK 64-Bit Server VM 1.6.0_0; '
            'Linux 2.6.24-gg804003-generic (amd64)</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorTypes>'
            '<ConnectorType>%s</ConnectorType>'
            '</ConnectorTypes>'
            '</CmResponse>') % self.connectorref.connector_type
  getConnectorList.exposed = True

  def getConfigForm(self, Lang=None, ConnectorType=None):
    #Lang=en&ConnectorType=sitemap-connector
    self.log('getConfigForm')
    return self.connectorref.config_form
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
    data = cherrypy.request.body.read()
    self.log(('setConnectorConfig  %s') %data)
    ConnectorName = ''
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue
    #first check to see if a connector with this name exists
    c = self.getconnector(ConnectorName)
    #if not create a connector instance, add it to the list 
    if c is not None:
      c.stopConnector()
      self.removeConnector(ConnectorName)
    #create the connector given the string form of the connectorname
    #first get the string name of the connector
    classname = self.connectorref.__name__
    #then instantiate it, TODO: find a better, more secure way to do this.
    c = eval(classname)(ConnectorName, data, self.gsa, self.debug_flag)
    #c = connectorimpl(ConnectorName, data, self.gsa, self.debug_flag)
    c.setConfig(data)
    self.setconnector(c)
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setConnectorConfig.exposed = True

  def setSchedule(self):
    #<ConnectorSchedules>
    #<ConnectorName>connector1</ConnectorName>
    #<load>200</load>
    #<TimeIntervals>0-0</TimeIntervals>
    #</ConnectorSchedules>
    self.log(('setSchedule  '))
    data = cherrypy.request.body.read()
    ConnectorName = ''
    load = '200'
    xmldoc = xml.dom.minidom.parseString(data)
    m_node = xmldoc.getElementsByTagName('ConnectorSchedules')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'load':
          load = nodes.childNodes[0].nodeValue
        if nodes.nodeName == 'TimeIntervals':
          TimeIntervals = nodes.childNodes[0].nodeValue
    c = self.getconnector(ConnectorName)
    c.stopConnector()
    c.setLoad(load)
    c.setTimeInterval(TimeIntervals)
    self.setconnector(c)
    c.startConnector()
    self.savepropfile()
    return '<CmResponse><StatusId>0</StatusId></CmResponse>'
  setSchedule.exposed = True

  #Returns a list of all the connector instances running
  def getConnectorInstanceList(self, Lang=None):
    self.log('getConnectorInstanceList')
    instance_list = ''
    if len(connector_list) == 0:
      return ('<CmResponse>'
              '<Info>Google Enterprise Connector Manager 2.0.0 (build 2123  '
              'June 12 2009); Sun Microsystems Inc. OpenJDK 64-Bit '
              'Server VM 1.6.0_0; Linux 2.6.24-gg804003-generic (amd64)</Info>'
              '<StatusId>5215</StatusId>'
              '</CmResponse>')
    for c in connector_list:
      instance_list += ('<ConnectorInstance> '
                        '<ConnectorName>%s</ConnectorName>'
                        '<ConnectorType>%s</ConnectorType>'
                        '<Status>%s</Status>'
                        '<ConnectorSchedules version="3">%s:%s:300000:%s'
                        '</ConnectorSchedules>'
                        '<ConnectorSchedule version="1">%s:%s:%s'
                        '</ConnectorSchedule>'
                        '</ConnectorInstance>') %(c.getName(),
                                                  c.getConnectorType(),
                                                  c.getStatus(), c.getName(),
                                                  c.getLoad(),
                                                  c.getTimeInterval(),
                                                  c.getName(), c.getLoad(),
                                                  c.getTimeInterval())

    return ('<CmResponse>'
            '<Info>Google Enterprise Connector Manager 2.0.0 '
            '(build 2123  June 12 2009); Sun Microsystems Inc. '
            'OpenJDK 64-Bit Server VM 1.6.0_0; Linux 2.6.24-gg804003-generic'
            ' (amd64)</Info>'
            '<StatusId>0</StatusId>'
            '<ConnectorInstances>%s</ConnectorInstances>'
            '</CmResponse>') %(instance_list)
  getConnectorInstanceList.exposed = True

  def getConnectorStatus(self, ConnectorName=None):
    # ConnectorName=sitemap-connector
    self.log('getConnectorStatus')
    c = self.getconnector(ConnectorName)
    return ('<CmResponse>'
            '  <StatusId>0</StatusId>'
            '  <ConnectorStatus>'
            '    <ConnectorName>%s</ConnectorName>'
            '    <ConnectorType>%s</ConnectorType>'
            '    <Status>%s</Status>'
            '    <ConnectorSchedules version="3">%s:%s:300000:%s</ConnectorSchedules>'
            '  </ConnectorStatus>'
            '</CmResponse>') %(c.getName(), c.getConnectorType(), c.getStatus(),
                               c.getName(), c.getLoad(), c.getTimeInterval())
  getConnectorStatus.exposed = True

  def removeConnector(self, ConnectorName=None):
    # ConnectorName=connector1
    self.log('removeConnector')
    c = self.getconnector(ConnectorName)
    connector_list.remove(c)
    c.stopConnector()
    c = None
    self.savepropfile()
    return ('<CmResponse><StatusId>0</StatusId></CmResponse>')
  removeConnector.exposed = True

  def getConnectorConfigToEdit(self, ConnectorName=None, Lang=None):
    self.log(('getConnectorConfigToEdit '))
    c = self.getconnector(ConnectorName)
    return ('<CmResponse>'
            '<StatusId>0</StatusId>'
            '<ConfigureResponse>'
            '<FormSnippet>%s</FormSnippet>'
            '</ConfigureResponse>'
            '</CmResponse>')  %(c.getForm())
  getConnectorConfigToEdit.exposed = True

  #not implemented yet but 
  def restartConnectorTraversal(self, ConnectorName=None, Lang=None):
    self.log(('restartConnectorTraversal '))
    c = self.getconnector(ConnectorName)
    c.restartConnectorTraversal()
    return ('<CmResponse><StatusId>%s</StatusId></CmResponse>') %(c.getStatus())
  restartConnectorTraversal.exposed = True

  def getconnector(self, connector_name):
    for con in connector_list:
      if con.name == connector_name:
        return con
    return None

  def setconnector(self, cdata):
    found = False
    for index, con in enumerate(connector_list):
      if con.name == cdata.name:
        found = True
        connector_list[index] = cdata
    if found == False:
      connector_list.append(cdata)
      
  def savepropfile(self):
    self.log(('Saving Prop file '))
    str_out = ('<config><connectors><gsa>%s</gsa>') %(self.gsa)
    for c in connector_list:
        str_out += ('<connector><name>%s</name>'
                    '<interval>%s</interval><load>%s</load><config>%s</config>'
                    '</connector>') %(c.getName(), c.getTimeInterval(), 
                                      c.getLoad(), 
                                      base64.encodestring(c.getConfig()))
    str_out += '</connectors></config>'
    try:
      mode = 'w'
      if (os.path.exists(self.configfile) == False):
        in_file = open(self.configfile, mode)
        in_file.close()
      in_file = open(self.configfile, mode)
      in_file.writelines(str_out)
      in_file.close()
    except IOError:
      print 'Error Opening Config File' 
              
  def loadpropfile(self):
    self.log(('Loading Prop FIle '))
    try:
      if (os.path.exists(self.configfile) == False):
        mode ='w'
        in_file = open(self.configfile, mode)
        in_file.close()
        return
      mode = 'rw'
      in_file = open(self.configfile, mode)
      text = in_file.read()
      in_file.close()
      xmldoc = xml.dom.minidom.parseString(text)
      m_node = xmldoc.getElementsByTagName('gsa')
      try:
        for rnode in m_node:
          cgsa = rnode.childNodes[0].nodeValue
        if (self.gsa == ''):
          self.gsa = cgsa          
      except IndexError:
        self.log('GSA Address not found in config file..waiting for testConnectivity()')
      m_node = xmldoc.getElementsByTagName('connector')
      for rnode in m_node:
        rchild = rnode.childNodes
        for nodes in rchild:
          if nodes.nodeName == 'name':
            name = nodes.childNodes[0].nodeValue  
          if nodes.nodeName == 'interval':
            interval =  nodes.childNodes[0].nodeValue            
          if nodes.nodeName == 'load':
            load =  nodes.childNodes[0].nodeValue     
          if nodes.nodeName == 'config':
            config =  nodes.childNodes[0].nodeValue   
        config = base64.decodestring(config)   
        classname = self.connectorref.__name__
        c = eval(classname)(name, config, self.gsa, self.debug_flag)
        c.setLoad(load)
        c.setTimeInterval(interval)
        c.setConfig(config)      
        self.setconnector(c)
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
    for con in connector_list:
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
          source =  nodes.attributes["source"].value 
          password =  nodes.attributes["password"].value
        if (nodes.nodeName == 'Resource'):
          resource = nodes.childNodes[0].nodeValue
          resource_list.append(resource)
    for res in resource_list:
      for con in connector_list:
        az_decision = con.authorize(identity, domain, res)
        str_response += ('<Answer><Resource>%s</Resource>'
                         '<Decision>%s</Decision></Answer>') %(res, az_decision)
    str_response += ('</AuthorizationResponse>'
                     '<StatusId>0</StatusId></CmResponse>')
    return str_response
  authorization.exposed = True

  def log(self, deb_string):
    if (self.debug_flag):
      now = datetime.datetime.now()
      print  ("%s  %s") % (now, deb_string)

class postfeed(object): 

  def __init__(self, feed_type, debug_flag):
    self.debug_flag = debug_flag
    self.feed_type = feed_type
    self.records = ''

  def log(self, deb_string):
    if (self.debug_flag):
      now = datetime.datetime.now()
      print  ("%s  %s") % (now, deb_string)

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
               '</gsafeed>') %(datasource, self.feed_type, self.records)

    content_type, body = self.encode_multipart_formdata(datasource, xmldata)
    headers = {}
    headers['Content-type'] = content_type
    headers['Content-length'] = str(len(body))
    u = 'http://%s:19900/xmlfeed' %gsa
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


class iconnector:
  #constructor the connectormanager calls and passes in
  #the instance name, the raw XML connector configuration, the gsa's ip 
  #address and a debug flag for logging

  def __init__(self, name, config, gsa, debug_flag):
    raise NotImplementedError("__init__  not implemented")

  #returns the empty configuration form encapsulated inside a
  # <CmResponse><ConfigureResponse><FormSnippet>  CDATA tag
  def getForm(self):              
    raise NotImplementedError("getForm() not implemented")

  #returns the instance name
  def getName(self):
    raise NotImplementedError("getName() not implemented")

  #sets the raw CONFIG XML 
  def setConfig(self, config):
    raise NotImplementedError("setConfig() not implemented")

  def getConfig(self):
    raise NotImplementedError("getConfig() not implemented")

  #returns the current load setting (docs to traverse per min)
  #this parameter is initally provided inside config raw XML the connector
  #A connector does not have to do anything with this parameter
  def getLoad(self):
    raise NotImplementedError("getLoad() not implemented")

  def setLoad(self,load):
    raise NotImplementedError("setLoad() not implemented")

  #returns the timeinterval to traverse
  #this parameter is initally provided inside config raw XML the connector
  #manager sets.  Its also set and explictly by the connector.  A connector does
  # not have to do anything with this parameter (you can ignore it if needed)
  def getTimeInterval(self):
    raise NotImplementedError("getTimeInterval() not implemented")

  def setTimeInterval(self,interval):
    raise NotImplementedError("setTimeInterval() not implemented")

  #returns the status of the connector (0--->OK)
  def getStatus(self):
    raise NotImplementedError("getStatus() not implemented")

  #start/stop/restarttraversal the connector
  #the sitemapconnector is cron trigger based in that it runs after a certain
  #delay and stops.  You can implement any traversal scheme/scheduling here
  #that you want to.  
  def startConnector(self):
    raise NotImplementedError("startConnector() not implemented")

  def stopConnector(self):
    raise NotImplementedError("stopConnector() not implemented") 

  def restartConnectorTraversal(self):
    raise NotImplementedError("restartConnectorTraversal() not implemented")

  def authenticate(self, domain, username, password):
    raise NotImplementedError("authenticate() not implemented")

  def authorize(self, identity, domain, resource):
    raise NotImplementedError("authorize() not implemented")

  def getConfigParam(self, param_name):
    xmldoc = xml.dom.minidom.parseString(self.getConfig())
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'ConnectorName':
          ConnectorName = nodes.childNodes[0].nodeValue 
        if nodes.nodeName == 'Param':
          nodename =  nodes.attributes["name"].value 
          if (nodename == param_name):
            return nodes.attributes["value"].value
    return None      

class connectorimpl(iconnector): 
#class which implements the actual connector 
#it display the config form and in the case of the 'sitemap-connector' here
#this class will start a python threading.Timer thread and do the traversal
#when the timer fires.  
# connectormanager starts this class  during its  'setConnectorConfig' call and 
#the thread itself during 'setSchedule' method.

  connector_type = 'sitemap-connector' 
  config_form = ('<CmResponse>'
                 '<StatusId>0</StatusId>'
                 '<ConfigureResponse>'
                 '<FormSnippet>'
                 '<![CDATA[<tr><td>Sitemap Connector Form</td>'
                 '</tr><tr><td>Sitemap URL:</td><td> '
                 '<input type="surl" size="65" name="surl"/>'
                 '</td></tr>'
                 '<tr><td>Fetch Delay:</td>'
                 '<td><input type="delay" size="10" name="delay"/></td>'
                 '</tr>]]>'
                 '</FormSnippet>'
                 '</ConfigureResponse>'
                 '</CmResponse>')
  global run

  def getConnectorType(self):
    return self.connector_type

  def getConfigForm(self):
    return self.config_form

  def getName(self):
    return self.name

  def setConfig(self, config):
    self.config = config
    
  def getConfig(self):
    return self.config
    
  def getLoad(self):
    return self.load

  def setLoad(self,load):
    self.load = load

  def getStatus(self):
    return self.status

  def getTimeInterval(self):
    return self.time_interval

  def setTimeInterval(self,interval):
    self.time_interval = interval

  def __init__(self, name, config,  gsa, debug_flag):
    self.name = name;
    self.config = config
    self.status = '0'
    self.load = '200'
    self.gsa = gsa
    self.time_interval = '0-0'
    self.debug_flag = debug_flag
    #self.config contains the raw XML config info for this connector
    #the GSA sends to the connectormanager.  <ConnectorConfig/>    
    self.delay = self.getConfigParam('delay')    

  def log(self, deb_string):
    if self.debug_flag:
      now = datetime.datetime.now()
      print  ("%s  %s") % (now, deb_string)

  def run(name, config, u, delay, load, gsa, debug_flag):
  #class called by the threading.Timer class
  #the arguments have to get passed into it.. i don't know how to use 
  #global class instead...
  # the parameters into the 'run' method
    print('%s -----> TIMER INVOKED for %s ' %(datetime.datetime.now(), name))
    # now go get the sitemap.xml file itself
    req = Request(u)
    response = urlopen(req)
    content = response.read()
    #parse out the sitemap and get all the urls
    sitemap_urls = []
    xmldoc = xml.dom.minidom.parseString(content)
    m_node = xmldoc.getElementsByTagName('url')
    for rnode in m_node:
      rchild = rnode.childNodes
      for nodes in rchild:
        if nodes.nodeName == 'loc':
          sitemap_urls.append(nodes.childNodes[0].nodeValue)
#        if nodes.nodeName == 'lastmod':
#          now = datetime.datetime.now()
#          strt = nodes.childNodes[0].nodeValue
#          lastmodtime_time = time.strptime(strt, "%Y-%m-%d")
#          lastmodtime_date = datetime.datetime(*lastmodtime_time[:6])
    #for each url in the sitemap, send them in batches to the GSA
    #the batch size is specified by the 'load' parameter from the config page 
    i = 0
    feed_type = 'metadata-and-url'
    #feed_type = 'incremental'
    feeder = postfeed(feed_type, debug_flag)
    for url in sitemap_urls:
      strrecord = ''
      if feed_type == 'metadata-and-url':
        strrecord = ('<record url="%s"  displayurl="%s"  action="add" '
                     'mimetype="text/html">'
                     '<metadata>'
                     '<meta name="google:action" content="add"/>'
                     '<meta name="google:ispublic" content="true"/>'
                     '<meta name="google:mimetype" content="text/html"/>'
                     '<meta name="text/html" content="text/html"/>'
                     '<meta name="metadataname" content="metadatavalue"/>'
                     '</metadata>'
                     '</record>') %(url, url)
      if feed_type == 'incremental':
        #now for the sitemap connecotr, download the content directly
        #req = Request(url)
        #response = urlopen(req)
        #content = response.read()
        content = 'python connector feed content  for %s' %url
        strrecord = ('<record url="googleconnector://%s.localhost/doc?docid=%s" '
                     'displayurl="googleconnector://%s.localhost/doc?docid=%s" '
                     'action="add" mimetype="text/html" authmethod="ntlm">'
                     '<metadata>'
                     '<meta name="google:action" content="add"/>'
                     '<meta name="google:ispublic" content="false"/>'
                     '<meta name="google:mimetype" content="text/html"/>'
                     '<meta name="text/html" content="text/html"/>'
                     '<meta name="metadataname" content="metadatavalue"/>'
                     '</metadata>'
                     '<content encoding="base64binary">%s</content>'
                     '</record>') %(name, url, name, url,
                                    base64.encodestring(content))
      feeder.addrecord(strrecord)
      #if the number of urls were going to send to the GSA right now is more
      #than what its expecting, send what we have now and reset the counter 
      #afer waiting 1 min (this is the poormans traversal rate limit delay)
      if (i >= float(load)):
        print('Posting %s URLs to the GSA for connector [%s]' %(i, name))
        feeder.post_multipart(gsa, name)
        i = 0
        time.sleep(60)
      else:
        i = i+1
    if i>0:
      print ('Final posting %s URLs to the GSA for connector [%s]' %(i, name))
      feeder.post_multipart(gsa, name)
    #restart the thread again ...the threading.Timer only runs once
    #so we reset again
    #t = threading.Timer(int(float(delay)),
    #   run, [name,config,delay,load,gsa,debug_flag])
    #t.start()
  def startConnector(self):
    #the sitemapconnector is cron trigger based in that it runs after a certain
    #delay and stops.  You can implement any traversal scheme/scheduling here
    #that you want to.
    u = self.getConfigParam('surl')
    self.delay = self.getConfigParam('delay')
    self.log(('Starting Thread for %s with delay %s  GSA %s') %(self.name, self.delay, self.gsa))    
    t = threading.Timer(int(float(self.delay)), run, [self.name, self.config, u, self.delay, self.load, self.gsa, self.debug_flag])
    t.start()

  def stopConnector(self): 
    self.log('Stopping Thread %s' %self.name)
    
  def restartConnectorTraversal(self):
    self.log('Restart Traversal Called')
    
  def authenticate(self, domain, username, password):
    #validate the username/domain/password combo and return the identity
    self.log(('authenticate called for user [%s] on connector [%s]')
             %(username, self.name))
    return username

  def authorize(self, identity, domain, resource):
    self.log(('authorize called for user [%s] on [%s] for resource [%s]')
             %(identity, self.name, resource))
    return 'Permit'

  #Return the completed XML form back to the connectormanager
  #self.config contains the RAW XML configuration form the GSA sends down
  def getForm(self):
    xmldoc = xml.dom.minidom.parseString(self.config)
    m_node = xmldoc.getElementsByTagName('ConnectorConfig')
    surl = self.getConfigParam('surl')
    delay = self.getConfigParam('delay')
    str_out=('<![CDATA[<tr><td>Sitemap Connector Form</td>'
             '</tr><tr><td>Sitemap URL:</td><td> '
             '<input type="surl" size="65" name="surl" value="%s"/>'
             '</td></tr>'
             '<tr><td>Fetch Delay:</td>'
             '<td>'
             '<input type="delay" size="10" name="delay" value="%s"/>'
             '</td></tr>]]>') %(surl, delay)
    return str_out

def main(argv):
  pass

if __name__ == '__main__':
  port = 38080
  use_ssl = False
  debug_flag = False
  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["debug","use_ssl","port="])
  except getopt.GetoptError:
    print ('Invalid arguments: valid args --debug  --use_ssl --port=<port> ')
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--debug":
      debug_flag = True
    if opt == "--use_ssl":
      use_ssl = True
    if opt == "--port":
      port = int(arg)
  connectormanager(connectorimpl, debug_flag, use_ssl, port)
