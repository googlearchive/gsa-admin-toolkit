from optparse import OptionParser
from contextlib import contextmanager
import re
from urllib2 import build_opener, HTTPCookieProcessor, Request
from cookielib import CookieJar
from urllib import urlencode as enc


import logging
logging.basicConfig()
logger = logging.getLogger()
err, warn, info, debug = logger.error, logger.warning, logger.info, logger.debug

def setloglevel(verbosity):
    """The log_level argument is expected to be 1, 2, 3 and correpond
    to the number of -v on the command line. 

    Everything in this script is logged to stderr, the formatter in
    the debug level has much more details."""
    for h in logging.getLogger().handlers:
        logging.getLogger().removeHandler(h)

    level  = logging.WARN - 10 * (verbosity if verbosity else 0)
    format = ( "%(asctime)s %(levelname)5s %(name)s %(lineno)d: %(message)s" 
              if level<=logging.DEBUG else "%(message)s" )

    logging.basicConfig(level=level, format=format)



def cookieget(request, body=None, 
              opener = build_opener(HTTPCookieProcessor(CookieJar()))):

    if logger.isEnabledFor(logging.INFO):
        if isinstance(request,basestring):
            url = request
        else:
            url, body = request.get_full_url(), request.get_data()

        info('Sending to this url:' + url )
        if body:
            info(' ... with this body: ' + body)

    if body is None:
        page = opener.open(request).read()
    else:
        page =  opener.open(Request(request, body)).read()
    debug("received: " + page)
    return page

def get_token(url, action='cache'):
    token_url = '%s?actionType=%s' % (url, action)
    page = cookieget(token_url)
    m = re.search('name="security_token"[^>]*value="([^"]*)"', page)
    if m:
        token = m.group(1)
        debug('Security token:'+token)
        return token
    else:
        raise Exception,"Could not find a security token on page '%s'." % token_url

def login(hostname, port, username, password):

    baseurl = 'http://%s:%s/EnterpriseController' % (hostname, port)
    # login : post the credentials and get the session cookie
    cookieget(baseurl)
    page = cookieget(baseurl,
                     enc({'actionType' : 'authenticateUser',
                          'userName' : username,
                          'password' : password}))

    # make sure login worked fine
    if re.search("Google Search Appliance\s*&gt;\s*Home", page) is None:
        err("Login failed")
    return baseurl

def logout(baseurl):
    cookieget(baseurl + '?' + enc({'actionType' : 'logout'}))

@contextmanager
def logged(hostname, port, username, password):
    baseurl = login(hostname, port, username, password)
    yield baseurl
    logout(baseurl)

def check_diagnostic(page):
    "Checking that the html status page says everything is fine"
    
    nodes      = re.findall("row.*(<b>.*</b>)", page)
    connStatus = re.findall("(green|red) button", page)
    
    return  nodes is not None and (
        connStatus is not None 
        and all(color == 'green' for color in connStatus))

if __name__=='__main__':

    p = OptionParser()
    p.add_option('-n', '--hostname',  help='GSA hostname', default='localhost')
    p.add_option('--port', help='Upload port. Defaults to 8000', default='8000')
    p.add_option('-u', '--username',  default='admin',
                 help='Username to login GSA. Defaults admin')
    p.add_option('-p', '--password', default='test', 
                 help='Password for GSA user. Defaults to "test"',)
    p.add_option("-v", "--verbose", action="count")

    o, a = p.parse_args()
    setloglevel(o.verbose)


    with logged(o.hostname, o.port, o.username, o.password) as baseurl:
        diagnostic_url = baseurl + '?' + enc({'actionType': 'gsanDiagnostics'})
        page = cookieget(diagnostic_url)
        # Get the diagnostics of distributed GSA

        if check_diagnostic(page):
            print 'No need to re-apply the configuration'
        else:
            warn('Re-applying the configuration')
        
            post_params = enc({'actionType'     : 'gsanConfig',
                               'action'         : 'APPLY_CONFIG',
                               'applyConfig'    : 'Apply Configuration',
                               'security_token' :  get_token(baseurl)})

            page = cookieget(baseurl, post_params)
        
            if check_diagnostic(diagnostic_url):
                warn("Status still in error. Check in a few minutes")
