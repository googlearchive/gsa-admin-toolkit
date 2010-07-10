#!/usr/bin/python2.4
#
# Copyright 2010 Google Inc. All Rights Reserved.

import connectormanager
import datetime
import threading
import urllib2
import xml.dom.minidom

class SitemapConnector(connectormanager.Connector):
#class which implements the actual connector
#it display the config form and in the case of the 'sitemap-connector' here
#this class will start a python threading.Timer thread and do the traversal
#when the timer fires.
# ConnectorManager starts this class  during its  'setConnectorConfig' call and
#the thread itself during 'setSchedule' method.

#  global run

  @staticmethod
  def getConnectorType():
    return 'sitemap-connector'

  @staticmethod
  def getConfigForm():
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
    return config_form

  def getStatus(self):
    return '0'

  def run(self, u):
  # the parameters into the 'run' method
    self.log('TIMER INVOKED for %s ' % self.name)
    # now go get the sitemap.xml file itself
    req = urllib2.Request(u)
    response = urllib2.urlopen(req)
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
    feeder = connectormanager.Postfeed(feed_type, self.debug_flag)
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
                     '</record>') %(self.name, url, self.name, url,
                                    base64.encodestring(content))
      feeder.addrecord(strrecord)
      #if the number of urls were going to send to the GSA right now is more
      #than what its expecting, send what we have now and reset the counter
      #afer waiting 1 min (this is the poormans traversal rate limit delay)
      if (i >= float(self.load)):
        print('Posting %s URLs to the GSA for connector [%s]' %(i, self.name))
        feeder.post_multipart(self.gsa, self.name)
        i = 0
        time.sleep(60)
      else:
        i = i+1
    if i>0:
      print ('Final posting %s URLs to the GSA for connector [%s]' %(i, self.name))
      feeder.post_multipart(self.gsa, self.name)
    #restart the thread again ...the threading.Timer only runs once
    #so we reset again
    #t = threading.Timer(int(float(delay)),
    #   run, [name,config,delay,load,gsa,debug_flag])
    #t.start()

    # just for demonstration--store the current time of the run
    self.setData(datetime.datetime.now())

  def startConnector(self):
    self.log('Last run time for %s: %s' % (self.name, str(self.getData())))
    #the sitemapconnector is cron trigger based in that it runs after a certain
    #delay and stops.  You can implement any traversal scheme/scheduling here
    #that you want to.
    u = self.getConfigParam('surl')
    self.delay = self.getConfigParam('delay')
    self.log('Starting Thread for %s with delay %s  GSA %s' % (self.name,
             self.delay, self.gsa))
    t = threading.Timer(int(float(self.delay)), self.run, [u])
    t.start()

  def stopConnector(self):
    self.log('Stopping Thread %s' %self.name)

  def restartConnectorTraversal(self):
    self.log('Restart Traversal Called')

  #Return the completed XML form back to the ConnectorManager
  #self.config contains the RAW XML configuration form the GSA sends down
  def getForm(self):
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
