#!/usr/bin/env python
# coding: utf-8

u"""Merge the search logs and advanced search logs. Can also be used to
extract fields by name from supported logs files.

Example 1 - Merge logs:

  ~$ gsalogs.py --queries sans3.log --clicks asr3.log
  ip content manager:
      bug.subject
  
  custom attribute not displayed:
      case.subject case.subject nav.next
  
  conversation view picture:
      bug.subject
  
  更新　リリース　　改善:
      case.subject nav.next
  [ ... ]
  

Example 2 - Extract search logs fields:
  ~$ gsalogs.py --queries sans-logs.txt --fields ip,q
  172.26.242.34 mini freeze
  172.24.154.99 総文字数
  172.24.154.59 nfs connector 
  172.26.192.84 supplimentry index GSS
  [ ... ]

Example 3 - Extract advanced search logs fields:
  ~$ gsalogs.py --clicks sans-asr.txt --fields q,clicktype --delim '|'
  5838193 片岡|case.sfstory
  blue_button google earth|case.id
  [ ... ]

"""



from collections import namedtuple, defaultdict
from urlparse import urlparse, parse_qs
from urllib import unquote, unquote_plus, quote
import optparse
import re
import time
from datetime import datetime
import textwrap


class Parser(object):
  """Flexible base class for fields file parsers.

  A parser must be instantied with an iterator, it is itself an
  iterator which return instances of _Transformed objects. These are
  namedtuple which have all the interesting parsed fields as
  attributes.
  
  Example:
  for line, click in ASR(open("exported_asr.log")):
    print click.date, click.clicktype, click.q
  
  To specialize the parser to a specific file format, the user must
  create a class deriving Parser, then
  
  1. define a class attribute namedtuple named "_Extracted"
  
  2. implement a function called "_extract" which receives a line
     string and which returns an _Extracted namedtuple.
  
     Usually, you will use "".split or a regular expression on the
     input line for parsing the line into a tuple fields pass the
     tuple to the _Extracted constructor.
  
  3. define transformers method which have the name of an attribute
     of the Extracted namedtuple and return a tuple. The transformers
     are useful to take one attribute of the _Extracted instance and
     transform or adapt it into possibly multiple attributes.
  
     transformer function name should match an _Extracted attribute
     name to be run.
  
     In general most such CSV fields have multivalued element in an
     adhoc serialization. Or a timestamp can be adapted into a date
     string, etc.
  
  
  4. a .cols attr name can be attached to a transformer function:
     these are names for each of the element of the returned
     tuple. The output Transformed tuple will have these attributes
     name"""

  def __init__(self, fd):
    self.fd = fd

    transformed_fields = []
    for f in self._Extracted._fields:
      attr = getattr(self, f, '')
      if attr and hasattr(attr, 'cols'):
        transformed_fields.extend(getattr(self, f).cols.split())
      else:
        transformed_fields.append(f)
    self._Transformed = namedtuple('Transformed', transformed_fields)
    
  def __iter__(self):
    for line in self.fd:
      yield line, self._transform(self._extract(line))

  def _transform(self, extracted):
    l = []
    for f in self._Extracted._fields:
      field_transformer = getattr(self, f, False)
      if field_transformer:
        l.extend(field_transformer(getattr(extracted,f)))
      else:
        l.append(getattr(extracted,f))
    return self._Transformed(*l)

  def _extract(self):
    raise NotImplementedError()

class CLF(Parser):

  _Extracted = namedtuple('Extracted', 'ips date path status bytes num_results timing')
  _extract_re = re.compile(
    '(\S*) - - \[(\S+ \S+)\] "GET (\S*) HTTP/1.." (\S*) (\S*) (\S*) (\S*)\n')

  def _extract(self, line):
    return self._Extracted(*self._extract_re.match(line.decode('utf-8')).groups())
  
  def ips(self, s):
    """172.28.88.100!172.24.224.50!172.28.88.100"""
    return s.split('!',1) if '!' in s else [s,'']
  ips.cols = 'hip proxy'
  
  def date(self, s):
    """22/Jun/2012:08:16:28 -0800"""
    time_string, tz = s.split()
    naive_ts = (time.mktime(time.strptime(time_string, '%d/%b/%Y:%H:%M:%S')) 
                - time.timezone)
    sign = 1 if tz[0]=='-' else -1
    offset = int(tz[1:3])*3600+int(tz[3:5])*60
    # print naive_ts, sign, offset, time.timezone, tz[1:3], tz[3:5]
    ts = naive_ts + sign * offset
    return [ts, datetime.fromtimestamp(ts).strftime("%c") ]
  date.cols = "timestamp date"
  
  def path(self, url):
    """/search?q=Documentation
          &btnG=Google+Search
          &access=p
          &client=default_frontend
          &output=xml_no_dtd
          &proxystylesheet=default_frontend
          &sort=date:D:L:d1
          &oe=UTF-8
          &ie=UTF-8
          &ud=1
          &exclude_apps=1
          &site=default_collection
          &ip=172.28.88.100,172.24.224.50
          &entqr=3
          &entqrm=0"""
    d, l = parse_qs(urlparse(unquote(url.encode('ascii'))).query), []
    for a in self.path.cols.split():
      if a in d:
        l.append(d[a][0])
        del d[a]
      else:
        l.append('')
    l[-2] = url

    # this function is a little more complicated than seemed needed
    # due to the need to remember the undocumented or unknown vars
    l[-1] = '&'.join([ '%s=%s' % (k, v[0]) for k,v in sorted(d.items())])
    return l

  path.cols = (
    'access as_dt as_epq as_eq as_filetype as_ft as_lq as_occt as_oq as_q '
    'as_sitesearch client entqr entsp filter getfields ie ip lr num numgm '
    'oe output partialfields proxycustom proxyreload proxystylesheet q '
    'requiredfields site sitesearch sort start tlen ud btnG url unknown')

class ASR(Parser):

  _Extracted = namedtuple(
    'Extracted', 'timestamp ips clicktype start rank q url')
  
  def _extract(self, line):
    l = line.strip().split(',')
    return self._Extracted(l[0], l[1], l[3], l[4], l[5], l[7], l[8])
  
  def timestamp(self, s):
    ts = float(s)/100
    return [ts, datetime.fromtimestamp(ts).strftime("%c")]
  timestamp.cols = "timestamp date"
  
  def q(self, s):
    return [unquote_plus(s)]

def fmt(fields):
  return '  '+'\n  '.join(textwrap.wrap(' '.join(fields)))

clf_fields = CLF(None)._Transformed._fields

usage = __doc__ + u"""Advanced search logs available fields:
%s

Exported search logs available fields:
%s
""" % (fmt(ASR(None)._Transformed._fields), 
         fmt(clf_fields))

p = optparse.OptionParser(usage=usage)
p.add_option('--queries', help="filename of a search log")

p.add_option('--clicks', help="filename of a an advanced search log")

p.add_option('--fields', help="requested fields (default to date,q)", default="date,q")

p.add_option('-d', '--delim', help="output field delimiters (default to ' ')", default=' ')

p.add_option('--duration', help=
             ("session duration in seconds for merging ASR "
              "and search logs (default to 10 minutes)"), 
             default=600, type=int)

p.add_option('--full-format', action='store_true', help=
             ("when set, the output is the search logs format "
              "with an additional fields with the list of clicks "
              "events. Else only the query terms and the list of "
              "clicks events are shown"), 
              default=False)


class LinkedList(object):
  __slots__ = "next prev obj head".split()

  def __init__(self, obj=None):
    self.obj, self.next, self.prev = obj, None, None

  def append(self, o):
    if self.obj:
      self.head.next = LinkedList(o)
      self.head.next.prev = self.head
      self.headself.next
    else:
      self.obj = o

  def __iter__(self):
    i=self
    yield i
    while i.next:
      yield i.next
      i = i.next
      

  def cut_tail(self):
    self.prev = None

  def suppress(self):
    if self.next:
      print 'Oh hi, I linked your next to your rev'
      self.next.prev = self.prev

    if self.prev:
      print 'Oh hi, your prev is next'
      self.prev.next = self.next



if '__main__' == __name__:
  
  o, a = p.parse_args()
  assert o.queries or o.clicks

  if (bool(o.queries) ^ bool(o.clicks)): 
    gen = (ASR(open(o.clicks)) if o.clicks 
           else CLF(open(o.queries)))

    for _, event in gen:
      print o.delim.join(str(getattr(event, attr)) for attr in o.fields.split(","))

  else:

    # set the right formatter according to merge-format-clf2. 
    if o.full_format:
      def fmt(line, query, clicks):
        serialized = ','.join(
          (':'.join((c.clicktype, quote(c.url), c.start, c.rank)) 
           for c in clicks))
        return '%s %s' % (line.strip(), serialized)
    else:
      def fmt(line, query, clicks):        
        return '%s:\n%s\n' % (query.q, '    '+' '.join(c.clicktype for c in clicks))

    # step 1. create a dict of all the clicks, indexed by query terms
    clicks = defaultdict(list)
    for _, click in ASR(open(o.clicks)):
      # Note that the clicklog is descending order (first line is most recent)
      clicks[(click.q,'127.0.0.1')].append(click)
      # clicks[(click.q, click.ip)].append(click)
    
    # step 2. for each query, build a list of  serialized  events
    query_counter, interesting_result_counter = 0, 0
    for line, query in CLF(open(o.queries)):
      candidates, relevants  = clicks[(query.q,'127.0.0.1')], [] 
      # candidates, relevants  = clicks[(query.q, click.ip)], [] 

      # 3a. suppress the clicks more recent than the current queries
      # (they will never be used)
      while candidates and (query.timestamp < candidates[-1].timestamp):
        # remember
        candidates.pop()

      while candidates and (candidates[-1].timestamp < query.timestamp + o.duration):
        relevants.append(candidates.pop())

      relevants = [i for i in relevants if i.clicktype !='load']
      
      query_counter +=1
      if relevants:
        interesting_result_counter +=1
        print fmt(line, query, relevants)
    print ("%s%% of the queries returned an URL that the user was interested in." 
           % (interesting_result_counter*100/query_counter))

# Inefficiency
      
# all clicks are kept in memory all the time while only the clicks
# whose timestamps is smaller than q.timestamp + o.duration are
# needed. A sliding windows is better and needs either a sorted map (a
# tree map) or a linked list + a map
