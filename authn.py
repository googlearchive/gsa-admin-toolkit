#!/usr/bin/env python

"""A website with 4 pages, 3 of them are "secure" with different mechanism.

               *********************************************

   Please note that this script is not secure and is not even trying.

   For example, the cookie login form displays, by default, a valid username and
   valid password to make it easy for the test user to get a authentication
   cookie.

   The purpose of this script is to speed up the GSA configuration for secure
   crawl or secure search in test use cases.

               *********************************************

On the Crawling side, this "secure content server" enables configuring
the GSA for testing:
1. "Forms Authentication",
2. and "Crawler access" (HTTP basic only, no NTLM),
3. some customers also use a combination of HTTP basic + Crawler access.

There is one web page for each authentication above. Simply run the webserver
without arguments and connects to the URL displayed on the console to get the
list and test the authentication.

For Secure Serving, this identity provider enables two "Universal Login Auth
Mechanisms":
4. "Cookie",
5. "HTTP".

Users and groups are added via the --users flag, this is a comma separated list
of <username>:<password>. See the help string for this flag for more information
about setting domains and groups.

6. This script can also generate a feed file for the 5 URLs served by this
script, with all groups and users explicitly listed as ACLs. This the the --feed
flag. You can either send the feed to the GSA or adapt it to match a specific
customer context, before sending it to the GSA. This enables quick setup of
secure search with per User ACLs:

  Note: deny ACLs, inheritance and inheritance type are not supported.
  More info below:
  Http://www.google.com/support/enterprise/static/gsa/docs/admin/72/gsa_doc_set/feedsguide/feedsguide.html#1084066

This script enables 2 ways for the GSA to resolve the groups of a user to match
the per user ACLs:

7. "GroupsDB": the script can format the users and groups read from the --user
  flag in the Groups XML feed format suitable to generate a GroupsDB on the
  GSA. Then use another script to send the groups feed to the GSA. Use the flag
  --groupsdb to get the XML feed.

8. "Cookie Cracking": whenever the user is logged in, the default behavior is to
  include, in the response headers, the X-Username, and X-Groups headers with
  the values (a.k.a. "cookie cracking"). This enables for instance:

  - quick setup of a "Trusted App" configuration,
  - as well as setup for "transparent authentication with verified identity and
    groups resolution", when the user already has an authentication cookie from an
    SSO and connects to the GSA search page.

9. The script also accepts domain names if needed, wherever it accepts username:
either in the format 'domain\\username' or in the format 'username@domain'. This
enable quick test the behavior of hte GSA handling of the domain name.

Note: This script does not help with the following mechanism: Client
Certificate, Kerberos, SAML, Connectors nor LDAP. Install your own.

To ease deployment, no need for additional external libraries, this script
builds only on the Python2 standard library.
"""

from base64 import b64decode
import BaseHTTPServer
from collections import defaultdict
from Cookie import BaseCookie
from optparse import OptionParser
import os
import platform
import socket
import ssl
import sys
from urlparse import parse_qsl
from urlparse import urlparse
from uuid import uuid1


p = OptionParser()

# Web server config
p.add_option(
    '--port', default=9000, type=int,
    help='Listening port for the webserver. Default to 9000')
p.add_option(
    '--cert', default='',
    help=('Turns on HTTPS. Filename of the cert. Should end in '
          ' .crt. authn.py will use, for the private key, the '
          ' same basename and the .key extension.'))

# Cookie configuration, all parameters of the authentication cookie can be set
# from the command line to help with replicating most customers scenario. For
# example, the cookie domain can be set with --domain .sub.company.com
p.add_option(
    '--cookie-name', default='sso',
    help='Name of the cookie. Default to sso.')
p.add_option(
    '--expires', default='',
    help='Cookie expiration date. Default to "" (unset).')
p.add_option(
    '--path', default='',
    help='Cookie path. Default to "" (unset).')
p.add_option(
    '--domain', default='',
    help='Cookie domain. Defaults to "" (unset).')
p.add_option(
    '--comment', default='',
    help='The cookie "comment".')
p.add_option(
    '--max-age', default='',
    help='The Max-Age value for the cookie.')
p.add_option(
    '--version', default='',
    help='The "version" of a cookie.')
p.add_option(
    '--secure', default=False, action='store_true',
    help='"secure" setting on the cookie.')
p.add_option(
    '--httponly', default=False, action='store_true',
    help='"HttpOnly" setting of the cookie.')

# Users configuration
p.add_option(
    '--users', default='joe:joe',
    help=(r'Comma separated tuples of username:password strings (inside '
          'the tuple, the separator is colon). Default to "joe:joe". '
          'username:password:group1:group2 is also supported. The '
          'username part can be of the 3 forms: joe, joe@domain, domain\\joe.'))
p.add_option(
    '--no-identity-resolution', default=False,
    help=('The webserver is sending in its response the X-Username:value '
          'and "X-Groups:value1, value2" headers by default. The Groups '
          'header is only present if some headers were set in --users.'))
p.add_option(
    '--addomain', default=None,
    help=('Default domain when the domain is unset for a user. There '
          ' is no domain by default.'))

# Feeds
p.add_option(
    '--feed', default=False, action='store_true',
    help='.')
p.add_option(
    '--groupsdb', default=False, action='store_true',
    help='"secure" setting on the cookie.')

# The script uses four modules variables: CONF, ACCOUNTS, SESSIONS, PAGES

CONF, _ = p.parse_args()

# Configuration that is not really useful to provide to users
CONF.host = platform.node()
CONF.identity_resolution = not CONF.no_identity_resolution

# List of the currently authenticated users. A request for a secure page with an
# authentication cookie is granted iff the cookie value is in the SESSIONS.
SESSIONS = {}

# PAGES is a mapping of (URL paths, HTML string)
PAGES = {
    '/public': '<html><body>An interesting public page<body><html>',

    '/cookie/sample': """<html><body>
A vewy secure document protected by cookies<body><html>""",

    '/basic/sample': 'Another "secure" article, "protected" by HTTP basic.',

    '/basiccookie/sample': 'Top secret article, HTTP basic + cookie.',

    '/cookie/creds_form': """<html><body>
  <form action="/authenticate_from_form" method="post">
    Login:    <input type="text"     name="login"    value="%s"/> <br/>
    Password: <input type="password" name="password" value="%s"/> <br/>
              <input type="hidden"   name="from"     value="%s"/> <br/>
              <input type="submit"   value="send credentials"/>
  </form>
</body></html>""",

    '/index': """
<html><body>
Four content pages on this web server:
<ul>
<li> <a href="/public">/public</a>: public page, no need for authn</li>
<li> <a href="/cookie/sample">/cookie/sample</a>: page only avail to
request with a cookie named <i>%s</i>
<li> <a href="/basic/sample">/basic/sample</a>: page "protected" by HTTP basic</li>
<li> <a href="/basiccookie/sample">/basiccookie/sample</a>:
page requring a session cookie obtained after an HTTP basic authn</li>
</li>
</ul>

One convenience page:
<ul>
<li><a href="/kill_cookie">/kill_cookie</a>: suppresses the authentication
cookie </li>
</ul>
</body></html>\r\n\r\n""" % CONF.cookie_name,

    'Unknown cookie': """<html><body>
The cookie sent is not in our session db anymore.<br>
You can use your browser settings to suppress the cookie '%s'.<body><html>""",

    'no cookie sent': """<html><body>
The browser sent no cookie or a cookie not in the sessions..<body><html>"""}

# "Database" of users. Authentication cookies are delivered if the user password
# matches the password for this user in ACCOUTNS. ACCOUNTS is provisioned from
# the entries from the --users flag.


class Accounts(dict):

  def __init__(self, users):
    """Returns a dict of users built from a string like --users.

    Args:
      users: a string formatted like --users.
    """
    dict.__init__(self)
    for u in users.split(','):
      split = u.split(':')
      if len(split)<2:
        raise ValueError(
            'User format is username:password or user@domain:password. Got: %s'
            % u)
      domain, username = Accounts.ParseUsername(split[0])
      password = split[1]
      groups = split[2:]
      self[(domain, username)] = password, groups

  @staticmethod
  def ParseUsername(username):
    if isinstance(username, basestring):
      if '\\' in username:
        domain, username = username.split('\\')
      elif '@' in username:
        username, domain = username.split('@')
      else:
        domain = CONF.addomain
      return domain, username
    elif len(username) == 2:
      return username
    else:
      raise ValueError(
          'A username can be user, user@domain, domain\\user or (domain, user)')

  def __getitem__(self, username):
    return dict.get(self, Accounts.ParseUsername(username), (None, None))

  def __setitem__(self, username, value):
    dict.__setitem__(
        self, Accounts.ParseUsername(username), value)

  def __contains__(self, username):
    return dict.__contains__(self, Accounts.ParseUsername(username))


class CookieHelper(object):
  """Helpers to create, suppress and extract cookies.

  CookieHelper knows about 2 modules variables:
  - CONF: which has the flags values,
  - SESSIONS: a mapping of cookie values -> full cookie object
  """

  @staticmethod
  def EndSession(headers):
    """Sets the max-age to 0, return the string value, delete the session.

    Remove the entry corresponding to cookie_value from the SESSIONS.

    When the return value of this function is sent back via Set-Cookie
    to a user browser, the cookie is suppressed (yes, max-age set to 0 is
    one way for a server to request the browser to suppress the cookie).

    Args:
      headers: a BaseHTTPHandler set of headers.

    Returns:
      The full cookie is returned, as a string.
    """
    cookies = BaseCookie(headers.getheader('Cookie'))
    if cookies:
      if CONF.cookie_name in cookies:
        cookie_value = cookies[CONF.cookie_name].value
        if cookie_value in SESSIONS:
          SESSIONS[cookie_value][0][CONF.cookie_name]['max-age'] = '0'
          cookie = SESSIONS[cookie_value][0][CONF.cookie_name].OutputString()
          del SESSIONS[cookie_value]
          print "Suppressing cookie 'Set-Cookie: %s' \n" % cookie
          return cookie

  @staticmethod
  def Make(username):
    """Return a session cookie. The cookie is kept in the SESSIONS.

    Args:
      None. The function generates a small random value for the cookie value.

    Returns:
      the full cookie as a string, ready to be pasted after a "Set-Cookie: ".
    """
    domain, username = Accounts.ParseUsername(username)
    value = str(uuid1())[:8]
    jar = BaseCookie()
    SESSIONS[value] = jar, domain, username
    jar[CONF.cookie_name] = value
    for a in 'expires path comment domain max-age version '.split():
      if getattr(CONF, a, False):
        jar[CONF.cookie_name][a] = getattr(CONF, a.replace('-', '_'))
    for a in 'secure', 'httponly':
      if getattr(CONF, a, False):
        jar[CONF.cookie_name][a] = True

    return jar[CONF.cookie_name].OutputString()

  @staticmethod
  def Authenticated(headers):
    """Return true if the authn cookie is in the SESSION.

    Args:
      headers: the headers object from a BaseHTTPRequestHandler
        (the HTTP headers for the request)

    Returns:
      True is the value of the authn cookie is in SESSIONS.
    """

    cookies = BaseCookie(headers.getheader('Cookie'))
    if cookies:
      if CONF.cookie_name in cookies:
        cookie, domain, username = SESSIONS.get(cookies[CONF.cookie_name].value,
                                                (None, None, None))
        if cookie:
          print(
              'Received an authn cookie tracking a known session:"Cookie: %s"'
              % cookies[CONF.cookie_name].OutputString())

          _, groups = ACCOUNTS[domain, username]

          return (username if domain is None
                  else ('%s\\%s' % (username, domain)),
                  groups)
        else:
          print(
              'Received an unknown authn cookie '
              '(server was most likely restarted)')
    return (None, None)


class VerySecureSite(BaseHTTPServer.BaseHTTPRequestHandler):

  domain, username, groups = None, None, None

  def log_request(self, *_):
    """Overriding automatic loggin, shutting it down."""
    pass

  def log_message(self, *_):
    """Overriding automatice logging, shutting it down."""
    pass

  def Respond(self, code, headers, body=None):
    """Helper for sending an HTTP status, header and body.

    Args:
      code: an integer, typically 200 or 401.
      headers: a dictionary of string -> strings.
      body: a string, HTTP body text or html page.

    Returns:
      None. All side effect using the methods from self.
    """
    self.send_response(code)
    if self.username and CONF.identity_resolution:
      self.send_header('X-Username', self.username)

      if self.groups:
        self.send_header('X-Groups', ', '.join(self.groups))

    [self.send_header(k, v) for k, v in headers.items()]

    self.end_headers()

    if body:
      self.wfile.write(body)
    self.connection.shutdown(socket.SHUT_RDWR)

  def SendPage(self, pagename, *args):
    """Helper for returning an HTTP page.

    Args:
      pagename: a text or html string.
      args: optional list of args required by the page for string formatting.

    Returns:
      None. All side effects, using the self methods.
    """
    print 'Sending page %s\n' % pagename
    self.Respond(200, {'Content-Type': 'text/html'}, PAGES[pagename] % args)

  def do_GET(self):    # pylint: disable=invalid-name
    """Processes HTTP GET requests, usually reponds with a page or 302.

    Returns:
      None. All side effects.
    """
    if self.path != '/favicon.ico':
      print 'Received GET request for', self.path
    parsed = urlparse(self.path)

    ### 0/4 the root page
    if parsed.path in ['', '/', '/index']:
      self.SendPage('/index')

    elif parsed.path == '/public':
      ### 1/4 public page
      self.SendPage('/public')

    elif parsed.path == '/basic/sample':
      ### 2/4 page protected by HTTP Basic
      # HTTP basic authn do not use no cookies, the flow goes like this:

      # 1. the server checks if the request has an 'Authorization' header

      # 2. if the request has none, the server sends 401 with a header
      # WWW-Authenticate. The value of the header is 'Basic realm="<name of the
      # realm>"'. The realm is a hint displayed to the user for the user to send
      # the right username and password for this website.

      # 3. the browser interprets the response and shows the user dialog box,
      # for the user to type in the credentials

      # 4. the browser sends the same request as in 1. with an additional header
      # 'Authorization'. The value is simply '<username>:<password>', and the
      # whole string base64 encoded.

      # 5. As in 1., the server now sess the header, checks if the username,
      # password pair matches the password known for this user, and if they
      # match sends the page.

      # The browser transparently remembers the passwords, the dialog only
      # appears once. The Authorization header is the same used for Kerberos or
      # NTLM, the value does not have 'Basic' though.

      auth_header = self.headers.getheader('Authorization')
      if not auth_header:
        msg = 'Page protected by HTTP basic and no Authorization header'
        print msg
        self.Respond(
            401, {'WWW-Authenticate': 'Basic realm="GSA Test Authn"'}, msg)
      else:
        if not auth_header.lower().startswith('basic'):
          msg = '401! Weird authentication header "%s"' % auth_header
          print msg
          self.Respond(401, {'Content-Type': 'text/html'}, msg)
        else:
          username, received_pass = b64decode(auth_header.split()[1]).split(':')
          stored_password, groups = ACCOUNTS[username]
          if stored_password == received_pass:
            self.username, self.groups = username, groups
            print 'The authz header has matching password for the username.'
            self.SendPage('/basic/sample')
          else:
            self.Respond(401, {'Content-Type': 'text/html'},
                         'Wrong credentials: %s' % [username, received_pass])

    elif parsed.path == '/cookie/sample':
      ### 3/4 page protected by cookie, credentials obtained via an html form

      # Authentication by cookies is more flexible and sophisticated as the
      # cookie mechanism was not originally designed specifically for this. If
      # you compare to HTTP basic above, the browser does not automatically
      # interpret the cookie header to display a credentials form to the
      # user. Here is how this script implements it:

      # 1. server receive a request for /cookie/sample, there is no authn cookie

      # 2. server sends 302 toward to the login form, sets the location header:
      #    /cookie/creds_form?from=/cookie/sample

      # 3. browser sees the 302, and Location header: new request to server

      # 4. server receives request, sends the html form whose form has:
      #   <form action="/authenticate_from_form" method="post">
      #   Login:    <input type="text"     name="login"    />
      #   Password: <input type="password" name="password" />
      #             <input type="hidden"   name="from"  value="/cookie/sample"/>

      # 5. user fills the form and press submit: POST request to the action URL

      # 6. the server receives the POST form values on /authenticate_from_form
      # login=joe&password=joe&from=/cookie/sample

      # 7. iff joe:joe is correct credentials, the server responds with:
      #   - create a new session, and sets an authentication cookie to the user
      #   - 302, sets the accompanying Location header to /cookie/sample

      # 8. browser receives the redirections, request the original page and
      #    sends along the authentication cookie.

      # Unlike the HTTP Basic page, this cookie authentication requires more
      # messages between browser and server: 4 pairs of requests/responses.
      # 2 additional URLs endpoints are required:
      # the login form and the form processing

      username, groups = CookieHelper.Authenticated(self.headers)
      if username:
        self.username, self.groups = username, groups
        self.SendPage('/cookie/sample')
      else:
        print 'No authn cookie, 302 Location:"/cookie/creds_form"\n'
        self.Respond(
            302, {'Location': '/cookie/creds_form?from=/cookie/sample'})

    elif parsed.path == '/cookie/creds_form':
      # The user browser is redirected here when it has no authn cookie.

      # quick hack to make the site more convenient to use:
      # the login form has valid credentials by default.
      (domain, username), (password, _) = ACCOUNTS.items()[0]
      form = PAGES['/cookie/creds_form'] % (
          username, password, dict(parse_qsl(parsed.query)).get('from', None))
      print 'Sending login form. action="/authenticate_from_form"\n'
      self.Respond(200, {'Content-Type': 'text/html'}, form)

    ### 4/4 page protected by cookie, credentials obtained via HTTP basic
    elif parsed.path == '/basiccookie/sample':
      username, groups = CookieHelper.Authenticated(self.headers)
      if username:
        self.username, self.groups = username, groups
        self.SendPage('/basiccookie/sample')
      else:
        print ('Did not received the authn cookie, 302 to Basic Auth: %s\n'
               % '/basiccookie/creds_form')
        self.Respond(
            302,
            {'Location': ('/basiccookie/creds_form?from=%s'
                          % '/basiccookie/sample')})

    elif parsed.path == '/basiccookie/creds_form':
      auth_header = self.headers.getheader('Authorization')
      if not auth_header:
        print 'Page protected by HTTP basic and no Authorization header'
        self.Respond(401, {'WWW-Authenticate': 'Basic realm="GSA Test Authn"'})
      else:
        if not auth_header.lower().startswith('basic'):
          msg = '401! Weird authentication header "%s"' % auth_header
          print 'Received a weird authentication header "%s"' % auth_header
          self.Respond(401, {'Content-Type': 'text/html'}, msg)
        else:
          username, received_password = b64decode(auth_header.split()[1]).split(':')
          stored_password = ACCOUNTS[username][0]
          if stored_password == received_password:
            cookie = CookieHelper.Make(username)
            location = dict(parse_qsl(parsed.query)).get('from', None)
            print ('Correct HTTP basic creds encoded: setting autn cookie: "%s"'
                   % cookie)
            self.Respond(302, {'Set-Cookie': cookie,
                               'Location': location})
          else:
            self.Respond(401, {'Content-Type': 'text/html'},
                         'Wrong credentials: %s' % [
                             username, received_password])

    elif parsed.path == '/kill_cookie':
      cookie_str = CookieHelper.EndSession(self.headers)
      if cookie_str:
        self.Respond(200,
                     {'Content-Type': 'text/html', 'Set-Cookie': cookie_str},
                     body='Cookie "%s" was suppressed' % CONF.cookie_name)
      else:
        self.SendPage('no cookie sent')

    else:
      if self.path != '/favicon.ico':
        print 'That page was not found. BOOM: 404\n'
        self.Respond(404, {'Content-Type': 'text/plain'},
                     '%s\n%s\n' % self.responses[404])

  def do_POST(self):    # pylint: disable=invalid-name
    """Processes the login forms delivers a cookie if creds a in ACCOUNTS."""

    if urlparse(self.path).path == '/authenticate_from_form':
      # The login form points its action to this URL for processing the
      # credentials and possibly delivers the cookie.
      body = self.rfile.read(
          int(self.headers.getheader('content-length')))

      form = dict(parse_qsl(body))
      print ('Received GET request for /authenticate_from_form with '
             'login=%s and password=%s') % (form['login'], form['password'])

      username, received_password = form['login'], form['password']
      stored_password, groups = ACCOUNTS[username]
      if stored_password == form['password']:
        self.username, self.groups = username, groups
        cookie = CookieHelper.Make(username)
        print ('Authentication succeeded, setting authentication cookie:'
               '\nSet-Cookie: %s\nand redirecting user back to %s\n'
               % (cookie, form['from']))
        self.Respond(302, {'Set-Cookie': cookie,
                           'Location': form['from']})
      else:
        print ('Authentication failed: received %s, %s\n' % (
            form['login'], form['password']))
        self.Respond(401,
                     {'Content-Type': 'text/html'},
                     'Incorrect password, ressource forbidden')
    else:
      self.Respond(
          401, {'Content-Type': 'text/plain'},
          '%s\n%s\n' % self.responses[401])


def StartServer():
  try:
    httpd = BaseHTTPServer.HTTPServer((CONF.host, CONF.port), VerySecureSite)
  except socket.error, err:
    if 'Address already in use' in str(err):
      print 'Port %s is already in use, use --port.' % CONF.port
    else:
      print err
    sys.exit(1)

  hostname = (CONF.host if CONF.port in [80, 443]
              else '%s:%s' % (CONF.host, str(CONF.port)))
  (domain, username), (password, _) = ACCOUNTS.items()[0]

  username = ('%s\\%s' % (domain, username)) if domain else username

  console_msg = """
Webserver now running on http://%s/ username is %s, password is %s\n""" % (
    hostname, username, password)

  if CONF.cert:
    keyfile = CONF.cert.replace('.crt', '.key')
    if not (os.path.exists(CONF.cert) and os.path.exists(keyfile)):
      print ('The certificate "%s" file or its private key "%s" is missing.'
             'Create one with:\n'
             'openssl req\n'
             '     -newkey rsa:2048 -nodes -keyout server.key\n'
             '     -subj "/C=UK/L=London/O=WWF/CN=%s"\n'
             '     -days 3650  -x509\n'
             '     -out server.crt\n' % (CONF.cert, keyfile, platform.node()))

      sys.exit(1)

    console_msg = (console_msg.replace('http', 'https')
                   if CONF.cert else console_msg)
    httpd.socket = ssl.wrap_socket(
        httpd.socket, certfile=CONF.cert, keyfile=keyfile, server_side=True)

  print console_msg
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print ': exiting...'


def PrintUrlFeedWithAcl():
  """Write on stdout the url-and-metadata feed corresponding the input URLs.

  Transforms the exported URLs to a metadata and URL feed.

  Args:
    exportedurl: A filename (should be the URLs exported from the
      admin console).

  Yields:
    Snippet of an XML document.
  """
  # pylint: disable=protected-access
  print ACCOUNTS
  acls = FormatAccountsToAclXML(ACCOUNTS)
  print PrintUrlFeedWithAcl.header
  for path in ['/basic', '/cookie', '/cookiebasic']:
    url = 'http://%s%s' % (platform.node(),path)
    print '    ' + PrintUrlFeedWithAcl.record % (url, acls)

  print PrintUrlFeedWithAcl.footer

PrintUrlFeedWithAcl.header = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<gsafeed>
  <header>
    <datasource>authn</datasource>
    <feedtype>metadata-and-url</feedtype>
  </header>
  <group>"""

PrintUrlFeedWithAcl.record = (
    '<record url="%s" action="add" mimetype="text/html">\n%s\n    </record>')
PrintUrlFeedWithAcl.acluser = (
    )
PrintUrlFeedWithAcl.footer = """  </group>
</gsafeed>
"""


def FormatAccountsToAclXML(urls):
  """Prints on stdout the ACLs feeds of the pages of this script."""

  users = [(user[1] if user[0] is None else '%s\\%s' % user)
           for user in ACCOUNTS.keys()]
  groups = set()
  [[groups.add(g) for g in a[1]] for a in ACCOUNTS.values()]

  xml = '\n'.join(
    '      <meta name="google:aclusers" content="%s"/>' % u for u in users)
  if groups:
    xml += '\n' + '\n'.join(
      '      <meta name="google:aclgroups" content="%s"/>' % g for g in groups)

  return xml
       

def PrintsGroupsToXML():
  """Prints on stdout the groups feed of the registered users."""
  groups = defaultdict(list)
  for (domain, username), (password, ugroups) in ACCOUNTS.items():
    for group in ugroups:
      groups[group].append(username)
  # users = ['%s\\%s' % username for username in ACCOUNTS]
  print PrintsGroupsToXML.header
  for g, users in groups.items():
    xml_users = '\n'.join(PrintsGroupsToXML.user % u for u in users)
    print PrintsGroupsToXML.group % (g, xml_users)
  print PrintsGroupsToXML.footer

PrintsGroupsToXML.header = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE gsafeed PUBLIC "-//Google//DTD GSA Feeds//EN" "">
<xmlgroups>"""

PrintsGroupsToXML.group = """  <membership>
    <principal namespace="Default" case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="GROUP">\n\
    %s\n    </principal>
    <members>\n%s\n    </members>
  </membership>"""

PrintsGroupsToXML.user = '       <principal namespace="Default" \
case-sensitivity-type="EVERYTHING_CASE_INSENSITIVE" scope="USER">\n\
        %s\n       </principal>'

PrintsGroupsToXML.footer = """</xmlgroups>"""

# Known error message, and likely configuration issue
# crawl diag says:
# Error: Cookie Manager failed to complete all actions for the
# configured Cookie Rule.
# -> likely that the creds in the form authn crawl rule are incorrect

# Error: Cookie Manager was unable to find any valid Cookies for the
# configured Cookie Rule ->  there should be no dot prefixing the cookie domain


if __name__ == '__main__':

  ACCOUNTS = Accounts(CONF.users)
  if CONF.feed:
    PrintUrlFeedWithAcl()
  elif CONF.groupsdb:
    PrintsGroupsToXML()
  else:
    StartServer()
