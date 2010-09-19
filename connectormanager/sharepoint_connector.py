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
    #logging.getLogger('suds.client').setLevel(logging.DEBUG) 

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
    # eg  http://sharepoint.esodomain.com:5456/
    # and http://sharepoint.esodomain.com:5456/mynewsite/ 
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
   
    # get the config param to save the last change token per site
    last_config_state = base64.decodestring(self.SP_STATE)
    if (last_config_state == ''):
      last_config_state = '<sites></sites>'

    # find the current tokens saved to disk
    config_state_dict = {}
    xmldoc = xml.dom.minidom.parseString(last_config_state)
    site_node = xmldoc.getElementsByTagName('site')
    for site in site_node:
      site_name = site.attributes["name"].value
      last_sync = site.attributes["last_sync"].value
      config_state_dict[site_name] = last_sync
    
    # for each site found, get the changes  
    site_config = ''
    for name in sites:
      self.logger().info('Found Site: [' + name + ' with URL: ' + sites[name] + ']')  
      if (name in config_state_dict):
	last_sync = config_state_dict[name]
        self.logger().info('Calling getSiteData for [' + name + ']' + ' sync: [' + last_sync + ']') 
        last_sync = self.getSiteData(name,sites[name],last_sync)
      else:
        last_sync = self.getSiteData(name,sites[name],'')
      #update the cofnig with the new change tokens
      # TODO:  figure out how to 'save' the new SP_STATE to the config.xml file right here
      #        right now it just saves state when cherrypy is unloaded      
      site_config = site_config + '<site name="' + name + '" last_sync="' + last_sync + '"/>'
    last_config_state = '<sites>' + site_config + '</sites>'
    self.setConfigParam('SP_STATE',base64.encodestring(last_config_state))
    self.logger().info('--------------------------------')
    self.logger().info('-----> End Traversal Run <------')
    self.logger().info('--------------------------------')   

  def getSiteData(self, site_name, url_prefix, last_state):

    self.logger().info('Running getSiteData for  site: [' + site_name  + '], DOMAIN\USERNAME [' + self.SP_DOMAIN + '\\' + self.SP_USER + ']')
 
    ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
    url = url_prefix + '/_vti_bin/SiteData.asmx?WSDL'
    client = suds.client.Client(url, transport=ntlm)
   
    # First get the FolderID number for that site 
    resp = client.service.GetListCollection()
    for _sList in resp.vLists._sList:
      if _sList.Title == "Shared Documents":
        folder_id =  _sList.InternalName
        self.logger().info('Found Shared Documents Folder ID: ' + folder_id)
    
        # Now get current ChangeID parameter for this FolderID
        # theres is some bug with suds which prevents reusing a suds.client.Client 
        ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
        client = suds.client.Client(url, transport=ntlm)
        client.service.GetContent("SiteCollection",folder_id,'','','true','false','')
        resp_site = client.last_received().getChild("soap:Envelope").getChild("soap:Body").getChild("GetContentResponse").getChild("GetContentResult").getText()
        xmldoc = xml.dom.minidom.parseString(resp_site)
        mdata = xmldoc.getElementsByTagName('Metadata')
        changeid = mdata[0].attributes['ChangeId'].value
        self.logger().info('Found Change ID: ' + changeid + ' for folderID [' + folder_id + ']')

        # get ready to refeed all the doc URLs
        feed_type = 'metadata-and-url'
        feed = connector.Feed(feed_type)
 
        # if we don't have a previous token, traverse the entire set
        if (last_state == ''):
          self.logger().info('Initializing Traversal for [' + site_name + ']')
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
            queryoptions = ('<QueryOptions><IncludeMandatoryColumns>true</IncludeMandatoryColumns>' +
	     	            '<DateInUtc>TRUE</DateInUtc><ViewAttributes Scope="Recursive"/>' +
		            '<Paging ListItemCollectionPositionNext="%s"/>' + 
		            '<OptimizeFor>ItemIds</OptimizeFor></QueryOptions>') % (escape(ListItemCollectionPositionNext))
            client.service.GetListItemChangesSinceToken(folder_id,'',Raw(query),Raw(viewfields),rowlimit,Raw(queryoptions))
            rsd =  client.last_received().getChild("soap:Envelope").getChild("soap:Body").getChild("GetListItemChangesSinceTokenResponse").getChild("GetListItemChangesSinceTokenResult").getChild("listitems").getChild("rs:data")
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
            # flush the records to the GSA
            self.logger().info('Transmitting [' + str(len(rsd)) + '] documents.')
            self.pushFeed(feed)
            feed.clear()
        else:
          # if we have a change token, ask sharepoint to get the deltas only
          self.logger().info('Getting changes for [' + site_name + '] from [' + last_state + ']')
          ntlm = WindowsHttpAuthenticated(username=self.SP_DOMAIN + '\\' + self.SP_USER , password=self.SP_PASSWORD)
          url = url_prefix + '/_vti_bin/SiteData.asmx?WSDL'
          client = suds.client.Client(url, transport=ntlm)
          # TODO:  iterate over ListItemCollectionPositionNext somehow
          client.service.GetChanges("SiteCollection",'',last_state,'',1000)
          resp_site = client.last_received().getChild("soap:Envelope").getChild("soap:Body").getChild("GetChangesResponse").getChild("GetChangesResult").getText()
          xmldoc = xml.dom.minidom.parseString(resp_site)
          zrows = xmldoc.getElementsByTagName('z:row')
          self.logger().info('Found [' + str(len(zrows)) + '] documents')
          for row in zrows:
            if row != None:
              my_url =  row.attributes["ows_EncodedAbsUrl"].value
              my_last_modified = row.attributes["ows_Last_x0020_Modified"].value 
              self.logger().debug('Found URL [' + my_url + ']')
              feed.addRecord(url=my_url, displayurl=my_url, action='add', mimetype='text/html')	
            else:
              break
          # flush the records to the GSA
          self.logger().info('Transmitting [' + str(len(zrows)) + '] documents.')
          self.pushFeed(feed)
          feed.clear()

        # Now return the changeID
        return changeid
    # for whatever reason there was a problem...return whatever we got back
    return last_state

  def authenticate(self, domain, username, password):
    self.logger().info('Authenticating [' + username + ']')
    return username

  def authorize(self, identity, domain, resource):
    self.logger().info('Authorizing [' + username + '] for [' + resource + ']') 
    return 'Permit'
