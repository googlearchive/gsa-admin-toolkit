#!/usr/bin/python2.4
#
# Copyright (C) 2008 Google Inc.
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
# reverse_proxy.py is a reverse proxy for HTTP requests written in Python.
# This code has not been extensively tested. It is intended as a proof-of-concept.
# You should not use in production, without more extensive testing.
# It has the following features:
#
#  * Queues HTTP requests before sending to the web server. Can prevent
#    overloading a search appliance with too many concurrent requests.
#  * Allows rewriting of both requests and responses. Can be used to
#    troubleshoot connections between two servers, for example when
#    using the Authn/Authz SPI.
#
# TODO(jlowry)
#   HTTPS support (http://pypi.python.org/pypi/ssl/)

import asynchat
import asyncore
import getopt
import logging
import re
import resource
import socket
import sys
import time
import traceback

# Globals
CONTENT_LENGTH_PATTERN = "content-length: *(\d+)"
HEADER_SEPARATOR = "\r\n\r\n"
QUEUE = None

class Queue(object):
  """Class that represents the queue of requests to be sent to the server."""

  def __init__(self, host, port, max_conns):
    """Initializes the queue to hold requests to send to the server.

    Args:
      host: a string, the hostname of the server.
      port: an integer, the port that the server listens on.
      max_conns: an integer, the maximum number of concurrent connections
        that can be handled by the server.
    """
    self.queue = []
    self.host = host
    self.port = port
    self.max_conns = max_conns
    self.open_conns = {}

  def Add(self, request):
    """Add a request to the queue.

    The Add() method calls Process() after adding the request to the queue.

    Args:
      request: a ClientConnection object, representing an HTTP request.
    """
    logging.debug("request %x added to queue" % (request.id))
    self.queue.append(request)
    self.Process()

  def Process(self):
    """Process the queue.

    Sends requests to the server if the following conditions are met:
      * The number of open connections to the server is less than the maximum
        allowable.
      * There are requests in the queue waiting to be sent
    """
    logging.debug("processing queue")
    while len(self.open_conns) < self.max_conns:
      logging.debug("current open connections: %d" % (len(self.open_conns)))
      if not self.queue:
        logging.debug("queue is empty")
        break
      request = self.queue.pop()
      logging.debug("request %x dequeued" % (request.id))
      request.server_conn = ServerConnection(request)
      request.server_conn.push(request.buffer)

  def EndConnection(self, request_id):
    """The method must be called when a connection to the server is closed.

    We rely on the code that uses the Queue class to call EndConnection()
    when a connection to the server is closed.

    Args:
      request_id: an integer, an object identifier as returned by id(self).
    """
    logging.debug("request %x ended" % (request_id))
    try:
      del self.open_conns[request_id]
    except KeyError:
      logging.info("could not delete %s in %s" % (request_id, repr(self.open_conns)))
    self.Process()

  def StartConnection(self, request_id):
    """The method must be called when a connection to the server is opened.

    We rely on the code that uses the Queue class to call StartConnection()
    when a connection to the server is opened.

    Args:
      request_id: an integer, an object identifier as returned by id(self).

    Returns:
      A tuple containing the hostname and port of the remote server.
    """
    logging.debug("request %x started" % (request_id))
    self.open_conns[request_id] = time.time()
    return (self.host, self.port)


class ReverseProxy(asyncore.dispatcher):

  def __init__(self, bindhost, bindport):
    asyncore.dispatcher.__init__(self)
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.set_reuse_addr()
    self.listening_address = (bindhost, bindport)
    self.bind((bindhost, bindport))
    self.listen(10)

  def handle_accept(self):
    (conn, addr) = self.accept()
    logging.info("reverse_proxy got connection from: %s:%s" % (addr[0], addr[1]))
    try:
      ClientConnection(conn)
    except:
      exc, err_str, stack_trace = sys.exc_info()
      trace_str = traceback.format_tb(stack_trace, None)
      logging.error("client_conn failed: %s" % (err_str[1]))
      logging.error("\n%-20s%s: %s" % ("".join(trace_str), exc, err_str))


class HTTPConnection(asynchat.async_chat):

  def __init__(self, the_id, conn=None):
    asynchat.async_chat.__init__(self, conn)
    self.conn = conn
    self.id = the_id
    self.buffer = ""
    self.set_terminator(HEADER_SEPARATOR)

  def Rewrite(self):
    """Edit this method to rewrite requests or responses."""
    pass

  def found_terminator(self):
    logging.debug("found_terminator %x" % (self.id))
    if self.get_terminator() == HEADER_SEPARATOR:
      self.buffer += HEADER_SEPARATOR
      match = re.search(CONTENT_LENGTH_PATTERN, self.buffer, re.I)
      if match:
        clen = match.group(1)
        self.set_terminator(int(clen))
      else:
        self.set_terminator(None)
        if self.conn:
          self.Rewrite()
          QUEUE.Add(self)
    else:
      self.set_terminator(None)
      self.Rewrite()
      if self.conn:
        QUEUE.Add(self)
      else:
        self.handle_close()

  def collect_incoming_data(self, data):
    logging.debug("http_connection %x collect_incoming_data" % (self.id))
    self.buffer += data


class ClientConnection(HTTPConnection):

  def __init__(self, conn):
    HTTPConnection.__init__(self, id(self), conn=conn)
    logging.debug("client_conn %x init" % (self.id))
    self.server_conn = None

  def handle_close(self):
    logging.debug("client_conn %x handle_close" % (self.id))
    try:
      self.server_conn.close()
      QUEUE.EndConnection(self.id)
    except: pass
    self.close()


class ServerConnection(HTTPConnection):

  def __init__(self, client_conn):
    HTTPConnection.__init__(self, client_conn.id)
    logging.debug("server_conn %x init" % (self.id))
    self.client_conn = client_conn
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    dest = QUEUE.StartConnection(self.id)
    try:
      self.connect(dest)
    except:
      exc, err_str, stack_trace = sys.exc_info()
      trace_str = traceback.format_tb(stack_trace, None)
      logging.error("server_conn failed: %s" % (err_str[1]))
      logging.error("\n%-20s%s: %s" % ("".join(trace_str), exc, err_str))
      self.handle_error()

  def handle_connect(self):
    logging.debug("server_conn %x handle_connect" % (self.id))

  def handle_error(self):
    time_str = time.strftime("%a, %d-%b-%Y %H:%M:%S GMT", time.gmtime())
    self.buffer = ("HTTP/1.x 503 Service unavailable\nDate: %s\n"
                   "Server: GSA_Reverse_Proxy\r\n\r\nRequest failed."
                   % (time_str))
    self.handle_close()

  def handle_close(self):
    logging.debug("server_conn %x handle_close" % (self.id))
    QUEUE.EndConnection(self.id)
    self.client_conn.push(self.buffer)
    self.client_conn.close_when_done()
    self.close()


def Usage():
  return ("%s --bind_host=<listen-on-this-address> "
          "--remote_host=<send-requests-to-this-address> "
          "[--bind_port=<listen-on-this-port>] "
          "[--remote_port=<send_request-to-this-port>] "
          "") % (sys.argv[0])


def main():
  try:
    opts, args = getopt.getopt(sys.argv[1:], None,
                               ["bind_host=", "bind_port=", "remote_host=",
                                "remote_port=", "max_conns="])
  except getopt.GetoptError:
    print Usage()
    sys.exit(1)

  bind_port = 8080
  remote_port = 80
  max_conns = 5
  bind_host = None
  remote_host = None
  for opt, arg in opts:
    if opt == "--bind_host":
      bind_host = arg
    if opt == "--bind_port":
      bind_port = int(arg)
    if opt == "--remote_host":
      remote_host = arg
    if opt == "--remote_port":
      remote_port = int(arg)
    if opt == "--max_conns":
      max_conns = int(arg)

  if not bind_host or not remote_host:
    print Usage()
    sys.exit(1)

  logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")
  resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
  global QUEUE
  QUEUE = Queue(remote_host, remote_port, max_conns)
  ReverseProxy(bind_host, bind_port)
  asyncore.loop(timeout=4)


if __name__ == "__main__":
  main()
