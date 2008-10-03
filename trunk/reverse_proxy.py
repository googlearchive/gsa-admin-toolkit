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
# This code has not been extensively tested. It is intended as a
# proof-of-concept. You should not use in production, without more
# extensive testing. It has the following features:
#
#  * Queues HTTP requests before sending to the web server. Can prevent
#    overloading a search appliance with too many concurrent requests.
#  * Allows rewriting of both requests and responses. Can be used to
#    troubleshoot connections between two servers, for example when
#    using the Authn/Authz SPI.
#
# TODO(jlowry): HTTPS support (http://pypi.python.org/pypi/ssl/)

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
      # For example, if request is not a valid HTTP request it will not be
      # added to the queue, so cannot be deleted.
      logging.debug("could not delete %x" % (request_id))
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
  """Class that creates the listening socket for the reverse proxy."""

  def __init__(self, bindhost, bindport):
    """Sets up the listening socket.

    Args:
      bindhost: a string, hostname for the server to run on.
      bindport: an integer, port for the server to run on.
    """
    asyncore.dispatcher.__init__(self)
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.set_reuse_addr()
    self.listening_address = (bindhost, bindport)
    self.bind((bindhost, bindport))
    self.listen(10)

  def handle_accept(self):
    """Accept an incoming connection from a client."""
    (conn, addr) = self.accept()
    logging.info("reverse_proxy connection from: %s:%s" % (addr[0], addr[1]))
    try:
      ClientConnection(conn)
    except:
      exc_type, exc_value, exc_traceback = sys.exc_info()
      trace_str = traceback.format_tb(exc_traceback, None)
      logging.info("client_conn failed: %s" % (exc_value[1]))
      logging.info("\n%-20s%s: %s" % ("".join(trace_str), exc_type, exc_value))


class HTTPConnection(asynchat.async_chat):
  """Abstract class representing an HTTP connection.

  Must be subclassed by a class that implements the DoRewrite() and
  LogRequest methods.
  """

  def __init__(self, the_id, conn=None):
    asynchat.async_chat.__init__(self, conn)
    self.conn = conn
    self.id = the_id
    self.buffer = ""
    self.set_terminator(HEADER_SEPARATOR)

  def Rewrite(self):
    self.DoRewrite()

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
        self.Rewrite()
        if self.conn:
          self.LogRequest()
          QUEUE.Add(self)
    else:
      self.set_terminator(None)
      self.Rewrite()
      if self.conn:
        self.LogRequest()
        QUEUE.Add(self)
      else:
        self.handle_close()

  def collect_incoming_data(self, data):
    logging.debug("http_connection %x collect_incoming_data" % (self.id))
    self.buffer += data

  def ExceptionHandler(self):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    trace_str = traceback.format_tb(exc_traceback, None)
    logging.info("exception: %s" % (exc_value[1]))
    logging.info("\n%-20s%s: %s" % ("".join(trace_str), exc_type, exc_value))


class ClientConnection(HTTPConnection):

  def __init__(self, conn):
    HTTPConnection.__init__(self, id(self), conn=conn)
    self.start_time = time.time()
    logging.debug("client_conn %x init" % (self.id))
    self.server_conn = None

  def handle_close(self):
    # This method does not appear to be called when the client connection
    # is closed.
    logging.debug("client_conn %x handle_close" % (self.id))
    try:
      try:
        if self.server_conn:
          self.server_conn.close()
        self.close()
      finally:
        QUEUE.EndConnection(self.id)
    except socket.error:
      self.ExceptionHandler()

  def DoRewrite(self):
    """Edit this method to rewrite self.buffer to change the requests."""
    pass

  def LogRequest(self):
    ip, port = self.conn.getpeername()
    if self.buffer.startswith("GET") or self.buffer.startswith("POST"):
      request_lines = self.buffer.splitlines()
      logging.info("request %x from %s:%s: %s" %
                   (self.id, ip, port, request_lines[0]))
    else:
      logging.info("request %x invalid from %s:%s:\n%s\n" %
                   (self.id, ip, port, self.buffer))


class ServerConnection(HTTPConnection):

  def __init__(self, client_conn):
    HTTPConnection.__init__(self, client_conn.id)
    logging.debug("server_conn %x init" % (self.id))
    self.client_conn = client_conn
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    dest = QUEUE.StartConnection(self.id)
    try:
      self.connect(dest)
    except socket.error:
      logging.debug("server_conn %x calling handle_error" % (self.id))
      self.ExceptionHandler()
      self.handle_error()

  def handle_connect(self):
    logging.debug("server_conn %x handle_connect" % (self.id))

  def handle_error(self):
    logging.debug("server_conn %x handle_error" % (self.id))
    time_str = time.strftime("%a, %d-%b-%Y %H:%M:%S GMT", time.gmtime())
    self.buffer = ("HTTP/1.x 503 Service unavailable\nDate: %s\n"
                   "Server: GSA_Reverse_Proxy\r\n\r\nService unavailable.\n"
                   % (time_str))
    self.handle_close()

  def handle_close(self):
    logging.debug("server_conn %x handle_close" % (self.id))
    try:
      try:
        self.client_conn.push(self.buffer)
        logging.info("request %x took %f secs" %
                     (self.id, time.time() - self.client_conn.start_time))
        self.client_conn.close_when_done()
        self.close()
      finally:
        QUEUE.EndConnection(self.id)
    except socket.error:
      self.ExceptionHandler()

  def DoRewrite(self):
    """Edit this method to rewrite self.buffer to change the responses."""
    pass

  def LogRequest(self):
    logging.info("server_conn %x should never call log_request" % (self.id))


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
                                "remote_port=", "max_conns=", "log_level="])
  except getopt.GetoptError:
    print Usage()
    sys.exit(1)

  bind_port = 8080
  remote_port = 80
  max_conns = 5
  bind_host = None
  remote_host = None
  level = logging.INFO
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
    if opt == "--log_level":
      if arg.lower() == "debug":
        level = logging.DEBUG

  if not bind_host or not remote_host:
    print Usage()
    sys.exit(1)

  logging.basicConfig(level=level, format="%(asctime)-15s %(message)s")
  resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
  global QUEUE
  QUEUE = Queue(remote_host, remote_port, max_conns)
  ReverseProxy(bind_host, bind_port)
  asyncore.loop(timeout=4)


if __name__ == "__main__":
  main()
