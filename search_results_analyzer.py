#!/usr/bin/python
# Copyright 2011 Google Inc.
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


"""Simple script for parsing XML contents of a search result.

 This script can be used to print either the URL or the title
from XML search results. It takes the XML file or the URL location
provided as an argument and will display the XML Element requested.
Search results from two different appliances can then be compared
by dumping out the URL for each appliance using this script and then
using a utility such as "diff" to compare the two results.

  The various elements which could be displayed include,

   url, --url
   title, --title

For example:

 To display all the URLs for the search query (http://gsa/
search?q=test&site=default_collection&btnG=Google+Search
&access=p&client=default_frontend&output=xml_no_dtd
&sort=date%3AD%3AL%3Ad1&oe=UTF-8&ie=UTF-8&ud=1)

where gsa is the name of your search appliance.

   search_results_analyzer.py --results_url --url="http://gsa/
search?q=test&site=default_collection&btnG=Google+Search
&access=p&client=default_frontend&output=xml_no_dtd
&sort=date%3AD%3AL%3Ad1&oe=UTF-8&ie=UTF-8&ud=1"

Limitations:

 The script can only parse the XML structure of the search
results returned by a Google search appliance.


"""

#__author__ ='sheikji@gmail.com' (Sheikji Nazirudeen)

# Import the minidom module from xml.dom package
import getopt
import sys
import urllib
from xml.dom import minidom


class XmlParser(object):

  """XmlParser class."""

  def __init__(self, display_url, display_title, resource):
    self.display_url = display_url
    self.display_title = display_title
    self.resource = resource

# Iterate through the nodes in the xml document.

  def GetResults(self, node_list):
    self.node_list = node_list
    return self.node_list

# Open the url location or the file and set the option requested.

  def AnalyzeResults(self):
    self.resultset = ""
    xmldoc = minidom.parse(self.resource)
    if self.display_url == True:
      self.resultset = xmldoc.getElementsByTagName("U")
    elif self.display_title == True:
      self.resultset = xmldoc.getElementsByTagName("T")
    return self.GetResults (self.resultset)

# Print the values from the XML element selected

  def PrintResults(self, node_list):
    for nodes in node_list:
      if nodes.nodeType != nodes.TEXT_NODE:
        for values in nodes.childNodes:
          print values.nodeValue


def main():

# Initialize variables
  display_title = False
  display_url = False
  search_request_url = ""
  resource = ""
  xml_file = ""
  node_list = ""

  # Print usage.

  def Usage():
    return "(search_results_analyzer.py [--results_url] [--results_title] [--xmlfile=<xml_file>] [--url=<url>])"

  try:
    opts, args = getopt.getopt(sys.argv[1:],
                               None, ["results_url", "results_title",
                                      "xmlfile=", "url="])

  except getopt.GetoptError:
    print Usage()
    sys.exit(1)

  for opt, arg in opts:
    if opt == "--results_title":
      display_title = True
    if opt == "--results_url":
      display_url = True
    if opt == "--xmlfile":
      xml_file = arg
    if opt == "--url":
      search_request_url = arg

  if search_request_url:
    resource = urllib.urlopen (search_request_url)
  elif xml_file:
    resource = xml_file
  else:
    print Usage()
    sys.exit(1)

# Xml parser for parsing file or url location
  xp = XmlParser(display_url, display_title, resource)
  node_list = xp.AnalyzeResults()
  xp.PrintResults(node_list)

if __name__ == "__main__":
  main()
