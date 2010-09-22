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
"""Simple SharepointConnector for the Google Search Appliance (GSA)

A python connector that queries sharepoint to get a list of Site document URLs
to feed into a GSA.  The connector uses the webservice APIs for Sharepoint to get
the Shared document list and sends each doc as metadata+url feed to a GSA.  After the initial
traversal, this script will trigger and requery sharepoint for any documents that got
changed since the last invocation.

Prerequisite:
  Sharepoint Services 3.0
  Python 2.6
  GSA Python ConnectorManager (http://code.google.com/p/gsa-admin-toolkit)
  CherryPy  (http://www.cherrypy.org/)
  suds      (https://fedorahosted.org/suds/)

Run:
  python connectormanager.py  --connectors=sharepoint_connector.SharepointConnector
  Then:
     1. Register the python connectormanager from the GSA
     2. Create a Sharepoint connector instance:
        Config Params:
          a. sharepoint url    : the root URL for your Sharepoint Site:
                                 http://www.yoursharepoint.com/
          b. state             : Base64 encoded XML Sharepoint ChangeTokens
                                 (leave blank for initial configuration)
          c. username          : Sharepoint Admin username
          d. domain            : Sharepoint Domain
          e. password          : Sharepoint Admin password
          f. delay             : How often (in seconds) to query Sharepoint for changes.
                                                 

Also see:
http://msdn.microsoft.com/en-us/library/ms774532(office.12).aspx
http://www.jansipke.nl/python-soap-client-with-suds
http://cbess.blogspot.com/2009/01/python-suds-with-windows-authentication.html


 TODO:
   1. Security for content feeds- AuthZ (use Google sharepoint services API)
   2. Use the 'GetChanges()' ListItemCollectionPositionNext for incremental changes
   3. Add additional meta-data about each doc to the feed
   4. Find out how to detect deleted documents
   5. Exception Handling
"""

import connector
import suds
from suds.sax.element import Element
from suds.sax.document import Document
from suds.transport.https import WindowsHttpAuthenticated
from suds.sax.text import Raw
import logging
import xml.dom.minidom
import datetime
from xml.sax.saxutils import escape
import base64

class SharepointConnector(connector.TimedConnector):
  CONNECTOR_TYPE = 'sharepoint-connector'
  CONNECTOR_CONFIG = {
      'SP_URL': { 'type': 'text', 'label': 'sharepoint url' },
      'SP_USER': { 'type': 'text', 'label': 'username' },
      'SP_DOMAIN': { 'type': 'text', 'label': 'domain' },
      'SP_PASSWORD': { 'type': 'password', 'label': 'password' },
      'DELAY': { 'type': 'text', 'label': 'delay' },
      'SP_STATE': { 'type': 'text', 'label': 'state (b64encoded)' }
  }

  def init(self):
    self.setInterval(int(self.getConfigParam('DELAY')))
    logging.getLogger('suds.client').setLevel(logging.DEBUG) 

  def run(self):
    self.logger().info('TIMER INVOKED for %s ' % self.getName())
    self.logger().info('--------------------------------')
    self.logger().info('----> Start Traversal Run <-----')
    self.logger().info('--------------------------------')
    # First get the parameters we need
    self.SP_URL = self.getConfigParam('SP_URL')
    self.SP_USER = self.getConfigParam('SP_USER')
    self.SP_DOMAIN = self.getConfigParam('SP_DOMAIN')
    self.SP_PASSWORD = self.getConfigParam('SP_PASSWORD')
    self.SP_STATE = self.getConfigParam('SP_STATE')
  
    # go get a list of all the sites below the root:
    ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
    url = self.SP_URL + '/_vti_bin/Webs.asmx?WSDL'
    client = suds.client.Client(url, transport=ntlm)
    resp = client.service.GetAllSubWebCollection()
    resp_site = client.last_received().getChild("soap:Envelope").getChild("soap:Body").getChild("GetAllSubWebCollectionResponse").getChild("GetAllSubWebCollectionResult").getChild("Webs")
    sites = {}
    for web in resp_site:
      if web != None:
       sites[web.getAttribute("Title").getValue()] = web.getAttribute("Url").getValue()
      else:
        break 
   

    config_state_dict ={}
    # get the config param to save the last change token per site per document list
    last_config_state = base64.decodestring(self.SP_STATE)
    if (last_config_state == ''):
      last_config_state = '<sites></sites>'

    # find the current tokens saved to disk
    xmldoc = xml.dom.minidom.parseString(last_config_state)
    xsites = xmldoc.getElementsByTagName('site')
    for xsite in xsites:
      site_name = xsite.attributes["name"].value
      libraries = xsite.getElementsByTagName('library')
      config_state_dict[site_name] = libraries

    # for each site found, get the url  
    site_config = ''
    for name in sites:
      self.logger().info('Found Site ID: [' + name + ' with URL: ' + sites[name] + ']')
      # see if the current site has its crawltokens saved to disk
      if (name in config_state_dict):
        self.logger().info('Calling getSiteData for [' + name + ']') 
        lib_dict = self.getSiteData(name,sites[name],config_state_dict[name])
      else:
        # no previous crawl...so start a new one
        lib_dict = self.getSiteData(name,sites[name],None)
      #update the cofnig with the new change tokens
      # TODO:  figure out how to 'save' the new SP_STATE to the config.xml file right here
      #        right now it just saves state when cherrypy is unloaded
      state_xml = ''
      # for each document library in this site, add on a new entry with its crawltoken
      for lib_entry in lib_dict:
        state_xml = state_xml + lib_entry
      site_config = site_config + '<site name="' + name + '">' + state_xml + '</site>'
    last_config_state = '<sites>' + site_config + '</sites>'
    self.setConfigParam('SP_STATE',base64.encodestring(last_config_state))
    self.logger().info('--------------------------------')
    self.logger().info('-----> End Traversal Run <------')
    self.logger().info('--------------------------------')   

  def getSiteData(self, site_name, url_prefix, libraries):

    if (libraries != None):
      self.logger().info('Running getSiteData for  site: [' + site_name  + '], for [' + str(libraries.length) + '] libraries')
    else:
      self.logger().info('Running Initial Traversal for  site: [' + site_name  + ']')

    lib_dict = []

    ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
    url = url_prefix + '/_vti_bin/SiteData.asmx?WSDL'
    client = suds.client.Client(url, transport=ntlm)
   
    # First get the FolderID number for that site 
    resp = client.service.GetListCollection()
    for _sList in resp.vLists._sList:      
      if _sList.BaseType == "DocumentLibrary":

        folder_id =  _sList.InternalName
        self.logger().info('Found [' +  _sList.Title  + '] of type [' +  _sList.BaseType + ']' + ' with Folder ID: ' + folder_id)
    
        # get ready to refeed all the doc URLs
        feed_type = 'metadata-and-url'
        feed = connector.Feed(feed_type)
 
        last_sync = None

        # See if there  is a change token for the current site
	if (libraries != None):
          for lib in libraries:            
            if (lib.attributes['id'].value == folder_id):
	      last_sync = lib.attributes['last_sync'].value
              self.logger().info('Retrieved LastChangeToken from file [' + last_sync + ']')
        
        # then use that ID to get the document lists
        ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
        url = url_prefix + '/_vti_bin/Lists.asmx?WSDL'
        client = suds.client.Client(url, transport=ntlm)
              
        # attribute used for paging
        ListItemCollectionPositionNext = ''      
        while (ListItemCollectionPositionNext != None):
          query = ('<Query><OrderBy><FieldRef Name="Created" Ascending="TRUE" /></OrderBy></Query>')
          viewfields='<ViewFields Properties="TRUE"/>'
          # get 100 rows now per cursor... 
          rowlimit = 100
          if (ListItemCollectionPositionNext != ''):
            queryoptions = ('<QueryOptions><IncludeMandatoryColumns>true</IncludeMandatoryColumns>' +
	 	            '<DateInUtc>TRUE</DateInUtc><ViewAttributes Scope="Recursive"/>' +
		            '<Paging ListItemCollectionPositionNext="%s"/>' + 
		            '<OptimizeFor>ItemIds</OptimizeFor></QueryOptions>') % (escape(ListItemCollectionPositionNext))
          else:
            queryoptions = ('<QueryOptions><IncludeMandatoryColumns>true</IncludeMandatoryColumns>' +
	 	            '<DateInUtc>TRUE</DateInUtc><ViewAttributes Scope="Recursive"/>' +
		            '<OptimizeFor>ItemIds</OptimizeFor></QueryOptions>')
          contains = ('<Contains><FieldRef Name="Status"/><Value Type="Text">Complete</Value></Contains>')

          client.service.GetListItemChangesSinceToken(folder_id,'',Raw(query),Raw(viewfields),rowlimit,Raw(queryoptions),last_sync,Raw(contains))
          
          li =  client.last_received().getChild("soap:Envelope").getChild("soap:Body").getChild("GetListItemChangesSinceTokenResponse").getChild("GetListItemChangesSinceTokenResult").getChild("listitems")
          
          # Read the last change token from Sharepoint
          changes = li.getChild('Changes')
          if (changes != None):
            if (changes.getAttribute("LastChangeToken") != None):
              changeid = changes.getAttribute("LastChangeToken").getValue()
              self.logger().info('Found new LastChangeToken [' + changeid + ']')
            else:
              self.logger().info('LastChangeToken is None') 
          else:
            self.logger().info('LastChangeToken is None') 
          
          rsd = li.getChild("rs:data")
          # extract out the cursor ListItemCollectionPositionNext
          if (rsd.getAttribute('ListItemCollectionPositionNext') != None):
            ListItemCollectionPositionNext = rsd.getAttribute('ListItemCollectionPositionNext').getValue()
	    self.logger().info('Found response cursor ListItemCollectionPositionNext [' + ListItemCollectionPositionNext + ']')
          else:
            ListItemCollectionPositionNext = None
          # now for each row returned, add that to the feed set
          for zrow in rsd:
            if zrow != None:
              my_url =  zrow.getAttribute("ows_EncodedAbsUrl").getValue()
              my_last_modified = zrow.getAttribute("ows_Last_x0020_Modified").getValue()
              self.logger().debug('Found URL [' + my_url + ']')
              # set all the attributes for this feed (TODO: set the security SPI parameters)
              feed.addRecord(url=my_url, displayurl=my_url, action='add', mimetype='text/html')
            else:
              break
          # Finally, save the library name and change token so that the next time, we know where we left off...
          lib_dict.append('<library id="' +  folder_id + '" name="' +  _sList.Title + '" last_sync="' + changeid + '" />')  
          # flush the records to the GSA
          self.logger().info('Transmitting [' + str(len(rsd)) + '] documents.')
          self.pushFeed(feed)
          feed.clear()
    # return the last sync time
    return lib_dict

  def authenticate(self, domain, username, password):
    self.logger().info('Authenticating [' + username + ']')
    return username

  def authorize(self, identity, domain, resource):
    self.logger().info('Authorizing [' + username + '] for [' + resource + ']') 
    return 'Permit'
