#!/usr/bin/env python
"""Checks four causes of license overflow and attempts to provide a solution.

The GSA requires a unique URL per documents, but some contents servers
provide different links to the same documents, and this accounts for a
high license count. Once one of the issues below is identified, the
content owner or the GSA administrator might be able to remediate the
problem.

Note: when the license is overflown, depending on how valuable the
content is, a solution is to acquire a larger license to make sure
that no URL is discarded from the index.

Note: for the four issues described below, "coverage tuning", found in
"Content Sources > Web Crawl > Coverage Tuning" can be used to
mitigate the issue.


Problem 1. There is a session ID in the URL. Whenever the GSA recrawls
the content server, a new session ID might be included on the links
found. The GSA is going to add URL and documents to the index that
only differs from this unique ID.

- The script shows the URL parameters with the most distinct values.

- The content owner should configure the content server not to display
  the session ID.


Problem 2. For the same document, several URLs are found which only
differs by the order of their URL parameters. Each permutations is
counted as a different document.

- The script shows the number of URLs which are duplicate only for
  their URL parameters. The script can additionaly show the URL paths
  and the number of duplicates (not the default, this can hog the
  memory for large list of URLs) and the parameters involved in the
  permutations. This is the option --param_permutation.

- The content owner can then setup Block URLs patterns to only accept
  URLs where the parameters are in a canonical order. The customer
  must make sure that this canonical order will be seen at least once
  and that no URLs are discarded.


Problem 3. Some "directories" of URLs on some hosts have many more
URLs than the customer expected.

- The script will show a breakdown of "URL directories" and the number
  of URLs contained in said directory.

- The content owner can decide whether some of the large
  directory really are relevant or whether they should be discarded
  with block patterns.

Problem 4. Some URLs found by the GSA only differs by case, and the
content server serves the exact same URL for both.

- The script shows the number of URLs and the number of URLs distinct
  only in case.

- The GSA administrator can set patterns in "Content Sources > Web
  Crawl > Case-Insensitive Patterns" for the GSA to stop
  distinguishing URLs by case. The duplicates with uppercase will need
  to be removed by the GSA administrator.
"""

__author__ = 'jeandaniel.browne@gmail.com (Jean-Daniel Browne)'


from BaseHTTPServer import BaseHTTPRequestHandler
from BaseHTTPServer import HTTPServer
import collections
import contextlib
import json
import optparse
import platform
import socket
import sys
import textwrap
import urllib
import urlparse
import webbrowser


try:
  import hyperloglog
except ImportError:
  print (
      'Missing a Python library: please execute "sudo pip install hyperloglog"'
      '\nPossibly "sudo aptitude install python-pip"')
  sys.exit(1)


p = optparse.OptionParser()


#### Use more memory to present more information. When one of these
#### options is set, the general report is not shown, only the specific
#### detailed info are shown.
TOP_DIR, UNIQUE_PARAM_VALUE, PARAM_PERMUTATION, CASE = (
    'top-dir unique-param-values param-permutation case'.split())

p.add_option(
    '--%s' % TOP_DIR,
    help=('Assess which directories contribue most to the license count. '
          'Off by default.'),
    action='store_true', default=False)
p.add_option(
    '--%s' % UNIQUE_PARAM_VALUE,
    help=('URL can be duplicates when ignoring a session ID stored in a URL '
          'parameter. Set this parameter to list the duplicate URLs. '
          'Off by default.'),
    action='store_true', default=False)
p.add_option(
    '--%s' % PARAM_PERMUTATION,
    help=('URLs can be duplicates when ignoring the URL params ordering. '
          'Set this parameter to list the duplicate URLs. '
          'Off by default.'),
    action='store_true', default=False)
p.add_option(
    '--%s' % CASE,
    help=('URLs can be duplicates when ignoring the URL params ordering. '
          'Set this parameter to list the duplicate URLs. '
          'Off by default.'),
    action='store_true', default=False)


##### Top directories options: which dir contribue most to the license count.
p.add_option(
    '--depth',
    help=('Directory tree display option, an integer, the depth of shown '
          'directories. Default to 1 (only the hostname). Increase to '
          'better understand which directories take up more space. When '
          'using --top-dir, the default is 9.'),
    type=int,
    default=None)
p.add_option(
    '--max-siblings',
    help=('Directory tree display option. Shows 1000 directories max '
          'by default. Reduce this for readability or resource reduction.'),
    default=1000,
    type=int)
p.add_option(
    '--min',
    help=('Percentage, a positive integer between 0 and 100. Only show '
          'directories where the count is higher that --min. Defaults to 2'),
    type=int,
    default=2)
p.add_option(
    '--min-count',
    help=('A positive integer. Only show directories where the count is higher '
          'that --min-count. Not used by default, the percent --min is used by '
          'default.'),
    type=int,
    default=None)


#### The interactive browser visualisation
## Very basic at this point.
p.add_option(
    '--browser',
    help=('Displays an interactive visualization in the browser. '
          'Off by default'),
    action='store_true', default=False)
p.add_option(
    '--json',
    help=('Writes the URL count in the current directory: url.json. '
          'Off by default.'),
    action='store_true', default=False)


p.add_option(
    '--skip-header',
    help=('Exported URLs may have a header first line that needs '
          'to be skipped. On by default.'),
    action='store_true', default=True)

#### Mostly internal options, no need to clutter the --help with these options
# p.add_option(
#     '--error',
#     help=('Float between 0 and 100. The accepted error, in percent, between '
#           'the estimated count and the correct count. Defaults to 1%'),
#     default=1)
# p.add_option(
#     '--max-node',
#     help=('Sets the float percentage for the bottom and top. Defaults to 5.'),
#     default=5)
# TODO(jdbrowne): check own's memory usage to bail out
p.add_option(
    '--depth-parsed',
    type=int,
    help=('Decrease memory usage, directories deeper than 10 (the default), '
          'are not detailed when parsing the file.'),
    default=10)

CONF, ARGS = p.parse_args()
CONF.error = 1
CONF.max_node = 10**8

if CONF.min_count is None:
  CONF.min_count = 1


class Counters(object):

  hll = staticmethod(
      lambda: hyperloglog.hll.HyperLogLog(float(CONF.error) / 100))

  def __init__(self):

    self.url = 0
    self.url_sortedquery = Counters.hll()
    # if self.url - len(self.url_sortedquery) if large, then many
    # URLs exists where only the order of the parameters
    # changes. If you have 5 parameters in a URL, there can be
    # 5!==120 permutations that waste the license.

    self.val = Counters.hll()
    # number of distinct vals is large, it is possible that one of
    # the parameters includes a session id that eats up the
    # license.

    self.key = Counters.hll()
    # The number of distinct keys should always be low. In the
    # unlikely case the number of keys is large, self.keys should
    # not be extended anymore, and self.key only should be used,
    # even if it does not have the key names.

    self.keyval_num_per_urls = collections.defaultdict(int)
    # This gives the distribution of number of parameters per URL

    self.path = Counters.hll()
    self.query = Counters.hll()
    # If the number of query is large compared to the number of
    # path, then it likely that URLs uses many parameters, and are
    # subject to the permutations issue, or "sessions ids". These
    # two problems can quickly eat up the license.

    self.casei = Counters.hll()
    # The GSA distinguishes (this is configurable) case sensitive URLs
    # and case insensitive URLs. If the content server does not serve
    # diferent documents for different cases, and the number of case
    # insensitive URLs is much smaller than the number of URLs, the
    # license is being wasted.

    if CONF.param_permutation:
      self.paths = collections.defaultdict(int)


class Node(dict):

  __slots__ = ('count',)
  # __slots__ is a documented "trick" to save memory when large number
  # of small Python objects are instantiated.

  CONF = CONF
  # The configuration taken from the command line flags is a static
  # attribute to make sure instances do not all duplicate this
  # pointer.

  def __init__(self):
    dict.__init__(self)
    self.count = 0

  def Add(self, path, depth=0):
    self.count += 1
    if path and (depth < CONF.depth_parsed):
      depth += 1
      child, path = path[0], path[1:]
      if child not in self:
        self[child] = Node()
      self[child].Add(path, depth)

  def BigEnough(self, node):
    if CONF.min_count is not None:
      if node.count <= CONF.min_count:
        return False
    if CONF.min is not None:
      return node.count/float(self.count) > CONF.min/float(100)
    else:
      raise ValueError('Either --min-count or --min should be set')

  # pylint: disable=dangerous-default-value
  # for each append, I made sure there is a pop, so no worries. Not re-entrant!
  def Traverse(self, path=[], depth=0, pcount=None):
    percent = None if pcount is None else (100 * self.count / float(pcount))
    yield path, self.count, percent
    if depth < CONF.depth:
      depth += 1
      for name, child in sorted(self.items(),
                                key=lambda e: -e[1].count)[:CONF.max_siblings]:
        if self.BigEnough(child):
          path.append(name)
          for d in child.Traverse(path, depth, self.count):
            yield d
          path.pop()

  def Format(self):
    gen = self.Traverse()
    _, count, percent = next(gen)

    yield 'Number of URLs per directory (largest first)'
    yield ('--depth %s: dirs deeper than %s level are not shown.'
           % (CONF.depth, CONF.depth))
    yield (
        '--max-siblings %s: for each directory, the %s first larger childs '
        'are shown.' % (CONF.max_siblings, CONF.max_siblings))
    if CONF.min_count:
      yield ('--min-count %s: only dirs with more than %s URLs '
             'are shown.' % (CONF.min_count, CONF.min_count))
    if CONF.min:
      yield ('--min %s: only dirs whose #URLs is more than %s%% their '
             'parent\'s #URLs are shown.\n' % (CONF.min, CONF.min))
    yield '  %20s  %s' % ('% of its parent\t#URLs', 'path')
    yield '       -    %11s %s' % (count, 'Total')
    for path, count, percent in gen:
      yield '%10.1f%% %11s %s' % (percent, count, '/'.join(path))

  def __str__(self):
    return '\n'.join(self.Format())

  def Json(self, name='root'):
    out = {'name': name}
    if self:
      out['children'] = [v.Json(k) for k, v in self.items()]
    else:
      out['count'] = self.count
    return out


def Parse(fd, detailed_flag):
  """Parses one URL per line, returns a tree of counts, and other counters.

  Args:
    fd: a line iterator

  Returns:
    (a Counters instance, a hierarchy of counts)
  """

  counters = Counters()
  details = {
      TOP_DIR: Node(),
      # This is a dictionary of Node, recursively. Each node has a
      # count of URLs "in the directory". Each node is also a
      # dictionary, whose keys are the name of the childrens and the
      # values are the Node having holding the count of the subtree

      CASE: collections.defaultdict(list),
      # This is a dictionary of list of strings. For each unique
      # lowercase, this dict has a list of URLs that only differ per
      # their case sensitivity

      PARAM_PERMUTATION: collections.defaultdict(list),
      # This dict maps strings to list of strings. For each unique URL
      # with regard to param permutation, this dict has a list of URLs
      # that are duplicates (their URL parameters are in different
      # orders)

      UNIQUE_PARAM_VALUE: collections.defaultdict(Counters.hll)
      # This is a counter of distinct parameter values for each
      # parameter keys. The top counts may be a session id.  I have
      # never seen a session id encoded in URL parameter key name, but
      # it is likely that it exists. In this case, self.keys can grow
      # linearly with the number of distinct keys
      }

  for l in fd:
    l = l.strip()
    try:
      # urlparse does not parse the fragment and the query when
      # the scheme is not HTTP. The query and fragment are left
      # untouched, in the path.
      # For the googleconnectors versions, docids will be seen as
      # part of the path.

      u = urlparse.urlparse(l)
      keyvals = urlparse.parse_qsl(u.query)
    except ValueError:
      continue

    url_with_params_sorted = urlparse.urlunparse(
        [u.scheme,
         u.netloc,
         u.path,
         u.params,
         urllib.urlencode(sorted(keyvals)),
         u.fragment])

    counters.url += 1

    if PARAM_PERMUTATION in detailed_flag:
      details['param-permutation'][url_with_params_sorted].append(l)
    counters.url_sortedquery.add(url_with_params_sorted)

    counters.query.add(u.query)
    counters.path.add('%s%s' % (u.netloc, u.path))

    counters.keyval_num_per_urls[len(keyvals)] += 1

    simplified_netloc_and_path = (
        [u.netloc] if u.path == '/'
        else [u.netloc] + u.path.strip('/').split('/'))

    if TOP_DIR in detailed_flag:
      details[TOP_DIR].Add(simplified_netloc_and_path)

    low = l.lower()
    counters.casei.add(low)
    if CASE in detailed_flag:
      details[CASE][low].append(l)

    for k, v in keyvals:
      counters.key.add(k)
      counters.val.add(v)
      if UNIQUE_PARAM_VALUE in detailed_flag:
        details[UNIQUE_PARAM_VALUE][k].add(v)

  return counters, details


def Wrap(string):
  return textwrap.fill(
      string, 80, initial_indent='  ', subsequent_indent='  ')


@contextlib.contextmanager
def Color(col):

  if col not in Color.colors:
    raise ValueError('in colors(col), col should be in %s' % list(Color.colors))

  print Color.colors[col],
  yield
  print Color.colors['no color'],
Color.colors = {'pass': '\033[92m',      # this is green
                'warn': '\033[93m',      # orange
                'fail': '\033[91m',      # red
                'see info': '\033[94m',  # blue
                'no color': '\033[0m'}   # switch off coloring


class Report(object):

  @staticmethod
  def PrintChecks(actions, counters, details):
    print '\n%s\n\n' % Report.HINT

    for i, r in enumerate(
        v(counters, details[k]) for (k, v) in actions.items()):
      print '====== Test %s:' % str(i+1),
      Report.PrintStatus(r.status)
      print r.title

      if r.example:
        print '  Example:\n%s\n' % ('  ' + '\n  '.join(r.example.split('\n')))

      if r.msg:
        print '%s\n' % Wrap('Info: ' + r.msg)

      if r.details:
        print r.details

      if r.status in ['fail', 'warn', 'see info']:
        print '%s\n' % Wrap('Resolution step: ' + r.hint)

      print '  More info: %s\n' % r.more_info % r.more_info_param

  @staticmethod
  def PrintStatus(status):
    with Color(status):
      print status.upper(),

  @staticmethod
  def Sort(counts):
    return sorted(counts.items(), key=lambda t: -t[1])

  HINT = """The GSA index always requires a unique URL per document,
while some contents servers provides different links to the same
document. This potentially wastes a large portion of the license.

Resolution step: when the license is exceeded, a solution is to
  contact your account manager to acquire a larger license to make
  sure that no URL is discarded from the index.

Resolution step : coverage tuning, found in "Content Sources > Web
  Crawl > Coverage Tuning" can be used to mitigate the issue: it makes
  it possible top set a maximum of URLs in the index matching a URL
  pattern. URLs get discarded once the threshold is reached."""


class ParamPermutation(object):

  title = ('Permutations of URL parameters inflate the number of URL found')

  hint = ('For the same documents, several URLs are found, which only differ '
          'by the order of their URL parameters. Each permutation is counted  '
          'as a different document.'

          '- The script shows the number of URLs which are duplicate '
          'only for their URL parameters. The script can additionaly show '
          'the URL paths and the number of duplicates (not the default, this '
          'can hog the memory for large list of URLs) and the parameters '
          'involved in the permutations. '
          'This is the option --param_permutation.\n'

          '- The content owner can then setup Block URLs patterns to only '
          'accept  URLs where the parameters are in a canonical order. The '
          'customer must make sure that this canonical order will be seen at '
          'least once and that not URLs are discarded. ')

  example = ('http://content.com/art.doc?first=1&second=1\n'
             'http://content.com/art.doc?second=1&first=1')

  status, msg = 'see info', None
  more_info_param = '--param-permutation'
  more_info = 'Use %s to get the list of duplicates.'

  def __init__(self, counters, details):
    less = (counters.url - len(counters.url_sortedquery)) * 100 / counters.url

    self.details = '\n\n'.join(
        '\n'.join(v)
        for v in details.itervalues() if len(v) > 1)

    if less > 5:
      self.status = 'warn' if less < 15 else 'fail'
      self.msg = ('When sorting the URLs params for each URL, %s URLs seem '
                  'duplicate (%s%%), and depending on your content server, '
                  'might not be needed.\n'
                 ) % (counters.url - len(counters.url_sortedquery), less)
    else:
      self.status = 'pass'
      self.msg = ('There are very few (below 5%) or no URLs that are '
                  'duplicates due to URL parameter permutations.')


class Case(object):

  title = ('URLs which only differ by the case sensitivity are duplicate '
           'for most content servers')

  hint = ('In the administration console, on the page Content Sources > Web '
          'Crawl > Case-Insensitive Patterns, the custormer can set the URLs '
          'patterns for which the case will be ignored when comparing URLs.')

  example = ('http://content.com/article.doc\n'
             'http://content.com/ARTICLE.DOC')

  status, msg = 'see info', None
  more_info_param = '--case'
  more_info = ('Use %s for the list of duplicates.')

  def __init__(self, counters, details):
    percent_dup = (counters.url - len(counters.casei)) * 100 / counters.url

    self.details = '\n\n'.join(
        '\n'.join(v) for v in details.itervalues() if len(v) > 1)

    if percent_dup > 2:
      self.status = 'fail' if percent_dup > 10 else 'warn'
      self.msg = '%s%% are duplicates (%s in %s URLs overall).\n' % (
          (counters.url - len(counters.casei)) * 100 / counters.url,
          counters.url - len(counters.casei),
          counters.url)

    else:
      self.msg = ('None or almost (below 2%) no duplicates '
                  'due to case sensitivity')

      self.status = 'pass'


class UniqueParamValue(object):
  title = 'Sessions ID in URLs also generate many duplicates'

  hint = ('The content owner should configure the content server not to '
          'display the session ID.')

  example = ('http://content.com/article.doc?sessionID=09809898930\n'
             'http://content.com/article.doc?sessionID=17172417417')

  status, msg, details = 'see info', '', ''
  more_info_param = '--unique-param-value'
  more_info = 'Use %s for the list of duplicates.'

  def __init__(self, counters, details):
    # TODO(jdbrowne): need to refine the heuristic
    percent_dv = len(counters.val), len(counters.val)*100/counters.url
    percent_dk = len(counters.key), len(counters.key)*100/counters.url
    self.msg = 'Total num of URLs: %s, %s - %s' % (
        counters.url,
        '%s distinct URL parameter names (%s %%),' % percent_dk,
        '%s distinct URL parameter values (%s %%)\n' % percent_dv)

    if len(counters.key):
      keys = {k: len(v) for (k, v) in details.items()}

      self.details += '  %-20s\t%9s\t%9s\n' % (
          'Parameter name',
          '#unique values',
          '%%of this value among all URLs (%s)' % counters.url)
      for i, (k, v) in enumerate(Report.Sort(keys)):
        if i > 10:
          # It is very likely that document corpus have more than 10
          # different URL parameter names but it is very unlikely that
          # they have more than 10 URL parameters that have random
          # values, all of them significantly contributing insanely to
          # the license count. Only diagnosing and fixing the
          # parameters with the highest count really help driving the
          # license count down.
          break
        percent = v * 100 / counters.url
        if percent < 3:
          break
        self.details += '  %-20s\t%9s\t%9s%%\n' % (k, v, percent)

    else:
      self.status = 'pass'


class TopDir(object):

  title = 'Hosts or directories can have more documents than anticipated'
  hint = ('The customer can decide whether some of the large directories '
          'really are relevant or whether they should be discarded '
          'with by setting "Do Not Follow Patterns" in Content Sources '
          '> Web Crawl > Start and Block URLs.')

  example = ('100% 1,000,005  content.com/\n'
             ' 97%   970,003  content.com/webapp\n'
             '  3%    29,972  content.com/articles')

  status, msg, details = 'see info', '', ''
  more_info_param = '--top-dir'
  more_info = 'Use %s for the list of directories and their counts.'

  def __init__(self, unused_counters, details):
    for line in details.Format():
      self.details += '  ' + line +  '\n'


actions = {
    'top-dir': TopDir,
    'unique-param-values': UniqueParamValue,
    'param-permutation': ParamPermutation,
    'case': Case}


class ServeViz(BaseHTTPRequestHandler):

  index = """<!DOCTYPE html>
<html>
<meta charset="utf-8">
<style>

body {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  margin: auto;
  position: relative;
  width: 960px;
}

form {
  position: absolute;
  right: 10px;
  top: 10px;
}

</style>
<form>
  <label><input type="radio" name="mode" value="size"> Size</label>
  <label><input type="radio" name="mode" value="count" checked> Count</label>
</form>
<script src="http://d3js.org/d3.v3.min.js"></script>
<script>
var width = 960,
    height = 700,
    radius = Math.min(width, height) / 2,
    color = d3.scale.category20c();

var svg = d3.select("body").append("svg")
    .attr("width", width)
    .attr("height", height)
  .append("g")
    .attr("transform", "translate(" + width / 2 + "," + height * .52 + ")");

var partition = d3.layout.partition()
    .sort(null)
    .size([2 * Math.PI, radius * radius])
    .value(function(d) { return 1; });

var arc = d3.svg.arc()
    .startAngle(function(d) { return d.x; })
    .endAngle(function(d) { return d.x + d.dx; })
    .innerRadius(function(d) { return Math.sqrt(d.y); })
    .outerRadius(function(d) { return Math.sqrt(d.y + d.dy); });

d3.json("url.json", function(error, root) {
  var path = svg.datum(root).selectAll("path")
      .data(partition.nodes)
    .enter().append("path")
      .attr("display", function(d) { return d.depth ? null : "none"; }) // hide inner ring
      .attr("d", arc)
      .style("stroke", "#fff")
      .style("fill", function(d) { return color((d.children ? d : d.parent).name); })
      .style("fill-rule", "evenodd")
      .each(stash);

  d3.selectAll("input").on("change", function change() {
    var value = this.value === "count"
        ? function() { return 1; }
        : function(d) { return d.count; };

    path
        .data(partition.value(value).nodes)
      .transition()
        .duration(1500)
        .attrTween("d", arcTween);
  });
});

// Stash the old values for transition.
function stash(d) {
  d.x0 = d.x;
  d.dx0 = d.dx;
}

// Interpolate the arcs in data space.
function arcTween(a) {
  var i = d3.interpolate({x: a.x0, dx: a.dx0}, a);
  return function(t) {
    var b = i(t);
    a.x0 = b.x;
    a.dx0 = b.dx;
    return arc(b);
  };
}

d3.select(self.frameElement).style("height", height + "px");

</script>
<body>
</body>
</html>
"""

  def do_GET(self):   # pylint: disable=invalid-name
    if self.path == '/':
      self.send_response(200)
      self.send_header('Content-Type', 'text/html')
      self.end_headers()
      self.wfile.write(self.index)
    elif self.path == '/url.json':
      self.send_response(200)
      self.send_header('Content-Type', 'application/json')
      self.end_headers()
      self.wfile.write(json.dumps(self.details[TOP_DIR].Json()))
    else:
      self.send_response(404)
      self.end_headers()

  @staticmethod
  def Bind():
    httpd, port = None, None
    for port in range(20000, 20100):
      try:
        httpd = HTTPServer((platform.node(), port), ServeViz)
        break
      except socket.error:
        print 'Port %s is used, trying the next.' % port
    else:
      raise Exception('All ports from 20000 to 20100 are used.'
                      'Can not start the viz.')
    return httpd, port


def main():

  if sys.stdin.isatty():
    if ARGS:
      print 'Reading from %s' % ARGS[0]
      gen = (l.strip().split('\t')[0] for l in open(ARGS[0]))
    else:
      print ('Error: no data piped in stdin, no files on the command line: '
             'please provide a GSA exported URLs  files as first argument.')
      sys.exit(1)
  else:
    print 'Reading from the standard input.'
    gen = (l.strip().split('\t')[0] for l in sys.stdin)

  if CONF.skip_header:
    next(gen)
    # Do not forget to skip the headers from the Exported URLs

  detailed_flag = [k for k in actions if getattr(CONF, k.replace('-', '_'))]

  if detailed_flag:
    if CONF.depth is None:
      CONF.depth = 8
    counters, details = Parse(gen, detailed_flag)
    flag = detailed_flag[0]
    out = actions[flag](counters, details[flag]).details
    if out:
      print out
  elif CONF.browser:
    if CONF.depth is None:
      CONF.depth = 8
    counters, ServeViz.details = Parse(gen, [TOP_DIR])

    httpd, port = ServeViz.Bind()
    url = 'http://%s:%s/' % (platform.node(), port)
    print 'Connect to %s' % url

    # Note that there is a race condition, which should work fine in
    # most cases: the browser is run on a URL before running the
    # server, which is started one line below. Fixing this, if really
    # needed, requires a thread and messing with signal handler so
    # that Ctrl-C reaches the main loop and properly terminates the
    # script.
    webbrowser.open(url)
    try:
      httpd.serve_forever()
    except KeyboardInterrupt:
      print ': exiting...'

  else:
    if CONF.depth is None:
      CONF.depth = 1
    detailed_flag.extend([TOP_DIR, UNIQUE_PARAM_VALUE])
    counters, details = Parse(gen, detailed_flag)
    Report.PrintChecks(actions, counters, details)

  if CONF.json:
    with open('url.json', 'w') as f:
      json.dump(details[TOP_DIR].Json(), f, indent=1)

if __name__ == '__main__':
  main()
