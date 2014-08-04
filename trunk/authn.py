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
#
# This code is not supported by Google
#


"""Simple web server for testing the Authn

usage:
  ./authn.py
    --debug           Show debug logs

    --use_ssl         Start with SSL using ssl.crt and ssl.key in PEM format;
                      the ssl.key must not be password protected

    --port=           Set the listener port of the cherrypy webserver
                      (default 28080)

    --consumer_mech=  Specifies which mechanism to use to figure out where
                      to redirect the SAMLRequest back to.
                      The options for this switch:
                      (saml|static)  default saml

                      saml: Usually this information is
                      contained in the SAMLRequest's decoded
                      samlp:AuthnRequest/AssertionConsumerServiceURL parameter)

                      static: hardcoded return path (defined in def login())
                      Must specify --gsa_host for this option.

    --gsa_host=       The Fully quaified hostname of the GSA for static redirecting.
                      Using the qualified hostname is critical for this mechanism
                      to work (otherwise the cookies will not be transmitted
                      properly)

    --saml_issuer=    set the SAML_issuer ID parameter
                      Default is set to authn.py

    --binding=        Specifies which SAML binding to use. The options are
                      (artifact|post) default artifact.

                      artifact: This script will expose /login and
                      /artifact_service, and the GSA should be configured to use
                      these appropriately.

                      post: This script will expose /login, and the GSA should
                      be configured to use this /login as well as a public key
                      associated with the private key given by --key_file.

    --key_file=       The private key in PEM format to use for POST binding. A
                      prompt will appear for the password.

    --key_blank_pwd   Assume a blank password for the private key for POST
                      binding and don't prompt for one.
                      
    --use_legacy      Use legacy AuthN on the GSA (i.e, security-manager 
                      disabled on 6.2 GSA).  Setting should only be used with
                      --consumer_mech=static --gsa_host=

    --exclude_keyinfo Exclude the <ds:KeyInfo/> node

This script runs a web server on port 28080 that allows you to test the
Authn SPI on the Google Search Appliance.

The authn.py script is basically a SAML IDP server which prompts the users
with FORM username/password info and then complies with SAML2.0
specifications for POST and artifact binding.

It is not designed to handle full production load but rather just as a
proof-of-concept.

SETUP and RUN configuration.
   After startup, you can view the configured username and passwords
   by visiting http://idp.yourdomain.com:28080/  (if idp.yourdomain.com is
   where authn.py is running)


   self.user_db = {'user1':'password1', 'user2':'password1',
                      'gsa1':'password1'}

   On the GSA, set it up for crawling:
            Crawl&Index-->CrawlURLs:
                        StartURLs:   http://idp.yourdomain.com:28080/
                        Follow:      http://idp.yourdomain.com:28080/

            Serving-->Access Control
                          IDP Entity ID:
                            authn.py
                          User Login URL:
                            http://idp.yourdomain.com:28080/login
                          Artifact Service URL (only if using artifact binding):
                            http://idp.yourdomain.com:28080/artifact_service
                          Public Key of IDP (only if using post binding):
                            <public key>
           (check Disable prompt for Basic authentication or NTLM authentication)

For POST binding, this script uses libxml2, the Python libxml2 bindings,
xmlsec, and PyXMLSec. The user must install these in advance in order to use
POST binding.
PyXMLSec is available at http://pyxmlsec.labs.libre-entreprise.org/

# apt-get install python-cherrypy3 libxmlsec1-openssl libxml2 python-libxml2 python-libxml2-dbg  
                  libxml2-dev  libxslt-dev libltdl-dev

#then a manual install of xmlsec from source as sudo
# http://www.aleksey.com/xmlsec/download/xmlsec1-1.2.18.tar.gz
# gzip -d
# untar
# cd xmlsec...
# sudo ./configure
# sudo make
# sudo make install

#then install pyxmlsec from source as sudo
# svn checkout svn://labs.libre-entreprise.org/svnroot/pyxmlsec
# cd trunk
# ./setup.py
#  (select build, select openssl)
# ./setup.py 
# (select install)

This script requires the cherrypy v3 to be installed (v2 gives an error since
quickstart is not available).

http://www.cherrypy.org/

Also see:
code.google.com/apis/searchappliance/documentation/64/authn_authz_spi.html
"""


import base64
import datetime
import getopt
import getpass
import md5
import random
import sys
import time
import urllib
from urlparse import urlparse
import xml.dom.minidom
import zlib
import cherrypy
from xml.sax.saxutils import escape
from socket import gethostname
import cgi

class SignatureError(Exception):
  pass

class AuthN(object):

  def __init__(self, port, protocol, debug_flag, consumer_mech,
               saml_issuer, gsa_host, binding, cert_file, key_file, key_pwd, use_legacy, exclude_keyinfo):
    self.realm = "authn"
    self.protocol = protocol
    self.debug_flag = debug_flag
    self.use_legacy = use_legacy
    self.consumer_mech = consumer_mech
    if gsa_host:
      self.gsa_host = gsa_host
    self.binding = binding
    self.cert_file = cert_file
    self.key_file = key_file
    self.key_pwd = key_pwd
    self.exclude_keyinfo = exclude_keyinfo

    log ('--------------------------------')
    log ('-----> Starting authn.py <------')
    log ('--------------------------------')

    # authentication database in the form of:
    #  username: [password, [group1, group2,...]]
    self.user_db = {'administrator@ESODOMAIN': ['pass1', []],
                    'administrator': ['pass2', []],
                    'user2@esodomain': ['pass1', ['esodomaingrp with space']],
                    'esodomain\gsa':   ['pass1', ['ESODOMAIN\gShare1', 'ESODOMAIN\gShare2']]}

    # stores the authenticated sessions
    self.authnsessions = {}
    self.recipients = {}
    self.login_request_ids = {}
    self.saml_issuer = saml_issuer

  #Main landing page
  def index(self):
    indexHTML = ('<html><title>Authn Landing Page</title>'
                 '<body><center>'
                 '<h3>Landing page for SPI authn.py</h3>'
                 '<p>'
                 'The following usernames/passwords are available for testing<br>'
                 '</p><p>')

    # Generate a username/password table
    indexHTML += ('<table  border="1" cellpadding="5" cellspacing="0">'
                  '<tr><th>Username</th><th>Password</th></tr>')

    for user in self.user_db:
      indexHTML += ('<tr><td>' + user + '</td><td>' + self.user_db[user][0] +
                    '</td><td>' + "".join(self.user_db[user][1]) +
                    '</td></tr>')
    indexHTML += ('</table>'
                  '<p><a href="login">Login</a>'
                  '</center></body></html>')
    return indexHTML
  index.exposed = True


  # Generates SAML 2.0 IDs randomly.
  def getrandom_samlID(self):
    return random.choice('abcdefghijklmnopqrstuvwxyz') + hex(random.getrandbits(160))[2:-1]

  # 
  def get_saml_namespace(self, xmldoc, tagname):
    a = xmldoc.getElementsByTagName('samlp:%s' % tagname)
    if a != []:
      return ("samlp", "saml", a)
    a = xmldoc.getElementsByTagName('saml2p:%s' % tagname)
    if a != []:
      return ("saml2p", "saml2", a)

    log("exotic namespace")
    #  TODO get the name space and return it
    return ("", "", [])

    
  # Collects the SAMLRequest, RelayState and prompts uses FORM to prompt the
  # user.
  def login(self,error = None, RelayState=None, SAMLRequest = None, SigAlg = None,
            Signature = None):
    log('-----------  LOGIN -----------')   
    if error == None:
      error = ""

    if not( RelayState is None):
      cherrypy.session['RelayState'] = RelayState
      log(' RelayState' + str(RelayState))
    if not (SAMLRequest is None):
      cherrypy.session['SAMLRequest'] = SAMLRequest
      log(' SAMLRequest' + str(SAMLRequest))

    return """<html><body>
         <center>
         <font color=red>%s</font></br>
               <form method="post" action="/authenticate">
               Username: <input type="text" name="username" value="" /><br />
               Password: <input type="password" name="password" /><br />
               <input type="submit" value="Log in" />
         </form>
               </center></body></html>""" %error
  login.exposed = True

  def authenticate(self, username=None, password=None):
    log('-----------  Authenticate -----------') 
    if (username == None or password == None or username == '' or password == ''):
      cherrypy.response.status = 302
      cherrypy.response.headers['location'] = '/login?error=specify username+password'
      return  

    try: 
      if password == self.user_db[username.lower()][0]:
        log('Authentication successful for ' + username.lower())
      else:
        cherrypy.response.status = 302
        cherrypy.response.headers['location'] = '/login?error=invalid username+password'
        return
    except KeyError:
      cherrypy.response.status = 302
      cherrypy.response.headers['location'] = '/login?error=invalid username+password'
      return
 
        
    RelayState = cherrypy.session.get('RelayState')
    SAMLRequest = cherrypy.session.get('SAMLRequest')

    if SAMLRequest is None:
      log('Received a request for authentication without SAMLRequest')
      log('-----------  Authenticate END  -----------')

      return ('<font color=\"darkgreen\">Authentication successful for: '
              '&quot;%s&quot;<br>However, SAMLRequest is None and we can\'t '
              'proceed' %username)

    # Now b64decode and inflate
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
    decoded_saml = decode_base64_and_inflate(SAMLRequest)
    xmldoc = xml.dom.minidom.parseString(decoded_saml)

    # Try to get the issuer and request id of the saml request
    saml_oissuer = None
    req_id = None
    (spprefix, sprefix, samlpnode) = self.get_saml_namespace(xmldoc, 'AuthnRequest')
    log('using prefix: %s and %s' % (spprefix, sprefix))

    for node in samlpnode:
      if node.nodeName == '%s:AuthnRequest' % spprefix:
        if samlpnode[0].hasAttribute('ID'):
          req_id = samlpnode[0].attributes['ID'].value
        samliss = node.getElementsByTagName('%s:Issuer' % sprefix)
        for n_issuer in samliss:
          cnode = n_issuer.childNodes[0]
          if cnode.nodeType == node.TEXT_NODE:
            saml_oissuer = cnode.nodeValue

    if not req_id:
      log('Error: could not parse request SAML request ID')
      return 'Error: could not parse request SAML request ID'

    if self.binding == 'artifact':
      # Generate a random artifiact ID and save it to recall later
      rand_art = self.getrandom_samlID()

      # Stash the artifact associated with the user it in a table so that
      # when asked who an artifact belongs to, we know who the user is.
      self.authnsessions[rand_art] = (username)

      if self.debug_flag:
        log('Parsed SAMLRequest: %s' %xmldoc.toprettyxml())

      self.login_request_ids[rand_art] = req_id

    # We can either use:
    # 1) Decode/decompress the unsigned SAMLRequest to figure out the AssertionConsumerServiceURL
    # 2) Statically redirect: provided as a command line argument
    if self.consumer_mech == 'static':
      if (self.use_legacy):
        log('Static redirect for Legacy AuthN ')
        static_redirect = 'https://' + self.gsa_host + '/SamlArtifactConsumer' 
      else:
        log('Static redirect for SecurityManager AuthN ')
        static_redirect = 'https://' + self.gsa_host + \
         '/security-manager/samlassertionconsumer'       

      if self.binding == 'artifact':
        self.recipients[rand_art] = static_redirect
        if self.debug_flag:
          log('Attempting to use STATIC  Header with Artifact [%s]'%(rand_art))
        # Redirect back to the GSA and add on the artifact,relaystate
        if (RelayState is None):
          location = ('%s?SAMLart=%s'
                      % (static_redirect, rand_art))
        else:
          location = ('%s?SAMLart=%s&RelayState=%s'
                      % (static_redirect, rand_art, urllib.quote(RelayState)))
      elif self.binding == 'post':
        location = static_redirect
      if self.debug_flag:
        log( 'Redirecting to: %s' %(location))
      log('-----------  LOGIN END  -----------')

    elif self.consumer_mech == 'saml':
      # Otherwise
      if self.debug_flag:
        log('Attempting to parse SAML AssertionConsumerServiceURL')

      acs_url = None
      for node in samlpnode:
        if node.nodeName == '%s:AuthnRequest' % spprefix:
          if samlpnode[0].hasAttribute('AssertionConsumerServiceURL'):
            acs_url = samlpnode[0].attributes \
                          ['AssertionConsumerServiceURL'].value
          else:
            log('NO AssertionConsumerServiceURL sent in saml request')
            return ('<html><title>Error</title><body>'
                    'No AssertionConsumerServiceURL provided in'
                    ' SAMLRequest</body></html>')
          if self.debug_flag:
            log('login Parsed AssertionConsumerServiceURL: %s' %(acs_url))
          samliss = node.getElementsByTagName('%s:Issuer' % sprefix)
          for n_issuer in samliss:
            cnode = n_issuer.childNodes[0]
            if cnode.nodeType == node.TEXT_NODE:
              saml_oissuer = cnode.nodeValue

      # We got a consumerservice URL, now redirect the browser back
      #to the GSA using that URL
      if acs_url:
        if self.binding == 'artifact':
          self.recipients[rand_art] = acs_url
          if (RelayState is None):
            location = ("%s?SAMLart=%s") % (acs_url,rand_art)
          else:
            location = ("%s?SAMLart=%s&RelayState=%s")%(acs_url,
                                                        rand_art,
                                                        urllib.quote(RelayState))
        elif self.binding == 'post':
          location = acs_url
        if self.debug_flag:
          log('Redirecting to: %s' %(location))
          log('-----------  LOGIN END  -----------')

    if self.binding == 'artifact':
      cherrypy.response.status = 302
      cherrypy.response.headers['location'] = location
      log('Artifact Redirecting to: %s' %(location))
      return ('<html><title>Error</title><body><h2>Unable to redirect'
              '</h2></body></html>')
    elif self.binding == 'post':
      now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
      one_min_from_now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()+60))
      samlresp = self._generate_response(now, one_min_from_now, username,
                                         req_id, location,
                                         saml_oissuer, True)

      log(xml.dom.minidom.parseString(samlresp).toprettyxml())

      if (self.debug_flag):
        onload_action = '<body>'
      else:
        onload_action = '<body onload="document.forms[0].submit()">'
    
      resp = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"'
              'http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
              '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
        '<head>'
          '<script>'
        '</script>'
        '</head>'
              '%s'
        '<p>Login Successful</p>'
              '<p>'
              '<strong>Note:</strong> Users do not see the encoded SAML response.  This page is'
              ' normally posted immediately <em>body onload=document.forms[0].submit()</em>'
              '</p>'
              '<form action="%s" method="post">'
              '<div>'
              '<li>RelayState: <input type="text" name="RelayState" value="%s"/></li>'
              '<li>SAMLResponse: <input type="text" name="SAMLResponse" value="%s"/></li>'
              '</div>'
              '<div>'
        '<p><em>click continue within  30 seconds of ' +  now + '</em></p>'
              '<input type="submit" value="Continue"/>'
              '</div>'
              '</form>'
        '<br/>'
              '<p>Decoded SAMLResponse</p>'
        '<textarea rows="75" cols="120" style="font-size:10px">%s</div>'
              '</body></html>') % (onload_action,location, RelayState, base64.encodestring(samlresp),cgi.escape(xml.dom.minidom.parseString(samlresp).toprettyxml()))
      log(resp)

      return resp
  authenticate.exposed = True

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
    (spprefix, sprefix, samlp) = self.get_saml_namespace(xmldoc, 'ArtifactResolve')

    log('-----------  ARTIFACT BEGIN  -----------')
    if self.debug_flag:
      log('artifact_service request: %s' %(xmldoc.toprettyxml()))

    saml_id = None
    saml_artifact = None
    saml_oissuer = None

    for node in samlp:
      if (node.nodeName == '%s:ArtifactResolve' % spprefix):
        saml_id = samlp[0].attributes["ID"].value
        samlartifact = node.getElementsByTagName('%s:Artifact' % spprefix)
        for n_issuer in samlartifact:
          cnode = n_issuer.childNodes[0]
          if cnode.nodeType == node.TEXT_NODE:
            saml_artifact = cnode.nodeValue
        samliss = node.getElementsByTagName('%s:Issuer' % sprefix)
        for n_issuer in samliss:
          cnode = n_issuer.childNodes[0]
          if cnode.nodeType == node.TEXT_NODE:
            saml_oissuer = cnode.nodeValue

      # See if the artifiact corresponds with a user that was authenticated
    username = self.authnsessions[saml_artifact]

    # If there is no username assoicated with the artifact, we should
    # show a SAML error response...this is a TODO, for now just show a message
    if (username is None):
      log('ERROR: No user associated with: %s' % saml_artifact)
      return 'ERROR: No user associated with: %s' % saml_artifact

    current_recipient = self.recipients[saml_artifact]
    login_req_id = self.login_request_ids[saml_artifact]
    # Now clear out the table
    self.authnsessions[saml_artifact] = None
    self.recipients[saml_artifact] = None
    self.login_request_ids[saml_artifact] = None
    rand_id = self.getrandom_samlID()
    rand_id_assert = self.getrandom_samlID()

    if self.debug_flag:
      log('artifact_service Artifact %s' %(saml_artifact))
      log('artifact_service ID %s' %(saml_id))
      log('artifact_service recipient %s' %(current_recipient))
      log('artifact_service login_req_id %s' %(login_req_id))

    five_sec_from_now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()+5) )
    resp_rand_id = self.getrandom_samlID()

    saml_response = self._generate_response(now, five_sec_from_now, username,
                                            login_req_id, current_recipient,
                                            saml_oissuer, False)
    # Writeup the ArtifactResponse and set the username back
    #along with the ID sent to it (i.e, the saml_id).
    response = ('<SOAP-ENV:Envelope '
                'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
                '<SOAP-ENV:Body>'
                '<samlp:ArtifactResponse '
                'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
                'xmlns="urn:oasis:names:tc:SAML:2.0:assertion" '
                'ID="%s" Version="2.0" InResponseTo="%s" IssueInstant="%s"> '
                '<Issuer>%s</Issuer>'
                '<samlp:Status>'
                '<samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
                '</samlp:Status>'
                '%s'
                '</samlp:ArtifactResponse>'
                '</SOAP-ENV:Body>'
                '</SOAP-ENV:Envelope>') % (rand_id, saml_id, now,
                                           self.saml_issuer, saml_response)
    if self.debug_flag:
      xmldoc = xml.dom.minidom.parseString(response)
      log('artifact_service response %s' %(xmldoc.toprettyxml()))
    log('-----------  ARTIFACT END   -----------')
    return response
  artifact_service.exposed = True

  def _generate_response(self, now, later, username, login_req_id, recipient, audience, signed):
    resp_rand_id = self.getrandom_samlID()
    rand_id_assert = self.getrandom_samlID()
    sigtmpl = ''
    if signed:
      if (self.exclude_keyinfo):
        key_info = ''
      else:
        key_info = ('<ds:KeyInfo>'
                    '<ds:X509Data>'
                    '<ds:X509Certificate></ds:X509Certificate>'
                    '</ds:X509Data>'
                    '</ds:KeyInfo>')

      # if the response is to be signed, create a signature template
      sigtmpl = ('<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
                 '<ds:SignedInfo>'
                 '<ds:CanonicalizationMethod '
                 'Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315" />'
                 '<ds:SignatureMethod '
                 'Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1" />'
                 '<ds:Reference URI="#%s">'
                 '<ds:Transforms>'
                 '<ds:Transform Algorithm='
                 '"http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
                 '</ds:Transforms>'
                 '<ds:DigestMethod Algorithm='
                 '"http://www.w3.org/2000/09/xmldsig#sha1" />'
                 '<ds:DigestValue></ds:DigestValue>'
                 '</ds:Reference>'
                 '</ds:SignedInfo>'
                 '<ds:SignatureValue/>'
                 '%s'
                 '</ds:Signature>') % (resp_rand_id,key_info)
    grptmpl = ''
    if self.user_db[username][1]:
      log('looking for group info for user ' + username)
      grptmpl += '<saml:AttributeStatement>' + '<saml:Attribute Name="member-of">'
      for grp in self.user_db[username][1]:
        grptmpl += '<saml:AttributeValue>%s</saml:AttributeValue>' % grp
        log('found group: ' + grp)
      grptmpl += '</saml:Attribute>' + '</saml:AttributeStatement>'
    resp = ('<samlp:Response '
            'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            'ID="%s" Version="2.0" IssueInstant="%s" Destination="%s">'
            '<saml:Issuer>%s</saml:Issuer>'
            '<samlp:Status>'
            '<samlp:StatusCode '
            'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
            '</samlp:Status>'
            '<saml:Assertion '
            'Version="2.0" ID="%s" IssueInstant="%s">'
            '<saml:Issuer>%s</saml:Issuer>'
            '<saml:Subject>'
            '<saml:NameID>%s</saml:NameID>'
            '<saml:SubjectConfirmation '
            'Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
            '<saml:SubjectConfirmationData '
            'InResponseTo="%s" Recipient="%s" NotOnOrAfter="%s"/>'
            '</saml:SubjectConfirmation>'
            '</saml:Subject>'
            '<saml:Conditions NotBefore="%s" NotOnOrAfter="%s">'
            '<saml:AudienceRestriction>'
            '<saml:Audience>%s</saml:Audience>'
            '</saml:AudienceRestriction>'
            '</saml:Conditions>'
            '<saml:AuthnStatement AuthnInstant="%s" SessionIndex="%s">'
            '<saml:AuthnContext>'
            '<saml:AuthnContextClassRef>'
            'urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport'
            '</saml:AuthnContextClassRef>'
            '</saml:AuthnContext>'
            '</saml:AuthnStatement>'
            '%s'
            '</saml:Assertion>'
            '%s'
            '</samlp:Response>') % (resp_rand_id, now, recipient,
                                    self.saml_issuer, rand_id_assert, now,
                                    self.saml_issuer, username,
                                    login_req_id, recipient, later,
                                    now, later, audience,
                                    now, rand_id_assert, grptmpl, sigtmpl)
    if signed:
      # hack DTD that lets xmlsec know the ID field name (pyxmlsec doesn't have
      # a method that lets us specify this)
      resp = '<!DOCTYPE samlp:Response [<!ATTLIST samlp:Response ID ID #IMPLIED>]>' + resp
      return self._signXML(resp)
    return resp

  def _signXML(self, xml):
    import libxml2
    import xmlsec
    dsigctx = None
    doc = None
    try:
      # initialization
      libxml2.initParser()
      libxml2.substituteEntitiesDefault(1)
      if xmlsec.init() < 0:
        raise SignatureError('xmlsec init failed')
      if xmlsec.checkVersion() != 1:
        raise SignatureError('incompatible xmlsec library version %s' %
                             str(xmlsec.checkVersion()))
      if xmlsec.cryptoAppInit(None) < 0:
        raise SignatureError('crypto initialization failed')
      if xmlsec.cryptoInit() < 0:
        raise SignatureError('xmlsec-crypto initialization failed')

      # load the input
      doc = libxml2.parseDoc(xml)
      if not doc or not doc.getRootElement():
        raise SignatureError('error parsing input xml')
      node = xmlsec.findNode(doc.getRootElement(), xmlsec.NodeSignature,
                             xmlsec.DSigNs)
      if not node:
        raise SignatureError("couldn't find root node")

      # load the private key
      key = xmlsec.cryptoAppKeyLoad(self.key_file, xmlsec.KeyDataFormatPem,
                                    self.key_pwd, None, None)
      if not key:
        raise SignatureError('failed to load the private key %s' % self.key_file)

      if xmlsec.cryptoAppKeyCertLoad(key, self.cert_file, xmlsec.KeyDataFormatPem) < 0:
        print "Error: failed to load pem certificate \"%s\"" % self.cert_file
        return self.cleanup(doc, dsigctx)

      keymngr = xmlsec.KeysMngr()
      xmlsec.cryptoAppDefaultKeysMngrInit(keymngr)
      xmlsec.cryptoAppDefaultKeysMngrAdoptKey(keymngr, key)
      dsigctx = xmlsec.DSigCtx(keymngr)

      if key.setName(self.key_file) < 0:
        raise SignatureError('failed to set key name')

      # sign
      if dsigctx.sign(node) < 0:
        raise SignatureError('signing failed')
      signed_xml = doc.serialize()

    finally:
      if dsigctx:
        dsigctx.destroy()
      if doc:
        doc.freeDoc()
      xmlsec.cryptoShutdown()
      xmlsec.shutdown()
      libxml2.cleanupParser()

    return signed_xml


def log(msg):
  print ('[%s] %s') % (datetime.datetime.now(), msg)

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


# -------
# Main
# -------------

def main():
  # Default listen port
  cherrypy.server.socket_port = 28080
  cherrypy.server.socket_host =  '0.0.0.0'
  protocol = "http"
  debug_flag = False
  use_legacy = False
  consumer_mech = "saml"
  saml_issuer = "authn.py"
  gsa_host = None
  binding = "artifact"
  key_file = None
  key_pwd = None
  cert_file = None
  exclude_keyinfo = False

  def usage():
    print ('\nUsage: authn.py --debug --use_ssl '
           '--port=<port> --consumer_mech=(saml|static) '
           '--saml_issuer=<issuer> --gsa_host=<gsa_host> '
           '--binding=(artifact|post) --key_file=<key_file> --cert_file=<cert_file> '
           '--key_blank_pwd --use_legacy --exclude_keyinfo\n')

  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["debug", "use_ssl", "port=",
                                "consumer_mech=", "saml_issuer=", "gsa_host=",
                                "binding=", "key_file=", "cert_file=", "key_blank_pwd",
                                "use_legacy", "exclude_keyinfo"])
  except getopt.GetoptError:
    usage()
    sys.exit(1)

  cherrypy.config.update({'global':{'log.screen': False, "tools.sessions.on": "True"}})
  for opt, arg in opts:
    if opt == "--debug":
      debug_flag = True
      cherrypy.config.update({'global':{'log.screen': True}})
    if opt == "--consumer_mech":
      if arg == "static":
        consumer_mech = "static"
    if opt == "--gsa_host":
      gsa_host = arg
    if opt == "--saml_issuer":
      saml_issuer = arg
    if opt == "--use_ssl":
      protocol = "https"
      cherrypy.config.update({"global": {
          "server.ssl_certificate": "ssl.crt",
          "server.ssl_private_key": "ssl.key"}})
    if opt == "--port":
      port = int(arg)
      cherrypy.config.update({"global": {"server.socket_port": port}})
    if opt == "--binding":
      binding = arg
    if opt == "--key_file":
      key_file = arg
    if opt == "--cert_file":
      cert_file = arg
    if opt == "--key_blank_pwd":
      key_pwd = ''
    if opt == "--use_legacy":
      use_legacy = True
    if opt == "--exclude_keyinfo":
      exclude_keyinfo = True

  if consumer_mech == "static":
    if gsa_host is None:
      log ("Please specify --gsa_host option for consumer_mech=static")
      usage()
      sys.exit(1)
  else:
    log ("ignoring gsa_host")
    gsa_host = None

  if binding == 'post':
    try:
      import libxml2
      import xmlsec
    except ImportError:
      log('POST binding is being used, but the Python bindings for libxml2 and'
          'xmlsec are not both available.')
      sys.exit(1)
    if not key_file:
      log('No private key specified to use for POST binding.')
      usage()
      sys.exit(1)
    elif key_pwd is None:
      key_pwd = getpass.getpass('Password for %s: ' % key_file)
    if not cert_file:
      log('Specify a public key (--cert_file=)')
      usage()
      sys.exit(1)

  cherrypy.quickstart(AuthN(cherrypy.server.socket_port, protocol, debug_flag,
                            consumer_mech, saml_issuer, gsa_host, binding,cert_file,
                            key_file, key_pwd, use_legacy, exclude_keyinfo))

if __name__ == '__main__':
  main()