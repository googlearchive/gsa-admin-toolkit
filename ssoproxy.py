#!/usr/bin/python

# Copyright (C) 2009 Google Inc.
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


"""SSO Proxy page for secure crawling and serving through the Google Search Appliance (GSA).

usage:  ./ssoproxy.py 
                       --debug      (show debug logs)
                       --use_ssl    (start with SSL using ssl.crt and ssl.key in PEM format;
                                     the ssl.key must not be password protected)
                       --port=      (set the listener port of the cherrypy webserver)

This script runs a web server thats designed to return the forms-authentication SSO cookie to the GSA.  
The GSA can then use those cookies to crawl secure content servers.

Normally, a GSA's administrator will train the appliance and run through the SSO rule-creation so that the GSA
interacts with the SSO system's login and results page directly.  Sometimes its not feasible for the GSA to interact
directly with the SSO login pages if it contains javascript or if the rules post various dynamic parameters
in the query string.

This script is designed to act as an intermediary between the GSA and an SSO system.  Its sole purpose is to
show a login form, collect a user/gsa's username/password, login by itself into the SSO system and then return 
the cookie to the browser or GSA.

The expectation is that the GSAs administrator would edit this file and customize it for the SSO system thats 
in place in the infrastructure.  At the core, the /doLogin method should POST the collected username and password
to the SSO system with all the form parameters/headers normally sent in. The SSO system should return the SSO cookies
to the script which inturn should set them a cookies back to the browser or GSA.

GSA administrators should understand how their SSO systems normally operate by using FireFox's LiveHTTPHeaders 
plugin and attempting an SSO system login.  The same POST parameters sent into the SSO system should be run
by this program manually.  Remember to clear all cookies on the browser prior to getting the capture or running
any tests.  The example this script comes with shows a SiteMinder-protected SSO/authentication scheme within 
a single domain. 

The administrator can run the script and attempt to login to the proxy using a browser directly.  The SSO cookie 
returned to browser should be valid such that it can be used to access a secure content server page without 
prompting.  Also, if the user does not have a valid SSO cookie the /checkAuth should redirect back to the 
login page.  Once the script is configured correctly and can be used by a browser for SSO login itself, the 
Crawling Rule on the GSA should look something like:

Under 
Crawling-->Forms Authentication
       Sample Protected URL:  http://proxyserver.yourdomain.com/checkAuth
       For pattern: http://yourcontentserver.yourdomain.com/
       
For serving, its advised the GSA administrator use the "Always Redirect to an External Login Server" option
and use their native SSO system or mandate the users always login to the SSO system *prior* to doing a 
secure search.  Or, if the SSO login page shown by the python script is sufficient, under you could set:

Serving --> Forms Authentication
       Login against following protected page:    http://proxyserver.yourdomain.com/checkAuth



http://proxyserver.yourdomain.com/              login page
http://proxyserver.yourdomain.com/doLogin       login page posts to doLogin which runs through all the steps the 
                                                SSO executes.  If its a successful login, the SSO cookies are sent
                                                back as cookies.
http://proxyserver.yourdomain.com/checkAuth     this page will redirect to the login page if an invalid or incorrect
                                                SSO cookie is sent in.
                                                

see  
http://docs.python.org/library/urllib2.html                                             
http://docs.python.org/library/httplib.html


Reference for form submission:
http://wwwsearch.sourceforge.net/ClientForm/

"""

__author__ = "salrashid123@gmail.com for Google on 2009.10.06"




import urllib
import cherrypy
import cookielib
import urllib2
import httplib
import getopt
import sys
import datetime


#edit these parameters for your environment and SSO system
SSO_COOKIE_NAME = "SMSESSION"
SSO_COOKIE_DOMAIN = ".esodomain2k3.com"
#the final, redirected SSO system login page (Siteminder example below)
SSO_LOGIN_URL = ("http://esotest.esodomain2k3.com:80/siteminderagent/forms/login.fcc?"
                 "TYPE=33554433&REALMOID=06-000d7583-9bb0-19f6-af1a-00017f00d004&"
                 "GUID=&SMAUTHREASON=0&METHOD=GET&"
                 "SMAGENTNAME=-SM-hjpE3OteK3xraxKO+pQ387eUvvdMoEFPO7DYOR1hPjGjtvd3bBfW47p4mvULrxSf&"
                 "TARGET=-SM-http://esotest.esodomain2k3.com/siteminder2/")
                 
#the protected page the user will get redirected to automatically after login 
SSO_PROTECTED_PAGE = "http://esotest.esodomain2k3.com/siteminder2/"
#the login page the proxy SSO system presents to the user.
SSO_LOGIN_PAGE =("<html><title>Proxy Login</title>"
                "<body><center><h2>Proxy Login Form</h2>"
                "<div id='msg'><font color=blue>%s</font></div>"
                "<form action='doLogin' method='post'>"
                "<table>"
                "<tr><td width=30>user:</td><td> <input type='text' name='user'></td></tr>"
                "<tr><td width=30>password:</td><td> <input type='password' name='password'></tr></td>"
                "</table>"
                "<INPUT TYPE=SUBMIT VALUE='submit'>"
                "</form>"
                "</center></body></html>" )


class SSO(object):
    
    def __init__(self,protocol, debug_flag):
        self.protocol = protocol
        self.debug_flag = debug_flag
    
    def index(self, msg = None):
        #show the login form
        self.debug ("Entering Login Page");
        str_hostname = cherrypy.request.headers['host']
        if (str_hostname.find(SSO_COOKIE_DOMAIN) == -1):
            login_msg = ("Incorrect Domain, need to access the Proxy using correct domain %s ") %SSO_COOKIE_DOMAIN
            return SSO_LOGIN_PAGE % (login_msg)
        if msg == None:
            msg = ""
        return SSO_LOGIN_PAGE % (msg)
    index.exposed = True


    def doLogin(self, user=None, password=None):
        #create a handler for the inbound cookies
        cj = cookielib.LWPCookieJar()    
        #urllib2 only notifies of the final page and not intermediate redirects...so
        #add a RedirectHandler class to capture when redirects happen, if necessary
        opener = urllib2.build_opener(RedirectHandler(self.debug_flag),urllib2.HTTPCookieProcessor(cj))
        urllib2.install_opener(opener)
        urlopen = urllib2.urlopen
        Request = urllib2.Request
        handle= httplib.HTTPMessage

        #add some siteminder specific POST parameters to send in...
        #you can figure out what these are by normally logging into the SSO system
        #and scanning the HTTP headers and form POST parameters (or look at the form html source)
        params = urllib.urlencode(
                                  {'USER': user, 
                                   'PASSWORD': password, 
                                   'smquerydata': "", 
                                   'SMENC': "ISO-8859-1", 
                                   'SMLOCALE': "US-EN", 
                                   'smagentname': "hjpE3OteK3xraxKO+pQ387eUvvdMoEFPO7DYOR1hPjGjtvd3bBfW47p4mvULrxSf", 
                                   'postpreservationdata': "", 
                                   'smauthreason': "0", 
                                   'target': SSO_PROTECTED_PAGE })
        headers = {"Accept": "text/plain, text/html"}

        self.debug ("Accessing Login page on final SSO system %s" %(SSO_LOGIN_URL))
        self.debug ("Posting Login Header  %s" %(headers))
        self.debug ("Posting Login POST data %s" %(params))
            
        try:
            req = Request(SSO_LOGIN_URL, params, headers)
            handle = urlopen(req)
        except IOError, e:
            self.debug (("Failed to connect to  %s") % SSO_LOGIN_URL)
            if hasattr(e, 'code'):
                self.debug (('Error - %s.') % e.code)
        #self.debug("Login RESPONSE CODE, HEADERS %s %s" %(handle.code, handle.info())

        self.debug("SSO login RESPONSE Headers %s" % (handle.info()))

        SSO_COOKIE = ""
        SSO_COOKIE_VALUE = ""
        for index, cookie in enumerate(cj):
            if cookie.name == SSO_COOKIE_NAME:
                SSO_COOKIE_VALUE = cookie.value
                
        #with siteminder, we'll only get an SMSESSION cookie if the login is valid
        #otherwise you should see if the redirected page is the target protected page we were 
        #originally after
        
        if SSO_COOKIE_VALUE == "":
            login_msg = "Invalid username/password"
            self.debug("Login FAILED (no sso cookie returned): %s" % (handle.info()))
            return SSO_LOGIN_PAGE % (login_msg)

        self.debug(("Landed at target login page %s") % (handle.geturl()))
        self.debug ("Login SUCCESS ")
        self.debug (("Setting SSO Cookie to browser/GSA in domain %s") %(SSO_COOKIE_DOMAIN))

        #now set the SMSESSION cookie on the domain
        SSO_COOKIE = SSO_COOKIE_NAME + "=" + SSO_COOKIE_VALUE + "; domain=" + SSO_COOKIE_DOMAIN 
        cherrypy.response.headers['Set-Cookie'] =  SSO_COOKIE

        return  "<html><body><h3>SSO Login successful</h3><br/> <li>SSO_COOKIE: %s  </body></html>" % ( SSO_COOKIE )
            
    doLogin.exposed = True
    
    def debug(self,deb_string):
        if (self.debug_flag):
            now = datetime.datetime.now()
            print  ("%s  %s") % (now, deb_string)

    #/checkAuth determines if the current user has an SSO cookie and if it is still valid
    #on the target SSO system.  The check is done by taking a cookie (if exists) and attempting
    #to retrieve the protected page on the SSO system.  If the cookie is invalid or non-existent,
    #the user is redirectd to the proxy login page /
    def checkAuth(self):
        #check to see if the SSO cookie is sent in and if its valid
        SSO_COOKIE_VALUE = ""
        if cherrypy.request.cookie.has_key(SSO_COOKIE_NAME):
            #so the cookie exists, now see if its valid
            #by navigating to the protected page and sending in that cookie
            SSO_COOKIE_VALUE = cherrypy.request.cookie[SSO_COOKIE_NAME].value
            cj = cookielib.LWPCookieJar()  
            rdhandle = RedirectHandler(self.debug_flag)
            opener = urllib2.build_opener(rdhandle,urllib2.HTTPCookieProcessor(cj))
            urllib2.install_opener(opener)
            urlopen = urllib2.urlopen
            Request = urllib2.Request
            handle= httplib.HTTPMessage
            #no need to post data
            params = urllib.urlencode({})
            #add the cookie as a parameter
            headers = {"Accept": "text/plain, text/html", "Cookie" : SSO_COOKIE_NAME + "=" + SSO_COOKIE_VALUE}
   
            try:
                req = Request(SSO_PROTECTED_PAGE, None , headers)
                handle = urlopen(req)
                #print handle.geturl()
            except IOError, e:
                self.debug ('Failed to connect to  "%s".') % url
                if hasattr(e, 'code'):
                    self.debug ('Error - %s.') % e.code
            else:
                #ok...so did we eventually land on the SSO_PROTECTED_PAGE?
                if (handle.geturl() ==  SSO_PROTECTED_PAGE):
                    debug_msg = ("Landed at target login page %s") % (handle.geturl())
                    self.debug(debug_msg)
                    return ("<html><title>Login COOKIE Valid</title<body><h3>Login Valid</h3> "
                            "<br/>%s</body></html>") %(SSO_COOKIE_VALUE)
                else:
                        self.debug ("SSO_COOKIE EXPIRED")
        else:
                self.debug ("SSO_COOKIE NOT PROVIDED")
                
                
        #either the cookie isn't valid or not provided, redirect user back to login page
        location = "%s://%s/%s" % (self.protocol, cherrypy.request.headers["host"], "")
        cherrypy.response.status = 302
        cherrypy.response.headers["location"] = location

    checkAuth.exposed = True
    
    
#class used to figure out if we if redirects occurred. from:
#http://diveintopython.org/http_web_services/redirects.html
class RedirectHandler(urllib2.HTTPRedirectHandler):
    
    debug_flag = False   
    
    def __init__(self, debug_flag = None):
        self.debug_flag = debug_flag
              
    def http_error_301(self, req, fp, code, msg, headers):  
        result = urllib2.HTTPRedirectHandler.http_error_301(self, req, fp, code, msg, headers)              
        result.status = code
        str_msg = ("301 redirecting to %s") % (req.get_full_url())      
        self.debug(str_msg)                    
        return result                                       

    def http_error_302(self, req, fp, code, msg, headers):   
        result = urllib2.HTTPRedirectHandler.http_error_302(self, req, fp, code, msg, headers)              
        result.status = code   
        str_msg = ("301 redirecting to %s") % (req.get_full_url())                            
        self.debug (str_msg)                          
        return result    
        
    def debug(self,deb_string):
        if (self.debug_flag):
            now = datetime.datetime.now()
            print  ("%s  %s") % (now, deb_string)
    
# START MAIN**********************************************
def main(argv):
  pass

#default listen port
cherrypy.server.socket_port = 18080


if __name__ == '__main__':
  protocol = "http"
  debug_flag = False
  try:
    opts, args = getopt.getopt(sys.argv[1:], None, ["debug","use_ssl","port="])
  except getopt.GetoptError:
    print "Invalid arguments"
    sys.exit(1)
  for opt, arg in opts:
    if opt == "--debug":
        debug_flag=True
    if opt == "--use_ssl":
      protocol = "https"
      cherrypy.config.update({"global": {
          "server.ssl_certificate": "ssl.crt",
          "server.ssl_private_key": "ssl.key", }})
    if opt == "--port":
      port = int(arg)
      cherrypy.config.update({"global": { "server.socket_port": port }})

cherrypy.server.socket_host = '0.0.0.0'
cherrypy.quickstart(SSO(protocol, debug_flag))
