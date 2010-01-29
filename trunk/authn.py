#!/usr/bin/python
#
# Copyright 2009 Google Inc. All Rights Reserved.
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


"""Simple web server for testing the Authn/Authz SPI.

usage:
  ./authn.py
    --debug           Show debug logs

    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected

    --port=           Set the listener port of the cherrypy webserver
                      (default 28080)

    --use_fqdn_hosts  Use Fully Qualified hosts in in the authz database.  If
                      this setting is enabled, the self.authz_db will have
                      fully qualified hostnames.  Otherwise, just the URI
                      pattern defined in the self_authz_db will be used.  You
                      must edit the self.authz_db variable within the script
                      and set the Fully Qualified URLs for your contentserver.
                      
    --consumer_mech=  Specifies which mechanism to use to figure out where
                      to redirect the SAMLRequest back to.
                      The options for this switch:
                      (saml|referer|static)  default referer

                      saml: Usually this information is
                      contained in the SAMLRequest's decoded
                      samlp:AuthnRequest/AssertionConsumerServiceURL parameter)
                      The GSA's SPI interface (as of GSA 6.0) does not send in
                      a AssertionConsumerServiceURL param in the saml request
                      so we *must* use the referer  header or use static.

                      referer:  Use the HTTP referer HTTP header the browser
                      sends after a redirect by the GSA.  Recommended to use
                      this setting with GSA 6.x.  Referer redirects to the
                      http: port of the GSA.  If https is required,
                      modify in def login() the following line from http to
                      to https:
                      location = ('http://%s/SamlArtifactConsumer?...

                      static: hardcoded return path (defined in def login())
                      set the static_redirect= 

    --saml_issuer=    set the SAML_issuer ID parameter (not used in the GSA)

This script runs a web server on port 28080 that allows you to test the
Authn/Authz SPI on the Google Search Appliance.

The authn.py script is basically a SAML IDP/Policy server which prompts users
for BASIC username/password info and then complies with as much of the SAML2.0
specifications the GSA handles.  It is not designed to handle full production
load but rather just as a proof-of-concept.  The username/password combinations
can be anything (in fact, they don't even need to be real users), but the URLs
need to match exactly what the GSA has securely crawled in an infrastructure

SETUP and RUN configuration.
   This script supports two modes of operation: A) crawl/serve using the
   internal basic-protected pages that comes built-in with the script (the
   default configuration) or B) Crawl actual secure content servers and
   specify URL patterns and Access Control Lists for users.  The latter
   configuration is enabled by specifying the '--use_fqdn_hosts' startup flag
   after editing the self.authz_db setting in the __init__ method

   After startup, you can view the current authz_db and internal protected URLs
   by visiting http://spi.yourdomain.com:28080/  (if spi.yourdomain.com is
   where authn.py is running)

   To use
   A) If you don't want the GSA to crawl your a real content
      server, you can use the  built in basic-protected
      pages included in this script.  The pages and authz database for these
      pages is:

      self.user_db = {'user1':'somepassword', 'user2':'otherpassword',
                      'gsa1':'gsapassword'}
                        
      self.authz_db = {
       '/secure?page=secure1':'user1,user2,gsa1',
       '/secure?page=secure2':'user1,gsa1',
       '/secure?page=secure3':'user2,gsa1',
       '/secure?page=secure4':'user1,user2,gsa1'}
       
       Which means user1,user2, user3 is allowed '/secure?page=secure1' and
       user1,gsa1 is allowd to view '/secure?page=secure2' and so on.

      This setting and internal authz_db is enabled by default so the user
      does not have to edit/modify the script

      On the GSA, set it up for crawling:
        (assume authn.py is run on a machine called 'spi.yourdomain.com')
            Crawl&Index-->Crawler Access:
                            URL Matching:  http://spi.yourdomain.com:28080/
                            Username:      gsa1
                            Password:      password1#
                            Domain:        (leave blank)
            Crawl&Index-->CrawlURLs:
                        StartURLs:   http://spi.yourdomain.com:28080/
                        Follow:      http://spi.yourdomain.com:28080/
                        
            Serving-->Access Control
                          User Login URL:
                            http://spi.yourdomain.com:28080/login
                          Artifact Service URL:
                            http://spi.yourdomain.com:28080/artifact_service
                          Authorization service URL:
                            http://spi.yourdomain.com:28080/authz
           check Disable prompt for Basic authentication or NTLM authentication)                       
   
   B) If this script is used against an actual content server
   eg:  running on secure.yourdomain.com, then the configuration on the GSA
   could be:
   1.Serving-->Access Control
           (assume authn.py is running on spi.yourdomain.com)
           User Login URL:
                       http://spi.yourdomain.com:28080/login
           Artifact Service URL:
                       http://spi.yourdomain.com:28080/artifact_service
           Authorization service URL:
                       http://spi.yourdomain.com:28080/authz
           check Disable prompt for Basic authentication or NTLM authentication)
           do NOT check Use batched SAML Authz Requests.)

    2.Crawling:
            Configure the GSA to crawl Form or NTLM protected content inside
            your infrastructure.  In the example in step 3 below,
            assume those protected URLs are:

        http://secure.yourdomain.com/protected/page1 accessible by user1,user2
        http://secure.yourdomain.com/protected/page2 accessible by user1
        http://secure.yourdomain.com/protected/page3 accessible by user2

    3.Edit authn.py script
             The script needs to know the URL's to authorize a list of users
             for. Edit this script and find below

             self.user_db = {'user1':'somepassword',
                             'user2':'otherpassword',
                             'gsa1':'gsapassword'}

             (you can use real usernames/password combos for your infrastructure
              but it is not necessary)

             self.authz_db = {
                 'http://secure.yourdomain.com/protected/page1':'user1,user2',
                 'http://secure.yourdomain.com/protected/page2':'user1',
                 'http://secure.yourdomain.com/protected/page3':'user2'}

             If the authn.py script is requested to authorize any URLs not found
             in this authz_db table, it will send back an "Indeterminate"
             response.  If a user is authorized (i.e, exists in the list,
             it will send back "Permit" otherwise "Deny"

             Then run authn.py with the argument

             ./authn.py --use_fqdn_hosts

After the crawl has completed, you can test serving with the
following command (need to set --consumer_mech=referer):

curl --insecure --location-trusted -v --basic --user user1:password1# \
-b /tmp/cookies "http://gsa.yourdomain.com/search?q=authenticated&
site=default_collection&client=default_frontend&output=xml&access=a"

This script requires the cherrypy v3 to be installed (v2 gives an error since
quickstart is not available).

http://www.cherrypy.org/

Also see: 
code.google.com/apis/searchappliance/documentation/60/authn_authz_spi.html
"""


import base64
import datetime
import getopt
import md5
import random
import sys
import time
import urllib
from urlparse import urlparse
import xml.dom.minidom
import zlib
import cherrypy

class AuthN(object):

  def __init__(self, protocol, debug_flag, use_fqdn_hosts, consumer_mech, 
               saml_issuer):
    self.realm = "authn"
    self.protocol = protocol
    self.use_fqdn_hosts = use_fqdn_hosts
    self.debug_flag = debug_flag
    self.consumer_mech = consumer_mech

    log ('-----> Starting authn.py <------')

    #authentication database in the form username: password
    self.user_db = {'user1': 'password1#',
                    'user2': 'password1#',
                    'gsa1': 'password1#'}
    #the authorization database in the form URL: authorized users
    #if use_authz_db enabled then the following table applies        
    if (use_fqdn_hosts == True):
      log ('Using Fully Qualified Hosts in authz_db')
      self.authz_db = {'http://secure.yourdomain.com/protected/page1':
                       'user1,user2,gsa1',
                       'http://secure.yourdomain.com/protected/page2':
                       'user1,gsa1',
                       'http://secure.yourdomain.com/protected/page3':
                       'user2,gsa1',
                       'http://secure.yourdomain.com/protected/page4':
                       'user1,user2,gsa1'}
    else:
      log ('Using URI in authz_db')
      self.authz_db = {'/secure?page=secure1':
                       'user1,user2,gsa1',
                       '/secure?page=secure2':
                       'user1,gsa1',
                       '/secure?page=secure3':
                       'user2,gsa1',
                       '/secure?page=secure4':
                       'user1,user2,gsa1'}

    log ('authz_db set to %s' % self.authz_db)

    # stores the authenticated sessions
    self.authnsessions = {}
    self.saml_issuer = saml_issuer
    self.passwd_db = {}
    for user in self.user_db:
      self.passwd_db[user] = md5.new(self.user_db[user]).hexdigest()

  #Main landing page
  def index(self):
    return ('<html><title>SAMPLE SPI Landing Page</title>'
            '<body><center>'
            '<h3>Landing page for SPI authn.py</h3>'
            '<a href=\"public\">public</a><br/>'
            '<a href=\"secure?page=secure1\">secure1</a><br/>'
            '<a href=\"secure?page=secure2\">secure2</a><br/>'
            '<a href=\"secure?page=secure3\">secure3</a><br/>'
            '<a href=\"secure?page=secure4\">secure4</a><br/>'
            '<a href=\"param?val1=foo&val2=bar\">param</a><br/>'
            '<a href=\"sleep\">sleep</a><br/>'
            'Current Logins %s<br/>'
            'Authz Table %s'
            '</center></body></html>') %(self.user_db, self.authz_db)
  index.exposed = True

  # Collects and verifies the username/password combos for BASIC authentication.
  def authenticate(self):
    if self.debug_flag:
      log('Request Headers %s' % cherrypy.request.headers)
    cherrypy.tools.basic_auth.callable(self.realm, self.passwd_db)
    return cherrypy.request.login

  # Public page
  def public(self):
    return 'Anyone can view this page. No authentication is required"'
  public.exposed = True

  # Secure pages for the internal basic-auth system.  The ?page=<pagename>
  # parameter determines which
  # page is going to get shown.
  def secure(self, page = None):
    login = self.authenticate()
    if self.debug_flag:
      log ('User Authenticated %s' %login)
    if (use_fqdn_hosts == True):
      authz_result = self.checkauthz(login,
                                     self.protocol + '://' +
                                     cherrypy.request.headers.get('Host', None)
                                     + cherrypy.request.path_info + "?page="
                                     + page)
    else:
      authz_result = self.checkauthz(login,"/secure?page=" + page)
    return self.checkPermit(authz_result, login)
  secure.exposed = True

  # Routine which checks to see if a user is Permitted to see a page, otherwise
  # send back a 401.
  def checkPermit(self, authz_result, login):
    if authz_result == 'Permit':
      return ('You must be authenticated to view this page.'
              'You are authenticated as &quot;%s&quot;.' % (login))
    else:
      cherrypy.response.status = 401
      return 'Not authorized'

  def param(self, val1, val2):
    login = self.authenticate()
    return ('The value of the &quot;val1&quot; parameter is: %s<br>'
            'The value of the &quot;val2&quot; parameter is: %s' % (val1, val2))
  param.exposed = True

  def sleep(self):
    login = self.authenticate()
    time.sleep(75)
    return 'I\'m awake!'
  sleep.exposed = True

  # Routine to check if a user is authorized to view a given resource.
  def checkauthz(self, username, resource):
    decision = 'Indeterminate'
    allowed_users = None
    try:
      allowed_users = self.authz_db[resource]
    except KeyError:
      log('Resource not found in database: %s ' %(resource))
    else:
      arr_users = allowed_users.split(",")
      if (self.debug_flag):
        log('Allowed users for Resource: %s %s ' %(resource, arr_users))
      if username in arr_users:
        decision = 'Permit'
      else:
        decision = 'Deny'
    return decision

  # Generates SAML 2.0 IDs randomly.
  def getrandom_samlID(self):
    rand_art = ''
    # Generate a randomID starting with an character
    for i in random.sample('abcdefghijklmnopqrstuvwxyz123456789', 30):
      rand_art += i
    rand_prefix = ''
    for i in random.sample('abcdefghijklmnopqrstuvwxyz', 2):
      rand_prefix += i
    return rand_prefix + rand_art

  # Collects the SAMLRequest, RelayState and prompts uses BASIC to prompt the
  # user.
  def login(self, RelayState=None, SAMLRequest = None):
    # Ask the user for username/password
    login = self.authenticate()

    if self.debug_flag:
      log('-----------  LOGIN BEGIN -----------')
    # Generate a random artifiact ID and save it to recall later
    rand_art = self.getrandom_samlID()
    # Stash the artifact associated with the user it in a table so that 
    # when asked who an artifact belongs to, we know who the user is.
    self.authnsessions[rand_art] = (login)
    # We can either use the Referer header or (per SAML spec), decode/decompress
    # the SAMLRequest to figure out 
    # the AssertionConsumerServiceURL or just statically redirect
    if self.consumer_mech == 'static':
      static_redirect = 'https://gsa.yourdomain.com/SamlArtifactConsumer'
      if self.debug_flag:
        log('Attempting to use STATIC  Header with Artifact [%s]'%(rand_art))
      cherrypy.response.status = 302
      # Redirect back to the GSA and add on the artifact,relaystate
      location = ('%s?SAMLart=%s&RelayState=%s'
                  % (static_redirect, rand_art, urllib.quote(RelayState)))
      cherrypy.response.headers['location'] = location
      if self.debug_flag:
        log( 'Redirecting to: %s' %(location))
      log('-----------  LOGIN END  -----------')       

    elif (self.consumer_mech == 'saml'):
      # Otherwise
      if self.debug_flag:
        log('Attempting to parse SAML AssertionConsumerServiceURL')
        # Now b64decode and inflate
      decoded_saml = decode_base64_and_inflate(SAMLRequest)
      xmldoc = xml.dom.minidom.parseString(decoded_saml)
        # XML parse out the result
        # the consumer service should be in
        # samlp:AuthnRequest/AssertionConsumerServiceURL attribute
        # it SHOULD something like:
        #        <?xml version="1.0" encoding="UTF-8"?>
        #            <samlp:AuthnRequest
        #            xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
        #            ID="eeijbbeleijhjejokdbcpcgppombbnamnjmmobbh"
        #            Version="2.0" IssueInstant="2008-07-09T15:22:44Z"
        #            ProtocolBinding=
        #                "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact"
        #            ProviderName="google.com"
        #            AssertionConsumerServiceURL=
        #                    "https://gsa.yourdomain.com/SamlArtifactConsumer"
        #            IsPassive="false">
        #            <saml:Issuer xmlns:saml=
        #                "urn:oasis:names:tc:SAML:2.0:assertion">
        #                google.com
        #            </saml:Issuer>
        #            <samlp:NameIDPolicy AllowCreate="true"
        #            Format="urn:oasis:names:tc:SAML:1.1:
        #                        nameid-format:unspecified" />
        #            </samlp:AuthnRequest>

      samlpnode = xmldoc.getElementsByTagName('samlp:AuthnRequest')
      acs_url = None
      for node in samlpnode:
        if node.nodeName == 'samlp:AuthnRequest':
          if samlpnode[0].hasAttribute('AssertionConsumerServiceURL'):
            acs_url = samlpnode[0].attributes \
                          ['AssertionConsumerServiceURL'].value
          else:
            log('NO AssertionConsumerServiceURL sent in saml request')
            return ('<html><title>Error</title><body>'
                    'No AssertionConsumerServiceURL provided in'
                    ' SAMLRequest</body></html>')
          log('AssertionConsumerServiceURL: %s' %(acs_url))

      # We got a consumerservice URL, now redirect the browser back
      #to the GSA using that URL
      if acs_url is not None:
        cherrypy.response.status = 302
        location = ("%s?SAMLart=%s&RelayState=%s") % (acs_url,
                                                      rand_art,
                                                      urllib.quote(RelayState))
        cherrypy.response.headers["location"] = location
        if self.debug_flag:
          log('Redirecting to: %s' %(location))
          log('-----------  LOGIN END  -----------')
    else: 
      if self.debug_flag:
        log ('Attempting to use Referer Header with Artifact [%s]'%(rand_art))
      str_referer = cherrypy.request.headers['Referer']
      parsed_URL = urlparse(str_referer)
      hostname = parsed_URL.hostname
      cherrypy.response.status = 302
      # redirect back to the GSA and add on the artifact,relaystate
      # redirect always to http://gsa.yourdomain.com/SamlArtifactConsumer
      # if https is required, modify the line below to https
      location = ('https://%s/SamlArtifactConsumer?SAMLart=%s&RelayState=%s'
                  % (hostname, rand_art, urllib.quote(RelayState)))
      cherrypy.response.headers['location'] = location
      if self.debug_flag:
        log('Redirecting to: %s' %(location))
      log('-----------  LOGIN END  -----------')
      return          
    return ('<html><title>Error</title><body><h2>Unable to proceed: no '
            'Referer Header or'
            ' AssertionConsumerServiceURL</h2></body></html>')
  login.exposed = True

  # The SAML artifiact service.
  # The GSA calls this and provides it the SAMLArt= ID that the auth.py sent
  # back to the GSA during the
  # redirect from  /login
  # Once it has the SAMLArt=, it will lookup in a table for the authenticated
  # user this artifact corresponds with
  def artifact_service(self):
    # Get the timestamp of now in the SAML format
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    authn_request = cherrypy.request.body.read()

    if self.debug_flag:
      log('-----------  ARTIFACT BEGIN  -----------')
      log('artifact_service request: %s' %(authn_request))

      # the SAML Request looks something like this:
      #        request = ("<soapenv:Envelope xmlns:soapenv=
      #            "http://schemas.xmlsoap.org/soap/envelope/\"
      #            "xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\"
      #            "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
      #            "<soapenv:Body>"
      #              "<samlp:ArtifactResolve"
      #              "ID=\"fdlgheibhbadpjcchojcgbaenjmgfdoinbmdgola\""
      #              "IssueInstant=\"2008-07-09T15:22:54Z\""
      #              "Version=\"2.0\""
      #              "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\""
      #              "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\">"
      #              "<saml:Issuer xmlns:saml=\
      #                    "urn:oasis:names:tc:SAML:2.0:assertion\">
      #                    google.com</saml:Issuer>"
      #              "<samlp:Artifact>
      #                a17809fb8401a4480959bc20fd17d4708
      #               </samlp:Artifact>"
      #               "</samlp:ArtifactResolve>"
      #               "</soapenv:Body>"
      #               "</soapenv:Envelope>")

      # Now parse out the SAML ID number, artifact

      xmldoc = xml.dom.minidom.parseString(authn_request)
      samlp = xmldoc.getElementsByTagName('samlp:ArtifactResolve')

      saml_id = None
      saml_artifact = None

      for node in samlp:
        if (node.nodeName == 'samlp:ArtifactResolve'):
          saml_id = samlp[0].attributes["ID"].value
          samlartifact = node.getElementsByTagName('samlp:Artifact')
          for n_issuer in samlartifact:
            cnode = n_issuer.childNodes[0]
            if cnode.nodeType == node.TEXT_NODE:
              saml_artifact = cnode.nodeValue

      if self.debug_flag:
        log('artifact_service Artifact %s' %(saml_artifact))
        log('artifact_service ID %s' %(saml_id))

      # See if the artifiact corresponds with a user that was authenticated
      username = self.authnsessions[saml_artifact]

      # If there is no username assoicated with the artifact, we should
      # show a SAML error response...this is a TODO, for now just show a message
      if (username is None):
        log('ERROR: No user assoicated with: %s' % saml_artifact)
        return 'ERROR: No user assoicated with: %s' % saml_artifact
    
      # Now clear out the table
      self.authnsessions[saml_artifact] = None
      
      rand_id = self.getrandom_samlID()
      rand_id_assert = self.getrandom_samlID()

      # Writeup the ArtifactResponse and set the username back
      #along with the ID sent to it (i.e, the saml_id).
      response = ('<SOAP-ENV:Envelope '
                  'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
                  '<SOAP-ENV:Body><samlp:ArtifactResponse '
                  'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
                  'xmlns="urn:oasis:names:tc:SAML:2.0:assertion" '
                  'ID="%s" Version="2.0" '
                  'InResponseTo="%s" IssueInstant="%s">'
                  '<Issuer>%s</Issuer><samlp:Status><samlp:StatusCode '
                  'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
                  '</samlp:Status><samlp:Response ID="%s" '
                  'Version="2.0" IssueInstant="%s">'
                  '<samlp:Status><samlp:StatusCode '
                  'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
                  '</samlp:Status><Assertion Version="2.0" ID="%s" '
                  'IssueInstant="%s"><Issuer>%s</Issuer><Subject>'
                  '<NameID>%s</NameID></Subject><AuthnStatement '
                  'AuthnInstant="%s"><AuthnContext><AuthnContextClassRef> '
                  'urn:oasis:names:tc:SAML:2.0:ac:classes:'
                  'PasswordProtectedTransport '
                  '</AuthnContextClassRef></AuthnContext></AuthnStatement>'
                  '</Assertion></samlp:Response></samlp:ArtifactResponse>'
                  '</SOAP-ENV:Body>'
                  '</SOAP-ENV:Envelope>' % (rand_id, saml_id,now,
                                            self.saml_issuer, saml_id,now,
                                            rand_id_assert, now,
                                            self.saml_issuer, username, now))

      if self.debug_flag:
        log('artifact_service response %s' %(response))
        log('-----------  ARTIFACT END   -----------')

      return response
  artifact_service.exposed = True

  # The SAML Authorization service (/authz) called by the GSA to query to see 
  # if individual URLs are authorized for a given user. Both the username 
  # and the URL to check for is passed in

  def authz(self):

    authz_request = cherrypy.request.body.read()

    if self.debug_flag:
      log('-----------  AUTHZ BEGIN  -----------')
      log('AUTHZ Request: %s' % authz_request)
      
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    # The request should look something like
    #    request = ("<soapenv:Envelope xmlns:soapenv=\
    #        "http://schemas.xmlsoap.org/soap/envelope/\"
    #               "xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\"
    #               "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
    #               "<soapenv:Body>"
    #               "<samlp:AuthzDecisionQuery ID=
    #                    \"dbppegngllhegcobmfponljblmfhjjiglbkbmmco\"
    #               "IssueInstant=\"2008-07-09T15:22:55Z\""
    #               "Resource=\"secure.yourdomain.com/protected/page2.html\"
    #                        Version=\"2.0\"
    #               "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\""
    #               "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\">"
    #               "<saml:Issuer>google.com</saml:Issuer>"
    #               "<saml:Subject>"
    #               "<saml:NameID>user1</saml:NameID>"
    #               "</saml:Subject>"
    #               "<saml:Action Namespace=\"urn:oasis:names:tc:SAML:1.0:
    #                        action:ghpp\">GET</saml:Action>"
    #               "</samlp:AuthzDecisionQuery>"
    #               "<samlp:AuthzDecisionQuery ID=
    #                    \"eeppegngllhegcobmfabcnljblmfhrrniglbkbeed\"
    #               "IssueInstant=\"2008-07-09T15:22:55Z\""
    #               "Resource=\"secure.yourdomain.com/protected/page3.html\"
    #                        Version=\"2.0\"
    #               "xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\""
    #               "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\">"
    #               "<saml:Issuer>google.com</saml:Issuer>"
    #               "<saml:Subject>"
    #               "<saml:NameID>user1</saml:NameID>"
    #               "</saml:Subject>"
    #               "<saml:Action Namespace=\"urn:oasis:names:tc:SAML:1.0:
    #                        action:ghpp\">GET</saml:Action>"
    #               "</samlp:AuthzDecisionQuery>"    
    #               "</soapenv:Body>"
    #               "</soapenv:Envelope>")

    saml_id = None
    resource = None
    username = None

    # parse out the SAML AuthzRequest
    # If we don't know *for sure* if a user is allowed or not, send back an
    # indeterminate.  if the URL does *not* exist in the built in self.authz_db,
    # then we don't know if the user is allowed
    # or not for sure, then send back an Indeterminate.

    # GSA 6.0+ can request batch authorization where there can be multiple
    # samlp:AuthzDecisionQuery  in one request for several URLs
    # which means we have to responde back in one response for each request.
     
    # If we're using the internal authz system, parse out the inbound
    # request for the URI and use that to check against the local authz db

    xmldoc = xml.dom.minidom.parseString(authz_request)
    samlp = xmldoc.getElementsByTagName('samlp:AuthzDecisionQuery')

    response = ('<soapenv:Envelope '
                'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
                '<soapenv:Body>')   
 
    for node in samlp:
      if (node.nodeName == "samlp:AuthzDecisionQuery"):
        saml_id = node.attributes["ID"].value
        resource = node.attributes["Resource"].value
        samlName = node.getElementsByTagName("saml:NameID")
        for n_issuer in samlName:
          cnode= n_issuer.childNodes[0]
          if cnode.nodeType == node.TEXT_NODE:
            username = cnode.nodeValue
        # the SAML response and assertion are unique random ID numbers
        # back in the sring with the decision.        
        rand_id_saml_resp = self.getrandom_samlID()
        rand_id_saml_assert = self.getrandom_samlID() 

        decision = None

        if (self.use_fqdn_hosts == False):
          uri_loc = resource.find("/secure?page=");
          lresource = resource[uri_loc:uri_loc+30]
          decision = self.checkauthz(username, lresource)
        else:
          decision = self.checkauthz(username, resource)

        if self.debug_flag:
          log ('authz ID: %s' %(saml_id))
          log ('authz Resource: %s' %(resource))
          log ('authz samlName %s' %(username))
          log ('authz decision for resource %s [%s]' % (resource, decision))

        response = response + ('<samlp:Response '
             'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
             'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
             'ID="%s" Version="2.0" IssueInstant="%s">'
             '<samlp:Status><samlp:StatusCode '
             'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
             '</samlp:Status><saml:Assertion Version="2.0" '
             'ID="%s" IssueInstant="%s">'
             '<saml:Issuer>%s</saml:Issuer><saml:Subject>'
             '<saml:NameID>%s</saml:NameID></saml:Subject>'
             '<saml:AuthzDecisionStatement Resource="%s" '
             'Decision="%s"><saml:Action '
             'Namespace="urn:oasis:names:tc:SAML:1.0:action:ghpp">'
             'GET</saml:Action></saml:AuthzDecisionStatement>'
             '</saml:Assertion></samlp:Response>') % (rand_id_saml_resp,now, 
                                                      rand_id_saml_assert, 
                                                      now, decision, username,
                                                      resource, decision)

    response = response + '</soapenv:Body></soapenv:Envelope>'    

    if self.debug_flag:
      log('authz response %s' %(response))
      log('-----------  AUTHZ END  -----------')
    return response
  authz.exposed = True

def log(msg):
  print ('%s %s') % (datetime.datetime.now(), msg)  

# Utility routintes to base64 encode/decode and inflate/deflate
# pg 16-17:
# http://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
# from: http://stackoverflow.com/questions/1089662/
#                                    python-inflate-and-deflate-implementations

def decode_base64_and_inflate(b64string):
  decoded_data = base64.b64decode(b64string)
  return zlib.decompress(decoded_data, -15)

def deflate_and_base64_encode(string_val):
  zlibbed_str = zlib.compress(string_val)
  compressed_string = zlibbed_str[2:-4]
  return base64.b64encode(compressed_string)


# **********************  START MAIN

def main(argv):
  pass

if __name__ == '__main__':
  # Default listen port
  cherrypy.server.socket_port = 28080
  cherrypy.server.socket_host = '0.0.0.0'
  protocol = "http"
  debug_flag = False
  consumer_mech = "referer"
  use_fqdn_hosts = False
  saml_issuer = "authn.py"
  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["debug", "use_fqdn_hosts", "use_ssl", "port=",
                                "consumer_mech=", "saml_issuer"])
  except getopt.GetoptError:
    print ('Invalid arguments: valid args --debug --use_fqdn_hosts --use_ssl '
           '--port=<port> --consumer_mech=(saml|referer|static) '
           '--saml_issuer=<issuer>')
    sys.exit(1)
  cherrypy.config.update({'global':{'log.screen': False}})   
  for opt, arg in opts:
    if opt == "--debug":
      debug_flag = True
      cherrypy.config.update({'global':{'log.screen': True}})                  
    if opt == "--use_fqdn_hosts":
      use_fqdn_hosts = True
    if opt == "--consumer_mech":
      if arg == "saml":
        conuserm_mech = "saml"
      elif arg == "static":
        consumer_mech = "static"
      else:
        consumer_mech = "referer"
    if opt == "--saml_issuer":
      saml_issuer = arg
    if opt == "--use_ssl":
      protocol = "https"
      cherrypy.config.update({"global": {
          "server.ssl_certificate": "ssl.crt",
          "server.ssl_private_key": "ssl.key",}})
    if opt == "--port":
      port = int(arg)
      cherrypy.config.update({"global": {"server.socket_port": port}})
      
cherrypy.quickstart(AuthN(protocol, debug_flag, use_fqdn_hosts, consumer_mech,
                          saml_issuer))
